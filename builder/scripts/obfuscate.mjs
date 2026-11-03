// @ts-check
/**
 * Post-export class-name obfuscation for the static `out/` directory.
 *
 * WHY a custom transform (not postcss-obfuscator):
 *   The shipped CSS is Tailwind's compiled output, full of escaped selectors
 *   (`.md\:flex`, `.bg-brand\/10`, `.aspect-\[16\/9\]`, `.sm\:text-lg`, ...).
 *   We need a deterministic, whole-token rewrite that maps the *logical* class
 *   name (what appears in `class="..."` and in JS string literals) to a short
 *   hash, while rewriting the matching (escaped) CSS selector. Doing it by hand
 *   gives us exact control over Tailwind's escaping rules and guarantees the
 *   HTML/JS tokens and the CSS selectors stay in sync.
 *
 * Pipeline (run AFTER `next build` which, with output:'export', writes `out/`):
 *   1. Parse every `out/_next/static/css/*.css`, extract class selectors,
 *      decode CSS escapes -> the logical class name.
 *   2. Build a deterministic logicalName -> short hash map (sorted, stable).
 *   3. Rewrite the CSS: replace each escaped selector with `.<hash>`.
 *   4. Rewrite every out HTML file: replace whole class tokens inside
 *      `class="..."` / `className` attributes.
 *   5. Rewrite every out JS file: replace whole class tokens that appear as
 *      standalone words inside string literals.
 *   6. Write `out/class-map.json` manifest (logical -> hash).
 *
 * Safety: only WHOLE class tokens are replaced (word-boundary aware), so we
 * never corrupt substrings, URLs, identifiers, or JS code.
 */

import { readdir, readFile, writeFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import crypto from "node:crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "out");

/* ------------------------------------------------------------------ */
/* helpers                                                            */
/* ------------------------------------------------------------------ */

/** Recursively collect files under `dir` matching one of `exts`. */
async function walk(dir, exts) {
  /** @type {string[]} */
  const found = [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return found;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...(await walk(full, exts)));
    } else if (exts.some((e) => entry.name.endsWith(e))) {
      found.push(full);
    }
  }
  return found;
}

/**
 * Decode a CSS-escaped class selector body into its logical class name.
 * Tailwind escapes special chars with a backslash, e.g.
 *   `md\:flex`        -> `md:flex`
 *   `bg-brand\/10`    -> `bg-brand/10`
 *   `aspect-\[16\/9\]`-> `aspect-[16/9]`
 *   `sm\:px-6`        -> `sm:px-6`
 *   `-mt-4` etc. need no decoding.
 * Also handles `\3a ` style numeric escapes defensively.
 */
function decodeCssSelector(raw) {
  // numeric escapes: \3a  -> char (rare in tailwind output, but be safe)
  let s = raw.replace(/\\([0-9a-fA-F]{1,6})\s?/g, (_, hex) =>
    String.fromCodePoint(parseInt(hex, 16))
  );
  // simple `\<char>` escapes -> the char
  s = s.replace(/\\(.)/g, "$1");
  return s;
}

/** Deterministic short hash for a logical class name. */
function hashClass(name, taken) {
  const digest = crypto.createHash("sha256").update(name).digest("hex");
  // class names must start with a letter; use a letter prefix + hex.
  let len = 6;
  let candidate;
  do {
    candidate = "c" + digest.slice(0, len);
    len += 1;
  } while (taken.has(candidate) && len <= digest.length);
  return candidate;
}

/**
 * Escape a logical class name back into a CSS selector body (Tailwind-style):
 * every char that is not [A-Za-z0-9_-] gets a leading backslash.
 */
function escapeForCss(name) {
  return name.replace(/[^A-Za-z0-9_-]/g, (ch) => "\\" + ch);
}

/** Escape a string for use as a literal inside a RegExp. */
function reEscape(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/* ------------------------------------------------------------------ */
/* 1. collect class names from compiled CSS                            */
/* ------------------------------------------------------------------ */

async function main() {
  if (!existsSync(OUT)) {
    console.error(
      `[obfuscate] out/ not found at ${OUT}. Run \`next build\` first (output:'export').`
    );
    process.exit(1);
  }

  // Use PostCSS so we only ever touch SELECTOR strings, never declaration
  // values. A naive global regex over the whole CSS text would also match
  // numeric fragments inside values (e.g. `.5rem` inside
  // `clamp(2.5rem,5.5vw)`) and corrupt them. PostCSS is already present
  // (Tailwind depends on it).
  const postcss = (await import("postcss")).default;

  const cssDir = path.join(OUT, "_next", "static", "css");
  const cssFiles = await walk(cssDir, [".css"]);
  if (cssFiles.length === 0) {
    console.error(`[obfuscate] no CSS files found under ${cssDir}`);
    process.exit(1);
  }

  // A class-selector body inside a SELECTOR string. A body is a sequence of:
  //   - a CSS NUMERIC escape `\<1-6 hex>` + optional trailing whitespace
  //     (Tailwind encodes commas/spaces in arbitrary values this way, e.g.
  //      `clamp(2.5rem,5.5vw)` -> `.\[...clamp(2\.5rem\2c 5\.5vw)...\]`). The
  //     trailing space is PART of the escape and must be consumed.
  //   - a simple `\<char>` escape (e.g. `\:`, `\/`, `\[`, `\.`)
  //   - a normal class char.
  const classSelectorRe = /\.((?:\\[0-9a-fA-F]{1,6}\s?|\\.|[A-Za-z0-9_-])+)/g;

  /** logical name -> escaped-body-as-seen-in-css (Set, may differ in theory) */
  const logicalToRaw = new Map();
  /** @type {{file:string, root:import('postcss').Root}[]} */
  const parsed = [];

  for (const file of cssFiles) {
    const css = await readFile(file, "utf8");
    const root = postcss.parse(css, { from: file });
    parsed.push({ file, root });
    root.walkRules((rule) => {
      classSelectorRe.lastIndex = 0;
      let m;
      while ((m = classSelectorRe.exec(rule.selector)) !== null) {
        const logical = decodeCssSelector(m[1]);
        if (!logicalToRaw.has(logical)) logicalToRaw.set(logical, new Set());
        logicalToRaw.get(logical).add(m[1]);
      }
    });
  }

  /* ---------------------------------------------------------------- */
  /* 2. build deterministic logical -> hash map                        */
  /* ---------------------------------------------------------------- */

  const logicalNames = [...logicalToRaw.keys()].sort();
  /** @type {Map<string,string>} */
  const map = new Map();
  const taken = new Set();
  for (const name of logicalNames) {
    const h = hashClass(name, taken);
    taken.add(h);
    map.set(name, h);
  }

  console.log(
    `[obfuscate] found ${logicalNames.length} class names across ${cssFiles.length} CSS file(s)`
  );

  /* ---------------------------------------------------------------- */
  /* 3. rewrite CSS selectors (selector strings only)                  */
  /* ---------------------------------------------------------------- */

  for (const { file, root } of parsed) {
    root.walkRules((rule) => {
      rule.selector = rule.selector.replace(classSelectorRe, (whole, rawBody) => {
        const hash = map.get(decodeCssSelector(rawBody));
        return hash ? "." + hash : whole;
      });
    });
    await writeFile(file, root.toString(), "utf8");
  }

  /* ---------------------------------------------------------------- */
  /* token replacement for HTML/JS                                     */
  /* ---------------------------------------------------------------- */

  /**
   * Replace whole class tokens within a single space-delimited class string.
   * Splits on whitespace, maps each token, rejoins. Unknown tokens pass through
   * (e.g. dynamic markers, `--font-sans` css-var values, picsum, etc.).
   */
  function rewriteClassValue(value) {
    return value
      .split(/(\s+)/) // keep the whitespace separators
      .map((tok) => (/\s+/.test(tok) ? tok : map.get(tok) ?? tok))
      .join("");
  }

  /* ---------------------------------------------------------------- */
  /* 4. whole-token regexes (for JS files + inline RSC flight data)     */
  /* ---------------------------------------------------------------- */
  // className strings appear (a) in client JS string literals and (b) inline
  // in HTML <script> RSC flight data (used for client-side navigation). We
  // replace each known logical token only when it appears as a *whole word*
  // (bounded by non-class-name chars), longest-first so `text-sm` wins over
  // `text`. The conservative boundary set + case-sensitivity make false hits
  // in prose effectively impossible.
  const sortedTokens = logicalNames
    .filter((n) => map.has(n))
    .sort((a, b) => b.length - a.length);

  const CLASS_CHAR = "A-Za-z0-9_:/\\[\\]\\.\\-%#()!,";
  const boundary = `[^${CLASS_CHAR}]`;
  const startB = `(^|${boundary})`;
  const endB = `(?=$|${boundary})`;

  const CHUNK = 800;
  /** @type {RegExp[]} */
  const jsRegexes = [];
  for (let i = 0; i < sortedTokens.length; i += CHUNK) {
    const slice = sortedTokens.slice(i, i + CHUNK).map(reEscape);
    jsRegexes.push(new RegExp(`${startB}(${slice.join("|")})${endB}`, "g"));
  }

  function applyTokenRegexes(text) {
    let out = text;
    for (const re of jsRegexes) {
      out = out.replace(re, (whole, pre, tok) => {
        const hash = map.get(tok);
        return hash ? pre + hash : whole;
      });
    }
    return out;
  }

  // A token is "class-like" if it could be a Tailwind/utility class: in the map,
  // a next/font class (__...), a known marker with no own rule, or a compound
  // utility (contains a tailwind separator -:/[ ). Plain dictionary words (prose)
  // are NOT class-like.
  const MARKERS = new Set(["group", "peer", "dark", "contents", "ltr", "rtl", "sr-only"]);
  function tokenClassLike(tok) {
    if (tok === "") return true;
    if (map.has(tok)) return true;
    if (tok.startsWith("__")) return true; // next/font generated classes
    if (MARKERS.has(tok)) return true;
    if (/[-:/[]/.test(tok) && /^[a-z0-9:/[\]_.@%!-]+$/i.test(tok)) return true;
    return false;
  }
  // True only for strings that are genuinely a class list (every token class-like
  // AND at least one real mapped class). Prevents rewriting prose / arbitrary
  // strings, which would make client text differ from the server HTML (#418).
  function looksLikeClassList(value) {
    const toks = value.split(/\s+/).filter(Boolean);
    if (!toks.length || !toks.some((t) => map.has(t))) return false;
    return toks.every(tokenClassLike);
  }

  // JS string/keyword safety: only rewrite INSIDE string literals, and only when
  // the literal is a class list (so `static getDerivedStateFromError` and prose
  // strings are never touched).
  const STRING_LITERAL_RE = /"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`/g;
  function rewriteJsClassLiterals(code) {
    return code.replace(STRING_LITERAL_RE, (lit) => {
      const q = lit[0];
      const inner = lit.slice(1, -1);
      if (!looksLikeClassList(inner)) return lit;
      return q + applyTokenRegexes(inner) + q;
    });
  }
  // RSC flight data is one big escaped-JSON string; rewrite ONLY the values of
  // \"className\":\"...\" so prose/text in the payload is left untouched.
  const FLIGHT_CLASSNAME_RE = /(\\"className\\":\\")(.*?)(\\")/g;
  function rewriteFlightClassNames(body) {
    return body.replace(FLIGHT_CLASSNAME_RE, (w, a, val, c) => a + applyTokenRegexes(val) + c);
  }
  // RSC payload .txt files (fetched on client-side <Link> navigation) use the
  // SAME flight format but with UNESCAPED quotes: "className":"...". Without
  // rewriting these, soft navigation renders original class names that don't
  // exist in the hashed CSS -> the page looks unstyled until a hard refresh.
  const RSC_CLASSNAME_RE = /("className":")([^"]*)(")/g;
  function rewriteRscClassNames(body) {
    return body.replace(RSC_CLASSNAME_RE, (w, a, val, c) => a + applyTokenRegexes(val) + c);
  }

  /* ---- 5. HTML: class="..." attrs + inline <script> flight data --- */

  const htmlFiles = await walk(OUT, [".html"]);
  const classAttrRe = /\bclass=("([^"]*)"|'([^']*)')/g;
  const scriptRe = /(<script\b[^>]*>)([\s\S]*?)(<\/script>)/g;
  let htmlTouched = 0;
  for (const file of htmlFiles) {
    const before = await readFile(file, "utf8");
    let html = before.replace(classAttrRe, (whole, _q, dq, sq) => {
      const isDouble = dq !== undefined;
      const value = isDouble ? dq : sq;
      // Use the SAME token rewriter as the flight data / JS so the server HTML
      // class attrs and the client RSC payload are byte-identical -> no hydration
      // mismatch (#418).
      const rewritten = applyTokenRegexes(value);
      if (rewritten === value) return whole;
      return isDouble ? `class="${rewritten}"` : `class='${rewritten}'`;
    });
    html = html.replace(scriptRe, (whole, open, body, close) => open + rewriteFlightClassNames(body) + close);
    if (html !== before) {
      await writeFile(file, html, "utf8");
      htmlTouched++;
    }
  }

  /* ---- 6. JS: rewrite whole class tokens in string literals ------ */

  const jsFiles = await walk(OUT, [".js"]);
  let jsTouched = 0;
  for (const file of jsFiles) {
    const js0 = await readFile(file, "utf8");
    const js = rewriteJsClassLiterals(js0);
    if (js !== js0) {
      await writeFile(file, js, "utf8");
      jsTouched++;
    }
  }

  /* ---- 7. RSC payloads (.txt) used for client-side navigation ----- */
  const txtFiles = await walk(OUT, [".txt"]);
  let txtTouched = 0;
  for (const file of txtFiles) {
    const t0 = await readFile(file, "utf8");
    const t = rewriteRscClassNames(t0);
    if (t !== t0) {
      await writeFile(file, t, "utf8");
      txtTouched++;
    }
  }

  /* ---------------------------------------------------------------- */
  /* 6. manifest                                                       */
  /* ---------------------------------------------------------------- */

  const manifest = Object.fromEntries(logicalNames.map((n) => [n, map.get(n)]));
  await writeFile(
    path.join(OUT, "class-map.json"),
    JSON.stringify(manifest, null, 2),
    "utf8"
  );

  console.log(
    `[obfuscate] rewrote ${cssFiles.length} CSS, ${htmlTouched}/${htmlFiles.length} HTML, ${jsTouched}/${jsFiles.length} JS, ${txtTouched}/${txtFiles.length} RSC(.txt) file(s)`
  );
  console.log(`[obfuscate] manifest -> out/class-map.json`);
}

main().catch((err) => {
  console.error("[obfuscate] failed:", err);
  process.exit(1);
});

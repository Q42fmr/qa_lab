/* i18n лаби: три мови без збірки, без залежностей і без переписування UI.
 *
 * Ключ перекладу — САМ УКРАЇНСЬКИЙ РЯДОК, як msgid у gettext. Причини рівно
 * три, і кожна практична:
 *
 *   1. розмітка не чіпається взагалі. В `index.html` 4260 рядків, і більшість
 *      видимого тексту народжується в JS усередині шаблонних рядків —
 *      розставити там `data-i18n` означало б переписати весь файл і зламати
 *      його в місцях, яких не видно ні в дифі, ні в тестах;
 *   2. відсутній переклад деградує в українську, а не в голий ключ. Найгірше,
 *      що може статись з новим рядком, — він лишиться українським;
 *   3. конвенція репозиторію (#5) каже, що UI українською. Вона лишається
 *      правдою: українська — джерело, решта — накладка.
 *
 * Перекладаємо ГОТОВИЙ DOM, а не шаблони: MutationObserver ловить усе, що
 * дорендерив JS, тому таби, тости й відповіді сервера перекладаються тим
 * самим механізмом.
 *
 * ⚠️ Чого НЕ чіпаємо ніколи: `script`, `style`, `textarea`, `pre`, `code` і
 * все з `data-i18n-skip`. Там лежить вміст файлів вітки, дифи й імена гілок —
 * «перекладений» диф був би гіршим за неперекладений інтерфейс.
 */
(function () {
  "use strict";

  var LANGS = { uk: "Українська", ru: "Русский", en: "English" };
  var STORE = "qa_lab_lang";
  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, PRE: 1, CODE: 1 };
  var ATTRS = ["title", "placeholder", "alt"];

  function saved() {
    try { return localStorage.getItem(STORE); } catch (e) { return null; }
  }

  var lang = saved();
  if (!LANGS[lang]) lang = "uk";

  /* Словник поточної мови з ФОЛБЕКОМ на решту.
   *
   * Порядок: обрана мова → інші переклади → українська (джерело). Тобто
   * рядок, у якого є лише російський переклад, англійцю покажеться
   * російською, а не українською: «хоч щось знайоме» краще за третю мову
   * поспіль. Нічого не знайшлось — лишається український оригінал, і це
   * найгірше, що взагалі може статись.
   *
   * Зливаємо один раз на старті, а не на кожен рядок: ключів за тисячу, а
   * пошук іде на кожному текстовому вузлі.
   */
  var ALL = window.I18N_DICT || {};
  var chain = [lang];
  for (var code in LANGS) {
    if (code !== lang && code !== "uk" && ALL[code]) chain.push(code);
  }
  var dict = {};
  for (var c = chain.length - 1; c >= 0; c--) {
    var src = ALL[chain[c]] || {};
    for (var k in src) {
      var v = src[k];
      // Порожній рядок — це не переклад, а забутий рядок: хай його
      // перекриє наступна мова в ланцюжку.
      if (typeof v === "string" && v) dict[k] = v;
    }
  }
  /* Шаблони — записи з `{0}`. Рядок у DOM уже зібраний (числа підставлені),
     тож єдиний спосіб їх упізнати — регулярка з дірками. Пробуємо їх ЛИШЕ
     коли точного збігу немає: інакше кожен текстовий вузол коштував би
     півтори сотні перевірок. */
  var patterns = [];
  if (lang !== "uk") {
    for (var key in dict) {
      if (!/\{\d\}/.test(key)) continue;
      /* Номери дірок беруться з коду, тож у ключі вони бувають будь-які —
         «(арх.: {1}, {2} віток)» цілком нормальний. Тому запам'ятовуємо
         ПОРЯДОК появи: група regex прив'язана до позиції, а не до номера. */
      /* ⚠️ Запобіжник на надто загальний шаблон. `{0} з {1}` — це регулярка
         `^(.+?) з (.+?)$`, тобто БУДЬ-ЯКИЙ рядок зі словом «з» усередині:
         одного такого ключа досить, щоб покришити половину екрана (спіймано
         на «, а не фраза з поради» → «, а не фраза of поради»). Тому шаблон,
         відкритий з обох боків, мусить мати вагому літеральну частину. */
      var literal = key.replace(/\{\d\}/g, "").replace(/\s+/g, "");
      var openBoth = /^\{\d\}/.test(key) && /\{\d\}$/.test(key);
      var words = key.replace(/\{\d\}/g, " ").match(/[\p{L}\p{N}]+/gu) || [];
      var longest = 0;
      for (var w = 0; w < words.length; w++) {
        if (words[w].length > longest) longest = words[w].length;
      }
      // Відкритий з обох боків шаблон мусить мати хоч одне справжнє слово
      // (4+ літери): «з», «с», «на» між дірками ловлять пів-екрана.
      if (openBoth ? longest < 4 : literal.length < 3) continue;
      var order = (key.match(/\{\d\}/g) || []).map(function (h) { return h[1]; });
      var rx = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\\\{(\d)\\\}/g, "(.+?)");
      /* Найдовший літеральний шматок ключа — дешевий відсів перед regex.
         Заміряно 02.09 на головній: повний прохід 1145 вузлів коштував
         702 мс, бо кожен рядок, що не збігся точно, проганявся через усі 168
         шаблонів з `(.+?)`, а на довгих рядках це бектрекінг. `indexOf`
         відкидає майже всі ще до regex. */
      var chunks = key.split(/\{\d\}/);
      var probe = "";
      for (var ci = 0; ci < chunks.length; ci++) {
        if (chunks[ci].length > probe.length) probe = chunks[ci];
      }
      try {
        patterns.push([new RegExp("^" + rx + "$"), dict[key], order, literal.length, probe]);
      } catch (e) {
        // Один кривий ключ не має гасити переклад усього застосунку.
        if (window.console) console.warn("i18n: пропущено шаблон", key, e);
      }
    }
    /* Довші літерали першими: конкретний шаблон має вигравати в загального,
       інакше «{0}/{1} перевірок мають скіл · своїх записів {2}» з'їдає хвіст,
       призначений докладнішому. */
    patterns.sort(function (a, b) { return b[3] - a[3]; });
  }

  /* Пам'ять на вже перекладене. Той самий підпис трапляється в десятках
     карток, а спостерігач ще й перечитує вузли після кожного рендера. */
  var memo = {};
  var memoSize = 0;
  var MEMO_MAX = 4000;

  function remember(core, value) {
    if (memoSize >= MEMO_MAX) { memo = {}; memoSize = 0; }
    if (!Object.prototype.hasOwnProperty.call(memo, core)) memoSize++;
    memo[core] = value;
    return value;
  }

  function t(raw) {
    if (lang === "uk" || !raw) return raw;
    var s = String(raw);
    var lead = s.match(/^\s*/)[0], tail = s.match(/\s*$/)[0];
    /* Пробіли ВСЕРЕДИНІ теж схлопуємо: у розмітці текст переноситься по
       рядках з відступами, а на екрані HTML і так показує його одним
       пробілом. Без цього ключ зі словника не збігався б із вузлом рівно
       там, де рядок довгий, — тобто саме на підказках і поясненнях. */
    var core = s.slice(lead.length, s.length - tail.length).replace(/\s+/g, " ");
    if (!core) return raw;
    if (Object.prototype.hasOwnProperty.call(memo, core)) {
      return memo[core] === null ? raw : lead + memo[core] + tail;
    }
    var hit = dict[core];
    if (hit === undefined) {
      for (var i = 0; i < patterns.length; i++) {
        if (patterns[i][4] && core.indexOf(patterns[i][4]) < 0) continue;
        var m = core.match(patterns[i][0]);
        if (m) {
          var order = patterns[i][2];
          hit = patterns[i][1].replace(/\{(\d)\}/g, function (_, n) {
            var at = order.indexOf(n);
            if (at < 0 || m[at + 1] === undefined) return "";
            /* Вміст дірки — теж рядок, і часто це відповідь сервера
               («ANTHROPIC_API_KEY не заданий»). Точний ключ у словнику
               перекладає і його; усе інше (числа, назви віток) лишається
               як є, бо ключа для нього немає. */
            var inner = dict[m[at + 1]];
            return inner === undefined ? m[at + 1] : inner;
          });
          break;
        }
      }
    }
    remember(core, hit === undefined ? null : hit);
    return hit === undefined ? raw : lead + hit + tail;
  }

  var busy = false;             // щоб спостерігач не ловив власні ж правки

  function skipped(node) {
    for (var el = node.parentNode; el && el.nodeType === 1; el = el.parentNode) {
      if (SKIP_TAGS[el.tagName]) return true;
      if (el.hasAttribute && el.hasAttribute("data-i18n-skip")) return true;
    }
    return false;
  }

  function walk(root) {
    if (lang === "uk" || !root) return;
    busy = true;
    try {
      if (root.nodeType === 3) {
        if (!skipped(root)) root.nodeValue = t(root.nodeValue);
      } else if (root.nodeType === 1) {
        var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
        var n, batch = [];
        while ((n = w.nextNode())) batch.push(n);
        for (var i = 0; i < batch.length; i++) {
          if (!skipped(batch[i])) batch[i].nodeValue = t(batch[i].nodeValue);
        }
        var all = root.querySelectorAll ? root.querySelectorAll("*") : [];
        var list = root.nodeType === 1 ? [root] : [];
        for (var k = 0; k < all.length; k++) list.push(all[k]);
        for (var j = 0; j < list.length; j++) attrs(list[j]);
      }
    } finally { busy = false; }
  }

  function attrs(el) {
    if (!el.getAttribute) return;
    for (var i = 0; i < ATTRS.length; i++) {
      var v = el.getAttribute(ATTRS[i]);
      if (v) {
        var tr = t(v);
        if (tr !== v) el.setAttribute(ATTRS[i], tr);
      }
    }
  }

  function selector() {
    var sel = document.createElement("select");
    sel.id = "qa_labLang";
    sel.setAttribute("data-i18n-skip", "");
    // Явно: селектор створюється вже ПІСЛЯ обходу DOM і ще ДО спостерігача,
    // тож жоден із двох механізмів його підпису не побачить.
    sel.title = t("мова інтерфейсу");
    for (var code in LANGS) {
      var o = document.createElement("option");
      o.value = code;
      o.textContent = LANGS[code];
      if (code === lang) o.selected = true;
      sel.appendChild(o);
    }
    sel.onchange = function () {
      try { localStorage.setItem(STORE, sel.value); } catch (e) {}
      /* Перезавантаження, а не переклад на місці: половина екрана намальована
         даними, які вже приїхали, і зібрати їх наново все одно дешевше, ніж
         тримати зворотний словник «переклад → джерело». */
      location.reload();
    };
    var slot = document.querySelector("[data-i18n-slot]");
    if (slot) { slot.appendChild(sel); return; }
    sel.style.cssText = "position:fixed;top:10px;right:12px;z-index:9999";
    (document.body || document.documentElement).appendChild(sel);
  }

  function start() {
    try {
      boot();
    } catch (e) {
      // Впасти тут означало б лишити людину з наполовину перекладеним
      // екраном і без селектора мови. Краще українською, але цілим.
      if (window.console) console.warn("i18n: переклад не застосовано", e);
    }
  }

  function boot() {
    document.documentElement.lang = lang;
    if (document.title) document.title = t(document.title);
    walk(document.body);
    selector();
    new MutationObserver(function (muts) {
      if (busy) return;
      try {
        for (var i = 0; i < muts.length; i++) {
          var m = muts[i];
          if (m.type === "attributes") { busy = true; attrs(m.target); busy = false; }
          for (var j = 0; j < m.addedNodes.length; j++) walk(m.addedNodes[j]);
        }
      } catch (e) {
        busy = false;              // інакше наступні мутації мовчки ігноруються
        if (window.console) console.warn("i18n: вузол не перекладено", e);
      }
    }).observe(document.documentElement, {
      childList: true, subtree: true,
      attributes: true, attributeFilter: ATTRS,
    });
  }

  window.I18N = { lang: lang, t: t, langs: LANGS, chain: chain, dict: dict };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();

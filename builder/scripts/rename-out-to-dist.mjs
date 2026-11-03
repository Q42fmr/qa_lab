// Rename Next's static-export `out/` to `dist/` (deploy server serves dist/).
// Cross-platform; runs after next build + obfuscate. Idempotent-safe.
import { existsSync, rmSync, renameSync } from "node:fs";
if (!existsSync("out")) {
  console.error("[rename] out/ not found — did next build run?");
  process.exit(1);
}
rmSync("dist", { recursive: true, force: true });
renameSync("out", "dist");
console.log("[rename] out/ -> dist/");

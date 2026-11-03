"""Media integrity: local image refs that point nowhere + image files nobody uses."""
from pathlib import Path

NAME = "Картинки: биті та непідключені"
GROUP = "review"
PROJECTS = ["php"]      # node-вайти тягнуть картинки через бандлер (~/assets, імпорти) — тут фолсить
DESCRIPTION = ("Локальні посилання на картинки, яких немає у вітці (error), "
               "та файли-картинки, які ніде не використовуються (warn).")
FILES = ["*.html", "*.php", "*.css", "*.xml"]


def run_branch(files, all_paths):
    from media import scan_text, normalize_local, IMAGE_EXT

    fileset = set(all_paths)
    images = {p for p in all_paths if Path(p).suffix.lower() in IMAGE_EXT}
    basenames = {}
    for p in images:
        basenames.setdefault(Path(p).name, p)

    used = set()
    issues = []
    for path, text in files.items():
        for ref in scan_text(path, text):
            if ref["external"]:
                continue
            tgt = normalize_local(ref["target"])
            match = tgt if tgt in fileset else basenames.get(Path(tgt).name)
            if match:
                used.add(match)
            else:
                issues.append({
                    "path": path, "line": ref["line"], "severity": "error",
                    "message": f"картинки '{ref['target']}' немає у вітці",
                })

    for img in sorted(images - used):
        issues.append({
            "path": img, "severity": "warn",
            "message": "картинка є у вітці, але ніде не використовується",
        })
    return issues

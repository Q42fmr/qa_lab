"""Dev-сміття у гіті. Базово шукаємо лише app.exe; інші назви/патерни
додаються руками у DEL_GLOBS нижче. Автофікс — видалення цих файлів."""
import fnmatch

NAME = "Dev-файли у гіті"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Ловить app.exe і папку .idea/ у вітці; автофікс видаляє. "
               "Інші назви додаються у DEL_GLOBS у checks/dev_files.py.")
FILES = ["app.exe", "*/app.exe", ".idea/*", "*/.idea/*"]

# що вважаємо сміттям (fnmatch по повному шляху) — додавай сюди свої патерни,
# наприклад: "*.exe", ".vscode/*", "Thumbs.db"
DEL_GLOBS = [
    "app.exe", "*/app.exe",
    ".idea", ".idea/*", "*/.idea/*",
]


def _is_junk(path: str) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in DEL_GLOBS)


def run_branch(files, all_paths):
    return [{"path": p, "severity": "error",
             "message": "службовий файл у гіті — прибрати (є автофікс)"}
            for p in all_paths if _is_junk(p)]


def fix_delete(all_paths):
    """Список файлів на видалення для автофіксу."""
    return [p for p in all_paths if _is_junk(p)]

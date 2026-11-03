"""Підпис лаби: хто саме зробив запис у GitLab і в ClickUp.

Один рядок англійською в кінці коміту і в кінці коментаря таски:

    committed via qa_lab by Yurii Spodarenko
    committed via qa_lab by AI bridge (TSM)

Навіщо. Токен один на всіх — і в GitLab, і в ClickUp запис приходить від
бота, тож з боку читача незрозуміло не тільки хто це зробив, а й чим. Підпис
відповідає на обидва питання одним рядком.

⚠️ Це часткове повернення фічі, знесеної 18.08.2026 рішенням замовника
(`qa_lab-work/notes/04-SERVICE-TOKENS-PLAN.md`). Повернено рішенням від
02.09.2026 і свідомо в найвужчому обсязі: тільки ТЕКСТ. Поля
`author_name`/`author_email` коміту не чіпаються — саме вони впирались би в
Push Rule «commit author must be a GitLab user», і саме через них знадобилась
би перевірка на живому GitLab.

Актор їде до точки запису контекстною змінною, а не аргументом: коміт
робиться у 19 місцях, і протягувати користувача через кожне означало б 19
шансів забути. Змінну ставить auth-middleware; синхронний ендпоінт FastAPI
виконується через `run_in_threadpool`, який копіює контекст, — перевірено на
starlette 1.6.0 з образу. Фоновий воркер ШІ-моста живе у власному потоці,
куди контекст не доїжджає, тому там актор ставиться явно.
"""
from __future__ import annotations

import re
from contextvars import ContextVar

LAB = "qa_lab"
BRIDGE = "AI bridge (TSM)"

# Ім'я приходить із профілю Slack, тобто це довільний рядок від людини.
# Обрізаємо, бо перенос рядка в імені дописав би в коміт фальшивий рядок, а в
# коментар ClickUp — фальшивий абзац.
MAX_NAME = 64

# Актор ШІ-моста. Окрема константа, а не запис користувача: у фоновому воркері
# запису немає взагалі, а читач таски й коміту має бачити одне й те саме імʼя.
SERVICE_ACTOR = {"is_service": True}

_actor: ContextVar[dict | None] = ContextVar("qa_lab_actor", default=None)


def set_actor(user: dict | None) -> None:
    _actor.set(user)


def actor() -> dict | None:
    return _actor.get()


def clean_name(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "")).strip()[:MAX_NAME]


def actor_name(user: dict | None = None) -> str:
    """Ім'я для підпису. Порожній рядок — коли актора немає."""
    user = user if user is not None else actor()
    if not user:
        return ""
    if user.get("is_service"):
        # Службовий запис — це ШІ-міст. Для читача таски й коміту він має
        # називатись однаково, тому ім'я тут константа, а не поле запису.
        return BRIDGE
    return clean_name(user.get("name") or user.get("login") or "")


def line(user: dict | None = None) -> str:
    name = actor_name(user)
    return f"committed via {LAB} by {name}" if name else f"committed via {LAB}"


def sign_commit(message: str, user: dict | None = None) -> str:
    """Підпис окремим абзацом у ТІЛІ повідомлення.

    Свідомо не префіксом у першому рядку: `gitlab_client.commits_range()`
    мапить лише `title`, а `stats_backfill.action_for()` визначає по ньому тип
    дії. Префікс змінив би заголовки всіх нових комітів і зламав би розбір
    історії в аналітиці.
    """
    msg = (message or "").rstrip()
    sig = line(user)
    if msg.endswith(sig):            # повторний коміт тим самим текстом
        return msg
    return f"{msg}\n\n{sig}" if msg else sig


def sign_comment(text: str, user: dict | None = None) -> str:
    """Те саме для коментаря в таску.

    Однорядковий коментар («fixed») підписується через тире — інакше короткий
    факт перетворюється на два абзаци. Багаторядковий (відповідь ШІ-моста)
    отримує підпис новим рядком.
    """
    body = (text or "").rstrip()
    sig = line(user)
    if body.endswith(sig):
        return body
    if not body:
        return sig
    return f"{body}\n{sig}" if "\n" in body else f"{body} — {sig}"


class SigningClient:
    """Обгортка навколо клієнта GitLab: єдині двері, через які йде підпис.

    Комітять через `app.client` усі — 17 місць у `app.py`, `replacer.apply()`
    (клієнт приходить аргументом) і `ai_bridge` (клієнт впорскується через
    `wire`). Тому обгортаємо один обʼєкт, а не правимо 19 викликів: інакше
    двадцятий забудуть. `MockClient` обгортається так само, тож офлайн-цикл
    preview → apply перевіряє підпис теж.
    """

    def __init__(self, inner):
        self._inner = inner

    def commit(self, branch: str, message: str, actions: list[dict]):
        return self._inner.commit(branch, sign_commit(message), actions)

    def __getattr__(self, name):
        if name == "_inner":                       # до __init__ — не рекурсія
            raise AttributeError(name)
        return getattr(self._inner, name)

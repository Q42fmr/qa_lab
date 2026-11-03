"""Шифрування дрібних секретів у сховищі — сьогодні це особистий токен ClickUp.

Навіщо взагалі. Застосунковий токен лежить у `.env` відкритим текстом, і це
нормально: він наш. Особистий токен колеги — ні: він відкриває його ClickUp,
а лежатиме або в Mongo кластера, або в `users.json` на томі `qa_lab-state`,
бекапу якого не робить ніхто. Копія такого файлу рано чи пізно опиниться там,
де її не чекали.

Від чого захищає і від чого ні, щоб не було ілюзій: захищає від дампа бази
БЕЗ тому стану. Від того, хто має і код, і том, — ні. Це усвідомлений рівень:
більший вимагав би окремого сховища ключів, якого в лабі немає.

Конструкція — encrypt-then-MAC на стдлібі, без нових залежностей (та сама
лінія, що `hashlib.scrypt` замість bcrypt у `users.py`): ключовий потік з
HMAC-SHA256 у режимі лічильника, тег окремим HMAC по шифротексту. Ключі для
шифрування і для тега розводяться з одного кореневого, щоб не використовувати
той самий ключ двічі.

Корінь — `auth.secret_key()`, той самий, яким підписуються куки: він переживає
рестарт (`.session_secret` у корені стану). Поміняється — токени перестануть
читатись, і це нормально: зміна цього ключа і так розлогінює всіх. Викликач
має показати «введи токен ще раз», а не впасти.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PREFIX = "v1"
_NONCE = 16
_BLOCK = 32


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _root() -> bytes:
    import auth                      # ліниво: auth тягне users, тут був би цикл
    return auth.secret_key()


def _sub(purpose: bytes) -> bytes:
    return hmac.new(_root(), purpose, hashlib.sha256).digest()


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(4, "big"),
                        hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def seal(plaintext: str) -> str:
    """`v1$<nonce>$<ciphertext>$<tag>`, кожен блок — base64url без padding."""
    if not plaintext:
        raise ValueError("порожнє значення")
    raw = plaintext.encode("utf-8")
    nonce = secrets.token_bytes(_NONCE)
    ct = bytes(a ^ b for a, b in zip(raw, _stream(_sub(b"qa_lab-enc"), nonce, len(raw))))
    tag = hmac.new(_sub(b"qa_lab-mac"), PREFIX.encode() + nonce + ct, hashlib.sha256).digest()
    return "$".join([PREFIX, _b64(nonce), _b64(ct), _b64(tag)])


def unseal(blob: str) -> str:
    """Назад. Будь-яка невідповідність — ValueError, ніколи не тихе сміття."""
    try:
        kind, nonce_b64, ct_b64, tag_b64 = (blob or "").split("$")
        nonce, ct, tag = _unb64(nonce_b64), _unb64(ct_b64), _unb64(tag_b64)
    except Exception as e:
        raise ValueError(f"не схоже на запечатане значення: {e}") from e
    if kind != PREFIX:
        raise ValueError(f"невідома версія формату: {kind}")
    expect = hmac.new(_sub(b"qa_lab-mac"), PREFIX.encode() + nonce + ct, hashlib.sha256).digest()
    # Тег звіряємо ДО розшифрування: інакше підроблений шифротекст спершу
    # перетворився б на довільні байти, і помилка вилізла б уже на decode.
    if not hmac.compare_digest(expect, tag):
        raise ValueError("значення не розшифровується цим ключем сесій")
    raw = bytes(a ^ b for a, b in zip(ct, _stream(_sub(b"qa_lab-enc"), nonce, len(ct))))
    return raw.decode("utf-8")


def looks_sealed(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX + "$")

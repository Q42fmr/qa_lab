"""Запечатування дрібних секретів (особистий токен ClickUp).

Токен колеги лежить або в Mongo кластера, або в `users.json` на томі
`qa_lab-state`, бекапу якого не робить ніхто, — тобто копія рано чи пізно
опиниться там, де її не чекали. Тут перевіряється те, від чого це справді
рятує: без ключа сесій значення не читається, а підроблене — не приймається
мовчки.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                    # noqa: E402

import auth                                                 # noqa: E402
import crypto_box                                           # noqa: E402

TOKEN = "pk_90118370_ABCDEF1234567890ZZ"


def _key(value: str):
    os.environ["QA_LAB_SECRET_KEY"] = value
    auth.reset_secret_for_tests()


def test_roundtrip():
    _key("key-one")
    assert crypto_box.unseal(crypto_box.seal(TOKEN)) == TOKEN


def test_the_value_is_not_in_the_blob():
    _key("key-one")
    assert TOKEN not in crypto_box.seal(TOKEN)


def test_two_seals_of_the_same_value_differ():
    """Nonce щоразу новий — інакше по базі було б видно, у кого токени
    однакові."""
    _key("key-one")
    assert crypto_box.seal(TOKEN) != crypto_box.seal(TOKEN)


def test_another_key_cannot_open_it():
    _key("key-one")
    blob = crypto_box.seal(TOKEN)
    _key("key-two")
    try:
        crypto_box.unseal(blob)
    except ValueError:
        return
    raise AssertionError("чужим ключем розпечаталось")


def test_tampered_ciphertext_is_refused_not_decoded():
    """Тег звіряється ДО розшифрування: інакше підробка спершу стала б
    довільними байтами, і помилка вилізла б аж на decode — тобто випадково."""
    _key("key-one")
    kind, nonce, ct, tag = crypto_box.seal(TOKEN).split("$")
    broken = "$".join([kind, nonce, ct[:-4] + "AAAA", tag])
    try:
        crypto_box.unseal(broken)
    except ValueError as e:
        assert "ключ" in str(e), e
        return
    raise AssertionError("підроблений шифротекст прийнято")


def test_garbage_does_not_crash():
    _key("key-one")
    for bad in ("", "x", "v1$$$", "v2$a$b$c", None):
        try:
            crypto_box.unseal(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"прийнято сміття: {bad!r}")


def test_looks_sealed_tells_a_blob_from_a_raw_token():
    _key("key-one")
    assert crypto_box.looks_sealed(crypto_box.seal(TOKEN))
    assert not crypto_box.looks_sealed(TOKEN)


def test_empty_value_is_refused():
    _key("key-one")
    try:
        crypto_box.seal("")
    except ValueError:
        return
    raise AssertionError("порожнє значення запечатано")


run(dict(globals()))

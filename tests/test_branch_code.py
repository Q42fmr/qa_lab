"""Branch code (branch_code.py) — порт гарантій selftest зі специфікації
Whites_maker/branch-code.md, плюс гейт runner.code_gate.

Код у назві вітки називає класи РЕАЛЬНИХ даних клієнта; чеки, чиї
MODIFIES перетинаються з захищеними класами, не запускаються взагалі
(«якщо не треба міняти пошту — чек пошти не запускається»).
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                        # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import branch_code as bc                                        # noqa: E402


def test_spec_worked_examples():
    # branch-code.md: приклади з таблиці — точні кодові сегменти
    assert bc.encode(["email", "phone", "address", "regno"]) == "p1f4"
    assert bc.encode(["phone", "company", "map", "media"]) == "p11oy8"
    assert bc.encode(["email", "phone", "address", "regno",
                      "company", "legal"]) == "p1tb7"
    assert bc.encode(bc.DICT) == "p135ro"
    assert bc.encode([]) == ""           # чисте ім'я, ніколи p10…


def test_every_bit_roundtrips():
    for i, cls in enumerate(bc.DICT):
        seg = bc.encode([cls])
        got = bc.decode(f"irecnuwvw-{seg}-ca-en")
        assert got["protected"] == {cls}, (cls, got)
        assert not got["legacy"] and got["unknown_bits"] == 0
    dense = bc.decode(f"x-{bc.encode(bc.DICT)}-it-it")
    assert dense["protected"] == set(bc.DICT)


def test_clean_and_legacy_numeric_names_decode_empty():
    for name in ("irecnuwvw-ca-en", "eskufoo-bog-406-br-pt",
                 "rerhouko-360-ch-fr", "nwf-setagojco-24s-br-pt",
                 "mds-epidoc-it-it"):
        assert bc.decode(name)["protected"] == set(), name
        assert bc.strip(name) == name, name


def test_v1_legacy_still_decodes():
    got = bc.decode("irecnuwvw-1f-ca-en")
    assert got["protected"] == {"email", "phone", "address", "regno"}
    assert got["legacy"] is True


def test_every_single_char_mutation_is_rejected():
    seg = bc.encode(["phone", "company", "map", "media"])   # p11oy8
    body = seg[1:]                                           # 11oy8
    alpha = "0123456789abcdefghijklmnopqrstuvwxyz"
    bad_accepted = []
    for i in range(len(body)):
        for ch in alpha:
            if ch == body[i]:
                continue
            mut = body[:i] + ch + body[i + 1:]
            name = f"irecnuwvw-p{mut}-ca-en"
            try:
                got = bc.decode(name)
            except bc.BranchCodeError:
                continue                                     # зловлено
            if got["protected"] == {"phone", "company", "map", "media"} \
                    and not got["legacy"]:
                bad_accepted.append(mut)
    assert not bad_accepted, bad_accepted


def test_unusual_tails_roundtrip():
    seg = bc.encode(["email"])
    assert bc.decode(f"x-{seg}-ch-fr-ch-de")["protected"] == {"email"}
    assert bc.decode(f"x-{seg}-sg-eng")["protected"] == {"email"}
    # коротке фінальне слово назви не з'їдається хвостом
    assert bc.decode("safis-sol-br-pt")["protected"] == set()
    assert bc.strip(f"alpha-{seg}-ch-fr-ch-de") == "alpha-ch-fr-ch-de"


def test_unknown_version_raises():
    try:
        bc.decode("x-p2f4-ca-en")
        raise AssertionError("мала бути помилка версії")
    except bc.BranchCodeError:
        pass


def test_unknown_bits_warn_not_crash():
    # маска з бітом 12 (поза словником): decode мусить віддати unknown_bits
    mask = 1 << 12
    m36 = ""
    n = mask
    while n:
        m36 = "0123456789abcdefghijklmnopqrstuvwxyz"[n % 36] + m36
        n //= 36
    payload = "1" + m36
    seg = "p" + payload + bc._check(payload)
    got = bc.decode(f"x-{seg}-ca-en")
    assert got["protected"] == set()
    assert got["unknown_bits"] == mask


def test_protected_of_fails_closed():
    assert bc.protected_of("x-p1f9-ca-en") == set(bc.DICT)   # битий чек-символ
    assert bc.protected_of("irecnuwvw-ca-en") == set()


# ------------------------------------------------------------ runner gate

def _fake(check_id, modifies=None, fixable=True):
    mod = types.SimpleNamespace()
    if modifies is not None:
        mod.MODIFIES = modifies
    if fixable:
        mod.fix_branch = lambda *a: []
    return {"id": check_id, "module": mod, "name": check_id}


def test_code_gate_skips_intersecting_checks():
    import runner
    checks = [_fake("geo_phone", {"phone"}),
              _fake("cookie_consent", set()),
              _fake("legacy_undeclared", None),          # без MODIFIES → "*"
              _fake("readonly_probe", None, fixable=False)]
    allowed, skipped, err = runner.code_gate("x-p13g-ca-en", checks)  # email+phone
    assert err == ""
    assert {c["id"] for c in skipped} == {"geo_phone", "legacy_undeclared"}
    assert {c["id"] for c in allowed} == {"cookie_consent", "readonly_probe"}


def test_code_gate_clean_branch_runs_everything():
    import runner
    checks = [_fake("geo_phone", {"phone"})]
    allowed, skipped, err = runner.code_gate("irecnuwvw-ca-en", checks)
    assert allowed == checks and not skipped and not err


def test_code_gate_corrupted_code_blocks_all():
    import runner
    checks = [_fake("geo_phone", {"phone"}), _fake("plumbing", set())]
    allowed, skipped, err = runner.code_gate("x-p1f9-ca-en", checks)
    assert err and "контрольний символ" in err
    assert {c["id"] for c in skipped} == {"geo_phone"}
    assert {c["id"] for c in allowed} == {"plumbing"}


def test_every_fixable_check_declares_modifies():
    """Контракт розмітки: кожен чек з fix-ентрі має явний MODIFIES —
    незадекларований фікс блокувався б на БУДЬ-ЯКІЙ захищеній вітці."""
    import glob
    import importlib.util as ilu
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.modules.setdefault("runner", types.SimpleNamespace())
    missing = []
    for p in glob.glob(os.path.join(root, "checks", "*.py")):
        src = open(p, encoding="utf-8", errors="replace").read()
        import re as _re
        if not _re.search(r"\ndef fix(_branch|_delete)?\(", src):
            continue
        if not _re.search(r"^MODIFIES\s*=", src, _re.M):
            missing.append(os.path.basename(p))
    assert not missing, f"чеки з фіксом без MODIFIES: {missing}"


if __name__ == "__main__":
    run(dict(globals()))

"""Фікс адреси карти (checks/map_address.py, 02.10).

Негеокодована/плейсхолдерна адреса Leaflet-карти лишає порожній білий блок.
Фікс: 1) спрощений варіант без юніт-частини, якщо геокодиться; 2) адреса
вітки (юридична або гео-база), звірена Nominatim-ом; мережі немає — нуль
дій. Мережа в тестах замокана.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                            # noqa: E402

mod = load_check("map_address")

BR = "mds-x-it-it"
PAGE = ('<html><body><div id="map"></div><script>'
        'var mapConfig = {{ address: "{addr}" }};'
        "L.map('map');</script></body></html>")


def _mock_geo(table):
    """_geocode повертає [hit] для відомих адрес, [] для решти."""
    def fake(addr):
        v = table.get(addr, [])
        return v if v is not None else None
    old = mod._geocode
    mod._geocode = fake
    old_sleep = mod.time.sleep
    mod.time.sleep = lambda *_: None
    def restore():
        mod._geocode = old
        mod.time.sleep = old_sleep
    return restore


def test_unit_address_is_simplified():
    full = "7 Temasek Blvd, #17-21 DUO Tower, Singapore 038987"
    simple = mod._simplify(full)
    r = _mock_geo({full: [], simple: [{"lat": 1}]})
    try:
        files = {"index.php": PAGE.format(addr=full)}
        acts = mod.fix_branch(dict(files), list(files), BR)
        assert acts and simple in acts[0]["content"], acts
        assert full not in acts[0]["content"]
    finally:
        r()


def test_garbage_address_gets_branch_geo():
    import company_req
    files = {"index.php": PAGE.format(addr="2020 Online")}
    geo = mod._branch_address(dict(files), BR)
    assert geo, "гео-база it-it мала дати адресу"
    r = _mock_geo({"2020 Online": [], geo: [{"lat": 1}]})
    try:
        acts = mod.fix_branch(dict(files), list(files), BR)
        assert acts and geo in acts[0]["content"], acts
        # після фікса — геокодиться, run мовчить про цю адресу
        healed = {"index.php": acts[0]["content"]}
        issues = [i for i in mod.run_branch(healed)
                  if "не геокодиться" in i["message"]]
        assert issues == [], issues
    finally:
        r()


def test_placeholder_address_is_replaced():
    files = {"index.php": PAGE.format(addr="{{ADDRESS}}")}
    geo = mod._branch_address(dict(files), BR)
    r = _mock_geo({geo: [{"lat": 1}]})
    try:
        acts = mod.fix_branch(dict(files), list(files), BR)
        assert acts and geo in acts[0]["content"]
    finally:
        r()


def test_no_network_means_no_actions():
    files = {"index.php": PAGE.format(addr="2020 Online")}
    r = _mock_geo({})
    mod._geocode = lambda addr: None          # мережа мертва
    try:
        assert mod.fix_branch(dict(files), list(files), BR) == []
    finally:
        r()


def test_good_address_untouched_and_idempotent():
    good = "Via Roma 10, 20121 Milano"
    files = {"index.php": PAGE.format(addr=good)}
    r = _mock_geo({good: [{"lat": 1}]})
    try:
        assert mod.fix_branch(dict(files), list(files), BR) == []
    finally:
        r()


if __name__ == "__main__":
    run(dict(globals()))

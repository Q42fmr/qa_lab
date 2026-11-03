"""Тести перенесення віток у node-проєкт при імпорті з ClickUp.

Кейс: таска ClickUp не каже, якого типу вайт. Vue-вайти регулярно заводять
у php-проєкт — `resolve_branch` ловить 404, і весь батч падає у «Проблеми»,
хоча гілки існують, просто в іншому репо. `_adopt_elsewhere` перепробовує їх
у node-проєкті й заводить ТУДИ разом з таскою й доменом.

Ключовий контракт, який тут стережеться, — ІЗОЛЯЦІЯ: запис у чужий проєкт
іде через projects.*_for() і не сміє ні зачепити стан активного проєкту, ні
перемкнути сам активний проєкт (він глобальний, а запити ходять пулом).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                    # noqa: E402

os.environ.setdefault("MOCK_MODE", "1")
import app                                                  # noqa: E402
import projects                                             # noqa: E402

NODE = "vue"


class FakeNode:
    """GitLab-клієнт node-репо: знає лише свої вітки, регістр важливий."""

    def __init__(self, names):
        self.names = set(names)
        self.asked = []

    def branch(self, name):
        self.asked.append(name)
        if name not in self.names:
            raise RuntimeError(f"404 Client Error: Not Found for url: .../{name}")
        return {"name": name, "commit": "deadbee", "updated": "2026-01-01"}

    def branch_url(self, name):
        return f"https://gl.test/development/new-white-front/-/tree/{name}"


class Sandbox:
    """Тимчасові теки стану обох проєктів + підставний node-клієнт."""

    def __init__(self, node_branches=("apoj-gencaa-br-pt",), with_node=True):
        self.node_branches, self.with_node = node_branches, with_node

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._reg, self._cl = dict(projects._registry), dict(projects._clients)
        self._cur = projects.current_id()
        projects._registry = {
            "white-pages": {**self._reg["white-pages"], "root": root / "php"},
        }
        if self.with_node:
            projects._registry[NODE] = {
                "id": NODE, "title": "node", "type": "node",
                "gitlab_path": "development/new-white-front",
                "token": "x", "mock": False, "root": root / "node",
            }
        self.node = FakeNode(self.node_branches)
        projects._clients = {NODE: self.node}
        return self

    def __exit__(self, *exc):
        projects._registry, projects._clients = self._reg, self._cl
        self._tmp.cleanup()

    def _read(self, pid, name, default):
        p = projects.state_file_for(pid, name)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def node_state(self, name, default):
        return self._read(NODE, name, default)

    def php_state(self, name, default):
        return self._read("white-pages", name, default)


def _fail(branch, domain=None, task="5 1 step campaigns p-52"):
    return {"branch": branch, "task": task, "task_id": "868abc",
            "task_url": "https://app.clickup.com/t/868abc", "domain": domain,
            "err": "404 Client Error: Not Found"}


def test_branch_present_in_node_is_adopted():
    with Sandbox() as sb:
        moved = app._adopt_elsewhere([_fail("apoj-gencaa-br-pt")])
        assert len(moved) == 1, moved
        assert moved[0]["branch"] == "apoj-gencaa-br-pt"
        assert sb.node_state("branches.json", []) == ["apoj-gencaa-br-pt"]


def test_task_link_and_domain_travel_with_branch():
    """«З їхньою лінкою і посиланням»: у node-проєкт їде таска і домен."""
    with Sandbox() as sb:
        moved = app._adopt_elsewhere([_fail("apoj-gencaa-br-pt", domain="apoj.pro")])
        rec = sb.node_state("clickup_map.json", {})["apoj-gencaa-br-pt"]
        assert rec["task_url"] == "https://app.clickup.com/t/868abc", rec
        assert rec["task_id"] == "868abc" and rec["domain"] == "apoj.pro", rec
        assert moved[0]["url"].endswith("/-/tree/apoj-gencaa-br-pt"), moved
        act = sb.node_state("domains.json", {}).get("active", {})
        assert act["apoj-gencaa-br-pt"]["domain"] == "apoj.pro", act


def test_branch_missing_everywhere_is_not_adopted():
    with Sandbox() as sb:
        assert app._adopt_elsewhere([_fail("nema-takoi-br-pt")]) == []
        assert sb.node_state("branches.json", []) == []


def test_active_project_state_is_untouched():
    """Найважливіше: перенесення не сміє писати у php-проєкт."""
    with Sandbox() as sb:
        app._adopt_elsewhere([_fail("apoj-gencaa-br-pt", domain="apoj.pro")])
        assert sb.php_state("branches.json", []) == []
        assert sb.php_state("clickup_map.json", {}) == {}
        assert sb.php_state("domains.json", {}) == {}


def test_active_project_is_not_switched():
    """set_current під час запиту зіпсував би паралельні виклики."""
    with Sandbox():
        before = projects.current_id()
        app._adopt_elsewhere([_fail("apoj-gencaa-br-pt")])
        assert projects.current_id() == before


def test_case_fallback_keeps_source_name_for_filtering():
    """APEX-... з ClickUp ↔ apex-... у репо: `src` тримає ВХІДНУ назву,
    інакше запис не вичиститься зі списку failed."""
    with Sandbox() as sb:
        moved = app._adopt_elsewhere([_fail("APOJ-GENCAA-BR-PT")])
        assert len(moved) == 1, sb.node.asked
        assert moved[0]["src"] == "APOJ-GENCAA-BR-PT", moved
        assert moved[0]["branch"] == "apoj-gencaa-br-pt", moved
        assert sb.node_state("branches.json", []) == ["apoj-gencaa-br-pt"]


def test_repeated_adoption_does_not_duplicate():
    with Sandbox() as sb:
        for _ in range(3):
            app._adopt_elsewhere([_fail("apoj-gencaa-br-pt")])
        assert sb.node_state("branches.json", []) == ["apoj-gencaa-br-pt"]


def test_existing_node_branches_are_kept():
    with Sandbox() as sb:
        projects.state_file_for(NODE, "branches.json").write_text(
            json.dumps(["stara-br-pt"]), encoding="utf-8")
        app._adopt_elsewhere([_fail("apoj-gencaa-br-pt")])
        assert sb.node_state("branches.json", []) == ["stara-br-pt", "apoj-gencaa-br-pt"]


def test_no_node_project_configured_is_noop():
    """Без VUE_GITLAB_* фіча просто мовчить, а не падає."""
    with Sandbox(with_node=False):
        assert app._adopt_elsewhere([_fail("apoj-gencaa-br-pt")]) == []


def test_empty_input_asks_gitlab_nothing():
    with Sandbox() as sb:
        assert app._adopt_elsewhere([]) == []
        assert sb.node.asked == []


def test_mixed_batch_splits_correctly():
    with Sandbox(node_branches=("apoj-gencaa-br-pt", "atgab-nenekeoc-br-pt")) as sb:
        moved = app._adopt_elsewhere([
            _fail("apoj-gencaa-br-pt"), _fail("nema-br-pt"),
            _fail("atgab-nenekeoc-br-pt")])
        assert {m["branch"] for m in moved} == {"apoj-gencaa-br-pt",
                                                "atgab-nenekeoc-br-pt"}, moved
        assert sorted(sb.node_state("branches.json", [])) == [
            "apoj-gencaa-br-pt", "atgab-nenekeoc-br-pt"]


def test_branch_without_domain_binds_nothing():
    with Sandbox() as sb:
        app._adopt_elsewhere([_fail("apoj-gencaa-br-pt", domain=None)])
        assert sb.node_state("domains.json", {}) == {}
        assert "domain" not in sb.node_state("clickup_map.json", {})["apoj-gencaa-br-pt"]


class FakePhp(FakeNode):
    def branch_url(self, name):
        return f"https://gl.test/development/white-pages/-/tree/{name}"


def test_a_php_branch_imported_from_vue_goes_to_php():
    """Зворотний бік (задача 21.09.2026): людина у vue імпортує таску з
    php-вітками — доти вони падали у «Проблеми» з 404, бо перенос ішов лише
    php → vue."""
    with Sandbox() as sb:
        php = FakePhp({"agihi-nomu-br-pt"})
        projects._clients["white-pages"] = php
        with projects.use(NODE):
            moved = app._adopt_elsewhere([_fail("agihi-nomu-br-pt", domain="agihi.pro")])
        assert [(m["branch"], m["project"]) for m in moved] == [
            ("agihi-nomu-br-pt", "white-pages")], moved
        assert sb.php_state("branches.json", []) == ["agihi-nomu-br-pt"]
        assert sb.php_state("clickup_map.json", {})["agihi-nomu-br-pt"]["domain"] == "agihi.pro"
        assert sb.node_state("branches.json", []) == []


def test_the_move_says_where_the_branch_went():
    with Sandbox():
        moved = app._adopt_elsewhere([_fail("apoj-gencaa-br-pt")])
        assert moved[0]["project"] == NODE and moved[0]["project_title"], moved


if __name__ == "__main__":
    run(dict(globals()))

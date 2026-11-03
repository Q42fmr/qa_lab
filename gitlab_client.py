"""GitLab API client.

Two implementations with the same interface:
  * GitLabClient  - talks to a real GitLab instance over the REST API v4
  * MockClient    - reads branches from local folders in ./fixtures/<branch>/
                    (handy for developing the tool itself without network access)

Interface:
    branches() -> [{name, commit, updated}]
    tree(ref) -> [path, ...]                      (blobs only)
    file_raw(ref, path) -> bytes
    commit(branch, message, actions) -> dict      (actions = GitLab commit actions)
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from pathlib import Path

import requests

import commit_gate


class GitLabClient:
    def __init__(self, base_url: str, project_path: str, token: str, gate: bool = False):
        self.web_base = base_url.rstrip("/")
        self.base = self.web_base + "/api/v4"
        self.project_path = project_path.strip("/")
        self.project = urllib.parse.quote_plus(project_path)
        self.headers = {"PRIVATE-TOKEN": token}
        self.gate = gate            # commit_gate: php-проєкт (див. projects.client_for)

    def commit_url(self, sha: str) -> str:
        return f"{self.web_base}/{self.project_path}/-/commit/{sha}"

    def branch_url(self, name: str) -> str:
        return f"{self.web_base}/{self.project_path}/-/tree/{name}"

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _check(r):
        """Те саме, що `raise_for_status`, але З ТІЛОМ відповіді.

        Голий варіант каже лише «403 Client Error: Forbidden for url: …» — а
        весь сенс лежить у тілі: GitLab пише туди «You are not allowed to push
        into this branch», «insufficient_scope» або ім'я захищеної вітки. Без
        нього відмова прав, захищена вітка і протухлий токен виглядають одним
        і тим самим рядком.

        Кейс 28.08: колега отримав «Закомічено у 0 віток; помилки: 20», і
        з'ясувати причину не було з чого — ні в UI, ні в логах.
        """
        if r.ok:
            return r
        try:
            j = r.json()
            detail = j.get("message") or j.get("error") or ""
            if not isinstance(detail, str):
                detail = str(detail)
        except Exception:
            detail = (r.text or "")[:300]
        raise requests.HTTPError(
            f"{r.status_code} {r.reason} — {detail or 'GitLab не пояснив'}",
            response=r)

    def _get(self, path: str, **params):
        r = requests.get(self.base + path, headers=self.headers, params=params, timeout=30)
        self._check(r)
        return r

    def _paged(self, path: str, **params):
        page = 1
        while True:
            r = self._get(path, per_page=100, page=page, **params)
            yield from r.json()
            if not r.headers.get("X-Next-Page"):
                break
            page += 1

    # -- public ------------------------------------------------------------
    def branches(self):
        return [
            {
                "name": b["name"],
                "commit": b["commit"]["short_id"],
                "updated": b["commit"]["committed_date"],
            }
            for b in self._paged(f"/projects/{self.project}/repository/branches")
        ]

    def branch(self, name: str):
        """Fetch a single branch by name (raises on 404).

        `protected` і `can_push` — з тієї самої відповіді, тобто безкоштовно.
        Це рівно ті два поля, якими 31.08.2026 діагностували не той токен
        (`can_push=False` на всіх вітках), і саме вони дають машинному
        конвеєру шанс сказати «не комітимо, вітка захищена» ЗАМІСТЬ тихого
        403 десь у логах.
        """
        enc = urllib.parse.quote_plus(name)
        b = self._get(f"/projects/{self.project}/repository/branches/{enc}").json()
        return {
            "name": b["name"],
            "commit": b["commit"]["short_id"],
            "updated": b["commit"]["committed_date"],
            "protected": bool(b.get("protected")),
            "can_push": b.get("can_push", True),
        }

    def tree(self, ref: str):
        return [
            item["path"]
            for item in self._paged(
                f"/projects/{self.project}/repository/tree", ref=ref, recursive="true"
            )
            if item["type"] == "blob"
        ]

    def tree_blobs(self, ref: str) -> dict:
        """path -> git blob sha на вказаному ref. Дає змогу порівнювати локальні
        файли з віткою без викачування вмісту (blob sha рахується локально)."""
        return {
            item["path"]: item["id"]
            for item in self._paged(
                f"/projects/{self.project}/repository/tree", ref=ref, recursive="true"
            )
            if item["type"] == "blob"
        }

    def file_raw(self, ref: str, path: str) -> bytes:
        enc = urllib.parse.quote_plus(path)
        return self._get(
            f"/projects/{self.project}/repository/files/{enc}/raw", ref=ref
        ).content

    def archive(self, ref: str) -> bytes:
        """Zip усієї вітки ОДНИМ запитом — на порядок швидше, ніж file_raw по одному."""
        r = requests.get(
            f"{self.base}/projects/{self.project}/repository/archive.zip",
            headers=self.headers, params={"sha": ref}, timeout=120,
        )
        self._check(r)
        return r.content

    def commit(self, branch: str, message: str, actions: list[dict]):
        notes = []
        if self.gate:
            actions, notes = commit_gate.apply(actions)
        r = requests.post(
            f"{self.base}/projects/{self.project}/repository/commits",
            headers=self.headers,
            json={"branch": branch, "commit_message": message, "actions": actions},
            timeout=120,
        )
        self._check(r)
        return {**r.json(), "lab_notes": notes}

    def commits(self, ref: str, limit: int = 20):
        """Останні коміти вітки."""
        r = self._get(f"/projects/{self.project}/repository/commits",
                      ref_name=ref, per_page=min(limit, 100))
        return [{"id": c["id"], "short": c["short_id"], "title": c["title"],
                 "author": c["author_name"], "date": c["committed_date"]}
                for c in r.json()]

    def commit_diff(self, sha: str):
        """Diff одного коміту: [{old_path, new_path, diff, new_file, deleted_file}]."""
        return self._get(
            f"/projects/{self.project}/repository/commits/{sha}/diff",
            per_page=100).json()

    def me(self) -> dict:
        """Користувач токена. Саме його ім'я стоїть автором комітів лаби, тож
        це єдиний надійний спосіб відрізнити їх від генераторських/людських."""
        return self._get("/user").json()

    def commits_range(self, ref: str, since: str = "", until: str = "") -> list[dict]:
        """ВСІ коміти вітки у вікні, з правильною пагінацією.

        Свідомо по одній вітці, а не `all=true`: з `all=true` GitLab фільтрує
        автора ПІСЛЯ пагінації, тож сторінки перекриваються (замір: 324 дублі
        на 424 рядки) і глибше першої сотні унікальних не дістати. Плюс тут
        вітка відома з запиту, а не окремим `/refs` на кожен коміт.
        """
        params = {"ref_name": ref}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        out, page = [], 1
        while True:
            j = self._get(f"/projects/{self.project}/repository/commits",
                          per_page=100, page=page, **params).json()
            if not isinstance(j, list) or not j:
                break
            out += [{"id": c["id"], "short": c["short_id"], "title": c["title"],
                     "author": c["author_name"], "date": c["committed_date"]}
                    for c in j]
            if len(j) < 100:
                break
            page += 1
        return out

    def commit_file_count(self, sha: str) -> int:
        """Скільки файлів зачепив коміт. З пагінацією: масова заміна легко
        перевалює 100 файлів, а `commit_diff` бере лише першу сторінку."""
        n, page = 0, 1
        while True:
            j = self._get(f"/projects/{self.project}/repository/commits/{sha}/diff",
                          per_page=100, page=page).json()
            if not isinstance(j, list) or not j:
                break
            n += len(j)
            if len(j) < 100:
                break
            page += 1
        return n

    def revert(self, sha: str, branch: str):
        """Відкочує коміт новим revert-комітом у вітці."""
        r = requests.post(
            f"{self.base}/projects/{self.project}/repository/commits/{sha}/revert",
            headers=self.headers, json={"branch": branch}, timeout=60,
        )
        self._check(r)
        return r.json()


class MockClient:
    """Serves branches from local folders: fixtures/<branch-name>/**.

    commit() writes changes back to the fixture folder so the whole
    preview -> apply flow can be exercised offline.
    """

    def __init__(self, fixtures_dir: str = "fixtures", root=None, gate: bool = False):
        self.root = Path(root) if root is not None else Path(fixtures_dir)
        self.root.mkdir(exist_ok=True)
        self.gate = gate

    def branches(self):
        out = []
        for d in sorted(p for p in self.root.iterdir() if p.is_dir()):
            out.append(
                {
                    "name": d.name,
                    "commit": "local",
                    "updated": time.strftime(
                        "%Y-%m-%dT%H:%M:%S", time.localtime(d.stat().st_mtime)
                    ),
                }
            )
        return out

    def branch(self, name: str):
        """Ті самі поля, що й у живого клієнта: офлайн-цикл preview → apply
        мусить проходити тим самим кодом, включно з перевіркою захисту.

        `commit` — відбиток вмісту теки, а не константа. Константа зламала б
        `sync_branch`: він пропускає завантаження, коли коміт не змінився, і
        офлайн-цикл preview → apply віддавав би застарілий знімок після
        власного ж коміту.
        """
        import hashlib
        d = self.root / name
        if not d.is_dir():
            raise ValueError(f"немає вітки {name}")
        h = hashlib.sha1()
        for p in sorted(d.rglob("*")):
            if p.is_file():
                st = p.stat()
                h.update(f"{p.relative_to(d)}:{st.st_size}:{st.st_mtime_ns}|"
                         .encode("utf-8"))
        return {"name": name, "commit": h.hexdigest()[:8],
                "updated": time.strftime("%Y-%m-%dT%H:%M:%S",
                                         time.localtime(d.stat().st_mtime)),
                "protected": False, "can_push": True}

    def tree(self, ref: str):
        base = self.root / ref
        return sorted(
            str(p.relative_to(base)).replace(os.sep, "/")
            for p in base.rglob("*")
            if p.is_file()
        )

    def file_raw(self, ref: str, path: str) -> bytes:
        return (self.root / ref / path).read_bytes()

    def tree_blobs(self, ref: str) -> dict:
        import hashlib
        out = {}
        base = self.root / ref
        for p in base.rglob("*"):
            if p.is_file():
                data = p.read_bytes()
                out[str(p.relative_to(base)).replace(os.sep, "/")] = hashlib.sha1(
                    b"blob %d\x00" % len(data) + data).hexdigest()
        return out

    def commit(self, branch: str, message: str, actions: list[dict]):
        notes = []
        if self.gate:
            actions, notes = commit_gate.apply(actions)
        for a in actions:
            target = self.root / branch / a["file_path"]
            if a["action"] == "update" or a["action"] == "create":
                target.parent.mkdir(parents=True, exist_ok=True)
                if a.get("encoding") == "base64":
                    import base64
                    target.write_bytes(base64.b64decode(a["content"]))
                else:
                    target.write_text(a["content"], encoding="utf-8")
            elif a["action"] == "delete":
                target.unlink(missing_ok=True)
        return {"id": "mock-" + str(int(time.time())), "message": message,
                "stats": {"files": len(actions)}, "lab_notes": notes}

    def revert(self, sha: str, branch: str):
        raise NotImplementedError("revert недоступний у MOCK MODE")

    def commits(self, ref: str, limit: int = 20):
        return []

    def commit_diff(self, sha: str):
        return []


def make_client():
    """Build a client from environment variables (.env)."""
    token = os.getenv("GITLAB_TOKEN", "").strip()
    if not token or os.getenv("MOCK_MODE") == "1":
        return MockClient(), True
    return (
        GitLabClient(
            os.getenv("GITLAB_URL", "https://gitlab.example.com"),
            os.getenv("GITLAB_PROJECT", "development/white-pages"),
            token,
        ),
        False,
    )

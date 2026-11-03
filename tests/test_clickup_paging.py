"""Сторінки джерел ClickUp читаються хвилями, а не одна за одною.

01.09.2026 вкладка ClickUp у проді віддавала 502, і віддавала його
Cloudflare, а не лаба: виклик `/api/clickup/tasks` тривав 99 с при межі
походу до origin у 100 с. Локально він укладався — рівно на межі, тому з
коду проблема не читалась ніяк.

83 с із тих 99 — ОДНЕ вʼю з трьох (`8abcd12-34567`, вʼю всього воркспейсу,
382 таски). `/view/{id}/task` віддає рівно по 30 тасок за ~6.4 с і не приймає
жодних фільтрів: з `date_updated_gt`, `statuses[]` і `subtasks` він повертає
той самий набір до таски. Тобто зменшити обсяг не можна, можна лише читати
сторінки одночасно.

Тести в мережу не ходять: `_pages` дістає підставну функцію сторінки, і
рахується не час, а ЯКІ сторінки вона запитала. Саме за цим видно різницю між
хвилею і послідовним читанням: хвиля просить сторінки за межею джерела, а
послідовний цикл — ніколи.
"""
from __future__ import annotations

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                    # noqa: E402

import clickup_client                                       # noqa: E402


class _Source:
    """Джерело з `total` тасок по `size` на сторінку. Пам'ятає, що просили."""

    def __init__(self, total: int, size: int = 30):
        self.total, self.size = total, size
        self.asked: set[int] = set()
        self._lock = threading.Lock()

    def page(self, p: int) -> list[dict]:
        with self._lock:
            self.asked.add(p)
        start = p * self.size
        return [{"id": f"t{i}"} for i in range(start, min(start + self.size,
                                                          self.total))]


def _pages(src, first=clickup_client.VIEW_FIRST, wave=clickup_client.VIEW_WAVE):
    return clickup_client._pages(src.page, src.size, first, wave)


def test_small_source_costs_one_request():
    """Вʼю на 9 тасок — це одна коротка сторінка, і питати більше нема чого.

    Заради цього перша хвиля й звужена до однієї сторінки: два з трьох наших
    вʼю саме такі (EVA — 9 тасок, List — 22), і широка хвиля з місця витратила
    б на них по шістнадцять запитів замість одного."""
    src = _Source(9)
    got = _pages(src)
    assert len(got) == 9, len(got)
    assert src.asked == {0}, src.asked


def test_big_source_is_read_in_one_wide_wave():
    """13 сторінок мають піти ОДНИМ заходом після пробної.

    Ознака, за якою це видно без секундоміра: хвиля просить і сторінки за
    межею джерела (13, 14, 15, 16) — послідовний цикл їх не просив би ніколи,
    бо зупинився б на неповній 12-й."""
    src = _Source(382)
    got = _pages(src)
    assert len(got) == 382, len(got)
    assert 0 in src.asked and 16 in src.asked, sorted(src.asked)
    assert src.asked == set(range(0, 17)), sorted(src.asked)


def test_nothing_is_lost_when_the_last_page_is_exactly_full():
    """Рівно 60 тасок = дві повні сторінки: ознаки кінця в них немає.

    Кінець тут видно лише з наступної хвилі, де сторінки порожні. Це та сама
    межа, на якій `last_page` з відповіді дав би відповідь одразу — і саме
    тому варто перевірити, що без нього нічого не губиться і не двоїться."""
    src = _Source(60)
    got = _pages(src)
    assert len(got) == 60, len(got)
    assert len({t["id"] for t in got}) == 60, "таски продубльувались"


def test_the_page_guard_still_holds():
    """Запобіжник у 30 сторінок на джерело лишився на місці.

    Він стоїть тут не від жадібності ClickUp, а від нашої власної помилки:
    якби кінець джерела не розпізнавався, цикл ходив би вічно."""
    src = _Source(10 ** 6)
    got = _pages(src)
    assert max(src.asked) == 29, sorted(src.asked)[-3:]
    assert len(got) == 30 * src.size, len(got)


def test_team_pages_keep_their_own_wave():
    """team-ендпоінт віддає по 100 тасок і лягає в одну хвилю з п'яти.

    Пробна сторінка йому не потрібна: 299 тасок воркспейсу — це три сторінки,
    тобто перша ж хвиля бачить неповну і зупиняється."""
    src = _Source(299, size=100)
    got = _pages(src, first=clickup_client.TEAM_WAVE, wave=clickup_client.TEAM_WAVE)
    assert len(got) == 299, len(got)
    assert src.asked == {0, 1, 2, 3, 4}, sorted(src.asked)


if __name__ == "__main__":
    run(dict(globals()))

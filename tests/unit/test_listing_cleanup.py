"""Deleting only the drafts an exploration made (agent/ec_skills/listing_cleanup)."""
import asyncio
import json

from agent.ec_skills import listing_cleanup as C


class Page:
    def __init__(self, drafts):
        self.drafts, self.clicks, self.closed, self.rows_asked = list(drafts), [], False, []

    async def evaluate(self, js, timeout=30):
        if "commit/list" in js:
            return json.dumps(self.drafts)
        if "row.querySelectorAll" in js:                       # the row-action lookup
            goods = json.loads(js.rsplit("})(", 1)[1].split(",")[0])
            self.rows_asked.append(goods)
            return [10, 20] if any(d["goods"] == goods for d in self.drafts) else None
        if "确认删除这条草稿" in js:
            return [30, 40]
        return True

    async def mouse_click(self, x, y):
        self.clicks.append((x, y))
        if (x, y) == (30, 40):
            self.drafts = [d for d in self.drafts if d["goods"] != self.rows_asked[-1]]

    async def close(self):
        self.closed = True


def _run(page, created, monkeypatch):
    from agent.ec_skills.explorer import page as P
    async def fake_open(port, url, reuse=""):
        return page
    monkeypatch.setattr(P.PageSession, "open", staticmethod(fake_open))
    monkeypatch.setattr(C.asyncio, "sleep", lambda *_: _noop())
    return asyncio.run(C.delete_pdd_drafts(1, created))


async def _noop():
    return None


def test_only_the_explorations_own_drafts_are_deleted(monkeypatch):
    store = {"commit": "203", "goods": "1017112122953"}            # the store's own draft
    ours = {"commit": "205099994178", "goods": "1023999000111"}
    page = Page([store, ours])
    out = _run(page, ["205099994178"], monkeypatch)
    assert out == {"deleted": ["205099994178"], "left": []}
    assert page.drafts == [store] and page.rows_asked == ["1023999000111"] and page.closed


def test_nothing_created_touches_nothing(monkeypatch):
    page = Page([{"commit": "203", "goods": "1017112122953"}])
    assert _run(page, [], monkeypatch) == {"deleted": [], "left": []}
    assert page.clicks == []

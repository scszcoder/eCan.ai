"""The explorer may work on a record its own tab created (拼多多's 下一步 makes a goods
draft), even when the new page's own requests pushed the create request out of the
recent network log (KEN 11-02 run 99: sent back off its own draft twice)."""
import asyncio

from agent.ec_skills.explorer import loop


class FakePage:
    def __init__(self, url, network, creates, bodies):
        self._url, self.network, self.creates, self._bodies = url, network, creates, bodies

    async def url(self):
        return self._url

    async def response_body(self, rid):
        return self._bodies.get(rid, "")

    async def evaluate(self, js, timeout=0):
        self._url = "https://mms.pinduoduo.com/goods/category"


URL = "https://mms.pinduoduo.com/goods/goods_add/index?type=add&id=205193743656&goods_id=1024296674320"


def _run(page, ctx):
    return asyncio.run(loop._leave_foreign_record(page, ctx, "ok"))


def test_own_draft_found_beyond_the_recent_window():
    create = {"id": "c1", "url": "https://mms.pinduoduo.com/glide/v2/mms/edit/commit/create_new"}
    noise = [{"id": f"n{i}", "url": f"https://mms.pinduoduo.com/q/{i}"} for i in range(150)]
    page = FakePage(URL, [create] + noise, [create], {"c1": '{"goods_id":1024296674320,"id":205193743656}'})
    ctx = {"own_ids": []}
    out = _run(page, ctx)
    assert "自己新建" in out and "1024296674320" in ctx["own_ids"] and "205193743656" in ctx["created"]


def test_a_record_we_did_not_create_is_left():
    page = FakePage(URL, [], [], {})
    out = _run(page, {"own_ids": []})
    assert "拒绝" in out

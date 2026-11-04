"""``pdd_confirm_listing``: is this goods really published on 拼多多?

Runs in the store's own mms.pinduoduo.com page, read-only, on the chat page's
goods API (the 商品列表 page's own API wants a signed anti-content header and
answers 54001 to a plain request; see knowledge/ks/store_images.py):

* ``/latitude/goods/skuSelectorForMall {goodsId, uid: "0"}`` -> ``mallId`` and
  ``sku[].skuId`` in 拼多多's order, with ``isOnsale``.

(KEN 2026-10-31.) That API gives no creation time, so "created before this run"
cannot be checked here; a repeat of the same goods is still never charged twice
(same keys). Only what 拼多多 answers is recorded, through
``listing_meter.record_listing``, which skips test runs.
"""

import json

from browser_use import BrowserSession
from browser_use.agent.views import ActionResult
from pydantic import BaseModel, Field

from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
from agent.ec_skills.browser_use_extension.form_store_tools import _run

PLATFORM = "pdd"

_READ_JS = r"""(async (want) => {
  const r = await (await fetch('/latitude/goods/skuSelectorForMall', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({goodsId: Number(want), uid: '0'})})).json();
  const g = r.success ? (r.result || {}) : null;
  if (!g || String(g.goodsId || '') !== want) return JSON.stringify({found: false, msg: r.errorMsg || ''});
  return JSON.stringify({found: true, product_id: String(g.goodsId), shop_id: String(g.mallId || ''),
    sku_ids: (g.sku || []).map(k => String(k.skuId || '')).filter(Boolean),
    published: Number(g.isOnsale) === 1, title: g.goodsName || ''});
})(%s)"""


class ConfirmListingAction(BaseModel):
    product_id: str = Field(description="The new goods' id (商品ID / goods_id) as the publish step got it")


@custom_controller.action(
    "Confirm a goods this run just published on 拼多多: reads it back from 拼多多 (read-only) and records "
    "the new listing. Run it on an mms.pinduoduo.com page, once, after publishing.",
    param_model=ConfirmListingAction,
)
async def pdd_confirm_listing(params: ConfirmListingAction, browser_session: BrowserSession) -> ActionResult:
    want = "".join(ch for ch in str(params.product_id) if ch.isdigit())
    if not want:
        return ActionResult(error="pdd_confirm_listing: no goods id")
    raw = await _run(browser_session, _READ_JS % json.dumps(want))
    try:
        seen = json.loads(raw)
    except Exception:
        return ActionResult(error=f"pdd_confirm_listing: could not read the goods ({raw[:200]})")
    if not seen.get("found"):
        return ActionResult(extracted_content=json.dumps(
            {"confirmed": False, "why": "拼多多 does not list it (not published, or still under review)",
             "msg": seen.get("msg", "")}, ensure_ascii=False))
    if not seen.get("published"):
        return ActionResult(extracted_content=json.dumps({"confirmed": False, "why": "not on sale",
                                                          "product_id": seen.get("product_id")}, ensure_ascii=False))
    from agent.ec_skills.listing_meter import record_listing
    billing = record_listing(PLATFORM, seen.get("shop_id", ""), seen["product_id"], seen.get("sku_ids") or [])
    return ActionResult(extracted_content=json.dumps(
        {"confirmed": True, "product_id": seen["product_id"], "skus": len(seen.get("sku_ids") or []),
         "billing": billing}, ensure_ascii=False))

"""``douyin_confirm_listing``: is this product really new and published on 抖店?

Runs in the store's own 抖店 back-office page (fxg.jinritemai.com), read-only:

* ``/product/tproduct/list`` (paged, all tabs) -> the product's row: ``shop_id``,
  ``create_time`` (Beijing time), ``publish_time`` (0 for a draft),
  ``draft_status`` (1 = draft), ``delete_time``;
* ``/product/tproduct/getSchema`` -> ``sku_detail[].sku_id`` in 抖店's order.

(KEN 2026-10-31.) Only what 抖店 answers is recorded -- never the agent's claim --
through ``listing_meter.record_listing``, which skips test runs and products
older than the run.
"""

import json

from browser_use import BrowserSession
from browser_use.agent.views import ActionResult
from pydantic import BaseModel, Field

from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
from agent.ec_skills.browser_use_extension.form_store_tools import _run

PLATFORM = "douyin"

_READ_JS = r"""(async (want) => {
  const get = async u => (await fetch(u, {credentials: 'include'})).json();
  let row = null;
  for (let page = 0; page < 10 && !row; page++) {
    const l = await get('/product/tproduct/list?page=' + page + '&pageSize=100&tab=all&business_type=4&appid=1');
    const rows = l.data || [];
    // An id cut short (13 of 19 digits, run 55) still names one product.
    row = rows.find(p => String(p.product_id) === want) || rows.find(p => String(p.product_id).startsWith(want)) || null;
    if (!rows.length) break;
  }
  if (!row) return JSON.stringify({found: false});
  const pid = String(row.product_id);
  const s = await (await fetch('/product/tproduct/getSchema?appid=1', {method: 'POST', credentials: 'include',
    headers: {'content-type': 'application/json'}, body: JSON.stringify({context: {product_id: pid}})})).json();
  const skus = ((((s.data || {}).model || {}).sku_detail || {}).value || []).map(k => String(k.sku_id || k.id || '')).filter(Boolean);
  const created = row.create_time ? Date.parse(String(row.create_time).replace(' ', 'T') + '+08:00') / 1000 : 0;
  return JSON.stringify({found: true, product_id: pid, shop_id: String(row.shop_id || ''), sku_ids: skus,
    created_at: created || null, published: Number(row.publish_time) > 0 && Number(row.draft_status) !== 1 && !Number(row.delete_time),
    title: row.name || ''});
})(%s)"""


class ConfirmListingAction(BaseModel):
    product_id: str = Field(description="The new product's id (商品ID) as the publish step got it")


@custom_controller.action(
    "Confirm a product this run just published on 抖店: reads it back from 抖店 (read-only) and records "
    "the new listing. Run it on the 抖店 back-office page, once, after publishing.",
    param_model=ConfirmListingAction,
)
async def douyin_confirm_listing(params: ConfirmListingAction, browser_session: BrowserSession) -> ActionResult:
    want = "".join(ch for ch in str(params.product_id) if ch.isdigit())
    if not want:
        return ActionResult(error="douyin_confirm_listing: no product id")
    raw = await _run(browser_session, _READ_JS % json.dumps(want))
    try:
        seen = json.loads(raw)
    except Exception:
        return ActionResult(error=f"douyin_confirm_listing: could not read the product ({raw[:200]})")
    if not seen.get("found"):
        return ActionResult(extracted_content=json.dumps({"confirmed": False, "why": "not in the store's product list"},
                                                         ensure_ascii=False))
    if not seen.get("published"):
        return ActionResult(extracted_content=json.dumps({"confirmed": False, "why": "a draft or deleted, not published",
                                                          "product_id": seen.get("product_id")}, ensure_ascii=False))
    from agent.ec_skills.listing_meter import record_listing
    billing = record_listing(PLATFORM, seen.get("shop_id", ""), seen["product_id"], seen.get("sku_ids") or [],
                             created_at=seen.get("created_at"))
    return ActionResult(extracted_content=json.dumps(
        {"confirmed": True, "product_id": seen["product_id"], "skus": len(seen.get("sku_ids") or []),
         "billing": billing}, ensure_ascii=False))

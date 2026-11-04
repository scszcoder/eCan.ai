"""Delete the drafts an exploration itself created, and nothing else.

拼多多's 下一步 creates a goods draft (a "commit") and opens it; the explorer is
allowed into a record its own tab created (explorer.loop._created_here) and
returns those ids as ``created``. When it ends, any of them still in the 草稿箱
is deleted the way a person does it there: 删除草稿, then 确认 (KEN 11-01, done by
hand on the live page first). Only rows whose commit id is in ``created`` are
touched; a draft the store owns is never selected.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict, List

from utils.logger_helper import logger_helper as logger

PDD_LIST = "https://mms.pinduoduo.com/goods/goods_list"

_PDD_DRAFTS_JS = r"""(async () => {
  const r = await (await fetch('/glide/v2/mms/query/commit/list', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({check_status: 0, start: 0, length: 50})})).json();
  return JSON.stringify(((r.result || {}).list || []).map(x => ({commit: String(x.goods_commit_id || ''), goods: String(x.goods_id || '')})));
})()"""

_ROW_ACTION_JS = r"""((goods, text) => {
  const row = [...document.querySelectorAll('tr')].find(r => r.innerText.includes(goods));
  if (!row) return null;
  const b = [...row.querySelectorAll('*')].find(e => e.children.length === 0 && (e.innerText || '').trim() === text);
  if (!b) return null;
  b.scrollIntoView({block: 'center'});
  const r = b.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2];
})(%s, %s)"""

_CONFIRM_JS = r"""(() => {
  const box = [...document.querySelectorAll('div')].find(d => (d.innerText || '').startsWith('确认删除这条草稿') && d.getBoundingClientRect().width > 0);
  if (!box) return null;
  const b = [...box.querySelectorAll('*')].filter(e => (e.innerText || '').trim() === '确认' && e.getBoundingClientRect().width > 0).pop();
  if (!b) return null;
  const r = b.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2];
})()"""

# The 新消息 panel lies over the rows' right-hand actions (KEN 11-01); hide it (display only).
_HIDE_PANELS_JS = r"""(() => { let n = 0;
  for (const e of document.querySelectorAll('body *')) { const cs = getComputedStyle(e);
    if ((cs.position === 'fixed' || cs.position === 'absolute') && /^新消息/.test((e.innerText || '').trim()) && e.getBoundingClientRect().width < 700) {
      let p = e; while (p.parentElement && getComputedStyle(p.parentElement).position !== 'static' && p.parentElement.getBoundingClientRect().width < 700) p = p.parentElement;
      p.style.display = 'none'; n++; } }
  return n; })()"""

_DRAFT_TAB_JS = r"""(() => {
  const e = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && /^草稿箱\(\d+\)$/.test((e.innerText || '').trim()));
  if (e) e.click();
  return !!e;
})()"""


async def delete_pdd_drafts(port: int, created: List[str]) -> Dict[str, Any]:
    from agent.ec_skills.explorer.page import PageSession
    want = {str(x) for x in created or [] if str(x).strip()}
    if not want:
        return {"deleted": [], "left": []}
    page = await PageSession.open(port, PDD_LIST)
    deleted: List[str] = []
    try:
        await asyncio.sleep(3)
        drafts = json.loads(await page.evaluate(_PDD_DRAFTS_JS, 30) or "[]")
        mine = [d for d in drafts if d["commit"] in want or d["goods"] in want]
        if not mine:
            return {"deleted": [], "left": []}
        await page.evaluate(_DRAFT_TAB_JS, 10)
        await asyncio.sleep(3)
        await page.evaluate(_HIDE_PANELS_JS, 10)
        for d in mine:
            pos = await page.evaluate(_ROW_ACTION_JS % (json.dumps(d["goods"]), json.dumps("删除草稿")), 10)
            if not pos:
                continue
            await page.mouse_click(*pos)
            await asyncio.sleep(1.5)
            ok = await page.evaluate(_CONFIRM_JS, 10)
            if not ok:
                continue
            await page.mouse_click(*ok)
            await asyncio.sleep(2.5)
            deleted.append(d["commit"])
        left = json.loads(await page.evaluate(_PDD_DRAFTS_JS, 30) or "[]")
        left_mine = [d["commit"] for d in left if d["commit"] in want or d["goods"] in want]
        logger.info(f"[listing-cleanup] pdd drafts made by the exploration: deleted {deleted}, still there {left_mine}")
        return {"deleted": deleted, "left": left_mine}
    finally:
        await page.close()


def delete_pdd_drafts_sync(store_id: str, created: List[str]) -> Dict[str, Any]:
    """From a skill's code node: delete this exploration's leftover 拼多多 drafts."""
    from agent.ec_skills.explorer.page import browser_port
    box: Dict[str, Any] = {}

    def run():
        try:
            port = browser_port(store_id)
            box["out"] = asyncio.run(delete_pdd_drafts(port, created)) if port else {"error": "no store browser"}
        except Exception as exc:
            logger.warning(f"[listing-cleanup] failed: {type(exc).__name__}: {exc}")
            box["out"] = {"error": f"{type(exc).__name__}: {exc}"}
    th = threading.Thread(target=run, name="listing-cleanup", daemon=True)
    th.start()
    th.join(180)
    return box.get("out") or {"error": "timed out"}

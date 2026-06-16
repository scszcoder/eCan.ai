"""ws076B: prime-on-attach via a ONE-TIME in-page DOM read of the conversation sidebar.

Sibling of ws076A — same goal (seed ``ws_session.prime_name`` talk_id -> real customer name so
a name-less card resolves from turn 1, milestone gap #2) but the SOURCE is a single in-page eval
scraping the sidebar list, rather than passive HTTP capture.

This is the FRAGILE approach the milestone is trying to move away from: it reads the DOM, whose
selectors break on Feige's frequent sidebar redesigns. Implemented to A/B against ws076A, which
relocates nothing to the DOM. One eval per attached tab at startup (off the hot path, retried a
few times while the SPA finishes rendering). Gated ``ECAN_FEIGE_WS_PRIME_DOM=1``.

No fixed hashed selectors (those are exactly what break) — a best-effort generic walk over
data-attributed nodes, pairing a snowflake-looking id with the most name-like text in the row.
"""
from __future__ import annotations

import asyncio
import json
import logging

from . import ws_session

logger = logging.getLogger("eCan")

_SCRAPE_JS = r"""
(function(){
  try{
    var out=[]; var seen={};
    var nodes=document.querySelectorAll(
      '[data-conversation-id],[data-conv-id],[data-talk-id],[data-cid],[data-id],[data-key]');
    for(var i=0;i<nodes.length;i++){
      var el=nodes[i], id='', a=el.attributes;
      for(var j=0;j<a.length;j++){
        var v=a[j].value||'';
        if(/^\d{16,21}$/.test(v)){ id=v; break; }      // snowflake-looking talk_id
      }
      if(!id||seen[id]) continue;
      var lines=(el.innerText||'').split('\n').map(function(s){return s.trim();}).filter(Boolean);
      var name='';
      for(var k=0;k<lines.length;k++){
        var t=lines[k];
        if(t.length>=1 && t.length<=24 && !/^\d+$/.test(t)
           && t.indexOf('已读')<0 && t.indexOf('草稿')<0 && t.indexOf('小店接入')<0){ name=t; break; }
      }
      if(name){ seen[id]=1; out.push({talk_id:id, name:name}); }
    }
    return JSON.stringify(out);
  }catch(e){ return '[]'; }
})()
"""


async def _scrape_once(client, sids) -> int:
    seeded = 0
    for sid in (sids or []):
        try:
            res = await client.send_raw(
                "Runtime.evaluate",
                {"expression": _SCRAPE_JS, "returnByValue": True},
                session_id=sid)
            rows = json.loads(((res or {}).get("result") or {}).get("value") or "[]")
        except Exception as e:
            logger.debug(f"[WS-PRIME-DOM] scrape failed on sid={sid}: {e}")
            continue
        if rows:
            logger.info(f"[WS-PRIME-DOM] sidebar read found {len(rows)} rows (sample={rows[:3]})")
        for r in rows:
            if ws_session.prime_name(r.get("talk_id"), r.get("name")):
                seeded += 1
    return seeded


async def prime(client, sids) -> int:
    """Run the one-time sidebar read (up to 3 attempts while the SPA renders); seed prime_name."""
    total = 0
    for _attempt in range(3):
        await asyncio.sleep(2.0)
        s = await _scrape_once(client, sids)
        total += s
        if s:
            break
    if total:
        logger.info(f"[WS-PRIME-DOM] seeded {total} talk->name from the sidebar DOM")
    else:
        logger.info("[WS-PRIME-DOM] no talk->name seeded (no snowflake-id'd rows matched)")
    return total

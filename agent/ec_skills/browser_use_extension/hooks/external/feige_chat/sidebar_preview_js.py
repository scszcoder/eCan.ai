"""ws189: structural fallback for reading a Feige sidebar row's last-message preview.

Live 2026-09-04 13:15 (customer 肽斯特, build 96s): a brand-new cold-start
conversation arrived (WS carried only the msg_type 1000/2004 system frames —
the customer's text never reaches WS), the ws108/ws166 backstop scan saw the
new rows render (rows 12 -> 14) but skipped EVERY row as ``empty_preview``,
because the preview selector ``[class*="msgContent"], .lF_M7QiFB0ukHWpMfQde span``
no longer matches anything on the rebuilt Feige frame. Same class-hash drift
as this morning's readRowName failure (85e2ab93a), on the detection side. The
customer waited 12 minutes ("用户已等待超...分钟，请尽快回复") with no reply.

The preview text IS in the row: the ws178 nameless-row dump shows the row's
textContent as name + date + preview back-to-back ('0333' '06/29'
'用户超时未回复，系统关闭会话'). So when the selectors miss, walk the row's leaf
text nodes and take the last one that is not the name, a time/date, a numeric
badge, or a warning tag — the preview sits in the bottom row of the item, after
the name row, so "last surviving leaf" is the preview on both the old and the
rebuilt layout.

Shared by the three JS readers that gate detection/dispatch/delivery so they
cannot drift apart again: front_desk (backstop scan), pre_dispatch_enrich (card
row resolution), site_tools (send-path card scan + stale precheck). Pure JS
source, no imports — safe to import from any of them.
"""

ROW_PREVIEW_FALLBACK_JS = r"""
  function __ecanRowPreviewFallback(row, name){
    if(!row||!row.querySelectorAll) return '';
    var skipCls=/badge|unread|reddot|userlabel|cardtag|avatar/i;
    var timeRe=/^(\d{1,2}:\d{2}(:\d{2})?|\d{1,2}[\/\-月]\d{1,2}日?|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}|\d+\s*(秒|分钟|小时|天)前?|刚刚|昨天|前天)$/;
    var tagRe=/预警$|^重复来访$/;
    var nm=String(name||'').trim();
    var els=row.querySelectorAll('*');
    var cands=[];
    for(var i=0;i<els.length;i++){
      var el=els[i];
      if(el.children&&el.children.length) continue;
      var tag=String(el.tagName||'').toLowerCase();
      if(tag==='img'||tag==='svg'||tag==='sup'||tag==='style'||tag==='script') continue;
      var skip=false, p=el;
      while(p&&p!==row){ if(skipCls.test(String(p.className||''))){skip=true;break;} p=p.parentElement; }
      if(skip) continue;
      var t=String(el.textContent||'').replace(/\s+/g,' ').trim();
      if(!t) continue;
      if(nm&&t===nm) continue;
      if(/^\d+$/.test(t)) continue;
      if(timeRe.test(t)) continue;
      if(tagRe.test(t)) continue;
      cands.push({el:el, t:t});
    }
    if(!cands.length) return '';
    // A preview split across sibling leaves (e.g. a '[商品]' marker span + text
    // span) shares one parent — join the trailing run that shares the last
    // candidate's parent so the whole preview comes back, not its tail.
    var par=cands[cands.length-1].el.parentElement;
    var parts=[];
    for(var c=cands.length-1;c>=0;c--){
      if(cands[c].el.parentElement!==par) break;
      parts.unshift(cands[c].t);
    }
    return parts.join('');
  }
"""

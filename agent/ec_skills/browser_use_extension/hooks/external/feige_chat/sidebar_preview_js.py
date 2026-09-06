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


# ws193 (2026-09-06): shared sidebar-row NAME reader — the redesign-resilient
# parser that had lived ONLY in front_desk's ws108 scan (ws110 broad fallbacks +
# ws183 all-[title] iteration). The click-to-open (FEIGE_CLICK_SIDEBAR_ROW_JS)
# and active-customer-verify (FEIGE_ACTIVE_CUSTOMER_JS) readers in dom_assets
# still used the mt062-era selectors and returned seen_names=[] on the rebuilt
# frame (live 96z 2026-09-06 cust 'sc': ws108 scan saw names=['sc',...] but the
# click reader could not find 'sc' → cold-start message never scraped → stuck).
# Sharing ONE reader stops the three parsers drifting apart again — same lesson
# as ROW_PREVIEW_FALLBACK_JS above, for the name.
ROW_NAME_JS = r"""
  function __ecanRowName(row){
    if(!row||!row.querySelector) return '';
    var nick=row.querySelector('[data-qa-id="qa-conversation-nickname"]');
    if(nick){var nv=(nick.textContent||'').trim(); if(nv) return nv;}
    var line=row.querySelector('[class*="nameLine"]');
    if(line){var lt=(line.getAttribute('title')||'').trim(); if(lt) return lt;
      var nc=line.querySelector('[class*="NameContent"]'); if(nc){var ncv=(nc.textContent||'').trim(); if(ncv) return ncv;}}
    var nc2=row.querySelector('[class*="NameContent"]'); if(nc2){var v=(nc2.textContent||'').trim(); if(v) return v;}
    // ws110: broad fallback for selector drift — any data-qa-id mentioning
    // nickname/name, or a short title= that isn't a numeric preview/time.
    var alt=row.querySelector('[data-qa-id*="nickname" i],[data-qa-id*="name" i]');
    if(alt){var av=(alt.getAttribute('title')||alt.textContent||'').trim(); if(av&&av.length<=24) return av;}
    // ws183: iterate ALL titled descendants — the 重复来访 revisit-row variant's
    // FIRST [title] is the unread badge ('1'); the real name is a later one.
    // Skip badge counts and time-ago strings.
    var titledAll=row.querySelectorAll('[title]');
    for(var t=0;t<titledAll.length&&t<6;t++){
      var tv=(titledAll[t].getAttribute('title')||'').trim();
      if(tv&&tv.length<=24&&!/^[\d:\s]+$/.test(tv)&&!/^\d+\s*(分钟|小时|秒|天)/.test(tv)) return tv;
    }
    // legacy hashed classes last (older layouts).
    var wrap=row.querySelector('.MP1bk3ccfHC9V2SnPCGD');
    if(wrap){var wt=(wrap.getAttribute('title')||'').trim(); if(wt) return wt;}
    var span=row.querySelector('.Jv6FtqUv5VoYARd2pp4y');
    if(span){var s=(span.textContent||'').trim(); if(s) return s;}
    return '';
  }
"""

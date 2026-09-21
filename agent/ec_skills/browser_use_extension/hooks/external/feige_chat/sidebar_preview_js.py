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
# Phase 1 of docs/SELF_HEALING_ROADMAP.md: each branch tags itself before
# returning, so a scan can tally WHICH parser is actually carrying the load.
# Purely additive — every branch returns exactly what it returned before, and
# a tagging failure cannot change a name. `__ecanRowNameTally` accumulates on
# the page; the scan hands it to element_targeting and resets it.
#
# The point of the tally: the branches below are six years of scar tissue, and
# nobody knows which still fire. If the semantic ones (titled-descendant scan)
# carry traffic while the hashed-class ones are dead, the migration in Phase 2
# is evidence-backed rather than a guess.
ROW_NAME_JS = r"""
  window.__ecanRowNameTally = window.__ecanRowNameTally || {};
  function __ecanRowNameTag(strategy, value){
    try { var t = window.__ecanRowNameTally;
          t[strategy] = (t[strategy] || 0) + 1; } catch(e) {}
    return value;
  }
  function __ecanRowName(row){
    if(!row||!row.querySelector) return '';
    var nick=row.querySelector('[data-qa-id="qa-conversation-nickname"]');
    if(nick){var nv=(nick.textContent||'').trim(); if(nv) return __ecanRowNameTag('data_qa_id_nickname', nv);}
    var line=row.querySelector('[class*="nameLine"]');
    if(line){var lt=(line.getAttribute('title')||'').trim(); if(lt) return __ecanRowNameTag('name_line_title', lt);
      var nc=line.querySelector('[class*="NameContent"]'); if(nc){var ncv=(nc.textContent||'').trim(); if(ncv) return __ecanRowNameTag('name_line_content', ncv);}}
    var nc2=row.querySelector('[class*="NameContent"]'); if(nc2){var v=(nc2.textContent||'').trim(); if(v) return __ecanRowNameTag('name_content', v);}
    // ws110: broad fallback for selector drift — any data-qa-id mentioning
    // nickname/name, or a short title= that isn't a numeric preview/time.
    var alt=row.querySelector('[data-qa-id*="nickname" i],[data-qa-id*="name" i]');
    if(alt){var av=(alt.getAttribute('title')||alt.textContent||'').trim(); if(av&&av.length<=24) return __ecanRowNameTag('ws110_fuzzy_qa_id', av);}
    // ws183: iterate ALL titled descendants — the 重复来访 revisit-row variant's
    // FIRST [title] is the unread badge ('1'); the real name is a later one.
    // Skip badge counts and time-ago strings.
    // NOTE: this is the closest thing here to SEMANTIC targeting — it finds the
    // name by what it LOOKS like to a human (short, not a number, not a time)
    // rather than by where it sits in the DOM. Watch this counter.
    var titledAll=row.querySelectorAll('[title]');
    for(var t=0;t<titledAll.length&&t<6;t++){
      var tv=(titledAll[t].getAttribute('title')||'').trim();
      if(tv&&tv.length<=24&&!/^[\d:\s]+$/.test(tv)&&!/^\d+\s*(分钟|小时|秒|天)/.test(tv)) return __ecanRowNameTag('ws183_titled_scan', tv);
    }
    // legacy hashed classes last (older layouts).
    var wrap=row.querySelector('.MP1bk3ccfHC9V2SnPCGD');
    if(wrap){var wt=(wrap.getAttribute('title')||'').trim(); if(wt) return __ecanRowNameTag('legacy_hashed_wrap', wt);}
    var span=row.querySelector('.Jv6FtqUv5VoYARd2pp4y');
    if(span){var s=(span.textContent||'').trim(); if(s) return __ecanRowNameTag('legacy_hashed_span', s);}
    return __ecanRowNameTag('unresolved', '');
  }
"""


# Drains the page-side tally built by ROW_NAME_JS. Appended to a scan snippet
# that already ran __ecanRowName over the rows, so the counts cost no extra DOM
# work. Returns {} and resets, so each scan reports only its own rows.
ROW_NAME_TALLY_DRAIN_JS = r"""
  (function(){
    try {
      var t = window.__ecanRowNameTally || {};
      window.__ecanRowNameTally = {};
      return t;
    } catch(e) { return {}; }
  })()
"""


# ── what the sidebar is BUILT from ─────────────────────────────────────────
#
# The tally above says which parser won. This says what the page is made of --
# and the difference matters, because the tally only moves once a parser has
# already started failing, whereas this moves the moment the site ships the
# change.
#
# Every entry in `anchors` is a DOM feature one of the branches in
# ROW_NAME_JS (or the preview/badge readers) depends on. When Feige redeployed
# in June the hashed wrappers vanished; in September `data-qa-id` stopped
# appearing on rebuilt frames. Both would show here as an anchor going 0.
#
# Deliberately NO text and NO hashed class tokens:
#   - text is customer data, and this is kept for years;
#   - hashed tokens rotate on every Feige deploy, so recording them would
#     report a change every time they ship anything, which is noise. The
#     anchor counts already say whether a rotation actually broke a parser,
#     which is the part worth a permanent record.
SIDEBAR_SHAPE_JS = r"""
  function __ecanSidebarShape(rows, extraAnchors){
    // `extraAnchors` are the selectors the DOM monitor is CONFIGURED with,
    // injected at call time. They matter because they live in skill config a
    // user can edit: a hand-written list here cannot know about them, and goes
    // stale the moment someone changes one in the skill editor. This is how the
    // watch stays tied to what the system actually depends on rather than to
    // what somebody remembered to type.
    var anchors = {
      'data_qa_id_nickname': '[data-qa-id="qa-conversation-nickname"]',
      'qa_id_fuzzy_name':    '[data-qa-id*="nickname" i],[data-qa-id*="name" i]',
      'name_line':           '[class*="nameLine"]',
      'name_content':        '[class*="NameContent"]',
      'titled_descendant':   '[title]',
      'legacy_hashed_wrap':  '.MP1bk3ccfHC9V2SnPCGD',
      'legacy_hashed_span':  '.Jv6FtqUv5VoYARd2pp4y',
      'preview_msg_content': '[class*="msgContent"]',
      'badge_count':         '[class*="badge-count"]',
      'badge_sup':           'sup',
      'user_label':          '[class*="userLabel"]',
      'card_tag':            '[class*="cardTag"]'
    };
    // Depth matters, not just presence. ROW_NAME_JS uses querySelector
    // throughout and does not care how deep an anchor sits -- but
    // ROW_PREVIEW_FALLBACK_JS walks leaf nodes and compares parentElement, so
    // it DOES. A site that re-nests without renaming anything would break the
    // preview reader while a presence-only fingerprint stayed silent, which is
    // exactly the ws189 failure. So the depth of each anchor below the row is
    // part of what we watch.
    //
    // The MINIMUM depth across sampled rows is what travels: row variants
    // legitimately differ (a tagged row nests one level deeper than a plain
    // one), and the minimum is stable as long as any row still has the shallow
    // form. It moves when the site inserts a wrapper above them all.
    function __ecanDepth(el, row){
      var d = 0, p = el;
      while (p && p !== row && d < 30) { p = p.parentElement; d++; }
      return p === row ? d : -1;
    }
    try {
      if (extraAnchors) {
        for (var ek in extraAnchors) {
          if (!extraAnchors.hasOwnProperty(ek)) continue;
          var esel = extraAnchors[ek];
          // Never shadow a built-in: a configured selector that happens to
          // share a name must not silently replace the one we reason about.
          if (typeof esel === 'string' && esel && !anchors['cfg:' + ek]) {
            anchors['cfg:' + ek] = esel;
          }
        }
      }
    } catch(e) {}
    var present = {}, depths = {}, attrs = {}, tags = {}, plainClasses = {};
    var hashed = 0;
    // Per-token row counts, for the build marker below.
    var hashedRows = {};
    // Two flavours of build-generated class name, and BOTH must be recognised
    // or the structural record fills with phantom changes on every deploy:
    //
    //   MP1bk3ccfHC9V2SnPCGD   fully opaque (the pre-June scheme)
    //   msgContent-JqEWJs      semantic prefix + build hash (the June scheme)
    //
    // The prefix of the second IS structure and must survive a rotation; only
    // the suffix is volatile. Recording the whole token as a plain class -- the
    // original bug here -- made a routine redeploy look like a redesign.
    var opaqueRe = /^[A-Za-z0-9_]{16,}$/;
    var prefixHashRe = /^([A-Za-z][A-Za-z0-9_]*)-([A-Za-z0-9_]{5,})$/;
    function classifyToken(tok, seenThisRow){
      var m = prefixHashRe.exec(tok);
      if (m && /[A-Z0-9]/.test(m[2])) {
        plainClasses[m[1].slice(0, 60)] = 1;      // the durable half
        noteHashed(tok, seenThisRow);             // identifies the build
        return;
      }
      if (opaqueRe.test(tok) && /[A-Z]/.test(tok) && /\d/.test(tok)) {
        noteHashed(tok, seenThisRow);
        return;
      }
      plainClasses[tok.slice(0, 60)] = 1;
    }
    function noteHashed(tok, seenThisRow){
      hashed++;
      // Count each token ONCE per row: a token repeated down a row must not
      // out-vote one that appears on every row.
      if (seenThisRow[tok] !== 1) {
        seenThisRow[tok] = 1;
        hashedRows[tok] = (hashedRows[tok] || 0) + 1;
      }
    }
    var list = rows || [];
    for (var i = 0; i < list.length && i < 40; i++) {
      var row = list[i];
      if (!row || !row.querySelector) continue;
      var seenThisRow = {};
      for (var key in anchors) {
        if (!anchors.hasOwnProperty(key)) continue;
        try {
          var hit = row.querySelector(anchors[key]);
          if (!hit) continue;
          present[key] = (present[key]||0) + 1;
          var d = __ecanDepth(hit, row);
          if (d > 0 && (depths[key] === undefined || d < depths[key])) {
            depths[key] = d;
          }
        } catch(e) {}
      }
      try {
        // The row's OWN attributes and classes matter as much as its
        // descendants': data-qa-id="qa-conversation-chat-item" lives THERE, and
        // it is the selector the whole scan depends on. querySelectorAll('*')
        // returns descendants only, so the row was invisible to itself -- a
        // rename of the row's own id would have gone unrecorded.
        var all = row.querySelectorAll('*');
        var nodes = [row];
        for (var q = 0; q < all.length && q < 120; q++) nodes.push(all[q]);
        for (var j = 0; j < nodes.length; j++) {
          var el = nodes[j];
          tags[String(el.tagName||'').toLowerCase()] = 1;
          var at = el.attributes || [];
          for (var a = 0; a < at.length && a < 16; a++) {
            var an = String(at[a].name||'');
            // Attribute NAMES are structure. Values can be anything, so no
            // value is read here -- except data-qa-id, whose value is a
            // stable machine identifier and is the thing that drifted.
            attrs[an] = 1;
            if (an === 'data-qa-id') {
              var qv = String(at[a].value||'').slice(0, 60);
              if (qv) attrs['data-qa-id=' + qv] = 1;
            }
          }
          var cls = String(el.className && el.className.baseVal !== undefined
                           ? el.className.baseVal : (el.className||''));
          var toks = cls.split(/\s+/);
          for (var c = 0; c < toks.length && c < 16; c++) {
            if (toks[c]) classifyToken(toks[c], seenThisRow);
          }
        }
      } catch(e) {}
    }
    function keys(o){ var k=[]; for (var x in o) if (o.hasOwnProperty(x)) k.push(x); return k.sort(); }

    // ── the deploy marker ──────────────────────────────────────────────
    // Build hashes rotate every time the site ships, whether or not anything
    // structural moved. That makes them useless as a CHANGE signal (they would
    // cry wolf on every routine deploy) but exactly right as a DEPLOY signal:
    // three years of it is a calendar of when this site ships.
    //
    // Only tokens carried by at least half the sampled rows count, so which
    // rows happened to be scrolled into view cannot move the marker. The
    // tokens are reduced to one 32-bit digest: enough to tell "different
    // build" from "same build", and not enough to reconstruct a selector.
    var rowsSeen = Math.min(list.length, 40);
    var stable = [];
    for (var tok2 in hashedRows) {
      if (hashedRows.hasOwnProperty(tok2) && hashedRows[tok2] * 2 >= rowsSeen) {
        stable.push(tok2);
      }
    }
    stable.sort();
    var digest = 5381;
    var joined = stable.join('|');
    for (var d = 0; d < joined.length; d++) {
      digest = ((digest * 33) ^ joined.charCodeAt(d)) >>> 0;
    }

    return {
      rows_sampled: rowsSeen,
      build_marker: stable.length
        ? { digest: digest.toString(16), stable_token_count: stable.length }
        : null,
      anchors_present: keys(present),
      anchor_depths: depths,
      anchors_missing: keys(anchors).filter(function(k){ return !present[k]; }),
      attributes: keys(attrs),
      tags: keys(tags),
      plain_classes: keys(plainClasses),
      // Per row, not absolute: how many rows a scan happened to have scrolled
      // into view must not move the fingerprint.
      hashed_classes_per_row: rowsSeen === 0 ? 0
        : Math.round(hashed / rowsSeen)
    };
  }
"""

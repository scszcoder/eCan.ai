# Feige Cold-Start Post-Mortem

**Status: SOLVED** — milestone tag `feige-coldstart-solved` (= `ws185`, commit `a40a9fa08`, 2026-07-26).
Validated by 10+ manual 1-vs-3 cold-start runs on the customer machine, 2026-07-26/27.

"Cold start" = the first message from a customer whose conversation is not currently
open/claimed by our seat — a fresh visitor, a 重复来访 re-visit after the server closed the
session (~15 min idle), or the first burst after an app (re)start. For ~2 months this was the
dominant loss/latency mode: replies took 40s–16min, arrived for the wrong question, or were
silently lost. Companion doc: `FEIGE_COLDSTART_DETECTION.md` (the ws167 dormant/live state
machine).

---

## 1. What the problem actually was (four independent layers)

The single symptom 卡死/回复慢 decomposed into **four separate mechanisms**, discovered in
roughly this order, each masking the next:

| # | Layer | Mechanism | Proof run |
|---|-------|-----------|-----------|
| 1 | **Server-side withhold** | An unassigned/dormant conversation gets NO WS pushes in either direction and no sidebar row; sends into it are accepted-but-ignored. Un-gated by the customer's *next* message (2s!), or eventual auto-assign (observed 66s … 29min). Frame bytes are necessary but not sufficient — the conversation must be OPEN/claimed (ws137: 0/27 first-contact raw sends confirmed). | 2026-07-18 (66s quantified); 2026-07-25 (16min, 5h50m); 2026-07-17 read-side |
| 2 | **Sidebar row invisible to us** | The 重复来访 revisit-row variant renders NO `data-qa-id` descendants; the name lived in the *second* `[title]` attribute but the parser stopped at the first (the numeric unread badge). `rows=0 total=1` for 67 straight scans → backstop had nothing to route. | 2026-07-26 15:35 (packet) |
| 3 | **Thread paint lag** | On a cold reopen, Feige lazily backfills the thread DOM: the fresh message isn't scrapeable for **25–44s**. Every DOM-based binder/scraper starved; scrape-latest returned stale bubbles (wrong-question answers); ws177 cmid-join attributed 0. | 2026-07-26 17:51 (measured per-message) |
| 4 | **Our own decoy dispatches** | A nameless card arrives as synthetic `card:<talk>` identity → dispatched to QA → its reply is undeliverable (no such sidebar row; `Session not found` ×9 in one run) → the delivery attempts' resolve-waits ran **inside the global typing lock** (8s each), deferring every named enrich behind 15s backstop ticks. | 2026-07-25, 2026-07-26 17:51 |

## 2. What eventually solved it (the winning combination)

No single fix. The final stack, in causal order of a cold message's life:

1. **ws108/ws168/ws166** — the missed-msg backstop: scan sidebar every 5s, route CONNECT-BANNER
   (小店接入) rows through enrichment; startup recovery for rows left over from a dead run;
   bootstrap the dispatch slot even from a quiet start. *This was always the safety net; the
   later fixes were about why it kept getting starved.*
2. **ws183** (`f1e91b21b`) — parse the revisit-row variant: iterate ALL `[title]` descendants,
   skip badge counts and time-ago strings. **Layer-2 killer** — without a parsed name, nothing
   downstream ever fires. One 11-line JS fix ended the "row visible to humans, invisible to
   the app" class.
3. **ws184** (`b6271deff`) — stop the decoys, join the content: park a nameless `card:<talk>`
   WS dispatch up to 12s; when the talk resolves to a real name, dispatch the *WS-carried card
   content* under the real identity — **no DOM paint dependency** (layer-3/4 killer). Plus
   click-bind: when we click a named row, the page's own read-ack (carrying the conversation
   id) binds talk→name within ~1s.
4. **ws185** (`a40a9fa08`) — click-bind hardening after it mis-routed a reply cross-customer:
   wire-echo guard (ignore page acks for convs we just wire-sent into), 8s different-row
   quiet-guard, and **identity-only binding** (a correlational bind may never write the
   name→talk wire-routing map — wrong binds degrade to the safe DOM-by-name lane).
5. **Standing correctness guards that earned their keep** (validated repeatedly in the final
   runs): ws172 settle-hold (don't dispatch a stale bubble on a reopen's first look — blocked a
   would-be duplicate answer after a relaunch), ws173 card-row ambiguity guard (refused two
   mis-deliveries), ws177 cmid-join + ws127/130 uid-bridge (deterministic binders), ws070
   sticky identity (one QA session per human).

**Layer 1 (server withhold) is NOT client-fixable and remains the latency floor** for a truly
dormant conversation (66s+ when the customer doesn't follow up). Mitigation shipped: the row
does eventually surface and the backstop now reliably catches it (ws183). Attack paths for
later: ws182's dormant read-probe phase 2 (phase 1's three JSON endpoints were the wrong
scope — they can't even see active conversations), the `can_start_conversation → canStart:true`
sibling call (主动联系 flow = the suspected claim API), and the captured row-click side-channel
(23 endpoints + 2 binary WS sent-frames, still to be decoded).

## 3. Dead ends and why they died (don't re-walk these)

- **First-contact raw frames** (ws028/ws131/ws136-137): byte-perfect frames into an unopened
  conversation are silently ignored (0/27). The template was never the whole story — reply #1
  via DOM works because the *row click opens/claims* the conversation.
- **Presume-delivered on timeout** (`WS_FC_PRESUME`): masked 40-min silences. Never presume
  delivery into a conversation without an observed echo/bubble.
- **Phase-1 dormant probe endpoints** (getConversationSummary / getCSReceptionInServiceAssist /
  can_start_conversation as replayed): returned empty even for ACTIVE conversations → wrong
  scope/params, retired as detection candidates.
- **Lean-baseline A/B** (ws125): stripping the pipeline did not restore ws095-era latency —
  the regression was elsewhere (event-loop starvation, later the ws175 lock deadlock).
- **Correlational click-bind with routing power** (ws184 v1): one page ack triggered by our
  own wire-delivered placeholder mis-bound a conversation and wire-routed one customer's reply
  into another's thread. Correlation may inform identity, never wire routing.

## 4. What to monitor (the health dashboard for this area)

Run `feige_log_health.py` (memory dir) on every run log; read **EVENT-LOOP HEALTH first**.
Key indicators, with their meaning:

| Signal | Healthy | Alarm means |
|--------|---------|-------------|
| `[SESSION] build=` first line | matches the build you think you shipped | stale install/shortcut — the run is invalid (burned us 2×) |
| `ws108 backstop scan rows=N total=M` | rows == total | `rows < total` = a row variant the parser can't read (layer 2 back) — the ws178 NAMELESS-ROW DUMP fires with the DOM evidence to fix it |
| `card->synthetic name` vs `attributed to real name` | attributions > 0 when cards flow | binders (click-bind/cmid/uid) not resolving — decoys will revive at park expiry |
| `ws184 park resolved` vs `park expired` | mostly resolved | expiries mean 12s wasted per card + decoy revival |
| `Session not found` / `delivery_failed` | 0 | delivery targeting an identity with no row (pre-ws177 class) |
| `[FEIGE-WS-FC-CONFIRM] talk=` | talk's owner == the dispatched customer | **cross-customer mis-delivery** (the ws185 class) — check every new binder against this |
| `[FEIGE-LEDGER] … presume/typing eval in flight` | rare | delivery verified only by presumption — audit the thread |
| wscap last-write time | advancing all run | capture died (ws120/ws181 deadlock class) — all WS evidence after this moment is missing, do NOT conclude "no frames arrived" |
| `pend-event timeouts` during dispatch | 0 | QA turn swallowed (resume-swallow bug, still open) |
| placeholder `pool saturated` | 0-1 | 过渡句 landing late/into monitor tab |
| RSS growth | ~30-45MB/min known leak, partially reclaims | not object growth (GC census flat) — native buffers; unresolved, tracked separately |

## 5. Logging & analysis techniques that actually cracked it

**Logging that paid for itself:**
- **Evidence-dump-on-failure** (ws178 NAMELESS-ROW DUMP, ws170 CARD-DOM-DUMP): when a parser
  returns nothing, dump the raw structure (classes, data-ids, titles, text) rate-limited.
  ws183 was written directly from a dump, zero guessing. This beat every "add more selectors
  and hope" iteration.
- **Ledger lines with full identity tuples** (`[FEIGE-LEDGER]` with customer / talk / msg_id /
  response_preview / stage): made the cross-customer mis-delivery provable in minutes —
  `FC-CONFIRM talk=X` + `RAW-DIAG cust=Y` on adjacent lines was the smoking gun.
- **Server timestamps in dispatch lines** (`ts_ms=`): separates *when the customer sent* from
  *when the server pushed* from *when we saw it* — this is how the withhold was measured
  (2s push after 2nd message vs 16min silence after 1st).
- **Counter pairs that expose non-firing fixes** (`name_synthetic` vs `name_resolved`,
  routed/skipped with reasons): a shipped fix that logs nothing is indistinguishable from a
  missing one — "attributed: 0" is what exposed the paint-lag starvation of cmid-join.
- **Env dump at startup** (`[FEIGE-ENV]`): every run's flag set is in the log — no guessing
  what configuration a customer run used.
- **Capture integrity as a first-class concern**: the ws181 deadlock (async body fetch inline
  on the CDP read loop — the ws120 lesson re-introduced) silently killed wscap at the *first
  card* in 3/3 runs, i.e., exactly at the interesting moment. Absence of evidence was
  evidence of a broken recorder. Any capture hook must be detached from the read loop.

**Analysis techniques that worked:**
- **Verify the build banner before analyzing anything.** Two full runs were spent debugging a
  binary that contained none of the fixes under test.
- **Copy `eCan.log` aside before any relaunch** — relaunch truncates it (destroyed the
  evidence for two incidents).
- **Event-loop health first**: a wedged/starved loop masquerades as every Feige bug.
- **Sidebar-scan histograms as ground truth**: `grep 'backstop scan' | uniq` on
  `names=[...]`/`rows=` gives a per-5s timeline of what the app *could* see — this proved the
  server withhold (row absent for 16min while scans ran) and the parser blindness
  (`rows=0 total=1` × 67).
- **Payload length as a fingerprint**: `len=16` matched 您好，在的，请问有什么可以帮您？
  character-for-character — identified *which* text went down *which* wire without frame dumps.
- **Minute-histogram of a customer's mentions** (`grep cust | cut -c1-16 | uniq -c`): shows
  presence/absence windows instantly (packet: zero mentions for 5h50m).
- **Per-symptom fresh trace, not pattern-matching to the last bug.** The same user-word
  (卡死/回复慢) had ≥6 distinct root causes across runs: process death, app-not-running,
  parser blindness, server withhold, typing-lock deferral, mis-bind. Each verdict above was
  wrong at least once before the evidence settled it — including this analyst's own premature
  "QA slots exhausted" and "settle-hold false positive" theories (both disproven by deeper
  digging in the same log).
- **When a fix ships, look for its markers in the next run** — and when a marker is absent,
  determine whether the code didn't run (build), didn't trigger (conditions), or triggered
  and was starved (paint lag). Three different follow-ups.

## 6. Design lessons (carry into ALL future Feige work)

1. **Prefer data you already hold over data you must scrape.** The WS frame carried the card
   content 30+ seconds before the DOM could render it. The ws184 pivot — "join the identity to
   the content we already have" instead of "wait for the DOM" — is the template for future
   latency work (and for response-quality: the product-detail JSON we already capture).
2. **Deterministic binders may route; correlational binders may only label.** cmid/uid binds
   (globally-unique keys) get wire routing; time-correlation binds get identity only, so a
   wrong guess degrades to the guarded DOM-by-name lane instead of mis-delivering.
3. **Never hold the global typing lock across a wait.** Every multi-second sleep/retry inside
   it (ws031, ws141, ws176) directly serialized all customers' latency.
4. **Everything env-gated with a kill switch, defaults on, one ws-number per commit, tag it.**
   Bisection across customer runs was only possible because of this discipline.
5. **The event loop is sacred**: no sync locks (ws175), no inline awaited CDP calls (ws120/
   ws181), no zlib (ws087/088) on the CDP/handler loops.

## 7. Open items adjacent to this work

- **Server withhold floor**: dormant probe phase 2 / claim-API hunt (`can_start_conversation`
  sibling; decode the 2 binary sent-frames from the 15:39 manual-click capture).
- **pend_event resume-swallow** (QA task resumed from stale checkpoint drops the customer
  message) — general-core runner bug, still open.
- **Memory growth** ~30-45MB/min, not Python objects (GC census flat), partially reclaims.
- **ws141 resolve-wait still sleeps inside the typing lock** on the (now-rare) synthetic
  fallback path.
- **Backlog recovery answers only the newest unanswered question** (有包邮吗 was silently
  skipped after an outage; only the later 退货 question was answered).

---

## Addendum 2026-09-06 — resurfaced (ws193): the sidebar name parser drifted

**Not a regression of the July stack** (all of it shipped in 96z; the
`lq_dev_multi-final` squash/rebase only changed commit hashes). A LATER Feige
sidebar redesign broke sidebar **name** extraction — but only in two of the
three parsers.

Cold-start recovery for a TEXT message needs two DOM parsers to read the
redesigned sidebar: the ws108 **scan** (finds/routes the row) and the
**click-to-open + active-verify** (opens the thread so the real bubble can be
scraped). The redesign-resilient reader (ws110 broad fallbacks + ws183
all-`[title]` iteration) lived only in the scan (`front_desk.py`); the
click-open and verify readers in `dom_assets.py` still used the mt062-era hashed
selectors. The redesign killed those → on 96z (cust 'sc') the scan saw
`names=['sc',...]` but the click reader returned `seen_names=[]`, so the thread
never opened, "有人吗" was never scraped, the preview stayed the store-assignment
banner, and PreDispatch deferred it as `system_message` forever → stuck →
转人工 → platform long-no-reply warning.

Why this slips past layers 1-4: it's a NEW instance of the selector-drift class
(layer 2), on the sibling parser July+ws189 didn't unify, and it only bites a
**text** cold start (cards ride ws184's WS path; text has no WS frame when
withheld, so DOM click-open-and-scrape is the sole recovery).

**Fix (ws193, commit 6da0d3e09):** one shared `__ecanRowName` reader in
`sidebar_preview_js.ROW_NAME_JS`, used by the click-open and active-verify JS
(delegate first, mt062 selectors kept as secondary) — so all three parsers
can't drift apart again. Plus a `[ws193 NAME-PARSER DRIFT]` dump (rows present,
zero names) so the next redesign is fixed from evidence, not a stuck customer.

**Lesson added to the dashboard:** `scrape-latest-customer: sidebar row not
found … seen_names=[]` while the ws108 scan reports non-empty `names=[...]` = a
parser has drifted off the current frame. The two readers must agree; when they
disagree, the newer-frame one (scan) is right.

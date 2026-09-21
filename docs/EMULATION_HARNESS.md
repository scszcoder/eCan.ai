# The Feige emulation harness

A local fake of the Feige (飞鸽) customer-service chat panel, with a metrics
oracle. Built 2026-04 → 2026-06 to reproduce production bugs that only appeared
under load, and used to diagnose the mt070 detection blackout.

**Why this document exists:** the harness itself lives under `customer_logs/`,
which is git-ignored (`.gitignore:11`). It is in no branch, on no backup, on
exactly one working copy. This file is the tracked record of what it is and how
to run it, so the knowledge survives even if the directory does not. Rescuing
the code into tracked space is step 0 of the plan in
`SELF_HEALING_ROADMAP.md` §15.

---

## 1. Why it matters now

It was built for load bugs, but it turns out to answer the question the
self-healing work is stuck on: **how do we know the detector works, without
waiting for the site to change?**

It has an **oracle**. The emulator knows how many queries it sent
(`total_queries`) and how many were answered (`answered_queries`). That makes
two things measurable that production cannot give us:

- **Labelled positives** — flip the fake site's layout and assert the
  fingerprint fires. Repeatable, thousands of times, with novel layouts rather
  than only the two redesigns we happen to have lived through.
- **Labelled silent failures** — `answered < sent` with nothing detected is
  *precisely* the dangerous case (a chat arrives and we never see it), and here
  it is directly countable instead of arriving as a customer complaint.

This is strictly better than back-dating the June/September redesigns out of
git history, which was the fallback plan.

## 2. Status and risk

| | |
|---|---|
| Location | `customer_logs/emulation/` |
| Tracked? | **No.** `.gitignore:11` ignores `/customer_logs/` |
| Exists in any branch? | No — `git ls-files customer_logs` is empty |
| Last touched | 2026-06-03 (the harness), 2026-08-13 (`check_monitor.ps1`) |
| Verified running | 2026-09-19 — page HTTP 200, report API responding |
| Dependencies | stdlib only (server, measure, analyzer); vanilla JS/CSS, no build |

`check_monitor.ps1` sits at the repo **root** and *is* tracked (commit
`e6f32b1c1`) — it is the only part of the setup currently in version control.

## 3. Inventory

All under `customer_logs/emulation/` unless noted.

| Path | Role |
|---|---|
| `server.py` | Entry point: stdlib threading HTTP server **and** the metrics oracle |
| `static/index.html` | The fake chat panel (sidebar / thread / control panes) |
| `static/app.js` | All emulation logic: rows, threads, chaos injectors, flood driver |
| `static/styles.css`, `static/avatars/*.svg` | Presentation |
| `sample0.png` | **Real screenshot from the live site** — see §7 before copying |
| `emulation_config.json` | Persisted chaos/fault config (deep-merged) |
| `measure.py` | Manual measurement driver — the preferred path |
| `run_flood_rounds.ps1` | Automated multi-round controller (fragile, see §6) |
| `rounds.sample.json` | Round matrix, including the blackout A/B pair |
| `skill_patcher.py` | Patches `domCheckIntervalMs` / `cdpFilterExpr` in skill JSON, with backup/restore |
| `analyze_detection_lag.py` | Joins emulation events with `runlogs/eCan.log` → detection-lag + HB-starvation report |
| `cdp_fake_harness.py`, `cdp_use_harness.py` | Offline CDP harnesses (2026-05, most likely to have drifted) |
| `HARNESS_README.md` | Primary doc: metrics, prerequisites, round schema, mt070 repro |
| `CDP_CHAOS_USAGE.md` | The chaos panel and every knob default |
| `given chatThreadDom.txt in customer.txt` | Captured real-site DOM reference (structure only — verified no CJK) |
| `results/` | 35 result JSONs + `summary.csv`, incl. the blackout A/B baselines |
| `../../check_monitor.ps1` | **Tracked.** Pre-flight: is the EventMonitor actually live? |

Also referenced from tracked code: `agent/ec_skills/build_node.py:1063`
(`_maybe_inject_llm_test_fault`) and `agent/ec_skills/rag/local_rag_mcp.py:16`
(`_maybe_inject_rag_test_fault`), both gated on `ECAN_EMULATION_TEST_FLAGS=1`.
`docs/CONFIGURATION.md:433-498` holds the mt0XX → repro map.

## 4. Running it

Three steps, not two. Skipping the middle one is how you get an all-zeros run
and misread it as a detection failure.

```bash
# 1. Debug Chrome, existing-chrome mode
chrome.exe --remote-debugging-port=9228 --user-data-dir="C:\chrome_data" \
           --disable-features=SharedStorage,InterestCohort

# 2. The fake site
python customer_logs/emulation/server.py          # 127.0.0.1:9876
# page: http://127.0.0.1:9876/im.jinritemai.com/
```

The URL path deliberately contains `im.jinritemai.com` so eCan's EventMonitor
`page_url_patterns` matches with no hosts-file hack. `/` 302s there.

```powershell
# 3. CONFIRM THE MONITOR IS LIVE — do not skip
.\check_monitor.ps1                # → MONITOR LIVE / STARTING / BUILD FAILED / NOT UP
```

```bash
# 4. Measure
python customer_logs/emulation/measure.py --label clean              # A/B reference
python customer_logs/emulation/measure.py --label blackout --stall   # the mt070 repro
```

Defaults: `--n 6 --join-spread 120 --followup-rounds 8
--followup-interval-ms 30000 --wait 360 --emu-port 9876`. It POSTs config →
`run/start` → `flood` → polls `/api/emulation/report` every 30 s → `run/stop` →
runs `analyze_detection_lag.py`.

Ports: emulation `9876`, CDP `9228`.

### The lesson worth stealing

`check_monitor.ps1`'s own doc block:

> The all-zeros measure runs (answered=0/detected=0/HB count=0) are ALWAYS one
> of BUILD FAILED or MONITOR NOT UP.

That is the **same ambiguity as the production silent-failure case, one level
up**: zero detections cannot distinguish "nothing happened" from "we are blind"
from "the harness never started". It was solved here with an explicit liveness
gate rather than by inferring from an absence of events — which is exactly the
shape of the production fix (see `SELF_HEALING_ROADMAP.md` §11). Any detector
stress harness needs its own liveness gate, or a detector that fails silently
will score as a clean run.

## 5. What it simulates

**Sidebar rows — yes, and in the real shape.** `static/app.js` renders
`.scroller > .scroller_content > .list_items >
[data-qa-id="qa-conversation-chat-item"]` with hashed-looking class names
(`newNameContent-DfqCyb`, `msgContent-JqEWJs`, `conversationCard-ePRNJi`), so
eCan's real `cdpFilterExpr` selectors work against it unchanged. Also system
rows (智能客服 / 系统通知) and unread `<sup>` badges.

**Chat threads — yes.** Customer/agent bubbles, 图文 image mode, 商品卡片
product cards with structured fields, placeholder/greeting bubbles.

**WebSocket — no.** There is no WS server. Cross-tab state uses
`localStorage` + `BroadcastChannel` explicitly as a stand-in for Feige's real
WS push. See §6.

**Customers:** 3 fixed (A/B/C) plus synthetic `客户NN` on demand. Flood
defaults to 20, caps at 200.

**Chaos knobs** (runtime, via the page panels or `POST /api/emulation/config`):
`renderer.{stallEnabled,blockMs,intervalMs}`, `send.{blockClickMs,
delayAgentAppendMs,neverAppendAgent}`, `dom.{selectorDelayMs,extraMessageRows,
systemRows,churnEnabled}`, `focus.{churnEnabled,switchIntervalMs,
rerenderDuringSend}`, `harness.*`, `llmFault`, `ragFault`, `followUp`.

**Oracle metrics:** `answered_queries`, `placeholder_late` (no agent message
within 35 s), `duplicate_responses`, `placeholder_after_real`, plus
`analyze_detection_lag.py`'s `detection_lag_s.max`, `hb.starvation_windows`,
`hb.max_starvation_s`.

## 6. Gaps for detector stress testing

In the order they block us.

**a. DOM shape is hard-coded, not a knob.** The 2026-06-02 redesign was
hand-edited into `app.js` (9 sites). There is no `layout` key in
`emulation_config.json`. To stress a *change* detector we need to flip layouts
at runtime:

```
dom.layout = "mt062" | "redesign_2026_06" | "rebuild_2026_09" | "mutate:<seed>"
```

The mutation mode is the part archaeology cannot provide: drop an attribute,
rename classes, rewrap a container, change nesting depth — then measure
detection rate *per mutation class*. That yields the honest answer ("attribute
removal 100%, class rename 100%, pure re-nesting 0%") rather than a single
pass/fail.

**b. No WebSocket, so `ws_protocol_watch` cannot be exercised here.** It does
not need the emulator: `ws_reader.py` is self-contained and already replays
captured frames offline (`python ws_reader.py <capture>.jsonl`). Mutating
captured frames — drop `nickname`, rename it, empty it — gives labelled ws
positives far more cheaply than building a WS server.

**c. `run_flood_rounds.ps1` is the fragile piece.** It greps `runlogs/eCan.log`
for the literal marker `"EventMonitor] DOM monitor loop start"`, kills the
python tree, and needs a pre-existing running front-desk agent bound to
`customer_front_desk` plus `rt_chat_bot03..07` responders. `measure.py` exists
because that path "doesn't bind the Feige monitor" — the manual route was
already preferred in June. Prefer `measure.py`.

**d. `rounds.sample.json` hard-codes `settings.repoRoot` and `skillDir`** —
check against the current `my_skills/` layout before using it.

## 7. Rescuing it into version control (step 0)

Move the harness out of the ignored `customer_logs/` into tracked space
(`tools/emulation/`), leaving the captured customer logs behind.

`customer_logs/` is ignored *for a good reason* — it holds real customer
captures — so the move must not drag customer data into git. What was checked
on 2026-09-19:

| File | Finding | Action |
|---|---|---|
| `given chatThreadDom.txt in customer.txt` | no CJK at all — structure only | safe to track |
| `results/*.json`, `summary.csv` | synthetic ids (`S017`), no names | safe to track |
| `emulation_config.json`, `*.py`, `static/*` | config and code | safe to track |
| **`sample0.png`** | **real screenshot from the live site** | **do not track** — generate a placeholder; it only backs the 图文 bubbles |

`.claude/settings.local.json` already carries pre-approved permissions for
curling `:9876` and `node --check`-ing `static/app.js`, so reviving it needs no
new approvals.

## 8. Related

- `SELF_HEALING_ROADMAP.md` Part II — what the detector is, ground truth, the
  fleet loop, and where this harness sits in the sequence
- `docs/CONFIGURATION.md:398-498` — `ECAN_EMULATION_TEST_FLAGS` and the mt0XX
  local-repro map
- `customer_logs/emulation/HARNESS_README.md` — the original, untracked

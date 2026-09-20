# Non-stop Feige flood-test harness

Automated, repeatable load testing of the live eCan app against the Feige
emulation. Each **round** launches the real `python main.py`, auto-logs-in,
waits for the Feige monitors to come alive, floods the emulation with N
simultaneous customers for a fixed window, then tears everything down and
moves to the next round — varying app env vars, emulation chaos knobs, and
skill-config knobs between rounds.

The **emulation is the metrics oracle**: it sends every query and receives
every reply, so it computes the four target metrics exactly.

## Pieces

| File | Role |
|------|------|
| `run_flood_rounds.ps1` | Round-controller. Launch this. |
| `rounds.sample.json` | Round matrix (env / emulation / skill knobs per round). |
| `server.py` | Emulation server **+ metrics oracle** (run/start, flood, run/stop, report). |
| `static/app.js` | Emulation page. Emits `q_sent` / `agent_msg` events; polls for flood commands. |
| `skill_patcher.py` | Patches `domCheckIntervalMs` / `cdpFilterExpr` in the skill JSON, with backup/restore. |
| `results/` | Per-run `<run_id>.json` (metrics + raw events) and `summary.csv`. |

## The four metrics (written per run to `results/<run_id>.json`)

1. **answered_queries** — customer queries that got a real (non-placeholder) reply.
2. **placeholder_late** — queries where no agent message (placeholder *or* real)
   appeared within 35 s of the query; an intervening placeholder resets the 35 s.
3. **duplicate_responses** — real replies whose text repeats an earlier real reply
   to the *same* customer.
4. **placeholder_after_real** — placeholders that arrive *after* the customer's
   real answer (with no new query in between).

## One-time prerequisites

0. **Launch your debug Chrome first (existing-chrome mode).** The Feige skill
   uses `browser: existing chrome`, so the app *attaches* to a Chrome you start
   yourself — the harness never starts or kills it (`killChrome: false`, the
   default). Start it before running the harness:
   ```
   chrome.exe --remote-debugging-port=9228 --user-data-dir="C:\chrome_data" --disable-features=SharedStorage,InterestCohort
   ```
   On teardown the harness kills only the `python` app and **closes the emulation
   tabs** it opened — your Chrome and other tabs stay open. (If instead you use
   `browser: new chromium` so the app spawns its own Chrome, set
   `killChrome: true` and the harness will kill that one.)
1. **Auto-login.** The app must have the `ECAN_AUTOLOGIN` hook (added to
   `gui/LoginoutGUI.py` + `main.py`). Log in once normally with *remember me* so
   saved credentials exist (keyring). The harness sets `ECAN_AUTOLOGIN=1`;
   `ECAN_AUTOLOGIN_USER` / `ECAN_AUTOLOGIN_PASS` are optional fallbacks.
1b. **The Feige front-desk agent must be RUNNING.** This is the #1 cause of a
   dead run. The app only **auto-resumes** agents that were already running when
   it last closed — it never *creates or starts* one. The sidebar `新消息`
   monitor (and therefore the typing-tab pool, and therefore everything) is
   started by a running front-desk task. So once, in the GUI:
   **start the front-desk agent** (bound to skill `customer_front_desk`) **and
   the responder agents** (`rt_chat_bot*`), confirm `runlogs/eCan.log` shows
   `EventMonitor … DOM monitor loop start` and that **6 typing tabs** open in
   Chrome, then exit cleanly so the running state persists. The harness's
   **pre-flight** (step 4b below) now fails fast with a diagnosis if the monitor
   never comes up, instead of flooding a dead app for the whole window.
2. **Feige tab → emulation (automatic).** There is no "monitored URL" field to
   set. The app keys the Feige tab off the **`im.jinritemai.com`** substring in
   any tab's URL and clones that tab to build its typing pool. The emulation URL
   `http://127.0.0.1:9876/im.jinritemai.com/` contains that substring, and the
   harness **seeds it automatically** (`seedFeigeTab: true`) by opening it in
   the eCan Chrome via the DevTools API (`PUT :9228/json/new?<url>`) once Chrome
   is up — before it waits for the monitor. Set `seedFeigeTab: false` only if you
   prefer to open the tab yourself.
3. **`skillDir`.** Set `settings.skillDir` (string *or* array) to every skill
   whose `domCheckIntervalMs` you want to vary. Two monitor roles:
   - `customer_front_desk` — the sidebar **`新消息`** detector (new-customer
     detection latency).
   - `rt_chat_bot03/04/05/06/07` + `rt_chat_bot` — the **`chat_message_added`**
     responders, one per tab (reply latency).

   The sample lists all 7. Confirm which responders your run actually starts via
   the `[BrowserAutomation] Parsed ... skill=rt_chat_botNN` lines in
   `runlogs/eCan.log`, and trim/extend the list to match.
4. Leave `readyMarkerCount` at **1**. Only monitors emit
   `[EventMonitor] DOM monitor loop started`, and the detector starts first;
   waiting for 1 is correct. Do **not** set it to the tab count — that risks a
   timeout. `settleSec` gives the responders time to come up after.

## Run

```powershell
powershell -ExecutionPolicy Bypass -File tools\emulation\run_flood_rounds.ps1 `
    -Config tools\emulation\rounds.sample.json
```

Single round for debugging: add `-OnlyRound 2`.

Per round the controller will:
1. restore the skill to pristine, then patch this round's `skill` knobs;
2. POST this round's `emulation` knobs to the server (deep-merged onto defaults);
3. set this round's `env` (+ `ECAN_AUTOLOGIN=1`), launch `python main.py`;
4. seed the emulation Feige tab, then **pre-flight**: tail `runlogs\eCan.log` for `readyMarker` (`EventMonitor … DOM monitor loop start`) × `readyMarkerCount`. If it never appears within `readyTimeoutSec`, print a diagnosis (front-desk task built? running? reached `start_monitors`?) and **SKIP the round** (no flood). On success, settle, then log the typing-pool tab count (`N/expected` opened);
5. `run/start` → `flood {n}` → wait `floodWaitSec` → `run/stop` (writes results);
6. kill the python tree and close the emulation tabs (existing-chrome mode — Chrome stays up; `killChrome: true` kills an app-spawned Chrome instead).

## Round config (`rounds.json`)

```jsonc
{
  "settings": {
    "repoRoot": "C:\\...\\eCan.ai",
    "skillDir": "my_skills/customer_front_desk_skill",  // or ["...","..."]
    "readyMarkerCount": 1,        // raise to #tabs (e.g. 6)
    "settleSec": 30, "floodN": 20, "floodWaitSec": 180,
    "cdpPort": 9228, "emuPort": 9876, "python": "python",
    "emulationTestFlags": false   // set true if any round uses llmFault/ragFault
  },
  "rounds": [
    {
      "name": "interval_250_clean",
      "env": { "ECAN_FRONTDESK_OOB_MIN_CUSTOMERS": "3" },  // any app env var
      "skill": {                                            // patched into skill JSON
        "interval": 250,                                    // domCheckIntervalMs
        "cdpRoot": ".list_items",                           // optional
        "cdpItem": "[data-qa-id='qa-conversation-chat-item']", // optional
        "cdpFields": { "customer_name": "[class*='NameContent']" } // optional
      },
      "emulation": {                                        // -> emulation_config.json
        "renderer": { "stallEnabled": false },
        "dom": { "churnEnabled": false },
        "focus": { "churnEnabled": false }
      },
      "floodN": 20
    }
  ]
}
```

`emulation` knob names mirror `emulation_config.json`
(`renderer` / `dom` / `focus` / `send` / `harness` / `llmFault` / `ragFault` / `followUp`).

## Results

- `results/<run_id>.json` — metrics, per-customer breakdown, and the raw event
  list (re-analysable offline).
- `results/summary.csv` — one row per run: the four metrics + totals.

The sample matrix is built to isolate the **mt059→mt065** question: it A/Bs
`domCheckIntervalMs` 250 vs 750 under a clean renderer and again under a
stalled/churning renderer, so the interval's effect can be separated from
renderer load.
```

## Reproducing the mt070 detection blackout (2026-06-03)

The customer's 1-to-6 live test (`customer_logs/eCan.log`, 15:45–15:56) went
**detection-blind for 100–184 s**: the `新消息` sidebar detector and the
per-customer bubble scrapes share one Chrome renderer, and under 6-customer load
a single `feige_scrape_bubble` `Runtime.evaluate` took **5–28 s** (it walks an
O(DOM) thread that grows over the test). That long synchronous eval holds V8's
single main thread, so the co-located detection poll's concurrent
`Runtime.evaluate` queues behind it and times out (6 s) → consecutive recycle
spiral → the customer's 174/176/188 s worst-case 已读/过渡句/回复. **It is
pre-detection blind time, not slow replies** (detection→reply stayed <92 s).

The `detection_blackout` round reproduces this locally via a **load-dependent
scrape stall** instead of the old fixed `renderer.blockMs`:

- `dom.scrapeStall` — when `enabled`, the page busy-waits inside the patched
  `querySelector(All)` **only for scrape-signature selectors** (the ones the
  eCan scraper uses, which run in the page main world via `Runtime.evaluate`).
  The wait scales with load and grows as threads accumulate:

  ```
  stall_ms = min(capMs, baseMs + perMsgMs·(total msgs across active convos)
                              + perConvoMs·(customers active in last 120s))
  ```

  Defaults `baseMs 120, perMsgMs 20, perConvoMs 500, capMs 30000` cross the 6 s
  detection-timeout cliff at ~7 min and climb to ~10 s by 11 min (see the
  curve in the round `_comment`). The page's own renders are excluded (a
  render-depth guard), so only eCan's CDP scrape pays the cost. Each charged
  stall logs `chaos.scrape_stall {ms, msgs, convos}` — **watch those `msgs`
  values in `runlogs/eCan.log` and set `perMsgMs ≈ target_ms / observed_msgs`
  to calibrate** if your reply cadence differs.

- Flood **ramp** knobs (per-round `"flood": { … }`, passed through to the page):
  - `joinSpreadSec` — stagger the N customers' first message across this window
    (concurrency ramps up like the real test).
  - `followUpRounds` / `followUpIntervalMs` — after joining, each customer keeps
    sending, so per-customer threads grow and the scrape stall climbs.
  - per-round `floodWaitSec` — lengthen the window to cover the whole ramp.

The matrix ships the scenario as an **A/B pair** (identical ramp/DOM/churn; the
only difference is `scrapeStall.enabled`), so run them back-to-back:

- **round 6 — `detection_blackout_clean`** (`scrapeStall` off): the baseline.
- **round 7 — `detection_blackout`** (`scrapeStall` on): the repro.

```powershell
# both rounds, clean first then the blackout (one invocation):
powershell -ExecutionPolicy Bypass -File tools\emulation\run_flood_rounds.ps1 `
    -Config tools\emulation\rounds.sample.json -OnlyRound 6
powershell -ExecutionPolicy Bypass -File tools\emulation\run_flood_rounds.ps1 `
    -Config tools\emulation\rounds.sample.json -OnlyRound 7
# (or omit -OnlyRound to run the whole matrix; the pair is the last two rounds.)
```

**What success looks like** (`results/<run>_detection.json`, written by
`analyze_detection_lag.py`):

| metric | clean (round 6) | blackout (round 7) |
|---|---|---|
| `detection_lag_s.max` | < ~35 s | **≫ 100 s** |
| `hb.starvation_windows` | 0 | **> 0** |
| `hb.max_starvation_s` | ~0 | **~100–180** |
| `high_lag_in_starvation` | 0 | **several** |
| `runlogs/eCan.log` | no spiral | `DOM check timed out … consecutive≥4` |

The clean baseline proves the ramp/churn alone don't cause lag; only the
load-dependent scrape stall does. That A/B is the proof the blackout is
shared-renderer scrape contention, and the regression test for any fix (e.g. a
dedicated detection tab should keep round 7's `max` as low as round 6 even with
`scrapeStall` on).

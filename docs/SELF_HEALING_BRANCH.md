# Branch guide: `feature/semantic-targeting-phase1`

19 commits, 368 tests, `master` untouched. This is the reviewer's map: what
each file is for, what actually runs, and how to check any of it yourself.

The plan behind it is `SELF_HEALING_ROADMAP.md` (Part I = the four-layer
targeting design, Part II = detection, ground truth and the fleet loop).

---

## 1. What the branch does

It makes a site change **detectable on the day it ships**, instead of days
later from a customer complaint, and it makes the install **say so** rather
than failing quietly.

It does *not* yet heal anything automatically. The healing layers (L2 resolver,
L3 learning) are built and tested but deliberately switched off and wired into
no site path — see §3.

Three questions the branch answers that could not be answered before:

| Question | Answered by |
|---|---|
| Did the site change? | the sidebar fingerprint + ws field watcher, against a shipped baseline |
| Did we fail a customer? | the site's own closure notices, matched to our conversation ledger |
| Does the detector actually work? | a stress harness driving real layouts and real frames |

---

## 2. The split (the rule every file here obeys)

**Platform code must not know any site.** Business specifics live in
`hooks/external/<site>/`. Every platform module on this branch has a test that
fails if a site name appears in it — that guard caught "Feige" in a docstring
twice while this was being written.

```
agent/ec_skills/browser_use_extension/          <- platform: vocabulary, storage, policy
agent/ec_skills/browser_use_extension/hooks/external/feige_chat/   <- one site's specifics
```

Platform owns *what a signal is*, *what a shape is*, *what a spending limit is*.
The bundle owns *which selectors*, *which phrases*, *which thresholds*.

---

## 3. What runs, and what does not

**On by default** — measurement and reporting only, no behaviour change to any
existing path:

- element-resolution counters (`element_targeting`)
- sidebar structural signature + deploy marker (`SIDEBAR_SHAPE_JS`)
- ws protocol field watcher (`ws_protocol_watch`)
- the site's distress notices (`signals`, `conversation_ledger`)
- the permanent journal (`drift_journal`) and the readiness dot
  (`degraded_state`)

**Off** — built, tested, and not reachable:

- **L2 resolver** (`element_resolver`): `resolver_enabled()` returns False
  unless `ECAN_ELEMENT_RESOLVER=1`, *and* nothing calls `resolve_element` from
  any site path.
- **L3 learning** (`learned_targets`): `best_for()` is called from no site
  path. The store records what it is told; nothing asks it for an answer yet.

This is deliberate sequencing: the spending limits and the measurement landed
*before* the thing that spends money is switched on.

---

## 4. New files

### Platform — detection and record

| File | Why it exists |
|---|---|
| `element_targeting.py` | The vocabulary (`TargetDescriptor`) plus per-strategy counters, so "which parser is carrying this element" is answerable. Also `detect_drift`, which fires when a strategy that was resolving everything resolves nothing. |
| `drift_journal.py` | The permanent record of site changes. Append-only, three-year floor, never rotated. Stores the **delta** (what moved), not a page dump, and reduces free text to a shape so a multi-year archive cannot accumulate customer data. |
| `site_signals.py` | The declared-signal vocabulary: four kinds (`distress` / `anchor` / `invariant` / `liveness`) and a severity scale. The registry is the truth — a signal that fires undeclared is reported as a gap, not invented. |
| `degraded_state.py` | Aggregates everything that knows something is wrong into one readiness level, so a broken install looks broken in its own UI. Amber while watched, red after two minutes. |

### Platform — healing (built, not switched on)

| File | Why it exists |
|---|---|
| `element_resolver.py` | L2: asks a model which candidate matches a descriptor, and returns an **index**, never a selector. Sends shape-only candidate descriptions by default, so page content does not travel. |
| `learned_targets.py` | L3: scores descriptors that worked, retires ones that stop. Refuses to learn a selector, refuses to learn a **fragile** descriptor, and banks retirement lifetimes by kind. |
| `resolver_guard.py` | Per-element and per-machine daily caps that survive a restart, backoff, and a circuit breaker that stops asking and says so loudly. Bounds what L2 can spend before L2 is enabled. |

### Bundle — `hooks/external/feige_chat/`

| File | Why it exists |
|---|---|
| `signals.py` | The site's declared signals: the three notice phrases, plus the two invariants that turn a closure notice into a verdict. Includes `notice_customer_uid`, the join between a notice and a conversation. |
| `conversation_ledger.py` | Long-window record of which conversations we saw and which we served, so "the site closed this for non-reply" becomes "and it was ours" or "and we never saw it". |
| `ws_protocol_watch.py` | Watches which named frame fields the backend still populates. Core keys are judged per window; optional ones are monotonic — with each key's measured frequency in the comments. |
| `baseline.py` / `baseline.json` | What this build expects the site to look like, so a fresh install detects drift on its first scan instead of adopting it as normal. |

### Surface

| File | Why it exists |
|---|---|
| `cli/drift/commands.py` | `ecan drift list / show / stats / shapes / export-baseline`. Read-only by construction — no delete, clear or prune command, with a test keeping it that way. |

### Harness

| File | Why it exists |
|---|---|
| `tools/emulation/**` | The Feige emulator, **rescued from the git-ignored `customer_logs/`** where it existed on one working copy and in no branch. `sample0.png` is a generated placeholder; the original was a real screenshot of the live site and is deliberately not tracked. |
| `tools/emulation/layouts.json` | Structural descriptions of the row layouts the site has actually shipped (mt062 legacy, the June redesign, the September rebuild). |
| `tools/emulation/shape_probe.js` | Runs the **real** fingerprint over those layouts in node. Nothing is reimplemented — a ported copy would measure the copy. |

---

## 5. Modified files, and why

| File | Change |
|---|---|
| `hooks/.../sidebar_preview_js.py` | Added `SIDEBAR_SHAPE_JS`: anchor presence, anchor **depth**, attribute and tag names, and a non-reversible deploy-marker digest. Depth is there because the preview reader compares `parentElement` and would otherwise break invisibly. |
| `hooks/.../site_tools.py` | The sidebar scan now carries the shape record back on its existing payload (no second CDP round trip) and reports it to the journal. |
| `hooks/.../ws_reader.py` | Stopped discarding the system-event channel — `continue # .8 may be a JSON system-event string; skip here`. Added a bounded recursive string walk, because the documented "field .8" location finds nothing in real captures. |
| `hooks/.../ws_observer.py` | Reads system events **before** parsing messages (a frame carrying only a closure notice has no message in it), and records every inbound conversation on the ledger. |
| `hooks/.../dispatch_state.py` | `note_talk_dispatched` also writes to the long-window ledger. Its own map is a 15-second duplicate guard that pops entries, so it cannot answer "did we ever serve this". |
| `agent/ec_tasks/runner.py` | Run-end reports: targeting counters, tripped signals, L2 spend, degraded refresh, descriptor-kind lifetimes. |
| `build_node.py`, `rag/local_rag_mcp.py` | Emulation fault injectors now prefer `tools/emulation/`, falling back to the old location. |
| `cli/main.py` | Registers the `drift` command group. |
| `gui_v2/.../ReadinessStrip.tsx` | A sixth readiness dot: targeting health. |
| `gui_v2/.../agentRuntimeStore.ts`, `i18n/*.json` | Types and labels for that dot. The locale files were edited **as text**: they contain duplicate keys, and a JSON round-trip silently deletes entries. |
| `.gitignore` | `drift_journal/`, `known_shapes.json`, `resolver_guard.json` — machine-local state, never committed. |

---

## 6. Expected behaviour

### On a healthy run

Nothing new in the log except periodic rollups and the run-end reports:

```
[element-targeting] feige_chat/sidebar_row_name: data_qa_id_nickname=412/412 ok, ...
[element-targeting] report (task=...): ...
```

No journal records, no readiness change. **Silence is the correct output** —
site changes are rare, which is why they are worth recording.

### When the site ships a change

```
[drift-journal] SITE CHANGE RECORDED feige_chat/sidebar_row (dom_shape_change):
  sidebar_row lost anchors_present: data_qa_id_nickname -> drift-2026.jsonl
```

One record per change per day. The deploy marker moves under its own key
(`site_deploy`) even when nothing structural changed, building a deploy
calendar over time.

### When we fail a customer

```
[site-signal] INCIDENT feige_chat/conversation_missed: the site closed a
  conversation for non-reply AND we have a record of seeing that customer's
  message — this one is ours | we saw the customer's message and never replied
```

The targeting dot on the Agents page goes amber, then red if it persists.

### When L2 is enabled and an element proves unresolvable

```
[resolver-guard] CIRCUIT OPEN feige_chat/sidebar_row_name: 5 resolutions in a
  row did not stick. Not calling the resolver for this element for 3600s.
  This element is BROKEN, not healing -- it needs a human.
```

---

## 7. How to run it

### Tests

```bash
# everything this branch added
python -m pytest tests/unit/test_element_targeting.py tests/unit/test_element_resolver.py \
  tests/unit/test_learned_targets.py tests/unit/test_drift_journal.py \
  tests/unit/test_site_signals.py tests/unit/test_resolver_guard.py \
  tests/unit/test_degraded_state.py tests/unit/test_shipped_baseline.py \
  tests/unit/test_descriptor_fragility.py tests/unit/test_detector_stress.py \
  tests/unit/test_ws_mutation_replay.py tests/unit/test_conversation_ledger.py \
  tests/unit/test_feige_signals.py tests/unit/test_feige_sidebar_shape.py \
  tests/unit/test_feige_ws_protocol_watch.py tests/unit/test_feige_row_name_tagging.py \
  tests/unit/test_cli_drift.py -q
# -> 364 passed  (+4 in tests/test_event_monitor_retarget.py)
```

The coverage table, printed rather than asserted:

```bash
python -m pytest tests/unit/test_detector_stress.py -q -s
```

Tests needing `node` skip cleanly without it. Tests needing the real capture
(`customer_logs/eCan_feigecap.jsonl`, git-ignored) skip on any machine that
does not have it.

### Reading the record

```bash
python ecan_cli.py drift stats             # how much history, and where
python ecan_cli.py drift list              # every change, newest first
python ecan_cli.py drift list --kind site_deploy    # the deploy calendar
python ecan_cli.py drift show 104          # one record in full
python ecan_cli.py drift shapes            # the live baseline
```

### Producing the next build's baseline

Run on a machine you believe is **healthy** — a baseline taken from a broken
install teaches every future install that broken is normal:

```bash
python ecan_cli.py drift export-baseline --site feige_chat \
  -o agent/ec_skills/browser_use_extension/hooks/external/feige_chat/baseline.json
```

### The emulator

```bash
python tools/emulation/server.py            # http://127.0.0.1:9876/im.jinritemai.com/
./check_monitor.ps1                         # confirm MONITOR LIVE before trusting a run
python tools/emulation/measure.py --label clean
```

Full detail in `EMULATION_HARNESS.md`.

### Switches

| Variable | Default | Effect |
|---|---|---|
| `ECAN_ELEMENT_RESOLVER` | off | Enables the L2 resolver. Leave off until the guard's limits have been reviewed. |
| `ECAN_RESOLVER_MODEL` | — | Which model L2 asks. |
| `ECAN_RESOLVER_SEND_CONTENT` | off | Sends candidate **content** instead of shape. Off means page text does not travel. |
| `ECAN_DRIFT_JOURNAL_DIR` | appdata | Where the permanent record lives. Tests point it at a temp dir. |
| `ECAN_RESOLVER_GUARD_DIR` | appdata | Where L2 spend state lives. |

---

## 8. Deliberately not done

- **The fleet layer.** Hold it until the local detector has caught one real
  site change — aggregating thousands of machines through an unvalidated
  detector is building on sand. And the rev stays human-gated regardless:
  descriptors derive from page content, and pages are attacker-influenceable.
- **Wiring L2/L3 into the Feige path.** The limits exist now; the switch is
  still a separate decision.
- **Driving the preview reader over a re-nested row.** The harness proves a
  re-nesting is *detected*, not that the reader would have broken.
- **Any claim of a real-world detection rate.** Both known site changes were
  diagnosed after the fact and the detector has never fired on a live one. The
  harness gives synthetic labels; a real event still has to happen.

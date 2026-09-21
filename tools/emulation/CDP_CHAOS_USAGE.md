# CDP / Renderer Chaos Emulation Usage

This guide explains the `CDP / Renderer Chaos` panel in the Feige emulation site.

The emulation site is served from:

```text
http://127.0.0.1:9876/im.jinritemai.com/
```

The persisted configuration file is:

```text
tools/emulation/emulation_config.json
```

## Quick Start

Start the emulation server:

```powershell
python tools\emulation\server.py
```

Open the site in the browser. The page now loads with `Realistic Feige site` enabled by default, so you can start a flood/debug run immediately after the page is loaded.

Default realistic profile:

| Field | Default | Purpose |
| --- | ---: | --- |
| `enabled` | `true` | Turns chaos on immediately when the page loads. |
| `preset` | `realistic_site` | Uses a mixed Feige-like renderer/DOM/focus/send profile. |
| `probability` | `55%` | Each eligible chaos action triggers about 55% of the time. |
| `blockClickMs` | `1200` | Adds moderate send-handler pressure without forcing a sender timeout by itself. |
| `delayAgentAppendMs` | `1800` | Delays the agent message bubble after send. |
| `stallEnabled` | `true` | Periodically stalls the browser renderer. |
| `renderer.blockMs` | `450` | CPU-block time per renderer stall. |
| `renderer.intervalMs` | `1800` | Time between renderer stalls. |
| `extraMessageRows` | `240` | Adds synthetic historical rows to make the DOM heavy. |
| `systemRows` | `12` | Adds platform/system rows similar to live Feige. |
| `selectorDelayMs` | `12` | Adds small blocking delays to DOM selector calls. |
| `dom.churnEnabled` | `true` | Periodically re-renders the thread/list. |
| `focus.churnEnabled` | `true` | Periodically switches the active customer/session. |
| `rerenderDuringSend` | `true` | Re-renders while the send path is executing. |

## Important Behavior

- **Config is persisted**: Changing a field in the GUI auto-saves to `emulation_config.json`.
- **Reset is realistic**: The `关闭/重置` button resets to the server default, which is now `Realistic Feige site`, not all-off.
- **Off requires selecting `Off`**: To disable chaos, select the `Off` preset or uncheck `启用 chaos` and save.
- **Page-level only**: Browser chaos is implemented in this emulation site. It does not modify installed `browser-use` or `cdp_use` source.

## Presets

### `Realistic Feige site`

Use this for normal diagnostic flood runs. It combines:

- Renderer stalls
- Heavy message DOM
- Platform/system rows
- DOM selector latency
- DOM churn
- Focus/session churn
- Moderate send path blocking and delayed bubble append

This is the best default for reproducing the real-vs-emulation gap seen in live Feige flood tests.

### `Runtime.evaluate timeout`

Use this when you want a direct reproduction of CDP send timeout behavior.

Primary effect:

- `Block click ms = 8000`

Expected symptom in app telemetry:

```text
[CDP-EVAL] ... phase=Runtime.evaluate ... timeout=True
[FEIGE-LEDGER] ... stage=cdp_evaluate_trace ... timed_out=true
```

### `Slow DOM`

Use this to stress DOM traversal and selector-heavy code.

Primary effects:

- More historical rows
- More system rows
- Selector call delay

### `Renderer stall`

Use this to stress Chrome renderer responsiveness.

Primary effects:

- Periodic synchronous CPU blocking on the page
- CDP `Runtime.evaluate` may take longer because evaluated JS runs in the stalled renderer

### `Focus churn`

Use this to emulate the live site switching focus/session state during operations.

Primary effects:

- Active customer/session changes periodically
- Thread/list re-renders during sends

### `Full flood chaos`

Use this for aggressive mixed-mode testing. It combines most chaos types with higher intensity.

## Field Reference

### Top-Level

#### `启用 chaos`

Turns all page-level chaos on or off.

- Checked: chaos logic can run.
- Unchecked: renderer stalls, DOM churn, focus churn, selector delays, and send chaos stop applying.

#### `Preset`

Applies a predefined profile. Selecting a preset immediately saves it.

#### `Probability %`

Controls how often eligible one-shot chaos actions trigger.

Examples:

- `0`: no probabilistic send/selector chaos triggers.
- `65`: default realistic setting.
- `100`: every eligible action triggers.

Periodic timers such as renderer stall, DOM churn, and focus churn still depend on their own enable checkboxes.

## Send Path Fields

### `Block click ms`

Synchronously blocks the browser main thread inside the send click path.

This is the most direct page-level way to make a CDP `Runtime.evaluate` call wait, because the application-side CDP wrapper is waiting for evaluated JS to complete.

Recommended values:

| Goal | Value |
| --- | ---: |
| Light send slowdown | `500` - `1500` |
| Realistic mixed profile | `1200` |
| Force likely 6s timeout | `7000` - `9000` |

### `Delay append ms`

Delays when the agent bubble is appended after send.

This emulates slow sidebar/thread updates and delayed message-id visibility.

### `Never append agent`

Skips appending the agent bubble after send.

Use this only for failure-path testing. It is intentionally destructive because the send action appears to complete without the expected visible result.

## Renderer Fields

### `Stall renderer`

Enables periodic main-thread CPU blocking.

This simulates a live Feige tab whose renderer is busy, frozen, or under heavy layout/script pressure.

### `Block ms`

How long each renderer stall blocks the page.

Recommended values:

| Goal | Value |
| --- | ---: |
| Mild jank | `200` - `400` |
| Realistic default | `650` |
| Aggressive stall | `1000` - `1500` |

### `Every ms`

How often renderer stalls occur.

Lower values create more frequent stalls.

### `Auto stop ms`

Automatically disables renderer stall after this duration.

Default is `180000` ms, or 3 minutes, so a flood run gets pressure but the browser is not left in a long-running stalled state forever.

## DOM / Focus Fields

### `Selector delay ms`

Adds a small blocking delay to `querySelector` and `querySelectorAll` calls.

This emulates slow DOM querying on large or virtualized pages.

### `Extra rows`

Adds synthetic historical chat rows to the latest thread render.

This makes DOM traversal, layout, and message extraction heavier.

### `System rows`

Adds platform/system rows like assignment, intervention, and status messages.

This helps reproduce live Feige where system rows can appear between customer and agent messages.

### `DOM churn`

Periodically re-renders the chat list and thread.

This emulates virtualized DOM churn and unstable node references.

### `Churn ms`

Interval for DOM churn.

Lower values churn more aggressively.

### `Focus churn`

Periodically switches the active customer/session.

This emulates live focus changes, target/session churn, or user/platform-driven active row changes.

### `Switch ms`

Interval for focus churn checks.

### `Switch prob %`

Probability that each focus churn check actually switches to another customer.

### `Rerender during send`

Forces list/thread re-render during agent send.

This is useful for reproducing send-time DOM instability.

### `Remove compose during send`

Temporarily removes the compose input box during send.

This is a destructive edge-case mode. Keep it off for normal realistic runs.

### `Remove ms`

How long the compose box is removed if `Remove compose during send` is enabled.

## Harness Fields

Harness fields affect only the local harness buttons. They do not affect the browser page until you click `Run fake CDP` or `Run cdp_use`.

### `Fake delay ms`

Delay used by `cdp_fake_harness.py` for fake `Runtime.evaluate`.

Default `7000` ms should exceed the app's 6-second CDP evaluate timeout.

### `Fake never resolve`

Makes the fake runtime evaluation never resolve.

Use this to verify timeout and pending-request telemetry in a controlled fake client.

### `cdp_use delay ms`

Delay used by the process-local `cdp_use` send_raw emulation harness.

### `cdp_use never respond`

Leaves the emulated pending request unresolved.

Use this to model the suspected pending-request leak/amplifier behavior.

### `Late response ms`

Schedules a response after the outer timeout.

Default `7000` ms means:

- The outer 6-second wait can time out first.
- A late response can arrive afterward.
- The harness can show whether pending requests are cleaned up after the late response.

## Buttons

### `保存 chaos`

Saves current GUI values to `emulation_config.json` and applies them immediately.

Most field changes auto-save, but this button is useful after manual edits.

### `关闭/重置`

Resets to server defaults.

Because server defaults are now realistic, this returns the panel to `Realistic Feige site`.

To fully disable chaos, select `Off` or uncheck `启用 chaos` and save.

### `Run fake CDP`

Runs:

```powershell
python tools\emulation\cdp_fake_harness.py --config tools\emulation\emulation_config.json
```

The output appears in the panel and includes timeout/pending/trace details.

### `Run cdp_use`

Runs:

```powershell
python tools\emulation\cdp_use_harness.py --config tools\emulation\emulation_config.json
```

This monkeypatches `CDPClient.send_raw` only inside the harness process. Library files are not modified.

## Recommended Test Workflow

1. Start the emulation server.
2. Open `http://127.0.0.1:9876/im.jinritemai.com/`.
3. Confirm the preset is `Realistic Feige site` and `启用 chaos` is checked.
4. Start the eCan flood/debug run.
5. Watch for these log events:

```text
[feige-emu]
[CDP-EVAL]
[FEIGE-LEDGER]
```

6. If no timeouts occur, increase one or more fields:

| Need | Increase |
| --- | --- |
| More direct send timeout pressure | `Block click ms` |
| More delayed visible send result | `Delay append ms` |
| More renderer pressure | `Block ms`, lower `Every ms` |
| More DOM pressure | `Extra rows`, `System rows`, `Selector delay ms` |
| More target/session instability | `Focus churn`, `Switch prob %` |

7. If the browser becomes too hard to operate, reduce renderer `Block ms`, increase renderer `Every ms`, or uncheck `Stall renderer`.

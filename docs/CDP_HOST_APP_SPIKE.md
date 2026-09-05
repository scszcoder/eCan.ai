# Spike: attach to a vendor desktop workbench (Electron) via CDP

_Status 2026-09-05: code shipped behind `ECAN_CDP_HOST_EXE` (default OFF),
build tags `v0.9.96y-spike-doudian-app-cdp-1` (GitHub-hosted, run 33982842382)
and `-2` (same commit 22ffe60, China self-hosted `win-runner`, run 33983963626).
Either installer works for the spike. Live verdict PENDING._

## Question

Merchants who run the vendor's desktop workbench (e.g. 抖店工作台) instead of
a browser: can eCan attach to that app and drive the same live-chat pages?
The app is a Chromium shell (Electron), so `--remote-debugging-port` may be
honoured exactly as it is for Chrome — unless the vendor strips the switch.

## What the switch does

`ECAN_CDP_HOST_EXE` = full path to the app's `.exe`, or (Windows) a substring
of its installed display name (looked up in the Uninstall registry keys and
`%LOCALAPPDATA%\Programs`).

When set, `_start_chrome_with_cdp()` in `gui/unified_browser_manager.py`:

1. Kills any running instance of that exe (Electron single-instance lock —
   a second launch just focuses the first and drops our switch).
2. Launches `<exe> --remote-debugging-port=<cdp_port>` — nothing else. No
   `--user-data-dir`, so the app keeps its own login.
3. Waits up to 30 s for the port, then logs `[CDP-HOST]` lines: browser/UA,
   every target's `type/url/title`, and a second snapshot 20 s later.

Unset → the ordinary Google Chrome path, byte-for-byte unchanged.

## How to run the spike on a machine with the app installed

```
setx ECAN_CDP_HOST_EXE "C:\Users\<you>\AppData\Local\Programs\抖店工作台\抖店工作台.exe"
```
(or `setx ECAN_CDP_HOST_EXE 抖店工作台` to let it be looked up). Restart eCan,
start the 抖店客服 agent as usual, then grep the log:

| Log line | Verdict |
|---|---|
| `[CDP-HOST] VERDICT: ... exited (code N) before CDP port opened` | app rejects the switch — spike FAILS |
| `[CDP-HOST] VERDICT: ... CDP port never opened in 30s` | app ignores the switch — spike FAILS |
| `[CDP-HOST] <name> up with CDP on port 9228` + `target type=page url='https://...jinritemai.com/...'` | attach WORKS; compare the URLs against the skill's `page_url_patterns` |
| targets are `file://` / custom scheme / `webview` only | attach works but the tab-discovery patterns need a follow-up |

Also check `[AGENT-STATUS] chrome=auto_started` and the later `site_tab=found`.

## Known limits (by design of the spike)

- Bot and human share ONE window. Row-clicks to open a conversation move the
  human's view; DOM typing races theirs. Only the off-DOM WS send avoids this.
- Hashed DOM selectors in the client build may differ from the web build.
- eCan exit does not kill the app (it is tracked in `_chrome_processes`
  like Chrome, which is not killed either).
- Higher ToS exposure than web automation: this relaunches the vendor's
  signed client with a debugging switch.

# CS stress bot + probe — where it lives

A standalone customer-service stress bot and probe for 抖店/飞鸽, 拼多多 and 千牛.
It answers every customer message with a template after a random 5–25 s
"LLM/RAG" delay, runs synthetic load, and logs WS frames, OCR calls, 千牛 memory
scans, Q&A pool scaling, every turn's timing and CPU/RAM. It also estimates how
many stores a machine can run. It exists to find scheduling, detection and send
bugs in minutes instead of a 40-minute app build per try.

**This file is the only tracked part.** The tool is kept out of git and out of
the app on purpose. This page records where it is, so it can be found again.
Built 2026-10-19.

## Where things are

| What | Path | In git? | In the app installer? |
|---|---|---|---|
| Source + README + build script + tests | `customer_logs/tools/cs_stress_bot_src/` | No (`customer_logs/` is git-ignored) | No |
| Exe to FTP to a customer | `customer_logs/tools/cs_stress_bot.exe` (~52 MB, one file; no local OCR — 千牛 uses the SZ server OCR API, signed in with the PC's eCan login) | No | No |
| Build intermediates | `customer_logs/tools/cs_stress_bot_src/{build,dist}/` | No | No |
| Run output | `cs_bot_out/<time>/` next to the exe (from source: `customer_logs/tools/cs_bot_out/`) | No | — |

The source exists only on the development PC that built it, in the main eCan.ai
working copy. Back it up yourself if it matters: it is on no branch.

## Files in `cs_stress_bot_src/`

| File | Role |
|---|---|
| `README.md` | How to run, flags, output format, rebuilding |
| `cs_stress_bot.py` | Entry point: CLI, store discovery, synthetic load and ramp, replay, report |
| `appmods.py` | Loads the APP's own modules from the repo without the app stack |
| `stores.py` | Per-store adapters: 飞鸽 / 拼多多 (CDP), 千牛 (memory observer + desktop send), virtual, replay |
| `pool.py` | Q&A agents driven by the app's `agent/ec_agents/agent_pool.py` |
| `events.py` | events.jsonl, resource sampler, report, capacity estimate |
| `cdp.py` | Minimal CDP client |
| `cs_stress_bot.spec`, `build_exe.ps1` | One-file exe build (repo `.venv`, Python 3.12) |
| `test_cs_stress_bot.py` | `pytest customer_logs/tools/cs_stress_bot_src/test_cs_stress_bot.py` |

## Coupling to the app (what to check when app code moves)

The bot imports these app files at run time, unchanged. If one is renamed or
its function signature changes, the bot breaks. Run `cs_stress_bot.exe --selfcheck`
(or the test file) after such a change.

- `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/`: `ws_reader`, `ws_session` (`frame_for`, `inject_js`, `wait_confirmed`, `note_recv_frame`, `note_sent_frame`, `register_shop`), `sidebar_preview_js`. It also parses (does not import) `site_tools._FEIGE_SEND_MESSAGE_JS` and `front_desk._COLDSTART_SIDEBAR_SCAN_JS`.
- `.../pdd_chat/`: `ws_protocol.decode_events`, `dom.send_text`, `dom.list_sessions`, `dom.get_thread`.
- `.../qianniu_chat/`: `observer.QianniuMemObserver(dispatch_fn=...)`, `name_map`.
- `agent/mcp/server/qianniu/`: `qianniu_tools.send_reply`, `qianniu_ocr.ocr_qianniu_window`, `remote_ocr.ocr_png` / `_auth`.
- `auth/auth_manager.py`: `AuthManager._get_saved_username`, `_get_wechat_session_token` (read-only server-OCR token); `agent/cloud_api/cloud_api._http_auth_header`; `agent/ec_skills/media/proxy_media_client.ProxyMediaClient` (>60 KB OCR uploads).
- `agent/ec_agents/agent_pool.py`: `register_pool`, `pick_for_customer`, `note_enqueued`, `note_started`, `active_members`, `_default_lookup`, `_traffic_path`.
- `scripts/site_probe_standalone.py`: `find_store_chromes` (store Chrome discovery).

Related: `docs/EMULATION_HARNESS.md` (the older fake-飞鸽-panel harness, also kept in `customer_logs/`).

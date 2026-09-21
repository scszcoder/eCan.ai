"""
Manual-launch measurement driver (2026-06-03).

Bypasses the harness's autologin app-launch (which doesn't bind the Feige
monitor) and drives the SAME measurement against an app you launched + logged
into yourself. Run this AFTER:

  1. Launch eCan manually (PyCharm run / `python main.py`) and log in.
  2. Open ONE emulation tab:  http://127.0.0.1:9876/im.jinritemai.com/
  3. Wait until the monitor is live — `runlogs/eCan.log` shows
     `EventMonitor ... DOM monitor loop started` and the sidebar gets scraped.
  4. (clean baseline) In the emulation tab's DevTools console run
     `localStorage.clear()` then Ctrl+Shift+R so scrapes aren't walking a
     bloated DOM.

Then:
  # clean baseline (scrapeStall OFF) — the A/B reference:
  python tools/emulation/measure.py --label clean

  # blackout variant (scrapeStall ON) — the injected detection stall:
  python tools/emulation/measure.py --label blackout --stall

It POSTs the emulation config (scrapeStall on/off), brackets a metrics run,
fires a staggered 6-customer flood, waits the window, stops the run, then runs
analyze_detection_lag.py and prints both the 4 metrics and the detection-lag
summary.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

EMU_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EMU_ROOT.parent.parent


def _post(base, path, body):
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description="Manual-launch flood + metrics driver.")
    ap.add_argument("--label", default="manual", help="run label (results/<label>_<ts>.json)")
    ap.add_argument("--stall", action="store_true", help="enable load-dependent scrapeStall (blackout variant)")
    ap.add_argument("--no-chaos", action="store_true",
                    help="mt072: also disable renderer.stall + send.blockClick + dom.churn, for a CLEAN "
                         "renderer. Isolates real PRODUCT send contention from synthetic renderer load — "
                         "if send timeouts vanish here, the 24-30s runtime_evaluate was injected, not the product.")
    ap.add_argument("--n", type=int, default=6, help="customer count")
    ap.add_argument("--join-spread", type=int, default=120, help="seconds to stagger customer joins over")
    ap.add_argument("--followup-rounds", type=int, default=8, help="follow-ups per customer")
    ap.add_argument("--followup-interval-ms", type=int, default=30000, help="ms between follow-ups")
    ap.add_argument("--wait", type=int, default=360, help="flood window seconds before stopping")
    ap.add_argument("--per-msg-ms", type=int, default=20, help="scrapeStall per-message cost (with --stall)")
    ap.add_argument("--emu-port", type=int, default=9876)
    ap.add_argument("--log", default=str(REPO_ROOT / "runlogs" / "eCan.log"))
    ap.add_argument("--ts", type=int, default=None, help="timestamp suffix (defaults to wall clock)")
    args = ap.parse_args()

    base = f"http://127.0.0.1:{args.emu_port}"
    ts = args.ts if args.ts is not None else int(time.time())
    run_id = f"{args.label}_{ts}"

    # sanity: emulation server reachable
    try:
        _get(base, "/api/emulation/config")
    except Exception as exc:
        print(f"[measure] emulation server not reachable on {base}: {exc}")
        return 1

    # 1) set scrapeStall on/off for this run (gated on run_active, so harmless until run/start)
    emu_cfg = {"dom": {"scrapeStall": {
        "enabled": bool(args.stall),
        "baseMs": 120, "perMsgMs": args.per_msg_ms, "perConvoMs": 500, "capMs": 30000,
    }}}
    if args.no_chaos:
        # mt072 clean-renderer: turn OFF the synthetic renderer-main-thread load that
        # otherwise inflates the send JS's runtime_evaluate (the 24-30s we saw). These
        # are deep-merged onto the persisted config by the server.
        emu_cfg["renderer"] = {"stallEnabled": False}
        emu_cfg["send"] = {"blockClickMs": 0, "delayAgentAppendMs": 0}
        emu_cfg["dom"]["churnEnabled"] = False
    _post(base, "/api/emulation/config", emu_cfg)
    print(f"[measure] scrapeStall.enabled={bool(args.stall)} (perMsgMs={args.per_msg_ms})  "
          f"chaos={'OFF (clean renderer)' if args.no_chaos else 'ON (renderer.stall+blockClick+churn)'}")

    # 2) start the metrics run, fire the staggered flood
    _post(base, "/api/emulation/run/start", {"run_id": run_id, "label": args.label})
    _post(base, "/api/emulation/flood", {
        "n": args.n,
        "joinSpreadSec": args.join_spread,
        "followUpRounds": args.followup_rounds,
        "followUpIntervalMs": args.followup_interval_ms,
    })
    print(f"[measure] run '{run_id}' started: {args.n} customers, join-spread {args.join_spread}s, "
          f"{args.followup_rounds} follow-ups @ {args.followup_interval_ms}ms; window {args.wait}s")

    # 3) wait the window, with a light progress line every 30s
    waited = 0
    while waited < args.wait:
        step = min(30, args.wait - waited)
        time.sleep(step)
        waited += step
        try:
            rep = _get(base, "/api/emulation/report").get("report", {})
            m = rep.get("metrics", {})
            print(f"[measure] +{waited}s  answered={m.get('answered_queries')} "
                  f"late={m.get('placeholder_late')} dup={m.get('duplicate_responses')} "
                  f"queries={rep.get('total_queries')}")
        except Exception:
            pass

    # 4) stop -> server writes results/<run_id>.json
    stop = _post(base, "/api/emulation/run/stop", {})
    rep = (stop or {}).get("report", {})
    m = rep.get("metrics", {})
    print("\n[measure] ===== METRICS =====")
    print(f"  answered_queries      : {m.get('answered_queries')}")
    print(f"  placeholder_late      : {m.get('placeholder_late')}")
    print(f"  duplicate_responses   : {m.get('duplicate_responses')}")
    print(f"  placeholder_after_real: {m.get('placeholder_after_real')}")
    print(f"  total_queries         : {rep.get('total_queries')}  customers={rep.get('customers')}")
    results_file = rep.get("written") or str(EMU_ROOT / "results" / f"{run_id}.json")

    # 5) detection-lag analysis (q_sent vs dom_observed + HB starvation)
    log_path = Path(args.log)
    if Path(results_file).is_file() and log_path.is_file():
        print("\n[measure] ===== DETECTION LAG =====")
        subprocess.run([sys.executable, str(EMU_ROOT / "analyze_detection_lag.py"),
                        "--results", results_file, "--log", str(log_path)],
                       cwd=str(REPO_ROOT))
    else:
        print(f"\n[measure] skip detection-lag: results={results_file} exists={Path(results_file).is_file()}, "
              f"log={log_path} exists={log_path.is_file()}")
    print(f"\n[measure] results: {results_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

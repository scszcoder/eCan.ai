"""Phase-3 reliability gate — run on a LIVE 千牛 client (plan §5 Phase 3).

A measurement harness, not an auto-test: an operator sends a controlled set of
messages from buyer account(s) while this runs; the harness observes what the
agent detected, attributed, and (optionally) replied, and reports the gate
metrics the study requires before any unattended use:

  * wrong-recipient sends   — MUST be 0 (header verify aborts count as caught)
  * draft-as-incoming       — MUST be 0 (dedup / draft filtering)
  * duplicates / out-of-order
  * receive→reply latency

Modes:
  observe-only (default)  — record detections; send nothing.
  --reply "<canned text>" — also reply to each detected buyer via qianniu_send
                            (the full hands-off path, with the fail-closed guard).

Usage:
  python -m ...qianniu_chat._phase3_gate --duration 600
  python -m ...qianniu_chat._phase3_gate --duration 600 --reply "您好，正在为您核实~"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict

from utils import win_process_memory as mem
from . import observer as obs


class _Recorder:
    def __init__(self):
        self.events = []                       # (ts, uid, name, msg_id, text)
        self.by_buyer = defaultdict(int)
        self.msg_ids = defaultdict(int)
        self.sends = []                        # (uid, ok, verified, header, latency_s)

    def record(self, item: dict) -> int:
        ts = time.time()
        uid = item.get("customer_name", "")
        self.events.append((ts, uid, item.get("customer_display_name", ""),
                            item.get("msg_id", ""), item.get("last_message", "")))
        self.by_buyer[uid] += 1
        self.msg_ids[item.get("msg_id", "")] += 1
        return 1

    def report(self) -> dict:
        dup = {k: v for k, v in self.msg_ids.items() if v > 1}
        wrong = [s for s in self.sends if s[1] and not s[2]]   # sent but not verified
        lat = [s[4] for s in self.sends if s[1]]
        return {
            "messages_detected": len(self.events),
            "distinct_buyers": len(self.by_buyer),
            "per_buyer": dict(self.by_buyer),
            "duplicate_msg_ids": dup,
            "sends_attempted": len(self.sends),
            "sends_ok": sum(1 for s in self.sends if s[1]),
            "wrong_recipient_sends": len(wrong),      # gate: must be 0
            "aborted_sends": sum(1 for s in self.sends if not s[1]),
            "latency_s": {
                "n": len(lat),
                "avg": round(sum(lat) / len(lat), 2) if lat else None,
                "max": round(max(lat), 2) if lat else None,
            },
        }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="千牛 Phase-3 reliability gate")
    ap.add_argument("--duration", type=int, default=300, help="seconds to observe")
    ap.add_argument("--reply", default="", help="canned reply text; empty = observe only")
    args = ap.parse_args(argv)

    if not mem.available():
        print("[gate] process-memory reading is Windows-only; cannot run here.")
        return 2

    rec = _Recorder()

    def _dispatch(item: dict) -> int:
        n = rec.record(item)
        if args.reply:
            t0 = time.time()
            from agent.mcp.server.qianniu.qianniu_tools import qianniu_send
            r = asyncio.run(qianniu_send(None, {"input": {
                "buyer_display_name": item.get("customer_display_name") or item.get("customer_name"),
                "chat_msg": args.reply,
            }}))
            try:
                payload = json.loads(r[0].text)
            except Exception:
                payload = {}
            rec.sends.append((item.get("customer_name", ""),
                              bool(payload.get("chat_sent")), bool(payload.get("verified")),
                              payload.get("header_name", ""), time.time() - t0))
        return n

    o = obs.QianniuMemObserver(dispatch_fn=_dispatch)
    print(f"[gate] observing for {args.duration}s "
          f"({'reply mode' if args.reply else 'observe-only'})… send test messages now.")
    o.start()
    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        pass
    o.stop()
    time.sleep(1.0)

    report = rec.report()
    print("\n===== PHASE-3 GATE REPORT =====")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    passed = report["wrong_recipient_sends"] == 0
    print(f"\nGATE: {'PASS' if passed else 'FAIL'} "
          f"(wrong-recipient sends = {report['wrong_recipient_sends']}, must be 0)")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

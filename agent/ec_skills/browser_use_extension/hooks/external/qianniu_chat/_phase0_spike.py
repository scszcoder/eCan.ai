"""Phase-0 de-risk spike — run against a LIVE 千牛 client. READ-ONLY.

Proves the two unknowns before any bundle is built (plan §5 Phase 0):
  1. memory receive + attribution: scan AliWorkbench memory, carve
     sender-anchored messages, separate seller from buyer(s) by sender id.
  2. select-verify: OCR the chat-header band and read the buyer display name.

Nothing here sends input or writes memory. Usage:

    python -m agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat._phase0_spike
    python -m ...._phase0_spike --verify-header "大作战panda"
"""
from __future__ import annotations

import argparse
import sys

from utils import win_process_memory as mem
from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import mem_locator

_PROC_NAME = "AliWorkbench"


def scan_memory(pid: int, limit: int = 40) -> None:
    print(f"[spike] scanning pid {pid} for sender-anchored messages (read-only)…")
    candidates: list = []
    for data in mem.scan_strings(pid, mem_locator.region_has_messages):
        candidates.extend(mem_locator.extract_candidates(data))
        if len(candidates) >= limit:
            break

    if not candidates:
        print("[spike] no message candidates found. The content field name may "
              "need calibration (plan §6), or no chat is loaded.")
        return

    seller = mem_locator.seller_id_of(candidates)
    print(f"[spike] {len(candidates)} candidate(s); inferred seller id: {seller!r}")
    for c in candidates[:limit]:
        buyer_ids = sorted(c.sender_ids - ({seller} if seller else set()))
        role = "seller" if (seller and seller in c.sender_ids and not buyer_ids) else "buyer"
        print(f"  [{role}] buyer_ids={buyer_ids} msg_id={c.msg_id or '-'} "
              f"text={c.text[:60]!r}")


def verify_header(name: str) -> None:
    from agent.mcp.server.qianniu.qianniu_ocr import verify_header_name
    print(f"[spike] OCR header verify against {name!r}…")
    r = verify_header_name(name)
    print(f"  matched={r.matched} header_text={r.header_text!r} "
          f"band_saw={r.candidates[:8]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="千牛 Phase-0 read-only spike")
    ap.add_argument("--pid", type=int, default=0, help="AliWorkbench pid (auto if omitted)")
    ap.add_argument("--verify-header", default="", help="OCR the header and match this display name")
    ap.add_argument("--no-memory", action="store_true", help="skip the memory scan")
    args = ap.parse_args(argv)

    if not mem.available():
        print("[spike] process-memory reading is Windows-only; cannot run the memory leg here.")

    if not args.no_memory and mem.available():
        from .observer import _qianniu_pids   # root AliWorkbench first (messages live there)
        pid = args.pid or next(iter(_qianniu_pids()), 0)
        if not pid:
            print(f"[spike] could not find a running {_PROC_NAME} process. Is 千牛 open?")
        else:
            scan_memory(pid)

    if args.verify_header:
        verify_header(args.verify_header)
    return 0


if __name__ == "__main__":
    sys.exit(main())

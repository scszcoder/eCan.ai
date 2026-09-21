from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_cdp_client_class():
    try:
        from cdp_use.client import CDPClient
        return CDPClient, "cdp_use.client.CDPClient"
    except Exception:
        try:
            from cdp_use import CDPClient
            return CDPClient, "cdp_use.CDPClient"
        except Exception:
            return None, "local.EmulatedCDPClient"


class EmulatedCDPClient:
    pass


async def main_async(config_path: Path) -> dict:
    config = load_config(config_path)
    harness = config.get("harness") or {}
    delay_ms = float(harness.get("cdpUseDelayMs") or 0)
    never_respond = bool(harness.get("cdpUseNeverRespond"))
    late_response_ms = float(harness.get("cdpUseLateResponseMs") or 0)
    response_delay_ms = late_response_ms if late_response_ms > 0 else delay_ms
    ClientClass, class_name = resolve_cdp_client_class()
    if ClientClass is None:
        ClientClass = EmulatedCDPClient
    original_send_raw = getattr(ClientClass, "send_raw", None)
    late_events = []

    async def patched_send_raw(self, method, params=None, session_id=None):
        self.msg_id = int(getattr(self, "msg_id", 0)) + 1
        msg_id = self.msg_id
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_requests[msg_id] = future

        def resolve_late():
            stored = self.pending_requests.pop(msg_id, None)
            if stored is None:
                late_events.append({"msg_id": msg_id, "status": "missing"})
                return
            if stored.cancelled():
                late_events.append({"msg_id": msg_id, "status": "cancelled"})
                return
            if stored.done():
                late_events.append({"msg_id": msg_id, "status": "done"})
                return
            stored.set_result({"id": msg_id, "result": {"value": {"ok": True}}})
            late_events.append({"msg_id": msg_id, "status": "resolved"})

        if method == "Runtime.evaluate" and not never_respond:
            loop.call_later(max(0.0, response_delay_ms / 1000.0), resolve_late)
        return await future

    ClientClass.send_raw = patched_send_raw
    client = object.__new__(ClientClass)
    client.msg_id = 0
    client.pending_requests = {}
    timeout_s = 6.0
    if response_delay_ms and response_delay_ms < 6000 and not never_respond:
        timeout_s = max(0.05, response_delay_ms / 1000.0 + 1.0)
    try:
        try:
            result = await asyncio.wait_for(
                client.send_raw("Runtime.evaluate", params={"expression": "1"}, session_id="emu-session-cdp-use"),
                timeout=timeout_s,
            )
            timed_out = False
            error = ""
        except TimeoutError as exc:
            result = None
            timed_out = True
            error = str(exc) or "TimeoutError"
        pending_immediate = len(client.pending_requests)
        pending_ids_immediate = list(client.pending_requests.keys())
        if not never_respond and response_delay_ms > 0:
            await asyncio.sleep(min(10.0, response_delay_ms / 1000.0 + 0.2))
        return {
            "ok": True,
            "class": class_name,
            "timed_out": timed_out,
            "error": error,
            "result": result,
            "delay_ms": delay_ms,
            "never_respond": never_respond,
            "late_response_ms": late_response_ms,
            "pending_immediate": pending_immediate,
            "pending_ids_immediate": pending_ids_immediate,
            "pending_after_late_wait": len(client.pending_requests),
            "pending_ids_after_late_wait": list(client.pending_requests.keys()),
            "late_events": late_events,
            "runtime_patch_scope": "process-local only; library files unchanged",
        }
    finally:
        if original_send_raw is None:
            try:
                delattr(ClientClass, "send_raw")
            except Exception:
                pass
        else:
            ClientClass.send_raw = original_send_raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "emulation_config.json"))
    args = parser.parse_args()
    result = asyncio.run(main_async(Path(args.config)))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agent.ec_skills.browser_use_extension import extension_tools_service as svc


class FakeRuntime:
    def __init__(self, client, *, delay_s: float, never_resolve: bool):
        self.client = client
        self.delay_s = delay_s
        self.never_resolve = never_resolve

    async def enable(self, params=None, session_id=None):
        return {}

    async def evaluate(self, params, session_id=None):
        self.client.pending_requests[1001] = asyncio.get_running_loop().create_future()
        if self.never_resolve:
            await asyncio.Future()
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        self.client.pending_requests.pop(1001, None)
        return {"result": {"value": json.dumps({"ok": True, "mode": "fake-runtime"})}}


class FakeSend:
    def __init__(self, client, *, delay_s: float, never_resolve: bool):
        self.Runtime = FakeRuntime(client, delay_s=delay_s, never_resolve=never_resolve)


class FakeCDPClient:
    def __init__(self, *, delay_s: float, never_resolve: bool):
        self.pending_requests = {}
        self._message_handler_task = None
        self.send = FakeSend(self, delay_s=delay_s, never_resolve=never_resolve)


class FakeCDPSession:
    def __init__(self, client):
        self.cdp_client = client
        self.session_id = "emu-session-fake"


class FakeBrowserSession:
    def __init__(self, client):
        self.client = client

    async def get_or_create_cdp_session(self, target_id=None, focus=True):
        self.target_id = target_id
        self.focus = focus
        return FakeCDPSession(self.client)


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


async def main_async(config_path: Path) -> dict:
    config = load_config(config_path)
    harness = config.get("harness") or {}
    delay_ms = float(harness.get("fakeRuntimeDelayMs") or 0)
    never_resolve = bool(harness.get("fakeRuntimeNeverResolve"))
    client = FakeCDPClient(delay_s=delay_ms / 1000.0, never_resolve=never_resolve)
    session = FakeBrowserSession(client)
    records = []
    old_trace = svc._log_cdp_eval_trace

    def capture_trace(**kwargs):
        records.append(kwargs)
        old_trace(**kwargs)

    svc._log_cdp_eval_trace = capture_trace
    try:
        result = await svc._evaluate_js(
            session,
            "(() => JSON.stringify({ok:true, mode:'fake-runtime'}))()",
            target_id="emu-target-fake",
            focus=False,
            trace_label="feige_send_message",
            trace_fields={"emulation_harness": "fake-runtime", "delay_ms": delay_ms, "never_resolve": never_resolve},
        )
        return {
            "ok": True,
            "timed_out": False,
            "result": result,
            "pending_after": len(client.pending_requests),
            "trace": records[-1] if records else None,
        }
    except TimeoutError as exc:
        return {
            "ok": True,
            "timed_out": True,
            "error": str(exc),
            "pending_after": len(client.pending_requests),
            "trace": records[-1] if records else None,
        }
    finally:
        svc._log_cdp_eval_trace = old_trace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "emulation_config.json"))
    args = parser.parse_args()
    os.environ.setdefault("PYTHONUTF8", "1")
    result = asyncio.run(main_async(Path(args.config)))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

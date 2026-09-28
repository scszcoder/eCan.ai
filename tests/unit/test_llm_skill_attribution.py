"""Per-skill billing needs X-Ecan-Skill-Id on every llm-proxy call (2026-09-28:
the server saw it on 0 of 2,672 calls). Two ways it was lost:
  * the LLM node / browser worker ran calls on bare threads, which start with
    an EMPTY context on this Python -- the run scope never reached the request;
  * the browser-use ecanai client had no attribution hook at all.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BUILD_NODE = Path("agent/ec_skills/build_node.py").read_text(encoding="utf-8")
LLM_UTILS = Path("agent/ec_skills/llm_utils/llm_utils.py").read_text(encoding="utf-8")


def test_llm_node_threads_carry_the_run_scope():
    assert "target=_wrap_ctx(_worker)" in BUILD_NODE          # single attempt
    assert "target=_wrap_ctx(_hedged_worker)" in BUILD_NODE   # hedged pair
    assert 'Thread(target=wrap_context(_worker), name="playwright-worker"' in LLM_UTILS


def test_direct_llm_proxy_client_gets_attribution():
    i = BUILD_NODE.index("def _build_llm_kwargs_from_runtime_spec(")
    body = BUILD_NODE[i:i + 3500]
    assert '"llm-proxy" in str(value_map.get("base_url")' in body
    assert "apply_attribution_to_request" in body


def _fake_proxy():
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append({k: v for k, v in self.headers.items() if k.lower().startswith("x-ecan")})
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                               "choices": [{"index": 0, "finish_reason": "stop",
                                            "message": {"role": "assistant", "content": "ok"}}],
                               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def test_browser_use_ecanai_client_sends_the_skill_id():
    from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm_by_provider_type
    from utils.log_scope import scope
    srv, seen = _fake_proxy()
    try:
        llm = create_browser_use_llm_by_provider_type(
            "ecanai", model_name="qwen-plus", api_key="k",
            base_url=f"http://127.0.0.1:{srv.server_port}/v1")
        assert llm is not None

        async def call():
            from browser_use.llm.messages import UserMessage
            await llm.ainvoke([UserMessage(content="hi")])

        with scope(skill_id="SK_TEST", source="agent_run"):
            try:
                asyncio.run(call())
            except Exception:
                pass            # the fake reply need not satisfy browser-use; only the request matters
    finally:
        srv.shutdown()
    assert seen and seen[0].get("X-Ecan-Skill-Id") == "SK_TEST"

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.hot_path_v2 import (
    ToolResult,
    execute_v2,
)


class StubPrimitives:
    async def eval_js(self, snippet, *, timeout_ms=3000):
        if "qa-message-warpper" in snippet:
            return {"found": True, "msg_id": "msg-1", "text": "question"}
        return {
            "ok": True,
            "active": "客户A",
            "header_name": "客户A",
            "sidebar_name": "客户A",
        }

    async def click(self, selector, *, timeout_ms=3000):
        return True

    async def read_dom(self, selector, *, depth=2):
        return ""

    async def type(self, selector, text, *, clear_first=True, submit=False):
        return True

    async def wait_for(self, selector, *, condition="present", timeout_ms=5000):
        return True


class StubInvoker:
    def __init__(self):
        self.calls = []

    async def invoke(self, name, args):
        self.calls.append((name, dict(args)))
        return ToolResult(ok=True, extracted_content="ok")


class StubTypingLock:
    def __init__(self):
        self.released = []

    def try_acquire(self, customer_key, *, ttl_s=None):
        return True

    def release(self, customer_key):
        self.released.append(customer_key)

    def holder(self):
        return ""


class HotPathV2ExecutorTests(unittest.TestCase):
    def test_feige_send_message_gets_source_turn_args_from_payload(self):
        invoker = StubInvoker()
        lock = StubTypingLock()
        payload = {
            "customer_name": "客户A",
            "response_text": "reply",
            "source_customer_msg_id": "msg-1",
            "source_latest_message": "question",
        }
        outcome = asyncio.run(
            execute_v2(
                primitives=StubPrimitives(),
                invoker=invoker,
                typing_lock=lock,
                customer_key="客户A",
                action_seq=[
                    {"tool": "feige_send_message", "args": {"text": "{{response_text}}"}}
                ],
                payload=payload,
                resolve_template=lambda value, data: data.get("response_text") if value == "{{response_text}}" else value,
                node_name="test_node",
            )
        )

        self.assertTrue(outcome.ok)
        self.assertEqual(invoker.calls[0][0], "feige_send_message")
        self.assertEqual(invoker.calls[0][1]["customer_name"], "客户A")
        self.assertEqual(invoker.calls[0][1]["source_customer_msg_id"], "msg-1")
        self.assertEqual(invoker.calls[0][1]["source_latest_message"], "question")
        self.assertEqual(lock.released, ["客户A"])

    def test_cdp_health_cooldown_defers_without_tool_invocation(self):
        invoker = StubInvoker()
        lock = StubTypingLock()
        with patch(
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.hot_path_v2._live_chat_cdp_health_cooldown_remaining",
            return_value=12.5,
        ):
            outcome = asyncio.run(
                execute_v2(
                    primitives=StubPrimitives(),
                    invoker=invoker,
                    typing_lock=lock,
                    customer_key="客户A",
                    action_seq=[
                        {"tool": "feige_send_message", "args": {"text": "reply"}}
                    ],
                    payload={"customer_name": "客户A", "response_text": "reply"},
                    resolve_template=lambda value, data: value,
                    node_name="test_node",
                )
            )

        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.reason, "cdp_health_cooldown_active")
        self.assertEqual(invoker.calls, [])
        self.assertEqual(lock.released, [])


if __name__ == "__main__":
    unittest.main()

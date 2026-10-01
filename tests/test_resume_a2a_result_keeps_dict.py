"""An A2A reply whose result is a text part must not replace state.result with a
string (2026-10-01 拼多多 front desk: the failed-delivery fallback resumed with the
reply JSON as text, and the next loop node crashed on result['counter'] = 0)."""

import json
import unittest

from agent.ec_tasks.resume import build_general_resume_payload


class FakeTask:
    def __init__(self, state):
        self.metadata = {"state": state}
        self.checkpoint_nodes = []
        self.skill = type("Skill", (), {})()


def _a2a_msg(text):
    return {"params": {"id": "w1", "sessionId": "s1",
                       "message": {"parts": [{"kind": "text", "text": text}]},
                       "metadata": {"mtype": "a2a_response"}}}


class A2AResultKeepsDictTests(unittest.TestCase):
    def _patch(self, text):
        task = FakeTask({"input": "", "messages": [], "attributes": {}, "result": {"counter": 2}})
        _payload, _cp, state_patch = build_general_resume_payload(task, _a2a_msg(text))
        return state_patch

    def test_json_object_text_is_merged_as_a_dict(self):
        reply = json.dumps({"customer_id": "2805683407187", "response_text": "国庆活动以店铺页面显示为准"},
                           ensure_ascii=False)
        result = self._patch(reply).get("result")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("customer_id"), "2805683407187")

    def test_plain_text_never_becomes_state_result(self):
        result = self._patch("在的亲").get("result", {})
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()

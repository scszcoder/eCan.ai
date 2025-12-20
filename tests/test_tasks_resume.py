import unittest
from agent.tasks_resume import normalize_event, build_resume_from_mapping, select_checkpoint, build_general_resume_payload, DEFAULT_MAPPINGS


class FakeTask:
    def __init__(self, mapping_rules=None):
        self.metadata = {"state": {"attributes": {}}}
        self.checkpoint_nodes = []
        self.skill = type("S", (), {"mapping_rules": mapping_rules})() if mapping_rules else type("S", (), {})()


class FakeCheckpoint:
    def __init__(self):
        self.values = {"attributes": {}}


class TasksResumeUnitTests(unittest.TestCase):
    def test_normalize_event_human_chat(self):
        msg = {
            "params": {
                "id": "t1",
                "sessionId": "s1",
                "message": {"parts": [{"type": "text", "text": "hello"}]},
                "metadata": {"mtype": "send_chat", "i_tag": "cp1", "chatId": "c1", "msgId": "m1"},
            }
        }
        ev = normalize_event(msg)
        self.assertEqual(ev["type"], "human_chat")
        self.assertEqual(ev["tag"], "cp1")
        self.assertEqual(ev["data"]["human_text"], "hello")

    def test_normalize_event_a2a_with_payloads(self):
        msg = {
            "params": {
                "id": "t2",
                "sessionId": "s2",
                "message": {"parts": [{"type": "text", "text": "ignored"}]},
                "metadata": {
                    "mtype": "send_task",
                    "i_tag": "cp2",
                    "qa_form_to_agent": {"q": 1},
                    "notification_to_agent": {"n": 2},
                },
            }
        }
        ev = normalize_event(msg)
        self.assertEqual(ev["type"], "a2a")
        self.assertEqual(ev["tag"], "cp2")
        self.assertEqual(ev["data"]["qa_form_to_agent"], {"q": 1})
        self.assertEqual(ev["data"]["notification_to_agent"], {"n": 2})

    def test_select_checkpoint(self):
        task = FakeTask()
        cp = FakeCheckpoint()
        task.checkpoint_nodes = [{"tag": "cpX", "checkpoint": cp}]
        chosen = select_checkpoint(task, "cpX")
        self.assertIs(chosen, cp)
        self.assertEqual(task.checkpoint_nodes, [])  # popped

    def test_default_mapping_resume_and_state_patch(self):
        task = FakeTask()
        msg = {
            "params": {
                "id": "t3",
                "sessionId": "s3",
                "message": {"parts": [{"type": "text", "text": "hi"}]},
                "metadata": {
                    "mtype": "send_chat",
                    "i_tag": "cp3",
                    "qa_form": {"a": 1},
                    "notification": {"b": 2},
                },
            }
        }
        # Use the lower-level builder to inspect patches
        ev = normalize_event(msg)
        resume, patch = build_resume_from_mapping(ev, task.metadata["state"], node_output=None, mapping=DEFAULT_MAPPINGS)
        self.assertEqual(resume["human_text"], "hi")
        self.assertEqual(resume["qa_form_to_agent"], {"a": 1})
        self.assertEqual(resume["notification_to_agent"], {"b": 2})
        # state patch contains attributes writes
        self.assertIn("attributes", patch)
        self.assertIn("human", patch["attributes"])

    def test_build_general_resume_payload_with_checkpoint_and_injection(self):
        task = FakeTask()
        cp = FakeCheckpoint()
        task.checkpoint_nodes = [{"tag": "cloud-123", "checkpoint": cp}]
        msg = {
            "params": {
                "id": "t4",
                "sessionId": "s4",
                "message": {"parts": [{"type": "text", "text": "yo"}]},
                "metadata": {"mtype": "send_chat", "i_tag": "cloud-123"},
            }
        }
        resume_payload, checkpoint, state_patch = build_general_resume_payload(task, msg)
        self.assertIs(checkpoint, cp)
        self.assertEqual(cp.values["attributes"].get("cloud_task_id"), "cloud-123")
        # state gets cloud_task_id mirrored if attributes present
        # Merge behavior is applied by caller; here we just ensure patch exists
        self.assertIn("attributes", state_patch)


class TasksResumeIntegrationLikeTests(unittest.TestCase):
    def test_integration_custom_skill_mapping_tool_input_and_metadata(self):
        mapping_rules = {
            "mappings": [
                {
                    "from": ["event.data.sample_tool_input"],
                    "to": [{"target": "state.tool_input.sample"}, {"target": "resume.sample_tool_input"}],
                    "on_conflict": "overwrite",
                },
                {
                    "from": ["event.data.sample_meta"],
                    "to": [{"target": "state.metadata.extra"}],
                    "on_conflict": "merge_deep",
                },
            ]
        }
        task = FakeTask(mapping_rules=mapping_rules)
        msg = {
            "params": {
                "id": "t5",
                "sessionId": "s5",
                "message": {"parts": [{"type": "text", "text": "hello"}]},
                "metadata": {
                    "mtype": "send_chat",
                    "i_tag": "tag-1",
                    # custom synthetic fields that the mapping expects
                    "sample_tool_input": {"k": 9},
                    "sample_meta": {"m": 8},
                },
            }
        }
        ev = normalize_event(msg)
        # bring custom fields into event.data (simulating pre-normalized injection)
        # In a full system, you may add a pre-step or transforms for this; for the test, we patch it.
        ev["data"]["sample_tool_input"] = ev["data"]["metadata"].get("sample_tool_input")
        ev["data"]["sample_meta"] = ev["data"]["metadata"].get("sample_meta")

        resume, patch = build_resume_from_mapping(ev, task.metadata["state"], node_output=None, mapping=task.skill.mapping_rules)
        self.assertEqual(resume.get("sample_tool_input"), {"k": 9})
        self.assertEqual(patch.get("tool_input", {}).get("sample"), {"k": 9})
        self.assertEqual(patch.get("metadata", {}).get("extra"), {"m": 8})


if __name__ == "__main__":
    unittest.main()

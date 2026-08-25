"""Tests for subscribe-time prompt download (the store's prompts leg).

Subscribing used to bring the SKILL but never its prompts — the runtime
cross-owner fetch persists nothing, so the customer's Prompts page never
had the author's prompts. `_download_skill_prompts` fetches every prompt
id referenced by the subscribed skill's diagram/config under the skill's
author and stores it in the subscribed_prompts store, which bulk cloud
push excludes (uploading an author's prompt from another account fails
"Prompt belongs to a different owner").
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import gui.ipc.w2p_handlers.skill_handler as sh


AUTHOR = "wechat_b603a407904569a4ea88f9ac"


class TestExtractSkillPromptIds:
    def test_finds_ids_in_diagram_and_config(self):
        skill = {
            "diagram": {"nodes": [{"inputsValues": {"promptSelection": {"content": "pr-330448"}}}]},
            "config": {"notes": "uses pr-287230 too"},
        }
        assert sh._extract_skill_prompt_ids(skill) == ["pr-287230", "pr-330448"]

    def test_handles_json_string_fields_and_dedup(self):
        skill = {"diagram": json.dumps({"a": "pr-111066", "b": "pr-111066"}), "config": None}
        assert sh._extract_skill_prompt_ids(skill) == ["pr-111066"]

    def test_no_ids(self):
        assert sh._extract_skill_prompt_ids({"diagram": {"nodes": []}}) == []


class TestDownloadSkillPrompts:
    def _run(self, tmp_path, *, skill, local_prompts, responses):
        prompt_handler = MagicMock()
        prompt_handler._load_all_prompts.return_value = local_prompts
        prompt_handler._get_subscribed_prompts_dir.return_value = Path(tmp_path)

        def fake_request(query, ctx, variables=None):
            pid = variables["input"]["id"]
            return responses.get(pid, {"data": {"queryPrompts": []}})

        with patch.dict("sys.modules", {}), \
             patch("gui.ipc.w2p_handlers.prompt_handler._load_all_prompts",
                   prompt_handler._load_all_prompts), \
             patch("gui.ipc.w2p_handlers.prompt_handler._get_subscribed_prompts_dir",
                   prompt_handler._get_subscribed_prompts_dir), \
             patch("gui.ipc.w2p_handlers.prompt_cloud_sync._get_cloud_context",
                   return_value={"owner": "customer@x"}), \
             patch("gui.ipc.w2p_handlers.prompt_cloud_sync._appsync_request",
                   side_effect=fake_request):
            sh._download_skill_prompts(skill)

    def test_downloads_missing_prompts_under_author(self, tmp_path):
        skill = {
            "owner": AUTHOR,
            "config": {"skill_owner": AUTHOR},
            "diagram": {"n": [{"promptSelection": {"content": "pr-330448"}}]},
        }
        prompt_payload = {"title": "飞鸽客服前台0", "sections": []}
        responses = {"pr-330448": {"data": {"queryPrompts": [
            {"id": "pr-330448", "owner": AUTHOR,
             "prompt": json.dumps(prompt_payload, ensure_ascii=False), "version": "1"},
        ]}}}

        self._run(tmp_path, skill=skill, local_prompts=[], responses=responses)

        saved = json.loads((Path(tmp_path) / "0_pr-330448.json").read_text(encoding="utf-8"))
        assert saved["id"] == "pr-330448"
        assert saved["title"] == "飞鸽客服前台0"

    def test_already_local_prompts_skipped(self, tmp_path):
        skill = {"owner": AUTHOR, "config": {},
                 "diagram": {"x": "pr-287230"}}
        self._run(tmp_path, skill=skill,
                  local_prompts=[{"id": "pr-287230"}], responses={})
        assert list(Path(tmp_path).glob("*.json")) == []

    def test_missing_on_server_logged_not_raised(self, tmp_path):
        """The dangling-reference case (skill references a prompt id that
        exists nowhere): must not raise, must not write files."""
        skill = {"owner": AUTHOR, "config": {},
                 "diagram": {"x": "pr-886478"}}
        self._run(tmp_path, skill=skill, local_prompts=[], responses={})
        assert list(Path(tmp_path).glob("*.json")) == []


class TestBulkPushExcludesSubscribed:
    def test_subscribed_source_filtered(self):
        prompts = [
            {"id": "pr-1", "source": "my_prompts"},
            {"id": "pr-330448", "source": "subscribed"},
            {"id": "pr-2", "source": "sample_prompts"},
        ]
        to_sync = [
            p for p in prompts
            if not p.get("readOnly") and p.get("id")
            and p.get("owner") != "system"
            and p.get("source") not in ("sample_prompts", "subscribed")
        ]
        assert [p["id"] for p in to_sync] == ["pr-1"]

"""A browser node's tool schema holds the page actions plus what its prompt names.

KEN 2026-10-26: every 商品上架 step sent all 54 shared-controller actions
(130 schema defs, 75KB) although the run only clicks, types and uploads.
"""
from browser_use.tools.service import Tools

from agent.ec_skills.browser_node.runner import (
    _default_allowed_actions,
    _filter_controller_actions,
)


def _controller_with_extras():
    tools = Tools()

    @tools.registry.action("Send a chat message")
    async def bu_send_chat(text: str):
        return text

    @tools.registry.action("Query the RAG store")
    async def bu_rag_query(query: str):
        return query

    return tools


def _kept(prompt_text, allowed=None, excluded=None):
    ctrl = _controller_with_extras()
    view = _filter_controller_actions(ctrl, allowed, excluded, node_name="t", prompt_text=prompt_text)
    return set(view.registry.registry.actions), ctrl


def test_prompt_without_extras_keeps_only_page_actions():
    kept, _ = _kept("打开商品发布页，上传主图，填写标题后点发布。")
    assert {"navigate", "click", "input", "upload_file", "done"} <= kept
    assert "bu_send_chat" not in kept and "bu_rag_query" not in kept


def test_extra_named_in_the_prompt_is_kept():
    kept, _ = _kept("When finished, call `bu_send_chat` with the summary.")
    assert "bu_send_chat" in kept
    assert "bu_rag_query" not in kept


def test_name_inside_a_longer_word_does_not_count():
    assert "bu_send_chat" not in (_default_allowed_actions(["click", "bu_send_chat"], "use bu_send_chat_v2") or [])


def test_explicit_allowed_list_wins():
    kept, _ = _kept("call bu_send_chat", allowed=["click", "bu_rag_query"])
    assert kept == {"click", "bu_rag_query", "done"}


def test_no_prompt_text_keeps_the_full_set():
    ctrl = _controller_with_extras()
    assert _filter_controller_actions(ctrl, None, None, node_name="t", prompt_text="") is ctrl


def test_shared_controller_is_not_modified():
    _, ctrl = _kept("plain page task")
    assert "bu_send_chat" in ctrl.registry.registry.actions

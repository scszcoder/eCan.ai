"""LightRAG's model calls are billed on their own knowledge-base line: every
request its OpenAI client makes to the llm-proxy carries X-Ecan-Source: lightrag
(it never carries a skill id -- LightRAG runs calls on its own worker tasks)."""

from unittest import mock

import openai


def test_launcher_labels_lightrag_calls(monkeypatch):
    from knowledge import lightrag_launcher as launcher
    monkeypatch.setenv("LLM_BINDING_HOST", "https://x.tcloudbase.com/api/llm-proxy/v1")
    monkeypatch.setenv("ECAN_USER_ID", "u1")
    original = openai.AsyncOpenAI.__init__
    try:
        launcher.patch_openai_client_for_lambda_proxy()
        client = openai.AsyncOpenAI(api_key="k", base_url="https://x.tcloudbase.com/api/llm-proxy/v1")
        headers = client.default_headers
        assert headers.get("X-Ecan-Source") == "lightrag"
        assert headers.get("X-User-Id") == "u1"
    finally:
        openai.AsyncOpenAI.__init__ = original


def test_rerank_proxy_labels_its_calls():
    src = open("gui/lightrag_rerank_proxy.py", encoding="utf-8").read()
    assert src.count("headers.setdefault('X-Ecan-Source', 'lightrag')") == 2

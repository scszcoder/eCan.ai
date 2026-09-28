"""Feige human-relevance judge (2026-09-28): judge_async called two helpers that
did not exist, so it never ran; it also went straight to api.openai.com. It is
now off by default and, when on, goes only through the eCan llm-proxy."""

import asyncio
import os
from types import SimpleNamespace
from unittest import mock

import pytest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import human_relevance_judge as hj


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for k in ("ECAN_HUMAN_JUDGE_ENABLED", "ECAN_HUMAN_JUDGE_MODEL", "ECAN_HUMAN_JUDGE_TIMEOUT_S"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(hj, "_JUDGE_LLM_CACHE", None)
    monkeypatch.setattr(hj, "_JUDGE_LLM_MODEL_KEY", "")


def test_off_by_default():
    assert hj.is_enabled() is False
    with mock.patch.dict(os.environ, {"ECAN_HUMAN_JUDGE_ENABLED": "1"}):
        assert hj.is_enabled() is True


def test_helpers_exist_and_read_env():
    assert hj._judge_model() == "qwen-plus"
    assert hj._judge_timeout_s() == 3.0
    with mock.patch.dict(os.environ, {"ECAN_HUMAN_JUDGE_MODEL": "m2", "ECAN_HUMAN_JUDGE_TIMEOUT_S": "5"}):
        assert hj._judge_model() == "m2" and hj._judge_timeout_s() == 5.0


def _mainwin(provider):
    cm = SimpleNamespace(llm_manager=SimpleNamespace(get_provider=lambda name: provider if name == "ecanai" else None))
    return SimpleNamespace(config_manager=cm)


def test_client_is_the_llm_proxy_never_a_vendor():
    proxy = "https://example.test/api/llm-proxy/v1"
    with mock.patch("app_context.AppContext.get_main_window", return_value=_mainwin({"name": "ecanai"})), \
         mock.patch("agent.ec_skills.llm_utils.llm_utils.extract_provider_config",
                    return_value={"api_key": "k", "base_url": proxy}):
        llm = hj._get_llm("qwen-plus")
    assert str(llm.openai_api_base).rstrip("/") == proxy


def test_no_proxy_url_means_no_client():
    with mock.patch("app_context.AppContext.get_main_window", return_value=_mainwin({"name": "ecanai"})), \
         mock.patch("agent.ec_skills.llm_utils.llm_utils.extract_provider_config",
                    return_value={"api_key": "k", "base_url": None}):
        with pytest.raises(RuntimeError):
            hj._get_llm("qwen-plus")


def test_judge_async_runs_without_name_errors():
    # With no proxy configured it must come back as a verdict, not a NameError.
    with mock.patch("app_context.AppContext.get_main_window", return_value=None):
        v = asyncio.run(hj.judge_async("有货吗", "亲，有的"))
    assert v.answered is False and v.reason == "llm_init_failed"

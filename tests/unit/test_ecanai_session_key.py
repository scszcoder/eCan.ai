"""Intl eCanAI without an account key uses the login token, and OPENAI_API_KEY is
never sent to another provider (2026-10-26: the browser step sent the OpenAI key
to the eCanAI proxy, which answered 401 "Invalid JWT format")."""
from agent.cloud_api import endpoints
from agent.ec_skills.llm_utils import llm_utils

ECANAI = {"name": "eCanAI", "provider": "ecanai", "api_key_env_vars": ["ECANAI_LLM_API_KEY"],
          "base_url": "https://proxy/v1", "default_model": "gpt-6-luna", "supported_models": []}


def test_no_account_key_gives_the_login_token(monkeypatch):
    monkeypatch.setattr(endpoints, "llm_proxy_session_token", lambda: "a.b.c")
    import utils.env.secure_store as ss
    monkeypatch.setattr(ss.secure_store, "get", lambda *a, **k: None)
    cfg = llm_utils.extract_provider_config(ECANAI, node_model_name="gpt-6-luna")
    assert cfg["api_key"] == "a.b.c"


def test_the_openai_env_key_never_reaches_another_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-secret")
    seen = {}
    monkeypatch.setattr(llm_utils, "_create_and_validate_browser_use_llm", lambda cfg: seen.update(cfg) or object())
    llm_utils.create_browser_use_llm_by_provider_type("ecanai", "gpt-6-luna", api_key=None, base_url="https://proxy/v1")
    assert seen["api_key"] != "sk-proj-secret"
    seen.clear()
    llm_utils.create_browser_use_llm_by_provider_type("openai", "gpt-5.5", api_key=None)
    assert seen["api_key"] == "sk-proj-secret"          # OpenAI itself still uses it

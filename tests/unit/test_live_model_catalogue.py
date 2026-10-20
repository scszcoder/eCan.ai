"""Skill-editor model choices come from the llm-proxy's live catalogue (the
server's model list), saved locally for offline use; the build-time
llm_providers.json is the last resort (2026-10-19: qwen3.8-flash was added on
the server but the LLM node only ever offered the bundled Qwen list)."""
import importlib
import json

import pytest

eu = importlib.import_module("gui.ecanai_utils")


def _providers():
    return [
        {"name": "eCanAI", "provider": "ecanai", "base_url": "https://proxy/v1", "supported_models": []},
        {"name": "Qwen", "provider": "dashscope", "supported_models": [
            {"name": "qwen3.7-plus", "model_id": "qwen3.7-plus", "display_name": "Qwen 3.7 Plus"},
            {"name": "qwen3.6-flash", "model_id": "qwen3.6-flash"}]},
        {"name": "DeepSeek", "provider": "deepseek", "supported_models": [{"name": "deepseek-chat"}]},
        {"name": "Ollama", "provider": "ollama", "supported_models": [{"name": "llama3"}]},
        {"name": "Mistral", "provider": "mistral", "supported_models": [{"name": "mistral-large"}]},
    ]


LIVE = [{"id": "qwen3.8-flash", "owned_by": ""}, {"id": "qwen3.7-plus", "owned_by": ""},
        {"id": "deepseek-v4-flash", "owned_by": "deepseek"}, {"id": "text-embedding-v3", "owned_by": ""}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(eu, "_live_file", lambda: tmp_path / "llm_live_models.json")
    monkeypatch.setattr(eu, "_models_cache", {"ts": 0.0, "ids": None, "rows": None})
    monkeypatch.setattr(eu, "_api_key", lambda t: "k")
    return tmp_path


def _qwen(ps):
    return [m["model_id"] for m in next(p for p in ps if p["name"] == "Qwen")["supported_models"]]


def test_live_catalogue_replaces_the_build_time_list_and_is_saved(env, monkeypatch):
    monkeypatch.setattr(eu, "_fetch_model_rows", lambda b, k: LIVE)
    ps = eu.merge_live_models_to_providers(_providers())
    assert _qwen(ps) == ["qwen3.8-flash", "qwen3.7-plus"]
    qwen = next(p for p in ps if p["name"] == "Qwen")
    assert qwen["supported_models"][1]["display_name"] == "Qwen 3.7 Plus"     # bundled label kept
    ds = next(p for p in ps if p["name"] == "DeepSeek")
    assert [m["model_id"] for m in ds["supported_models"]] == ["deepseek-v4-flash"]   # by owned_by
    assert next(p for p in ps if p["name"] == "Ollama")["supported_models"] == [{"name": "llama3"}]  # local: own list
    assert next(p for p in ps if p["name"] == "Mistral")["supported_models"] == [{"name": "mistral-large"}]  # not served
    assert "embedding" not in json.dumps(qwen)
    saved = json.loads((env / "llm_live_models.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in saved["models"]] == [r["id"] for r in LIVE]


def test_offline_uses_the_saved_list(env, monkeypatch):
    (env / "llm_live_models.json").write_text(json.dumps({"models": LIVE}), encoding="utf-8")
    monkeypatch.setattr(eu, "_fetch_model_rows", lambda b, k: None)
    ps = eu.merge_live_models_to_providers(_providers())
    assert _qwen(ps) == ["qwen3.8-flash", "qwen3.7-plus"]
    assert next(p for p in ps if p["name"] == "Qwen")["models_source"] == "saved"


def test_nothing_live_or_saved_keeps_the_build_time_list(env, monkeypatch):
    monkeypatch.setattr(eu, "_fetch_model_rows", lambda b, k: None)
    ps = eu.merge_live_models_to_providers(_providers())
    assert _qwen(ps) == ["qwen3.7-plus", "qwen3.6-flash"]


def test_ecanai_row_gets_the_same_catalogue(env, monkeypatch):
    monkeypatch.setattr(eu, "_fetch_model_rows", lambda b, k: LIVE)
    ps = eu.merge_ecanai_models_to_providers(_providers(), provider_type="llm")
    ecan = next(p for p in ps if p["name"] == "eCanAI")
    assert [m["model_id"] for m in ecan["supported_models"]] == ["qwen3.8-flash", "qwen3.7-plus", "deepseek-v4-flash"]


def test_speech_image_video_models_are_not_chat_choices(env, monkeypatch):
    live = [{"id": i, "owned_by": "qwen"} for i in
            ("qwen3.8-flash", "qwen3-vl-plus", "qwen3-omni-flash", "wan2.2-t2v-plus", "cosyvoice-v2",
             "paraformer-v2", "qwen-image", "qwen3-tts-flash", "qwen3-asr-flash")]
    monkeypatch.setattr(eu, "_fetch_model_rows", lambda b, k: live)
    assert _qwen(eu.merge_live_models_to_providers(_providers())) == [
        "qwen3.8-flash", "qwen3-vl-plus", "qwen3-omni-flash"]

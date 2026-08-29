import json
import threading

import knowledge.lightrag_server as server_module
from knowledge.lightrag_server import LightragServer


def test_build_env_applies_cached_vllm_limit_before_token_budget(tmp_path, monkeypatch):
    model = "Qwen3.8-27B-AWQ-INT4"
    (tmp_path / "vllm_max_model_len.json").write_text(
        json.dumps({model: 8196}), encoding="utf-8"
    )

    config = {
        "LOG_DIR": str(tmp_path),
        "LLM_BINDING": "openai",
        "LLM_BINDING_HOST": "https://example.invalid/v1",
        "LLM_MODEL": model,
        "MAX_TOTAL_TOKENS": "35000",
        "OPENAI_LLM_MAX_COMPLETION_TOKENS": "9000",
    }
    manager = type("Manager", (), {"get_effective_config": lambda self: config})()
    monkeypatch.setattr(server_module, "get_config_manager", lambda: manager)

    server = LightragServer.__new__(LightragServer)
    server.extra_env = {}
    server.is_frozen = False
    server.max_restarts = 3
    server.restart_cooldown = 30
    server._vllm_cache = {}
    server._vllm_cache_lock = threading.Lock()
    server._vllm_cache_file = None

    env = server.build_env()

    assert env["MAX_TOTAL_TOKENS"] == "8196"
    assert env["OPENAI_LLM_MAX_COMPLETION_TOKENS"] == "2732"
    assert env["QUERY_OPENAI_LLM_MAX_COMPLETION_TOKENS"] == "1024"


def test_create_log_files_reuses_launch_environment(tmp_path, monkeypatch):
    server = LightragServer.__new__(LightragServer)
    launch_env = {"LOG_DIR": str(tmp_path)}
    monkeypatch.setattr(
        server,
        "build_env",
        lambda: (_ for _ in ()).throw(AssertionError("environment was rebuilt")),
    )

    stdout, stderr, stdout_path, stderr_path = server._create_log_files(launch_env)
    try:
        assert stdout_path == str(tmp_path / "lightrag_server.log")
        assert stderr_path == str(tmp_path / "lightrag_server_error.log")
    finally:
        stdout.close()
        stderr.close()

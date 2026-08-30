"""eCanAI dynamic model discovery for Settings tabs (gui/ecanai_utils.py).

The Settings LLM/Embedding/Rerank tabs' model column renders
provider.supported_models; the merge fills the eCanAI row from a live
GET <llm-proxy>/v1/models with the synced account API key, partitioned by
name heuristics (embedding/rerank/other). Live-verified 2026-08-30:
llm=[qwen-plus], embedding=[text-embedding-v3], rerank=[] (server has no
rerank provider yet).
"""

from unittest.mock import patch

import gui.ecanai_utils as eu

IDS = ["qwen-plus", "qwen-max", "text-embedding-v3", "gte-rerank-v2"]


def _provider():
    return {"name": "eCanAI", "provider": "ecanai",
            "base_url": "https://x.example/api/llm-proxy/v1", "default_model": ""}


def _merge(role, ids=IDS, api_key="k"):
    eu._models_cache["ts"] = 0.0
    eu._models_cache["ids"] = None
    with patch.object(eu, "_api_key", return_value=api_key), \
         patch.object(eu, "_fetch_model_ids", return_value=ids):
        return eu.merge_ecanai_models_to_providers([_provider()], provider_type=role)[0]


def test_llm_gets_chat_models_only():
    row = _merge("llm")
    assert [m["name"] for m in row["supported_models"]] == ["qwen-plus", "qwen-max"]
    assert row["default_model"] == "qwen-plus"


def test_embedding_and_rerank_partitions():
    assert [m["name"] for m in _merge("embedding")["supported_models"]] == ["text-embedding-v3"]
    assert [m["name"] for m in _merge("rerank")["supported_models"]] == ["gte-rerank-v2"]


def test_no_key_leaves_provider_untouched():
    row = _merge("llm", api_key="")
    assert "supported_models" not in row


def test_fetch_failure_leaves_provider_untouched():
    eu._models_cache["ts"] = 0.0
    eu._models_cache["ids"] = None
    with patch.object(eu, "_api_key", return_value="k"), \
         patch.object(eu, "_fetch_model_ids", return_value=None):
        row = eu.merge_ecanai_models_to_providers([_provider()], provider_type="llm")[0]
    assert "supported_models" not in row


def test_non_ecanai_rows_ignored():
    rows = [{"name": "OpenAI", "provider": "openai", "base_url": "https://x"}]
    with patch.object(eu, "_api_key", return_value="k"), \
         patch.object(eu, "_fetch_model_ids", return_value=IDS):
        out = eu.merge_ecanai_models_to_providers(rows, provider_type="llm")
    assert "supported_models" not in out[0]


def test_cache_avoids_refetch():
    eu._models_cache["ts"] = 0.0
    eu._models_cache["ids"] = None
    with patch.object(eu, "_api_key", return_value="k"), \
         patch.object(eu, "_fetch_model_ids", return_value=IDS) as fetch:
        eu.merge_ecanai_models_to_providers([_provider()], provider_type="llm")
        eu.merge_ecanai_models_to_providers([_provider()], provider_type="embedding")
    assert fetch.call_count == 1

"""Product-knowledge embedding model: config, query instruction, punctuation."""
import numpy as np
import pytest

from knowledge.ks import service as service_mod
from knowledge.ks.embedding import OpenAICompatibleEmbedder, embed_query, wants_instruction


class _MW:
    def __init__(self, path):
        self.my_ecb_data_homepath = str(path)
        self.log_user = "tester"


@pytest.fixture
def mw(tmp_path, monkeypatch):
    stored = {}

    class FakeStore:
        def get(self, k):
            return stored.get(k)

        def set(self, k, v):
            stored[k] = v

        def delete(self, k):
            stored.pop(k, None)

    import utils.env.secure_store as ss
    monkeypatch.setattr(ss, "secure_store", FakeStore())
    service_mod.reset_services()
    yield _MW(tmp_path)
    service_mod.reset_services()


def test_default_is_app_embedder(mw):
    assert service_mod.embedder_config(mw)["mode"] == "app"


def test_openai_compatible_config_is_saved_without_the_key_in_the_file(mw, tmp_path):
    cfg = service_mod.save_embedder_config("openai", "http://127.0.0.1:1234/v1", "text-embedding-qwen3-embedding-8b",
                                           api_key="sk-secret", main_window=mw)
    assert cfg["mode"] == "openai" and cfg["has_api_key"]
    text = (tmp_path / "knowledge_service" / "embedder.json").read_text(encoding="utf-8")
    assert "sk-secret" not in text
    e = service_mod._configured_embedder(mw)
    assert isinstance(e, OpenAICompatibleEmbedder) and e.api_key == "sk-secret" and e.query_instruction
    with pytest.raises(ValueError):
        service_mod.save_embedder_config("openai", "ftp://x", "m", main_window=mw)


def test_instruction_only_for_instruction_models():
    assert wants_instruction("text-embedding-qwen3-embedding-8b")
    assert not wants_instruction("text-embedding-v3")
    assert not OpenAICompatibleEmbedder("http://x/v1", "bge-m3").query_instruction


def test_query_gets_instruction_and_loses_trailing_punctuation():
    seen = []

    class Fake(OpenAICompatibleEmbedder):
        def embed(self, texts):
            seen.extend(texts)
            return np.ones((len(texts), 4), dtype=np.float32) / 2

    e = Fake("http://x/v1", "Qwen3-Embedding-8B")
    embed_query(e, "会缩水吗？")
    assert seen[-1].startswith("Instruct: ") and seen[-1].endswith("Query:会缩水吗")

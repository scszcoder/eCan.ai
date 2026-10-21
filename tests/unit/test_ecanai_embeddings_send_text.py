"""eCanAI embeddings go to the llm-proxy's DashScope model, which takes text only
(alpha 2026-10-21: saving 店铺规则 failed with 'contents is neither str nor list
of str' -- OpenAIEmbeddings sent tiktoken token ids by default)."""
from unittest.mock import patch

from agent.memory.embedding_utils import EmbeddingFactory


def test_ecanai_embeddings_send_the_text_not_token_ids():
    with patch("utils.env.secure_store.secure_store.get", return_value="sk-test"), \
            patch("utils.env.secure_store.get_current_username", return_value="u"):
        emb = EmbeddingFactory.create_embeddings(provider_name="ecanai", model_name="text-embedding-v3")
    assert type(emb).__name__ == "OpenAIEmbeddings"
    assert emb.check_embedding_ctx_length is False

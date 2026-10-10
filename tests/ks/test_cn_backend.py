"""CN backend conventions (eCan_lambda): session tokens, DATABASE_URL, llm_proxy embeddings."""
import json
import time

import jwt
import numpy as np
import pytest

from knowledge.ks.identity import AuthError, CloudBaseVerifier, EcanSessionVerifier, IdentityRegistry, strip_bearer

SECRET = "test-ecan-jwt-secret"


def _session(sub="wx_openid_AbC", **extra):
    now = int(time.time())
    return jwt.encode({"sub": sub, "iat": now, "exp": now + 3600, **extra}, SECRET, algorithm="HS256")


def test_session_token_identity_is_case_sensitive_sub():
    reg = IdentityRegistry([EcanSessionVerifier(SECRET)])
    p = reg.verify(_session())
    assert p.user_id == "wx_openid_AbC" and p.source == "ecan-session"
    assert reg.verify(_session("Shop@Example.com")).email_lc == "shop@example.com"


def test_session_token_prefixes_are_stripped():
    tok = _session()
    assert strip_bearer(f"Bearer tenant1/@@/{tok}") == tok
    assert IdentityRegistry([EcanSessionVerifier(SECRET)]).verify(f"Bearer t/@@/{tok}").user_id == "wx_openid_AbC"


@pytest.mark.parametrize("token,msg", [
    (lambda: jwt.encode({"sub": "x", "exp": int(time.time()) - 3600}, SECRET, algorithm="HS256"), "expired"),
    (lambda: _session(typ="end_user"), "end-user"),
    (lambda: jwt.encode({"sub": "x", "exp": int(time.time()) + 60}, "wrong-secret", algorithm="HS256"), "invalid"),
])
def test_bad_session_tokens(token, msg):
    with pytest.raises(AuthError) as e:
        IdentityRegistry([EcanSessionVerifier(SECRET)]).verify(token())
    assert msg in str(e.value)


def test_failed_hs256_never_falls_through_to_cloudbase(monkeypatch):
    called = []
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: called.append(1))
    reg = IdentityRegistry([EcanSessionVerifier(SECRET), CloudBaseVerifier("sccb0-test")])
    bad = jwt.encode({"sub": "x", "exp": int(time.time()) + 60}, "wrong", algorithm="HS256")
    with pytest.raises(AuthError):
        reg.verify(bad)
    assert called == []


def test_cloudbase_identity_field_order(monkeypatch):
    import httpx

    class R:
        status_code = 200

        def json(self):
            return {"sub": "cb-sub", "customUserId": "custom-1", "uid": "u"}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
    assert CloudBaseVerifier("sccb0-test").verify("opaque").user_id == "custom-1"


def test_database_url_conventions(monkeypatch):
    from knowledge.ks.server import db_from_env
    monkeypatch.delenv("KS_DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://ecanai:pw@172.17.0.16:5432/appdb")
    monkeypatch.setenv("KS_DB_SCHEMA", "knowledge")
    monkeypatch.setenv("PGSSL", "false")
    url, schema, args = db_from_env("sqlite:///x.db")
    assert url == "postgresql+psycopg://ecanai:pw@172.17.0.16:5432/appdb"
    assert schema == "knowledge" and args == {"sslmode": "disable", "connect_timeout": 10}
    monkeypatch.delenv("PGSSL")
    assert db_from_env("sqlite:///x.db")[2]["sslmode"] == "require"


def test_llm_proxy_embedder_request_and_billing_owner(svc, shop, monkeypatch):
    import httpx
    from knowledge.ks.embedding import LlmProxyEmbedder
    bodies = []

    class Resp:
        status_code = 200
        text = ""

        def __init__(self, n):
            self._n = n

        def json(self):
            return {"data": [{"index": i, "embedding": list(np.ones(8) * (i + 1))} for i in range(self._n)]}

    def fake_post(self, url, json=None, headers=None):
        bodies.append((url, json, headers))
        return Resp(len(json["input"]))

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    e = LlmProxyEmbedder("https://sccb0-x.service.tcloudbase.com/api/llm-proxy", "internal-tok",
                         model="text-embedding-v3", dimensions=8, batch_size=2)
    assert e.embed(["a", "b", "c"]).shape == (3, 8)
    url, body, headers = bodies[0]
    assert url.endswith("/api/llm-proxy/v1/embeddings")
    assert body["action"] == "embeddings" and body["internalToken"] == "internal-tok"
    assert body["provider"] == "qwen" and body["source"] == "lightrag" and body["dimensions"] == 8
    assert len(bodies) == 2  # batched

    # A search is billed to the tenant owner, not a generic account.
    svc.embedder = e
    svc.retriever.embedder = e
    svc.indexes.invalidate(shop["tid"])
    bodies.clear()
    svc.search("会缩水吗", platform_item_id="6600001")
    assert bodies and bodies[-1][1]["owner"] == svc.local.user_id

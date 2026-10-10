"""Identity verification and permissions (docs/RAG_ENTERPRISE_PLAN.md §2.3)."""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from knowledge.ks.authz import PermissionDenied
from knowledge.ks.identity import AuthError, IdentityRegistry, JWKSVerifier, LocalVerifier, Principal

ISS = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(rsa_key, tmp_path):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key()))
    jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
    cache = tmp_path / "jwks.json"
    cache.write_text(json.dumps({"keys": [jwk]}))
    v = JWKSVerifier("cognito", ISS, jwks_url="http://127.0.0.1:1/unreachable", audience="client-123",
                     cache_path=str(cache))
    return v


def _token(key, **claims):
    now = int(time.time())
    body = {"iss": ISS, "sub": "user-1", "email": "Alice@Shop.com", "aud": "client-123", "iat": now, "exp": now + 600}
    body.update(claims)
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": "k1"})


# ---- identity ---------------------------------------------------------------------
def test_valid_token_uses_cached_jwks_when_offline(verifier, rsa_key):
    p = verifier.verify(_token(rsa_key))
    assert p.user_id == "user-1" and p.email_lc == "alice@shop.com" and p.source == "cognito"


def test_access_token_client_id_is_accepted(verifier, rsa_key):
    tok = _token(rsa_key, aud=None, client_id="client-123")
    assert verifier.verify(tok).user_id == "user-1"


@pytest.mark.parametrize("claims,msg", [
    ({"exp": int(time.time()) - 3600}, "expired"),
    ({"aud": "other-app"}, "another application"),
    ({"iss": "https://evil.example"}, "invalid"),
])
def test_bad_tokens_are_rejected(verifier, rsa_key, claims, msg):
    with pytest.raises(AuthError) as e:
        verifier.verify(_token(rsa_key, **claims))
    assert msg in str(e.value)


def test_forged_signature_is_rejected(verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        verifier.verify(_token(other))


def test_unverified_decode_is_not_enough(verifier, rsa_key):
    # The desktop app decodes tokens without checking signatures; KS must not.
    tampered = _token(rsa_key)[:-4] + "AAAA"
    with pytest.raises(AuthError):
        verifier.verify(tampered)


def test_registry_routes_by_issuer(verifier, rsa_key):
    local = LocalVerifier(secret="s3cret")
    reg = IdentityRegistry([verifier, local])
    assert reg.verify(_token(rsa_key)).source == "cognito"
    assert reg.verify(local.issue("admin", "admin@corp.cn")).source == "local"
    with pytest.raises(AuthError):
        reg.verify(jwt.encode({"iss": "https://unknown", "sub": "x"}, "k", algorithm="HS256"))
    with pytest.raises(AuthError):
        reg.verify("")


# ---- authorisation ------------------------------------------------------------------
def P(email, uid=None, **kw):
    return Principal(user_id=uid or email, email=email, **kw)


@pytest.fixture
def team(svc, shop):
    tid = shop["tid"]
    for email, role in (("admin@shop.com", "admin"), ("ed@shop.com", "editor"), ("view@shop.com", "viewer")):
        svc.save_member(email, role, status="active")
    return tid


def test_non_member_cannot_read_or_search(svc, team):
    stranger = P("x@elsewhere.com")
    with pytest.raises(PermissionDenied):
        svc.search("材质", platform_item_id="6600001", principal=stranger)
    with pytest.raises(PermissionDenied):
        svc.list_products(principal=stranger)


def test_viewer_reads_but_cannot_write(svc, team):
    v = P("view@shop.com")
    assert svc.search("这件是什么材质", platform_item_id="6600001", principal=v)["product"]["code"] == "TS-001"
    with pytest.raises(PermissionDenied):
        svc.save_product({"code": "N1", "title": "新品"}, principal=v)
    with pytest.raises(PermissionDenied):
        svc.save_policy("returns", "x", principal=v)


def test_editor_writes_but_cannot_administer(svc, team):
    e = P("ed@shop.com")
    assert svc.save_product({"code": "N1", "title": "新品"}, principal=e)["code"] == "N1"
    with pytest.raises(PermissionDenied):
        svc.save_member("new@shop.com", "viewer", principal=e)
    with pytest.raises(PermissionDenied):
        svc.reindex(principal=e)


def test_confidential_kb_needs_an_explicit_grant(svc, team):
    kb = svc.catalog_kb(team)
    svc.update_kb(kb["id"], sensitivity="confidential")
    v = P("view@shop.com")
    with pytest.raises(PermissionDenied):
        svc.search("材质", platform_item_id="6600001", principal=v)
    # Admins still manage it; a viewer gets in with a grant.
    assert svc.search("材质", platform_item_id="6600001", principal=P("admin@shop.com"))["product"]
    svc.set_grant(kb["id"], "user", "view@shop.com", "read")
    assert svc.search("材质", platform_item_id="6600001", principal=v)["product"]


def test_group_grant(svc, team):
    kb = svc.catalog_kb(team)
    svc.update_kb(kb["id"], sensitivity="confidential")
    members = {m["email"]: m for m in svc.access_view()["members"]}
    g = svc.save_group("售后组", [members["view@shop.com"]["id"]])
    svc.set_grant(kb["id"], "group", g["id"], "read")
    assert svc.search("材质", platform_item_id="6600001", principal=P("view@shop.com"))["product"]
    svc.delete_group(g["id"])
    with pytest.raises(PermissionDenied):
        svc.search("材质", platform_item_id="6600001", principal=P("view@shop.com"))


def test_store_agent_grant_without_membership(svc, team, shop):
    # The customer-service agent of a store reads the catalog through a store grant.
    kb = svc.catalog_kb(team)
    agent = Principal(user_id="agent:qa-1", source="agent", agent_id="qa-1", store_id=shop["tmall"]["id"])
    with pytest.raises(PermissionDenied):
        svc.search("材质", platform_item_id="6600001", principal=agent)
    svc.set_grant(kb["id"], "store", shop["tmall"]["id"], "read")
    assert svc.search("材质", platform_item_id="6600001", principal=agent)["product"]
    with pytest.raises(PermissionDenied):
        svc.save_product({"code": "Z", "title": "z"}, principal=agent)


def test_disabled_member_loses_access_despite_grant(svc, team):
    kb = svc.catalog_kb(team)
    svc.set_grant(kb["id"], "user", "view@shop.com", "manage")
    m = next(m for m in svc.access_view()["members"] if m["email"] == "view@shop.com")
    svc.save_member("view@shop.com", "viewer", status="disabled", member_id=m["id"])
    with pytest.raises(PermissionDenied):
        svc.search("材质", platform_item_id="6600001", principal=P("view@shop.com"))


def test_invite_links_on_first_sign_in_and_domain_auto_join(svc, team):
    svc.save_member("invitee@shop.com", "editor")  # status invited
    p = P("invitee@shop.com", uid="cognito-sub-9")
    assert svc.authz.membership(p, team) is None  # invited, not yet active
    assert svc.authz.link_user(p, team)["status"] == "active"
    assert svc.authz.membership(p, team).user_id == "cognito-sub-9"

    stranger = P("bob@corp.cn", uid="sub-bob")
    assert svc.authz.link_user(stranger, team) is None
    svc.set_email_domain("corp.cn")
    assert svc.authz.link_user(stranger, team)["role"] == "viewer"


def test_last_owner_is_protected_and_admins_cannot_create_owners(svc, team):
    owner = next(m for m in svc.access_view()["members"] if m["role"] == "owner")
    with pytest.raises(ValueError):
        svc.save_member(owner["email"], "admin", member_id=owner["id"])
    with pytest.raises(ValueError):
        svc.remove_member(owner["id"])
    with pytest.raises(PermissionDenied):
        svc.save_member("boss@shop.com", "owner", principal=P("admin@shop.com"))


def test_cross_tenant_ids_are_rejected(svc, team, shop):
    a = P("admin@shop.com")
    with pytest.raises(PermissionDenied):
        svc.save_policy("returns", "x", store_id=shop["other_store"]["id"], principal=a)
    other_kb = svc.catalog_kb(shop["other_tid"])
    with pytest.raises(PermissionDenied):
        svc.set_grant(other_kb["id"], "user", "admin@shop.com", "manage")
    with pytest.raises(PermissionDenied):
        svc.search("材质", tenant_id=shop["other_tid"], principal=a)


def test_audit_records_admin_actions(svc, team):
    actions = [a["action"] for a in svc.list_audit()]
    assert "member.save" in actions


# ---- CloudBase (CN app sign-in) ------------------------------------------------------
class _Resp:
    def __init__(self, code, body=None):
        self.status_code, self._body = code, body or {}

    def json(self):
        return self._body


def test_cloudbase_tokens_are_checked_with_cloudbase_and_cached(monkeypatch):
    from knowledge.ks.identity import CloudBaseVerifier
    calls = []

    def fake_get(url, timeout=None, headers=None):
        calls.append(headers["Authorization"])
        if headers["Authorization"].endswith("good"):
            return _Resp(200, {"sub": "cb-user-1", "email": "Shop@QQ.com", "name": "店主"})
        return _Resp(401)

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)
    v = CloudBaseVerifier("sccb0-test")
    reg = IdentityRegistry([v])
    p = reg.verify("opaque-good")  # not even a JWT: still checked with CloudBase
    assert p.user_id == "cb-user-1" and p.email_lc == "shop@qq.com" and p.source == "cloudbase"
    reg.verify("opaque-good")
    assert len(calls) == 1  # cached
    with pytest.raises(AuthError):
        reg.verify("opaque-bad")

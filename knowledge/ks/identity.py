"""
Identity for the Knowledge Service: who is calling.

App sign-in stays with Cognito / CloudBase. KS never trusts a token it has not
verified itself (the desktop app decodes tokens without checking signatures;
a shared server must not). Verifiers:

- ``JWKSVerifier``    RS256/ES256 tokens from Cognito, CloudBase or any OIDC
                      provider, verified against the issuer's JWKS. The key
                      set is cached on disk so an on-prem server keeps
                      verifying when the internet link is down.
- ``LocalVerifier``   HS256 tokens the KS server issues itself for local
                      accounts (bootstrap admin on an on-prem server).

Authorisation (what the caller may do) lives in ``authz.py``.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import jwt

from knowledge.ks._log import logger


class AuthError(Exception):
    """Token missing, invalid, expired or from an unknown issuer."""


@dataclass
class Principal:
    user_id: str
    email: str = ""
    name: str = ""
    source: str = "local"          # local | cognito | cloudbase | oidc | agent
    agent_id: str = ""             # set when an agent acts for this principal
    store_id: str = ""             # store the agent is serving, when known
    claims: Dict[str, Any] = field(default_factory=dict)
    # Only an email the sign-in provider vouches for may match an invite,
    # an email grant or a domain auto-join.
    email_verified: bool = False

    @property
    def email_lc(self) -> str:
        return (self.email or "").strip().lower()

    @property
    def verified_email(self) -> str:
        return self.email_lc if self.email_verified else ""

    @property
    def domain(self) -> str:
        e = self.verified_email
        return e.split("@", 1)[1] if "@" in e else ""

    def to_dict(self) -> Dict[str, Any]:
        return {"user_id": self.user_id, "email": self.email, "name": self.name, "source": self.source,
                "agent_id": self.agent_id, "store_id": self.store_id}


def local_principal(user: str) -> Principal:
    """The signed-in desktop user (the app already authenticated them)."""
    user = (user or "local-user").strip()
    return Principal(user_id=user, email=user if "@" in user else "", name=user, source="local",
                     email_verified=True)


# User ids from different sign-in systems live in one table, so each external
# provider's subject is prefixed with its namespace ("tcb:<uid>", "ecan:<sub>",
# "cognito:<sub>"); a subject from one provider can never collide with another's.
# Server-managed local accounts keep bare ids.
NAMESPACES = ("cognito", "oidc", "tcb", "ecan")


def namespaced(ns: str, subject: str) -> str:
    return f"{ns}:{subject}"


def subject_of(user_id: str) -> str:
    """The provider's own subject (what billing and the CN backend know)."""
    ns, sep, rest = (user_id or "").partition(":")
    return rest if sep and ns in NAMESPACES else (user_id or "")


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("true", "1", "yes")


class JWKSVerifier:
    def __init__(self, name: str, issuer: str, jwks_url: Optional[str] = None, audience: Optional[str] = None,
                 user_claim: str = "sub", email_claim: str = "email", name_claim: str = "name",
                 algorithms: Optional[List[str]] = None, cache_path: Optional[str] = None, leeway: int = 60):
        self._forced_at = 0.0
        self.name = name
        self.issuer = issuer.rstrip("/")
        self.jwks_url = jwks_url or f"{self.issuer}/.well-known/jwks.json"
        self.audience = audience
        self.user_claim, self.email_claim, self.name_claim = user_claim, email_claim, name_claim
        self.algorithms = algorithms or ["RS256", "ES256"]
        self.cache_path = cache_path
        self.leeway = leeway
        self._keys: Dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    @classmethod
    def cognito(cls, region: str, user_pool_id: str, client_id: Optional[str] = None, cache_dir: Optional[str] = None):
        issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        cache = os.path.join(cache_dir, f"jwks_cognito_{user_pool_id}.json") if cache_dir else None
        return cls("cognito", issuer, audience=client_id, cache_path=cache)

    def _load_jwks(self, force: bool = False) -> None:
        with self._lock:
            if self._keys and not force and time.time() - self._fetched_at < 3600:
                return
            data = None
            try:
                import httpx
                resp = httpx.get(self.jwks_url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if self.cache_path:
                    os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
                    with open(self.cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f)
            except Exception as e:
                if self.cache_path and os.path.exists(self.cache_path):
                    logger.warning(f"[KS] JWKS fetch failed for {self.name} ({e}); using cached keys")
                    with open(self.cache_path, encoding="utf-8") as f:
                        data = json.load(f)
                elif not self._keys:
                    raise AuthError(f"cannot load signing keys for {self.name}: {e}")
            if data:
                self._set_keys(data)

    def _set_keys(self, data: Dict[str, Any]) -> None:
        keys = {}
        for jwk in data.get("keys", []):
            try:
                keys[jwk.get("kid")] = jwt.PyJWK(jwk).key
            except Exception as e:
                logger.debug(f"[KS] skipping JWK {jwk.get('kid')}: {e}")
        self._keys = keys
        self._fetched_at = time.time()

    def set_jwks(self, data: Dict[str, Any]) -> None:
        """Install a key set directly (tests, air-gapped installs)."""
        with self._lock:
            self._set_keys(data)

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise AuthError(f"malformed token: {e}")
        kid = header.get("kid")
        if kid not in self._keys:
            # A new kid means key rotation, but unauthenticated callers can send
            # any kid: refetch at most once a minute.
            force = bool(self._keys) and time.time() - self._forced_at >= 60
            if force:
                self._forced_at = time.time()
            self._load_jwks(force=force)
        key = self._keys.get(kid)
        if key is None:
            raise AuthError("token signed with an unknown key")
        try:
            claims = jwt.decode(token, key=key, algorithms=self.algorithms, issuer=self.issuer, leeway=self.leeway,
                                options={"verify_aud": False})
        except jwt.ExpiredSignatureError:
            raise AuthError("token expired")
        except jwt.PyJWTError as e:
            raise AuthError(f"invalid token: {e}")
        if self.audience:
            # Cognito ID tokens carry aud; access tokens carry client_id instead.
            aud = claims.get("aud") or claims.get("client_id")
            auds = aud if isinstance(aud, list) else [aud]
            if self.audience not in auds:
                raise AuthError("token issued for another application")
        user = str(claims.get(self.user_claim) or "")
        if not user:
            raise AuthError(f"token has no {self.user_claim}")
        return Principal(user_id=namespaced(self.name, user), email=str(claims.get(self.email_claim) or ""),
                         name=str(claims.get(self.name_claim) or claims.get("username") or ""),
                         source=self.name, claims=claims, email_verified=_truthy(claims.get("email_verified")))


class LocalVerifier:
    """Accounts managed by the KS server itself (on-prem bootstrap admin)."""
    name = "local"

    def __init__(self, secret: Optional[str] = None, issuer: str = "ecan-ks", ttl_s: int = 12 * 3600):
        self.secret = secret or secrets.token_urlsafe(32)
        self.issuer = issuer
        self.ttl_s = ttl_s

    def issue(self, user_id: str, email: str = "", name: str = "") -> str:
        now = int(time.time())
        return jwt.encode({"iss": self.issuer, "sub": user_id, "email": email, "name": name,
                           "iat": now, "exp": now + self.ttl_s}, self.secret, algorithm="HS256")

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self.secret, algorithms=["HS256"], issuer=self.issuer)
        except jwt.ExpiredSignatureError:
            raise AuthError("token expired")
        except jwt.PyJWTError as e:
            raise AuthError(f"invalid token: {e}")
        # Accounts this server manages itself: the admin set the email.
        return Principal(user_id=claims["sub"], email=claims.get("email", ""), name=claims.get("name", ""),
                         source="local", claims=claims, email_verified=True)


class CloudBaseVerifier:
    """Tencent CloudBase sign-in (CN app). CloudBase does not publish a JWKS
    for its access tokens, so each token is introspected with the issuer
    (GET /auth/v1/user/me) and the result is cached until the token expires
    (at most ``cache_s``)."""
    name = "cloudbase"

    def __init__(self, env_id: str, cache_s: int = 300, timeout: float = 8.0, base_url: Optional[str] = None):
        self.env_id = env_id
        self.base_url = (base_url or f"https://{env_id}.api.tcloudbasegateway.com").rstrip("/")
        self.issuer = self.base_url
        self.cache_s = cache_s
        self.timeout = timeout
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def _expiry(self, token: str) -> float:
        try:
            exp = jwt.decode(token, options={"verify_signature": False}).get("exp")
            exp = float(exp) / (1000 if exp and float(exp) > 1e11 else 1) if exp else 0
        except Exception:
            exp = 0
        cap = time.time() + self.cache_s
        return min(exp, cap) if exp else cap

    def verify(self, token: str) -> Principal:
        import hashlib
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[1] > time.time():
                return hit[0]
        import httpx
        try:
            r = httpx.get(f"{self.base_url}/auth/v1/user/me", timeout=self.timeout,
                          headers={"Authorization": f"Bearer {token}"})
        except Exception as e:
            raise AuthError(f"cannot reach CloudBase to check the sign-in: {e}")
        if r.status_code in (401, 403):
            raise AuthError("CloudBase sign-in is invalid or expired")
        if r.status_code >= 400:
            raise AuthError(f"CloudBase sign-in check failed (HTTP {r.status_code})")
        u = r.json() or {}
        # Same order as the CN backend (eCan_lambda ws/index.js, ecbAccountManager).
        uid = str(u.get("customUserId") or u.get("custom_user_id") or u.get("sub") or u.get("user_id")
                  or u.get("uid") or u.get("uuid") or "")
        if not uid:
            raise AuthError("CloudBase did not return a user id")
        p = Principal(user_id=namespaced("tcb", uid), email=str(u.get("email") or ""),
                      name=str(u.get("name") or u.get("nickname") or u.get("username") or u.get("phone_number") or ""),
                      source="cloudbase", claims=u,
                      email_verified=_truthy(u.get("email_verified") or u.get("emailVerified")))
        with self._lock:
            if len(self._cache) > 5000:
                self._cache.clear()
            self._cache[key] = (p, self._expiry(token))
        return p


def strip_bearer(token: str) -> str:
    """'Bearer x' -> 'x', and drop a '<tenant>/@@/' prefix the CN gateway may add."""
    t = (token or "").strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    if "/@@/" in t:
        t = t.split("/@@/", 1)[1]
    return t


class EcanSessionVerifier:
    """The CN backend's 30-day HTTP session token (HS256, ECAN_JWT_SECRET),
    minted by mintHttpSessionToken / registerWeChatSession. ``sub`` is the
    account key the GraphQL backend and rag_* use (openid or user identifier);
    it is case-sensitive."""
    name = "ecan-session"
    issuer = ""  # these tokens carry no iss

    def __init__(self, secret: str, leeway: int = 60):
        if not secret:
            raise ValueError("ECAN_JWT_SECRET is required")
        self._secret = secret
        self.leeway = leeway

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._secret, algorithms=["HS256"], leeway=self.leeway,
                                options={"require": ["sub", "exp"]})
        except jwt.ExpiredSignatureError:
            raise AuthError("eCan session expired; sign in again")
        except jwt.PyJWTError as e:
            raise AuthError(f"invalid eCan session token: {e}")
        if claims.get("typ") == "end_user":
            raise AuthError("end-user tokens cannot access the knowledge service")
        sub = str(claims["sub"])
        # sub is an account key, not a verified email (and userIdentifier comes
        # from the client), so the token only carries an email if it says so.
        email = str(claims.get("email") or "") if _truthy(claims.get("email_verified")) else ""
        return Principal(user_id=namespaced("ecan", sub), email=email, name=sub, source="ecan-session",
                         claims=claims, email_verified=bool(email))


class IdentityRegistry:
    """Routes a bearer token to the verifier for its issuer."""

    def __init__(self, verifiers: Optional[List[Any]] = None):
        self._by_issuer: Dict[str, Any] = {}
        for v in verifiers or []:
            self.add(v)

    def add(self, verifier) -> None:
        if isinstance(verifier, EcanSessionVerifier):
            self._session = verifier
            return
        if isinstance(verifier, CloudBaseVerifier):
            self._introspect = getattr(self, "_introspect", []) + [verifier]
        self._by_issuer[verifier.issuer.rstrip("/")] = verifier

    def verify(self, token: str) -> Principal:
        token = strip_bearer(token)
        if not token:
            raise AuthError("missing bearer token")
        try:
            iss = str(jwt.decode(token, options={"verify_signature": False}).get("iss") or "").rstrip("/")
            alg = str(jwt.get_unverified_header(token).get("alg") or "")
        except jwt.PyJWTError:
            iss, alg = "", ""  # not a JWT we can route; an introspecting issuer may still know it
        # An HS256 token without an issuer is an eCan session token. If it fails
        # verification it is rejected; it never falls through to other checks.
        session = getattr(self, "_session", None)
        if session is not None and alg == "HS256" and not iss:
            return session.verify(token)
        verifier = self._by_issuer.get(iss)
        if verifier is None:
            # CloudBase tokens are checked with CloudBase itself, whatever iss says.
            for v in getattr(self, "_introspect", []):
                return v.verify(token)
            raise AuthError(f"tokens from {iss or 'unknown issuer'} are not accepted by this server")
        return verifier.verify(token)

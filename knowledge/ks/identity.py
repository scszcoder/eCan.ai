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

from utils.logger_helper import logger_helper as logger


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

    @property
    def email_lc(self) -> str:
        return (self.email or "").strip().lower()

    @property
    def domain(self) -> str:
        return self.email_lc.split("@", 1)[1] if "@" in self.email_lc else ""

    def to_dict(self) -> Dict[str, Any]:
        return {"user_id": self.user_id, "email": self.email, "name": self.name, "source": self.source,
                "agent_id": self.agent_id, "store_id": self.store_id}


def local_principal(user: str) -> Principal:
    """The signed-in desktop user (the app already authenticated them)."""
    user = (user or "local-user").strip()
    return Principal(user_id=user, email=user if "@" in user else "", name=user, source="local")


class JWKSVerifier:
    def __init__(self, name: str, issuer: str, jwks_url: Optional[str] = None, audience: Optional[str] = None,
                 user_claim: str = "sub", email_claim: str = "email", name_claim: str = "name",
                 algorithms: Optional[List[str]] = None, cache_path: Optional[str] = None, leeway: int = 60):
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
            self._load_jwks(force=bool(self._keys))
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
        return Principal(user_id=user, email=str(claims.get(self.email_claim) or ""),
                         name=str(claims.get(self.name_claim) or claims.get("username") or ""),
                         source=self.name, claims=claims)


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
        return Principal(user_id=claims["sub"], email=claims.get("email", ""), name=claims.get("name", ""),
                         source="local", claims=claims)


class IdentityRegistry:
    """Routes a bearer token to the verifier for its issuer."""

    def __init__(self, verifiers: Optional[List[Any]] = None):
        self._by_issuer: Dict[str, Any] = {}
        for v in verifiers or []:
            self.add(v)

    def add(self, verifier) -> None:
        self._by_issuer[verifier.issuer.rstrip("/")] = verifier

    def verify(self, token: str) -> Principal:
        if not token:
            raise AuthError("missing bearer token")
        try:
            iss = str(jwt.decode(token, options={"verify_signature": False}).get("iss") or "").rstrip("/")
        except jwt.PyJWTError as e:
            raise AuthError(f"malformed token: {e}")
        verifier = self._by_issuer.get(iss)
        if verifier is None:
            raise AuthError(f"tokens from {iss or 'unknown issuer'} are not accepted by this server")
        return verifier.verify(token)

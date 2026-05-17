"""
Service-tag fingerprint used in zeroconf TXT records.

Purpose: prevent ACCIDENTAL cross-account discovery on shared LANs (coffee
shops, conferences). NOT a full security boundary — anyone who can read
zeroconf records knows the ``org`` string, and the HMAC key in v1 is
derived from that same ``org`` string, so spoofing is trivial. For v1 we
treat the LAN as trusted; ``auth_fp`` mismatch only means "skip silently".

Phase 2+ plan: replace the org-derived HMAC key with a per-org secret stored
in Cognito user attributes, fetched once on login. That makes ``auth_fp`` a
real possession-of-secret proof rather than a glorified checksum.
"""

from __future__ import annotations

import hashlib
import hmac

# Versioned app-level salt — bumping this invalidates all currently-published
# auth_fps in the wild, so don't change without a coordinated rollout.
_AUTH_FP_SALT_V1 = b"ecan.discovery.auth_fp.v1"
_AUTH_FP_LEN = 8


def _org_secret_v1(org: str) -> bytes:
    """Derive a per-org HMAC key from the org identifier.

    v1 limitation: ``org`` (= sanitized user email) is the only secret. Anyone
    who knows the user's email + this app's salt can forge auth_fp. v2 will
    replace this with a real per-org secret from Cognito.
    """
    return hmac.new(
        _AUTH_FP_SALT_V1, (org or "").encode("utf-8"), hashlib.sha256
    ).digest()


def compute_auth_fp(org: str, target_id: str) -> str:
    """Compute the 8-char hex fingerprint advertised in a TXT record.

    ``target_id`` is either a ``machine_id`` (for ``_ecan-node`` records) or
    an ``agent_id`` (for ``_ecan-agent`` records). Different targets get
    different fps for the same org, so an attacker can't reuse a captured
    fp on a different agent.
    """
    if not org or not target_id:
        return ""
    key = _org_secret_v1(org)
    digest = hmac.new(key, target_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:_AUTH_FP_LEN]


def verify_auth_fp(org: str, target_id: str, fp: str) -> bool:
    """Constant-time check of a received fingerprint."""
    if not fp:
        return False
    expected = compute_auth_fp(org, target_id)
    if not expected:
        return False
    return hmac.compare_digest(expected, fp.strip())

"""
Unit tests for ``SessionSupervisor._decode_exp``.

Background
----------
CloudBase / WeChat JWTs sign ``exp`` in **milliseconds** (≈1e12), while
standard JWTs use **seconds** (≈1e9).  ``AuthManager._decode_token_expiry_unsafe``
already normalises (divides by 1000 when the value is > 1e10) but
``SessionSupervisor._decode_exp`` historically did not.  The result:

  * supervisor computed ``remaining = exp_ms - now`` ≈ 1.78e12 — a 56-year
    window
  * every ``remaining <= REFRESH_LEAD_SECONDS`` branch (refresh / silent
    refresh) fired on every tick
  * the silent WeChat OAuth path popped a browser window on every nudge,
    with the user just seeing "browser opened, no scan needed"

We exercise four scenarios:

  1. JWT with millisecond exp (CloudBase style)  → returned in seconds
  2. JWT with second exp     (standard JWT)     → returned unchanged
  3. JWT with no exp claim                       → returns None
  4. Malformed JWT                               → returns None (no raise)

The first test pins the regression: with the broken implementation,
``remaining`` was 1.78e12 — 5+ orders of magnitude larger than the
buffer window the supervisor uses.
"""

import base64
import importlib
import json
import time

import pytest


def _make_jwt(exp_value) -> str:
    """Build a minimal <base64header>.<base64payload>.<sig> string.

    Mirrors the helper in ``test_session_supervisor_token_rejection.py``.
    """
    def _b64(obj: bytes) -> str:
        return base64.urlsafe_b64encode(obj).rstrip(b"=").decode("ascii")

    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"exp": exp_value, "sub": "test"}).encode())
    return f"{header}.{payload}.sig"


def _supervisor_class():
    return importlib.import_module("auth.session_supervisor").SessionSupervisor


# ---------------------------------------------------------------
# 1) CloudBase millisecond exp must be normalised to seconds
# ---------------------------------------------------------------

def test_decode_exp_normalises_millisecond_exp_to_seconds():
    """JWT with exp in ms (≈1e12) must round-trip as Unix seconds."""
    now = int(time.time())
    exp_ms = (now + 600) * 1000  # 10 minutes from now, in ms

    jwt = _make_jwt(exp_ms)
    decoded = _supervisor_class()._decode_exp(jwt)

    assert decoded is not None, "valid JWT must decode"
    assert abs(decoded - (now + 600)) <= 1, (
        f"millisecond exp must be divided by 1000; "
        f"got {decoded}, expected ~{now + 600}"
    )

    # Regression guard: with the broken implementation this returned the
    # raw 1.78e12 value, which is what made every silent-refresh check fire.
    assert decoded < 10_000_000_000, (
        "decoded exp must be in seconds (~1e9), not milliseconds (~1e12); "
        f"got {decoded}"
    )


# ---------------------------------------------------------------
# 2) Standard JWT (seconds) must pass through unchanged
# ---------------------------------------------------------------

def test_decode_exp_leaves_seconds_exp_unchanged():
    """Standard JWT exp in seconds must NOT be divided."""
    now = int(time.time())
    exp_s = now + 7200  # 2 hours from now, in seconds

    jwt = _make_jwt(exp_s)
    decoded = _supervisor_class()._decode_exp(jwt)

    assert decoded is not None
    assert abs(decoded - exp_s) <= 1, (
        f"seconds exp must pass through; got {decoded}, expected {exp_s}"
    )


# ---------------------------------------------------------------
# 3) Missing exp claim must return None
# ---------------------------------------------------------------

def test_decode_exp_returns_none_when_exp_missing():
    """No exp claim → None. Supervisor treats this as 'don't refresh'."""
    def _b64(obj: bytes) -> str:
        return base64.urlsafe_b64encode(obj).rstrip(b"=").decode("ascii")

    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"sub": "no-exp-here"}).encode())
    jwt = f"{header}.{payload}.sig"

    assert _supervisor_class()._decode_exp(jwt) is None


# ---------------------------------------------------------------
# 4) Malformed input must return None, not raise
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "garbage",
    [
        "",                       # empty string
        "not-a-jwt",              # no dots
        "abc.def",                # only one dot, missing sig
        "only-one-segment",       # single segment
        "a.b.c.d",                # too many dots
        ".payload.sig",           # empty header
    ],
)
def test_decode_exp_returns_none_for_malformed_input(garbage):
    """Garbage in → None out.  Supervisor must never crash on bad tokens."""
    assert _supervisor_class()._decode_exp(garbage) is None

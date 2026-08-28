"""
Bundle signing — optional integrity / authenticity check for external
hook bundles.

Philosophy
==========

Hook bundles ship Python / JS / subprocess code that runs inside the
agent's address space.  For **out-of-tree** bundles distributed by a
vendor to many customers, we want a lightweight way to answer:

    "Did this manifest come from whoever the operator trusts?"

A full PKI is overkill for most deployments.  This module implements a
detached **HMAC-SHA256** signature model: the vendor owns a secret key,
produces a ``hook.sig`` side-car file, and the operator's keyring (a
plain JSON file or env var) lists the vendor's key ID.  The loader
verifies the signature before importing any code.

Trust modes (set via ``EC_HOOK_TRUST_MODE``):

  * ``permissive``  (default)  — signature NOT required.  If a
    ``hook.sig`` is present it's verified; absence is OK.  This is the
    only backward-compatible default.
  * ``strict``                 — every non-in-tree bundle MUST carry a
    valid signature.  In-tree bundles (under
    ``hooks/external/``) are always trusted by construction.
  * ``lockdown``               — every bundle (including in-tree) must
    have a valid signature.  Intended for paranoid production.

Signature file format
=====================

``hook.sig`` is a single-line JSON object::

    {"key_id": "vendor-a", "alg": "hmac-sha256", "sig": "<hex>"}

The signature covers the UTF-8 bytes of ``hook.yaml`` (or
``hook.json``) exactly as on disk — no normalisation, so operators
running a diff can reproduce the signature trivially.

Keyring
=======

A keyring maps ``key_id`` → secret.  Two sources, first-match wins:

  1. JSON file pointed to by ``EC_HOOK_KEYRING``
     (format: ``{"vendor-a": "<hex secret>", ...}``).
  2. Env var ``EC_HOOK_KEY_<KEY_ID>`` (dashes → underscores, uppercase).

Signing CLI (vendor side) is a one-liner::

    python -m agent.ec_skills.browser_use_extension.hook_signing \\
        path/to/bundle vendor-a

…but the CLI is optional; any HMAC-SHA256 implementation over the
manifest bytes produces the same signature.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .hook_api import HookApiError

from utils.logger_helper import logger_helper as logger  # CN app logger is "eCan.cn"

TrustMode = Literal["permissive", "strict", "lockdown"]

SIGNATURE_FILE_NAMES: tuple[str, ...] = ("hook.sig",)
SUPPORTED_ALGS: tuple[str, ...] = ("hmac-sha256",)
_DEFAULT_TRUST_MODE: TrustMode = "permissive"

# Root under which in-tree bundles live — these are implicitly trusted
# in ``strict`` mode (they shipped with the app itself).  Resolved once.
_IN_TREE_ROOT = (Path(__file__).parent / "hooks" / "external").resolve()


# ---------------------------------------------------------------------------
# Errors.
# ---------------------------------------------------------------------------
class BundleSignatureError(HookApiError):
    """Raised when a bundle signature is missing/invalid under the
    current trust mode."""


# ---------------------------------------------------------------------------
# Keyring resolution.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Keyring:
    """Flat key_id → secret-bytes map, loaded lazily."""
    keys: dict[str, bytes]

    def get(self, key_id: str) -> bytes | None:
        return self.keys.get(key_id)


def _load_keyring() -> _Keyring:
    """Assemble the keyring from ``EC_HOOK_KEYRING`` + env vars."""
    keys: dict[str, bytes] = {}
    keyring_path = os.environ.get("EC_HOOK_KEYRING", "").strip()
    if keyring_path:
        try:
            with open(keyring_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("keyring root must be an object")
            for kid, val in raw.items():
                if not isinstance(kid, str) or not isinstance(val, str):
                    continue
                keys[kid] = bytes.fromhex(val) if _looks_hex(val) else val.encode("utf-8")
        except Exception as e:
            logger.warning(f"[hook_signing] failed to read keyring {keyring_path!r}: {e}")
    # Env-var keys override file entries (explicit beats file).
    for env_name, env_val in os.environ.items():
        if not env_name.startswith("EC_HOOK_KEY_"):
            continue
        key_id = env_name[len("EC_HOOK_KEY_"):].lower().replace("_", "-")
        keys[key_id] = (
            bytes.fromhex(env_val) if _looks_hex(env_val) else env_val.encode("utf-8")
        )
    return _Keyring(keys=keys)


def _looks_hex(s: str) -> bool:
    if len(s) < 8 or len(s) % 2 != 0:
        return False
    try:
        bytes.fromhex(s)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Trust-mode resolution.
# ---------------------------------------------------------------------------
def get_trust_mode() -> TrustMode:
    raw = (os.environ.get("EC_HOOK_TRUST_MODE") or _DEFAULT_TRUST_MODE).strip().lower()
    if raw not in ("permissive", "strict", "lockdown"):
        logger.warning(
            f"[hook_signing] unknown EC_HOOK_TRUST_MODE={raw!r}; "
            f"falling back to {_DEFAULT_TRUST_MODE!r}"
        )
        return _DEFAULT_TRUST_MODE
    return raw  # type: ignore[return-value]


def _is_in_tree(bundle_dir: Path) -> bool:
    try:
        bundle_dir.resolve().relative_to(_IN_TREE_ROOT)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Signature math.
# ---------------------------------------------------------------------------
def compute_hmac_sha256(manifest_bytes: bytes, secret: bytes) -> str:
    """Return the lowercase hex digest of HMAC-SHA256."""
    return hmac.new(secret, manifest_bytes, hashlib.sha256).hexdigest()


def _find_manifest_bytes(bundle_dir: Path) -> tuple[str, bytes] | None:
    """Return (filename, bytes) for the first manifest found, or None."""
    for name in ("hook.yaml", "hook.json"):
        p = bundle_dir / name
        if p.is_file():
            return name, p.read_bytes()
    return None


def _read_signature(bundle_dir: Path) -> dict | None:
    for name in SIGNATURE_FILE_NAMES:
        p = bundle_dir / name
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                raise BundleSignatureError(
                    f"signature file {p} is not valid JSON: {e}"
                ) from e
    return None


# ---------------------------------------------------------------------------
# Public API called by the loader.
# ---------------------------------------------------------------------------
def verify_bundle_signature(bundle_dir: Path) -> dict | None:
    """Verify ``bundle_dir/hook.sig`` against the local keyring.

    Returns the parsed signature envelope on success, or ``None`` when
    no signature file is present.  Raises ``BundleSignatureError`` only
    when a signature exists AND is invalid (wrong key_id / bad sig /
    unsupported alg).  Absence of a signature file is NOT an error at
    this layer — the trust-mode gate in ``enforce_trust`` decides
    whether that matters.
    """
    sig = _read_signature(bundle_dir)
    if sig is None:
        return None

    alg = str(sig.get("alg") or "").strip().lower()
    key_id = str(sig.get("key_id") or "").strip()
    sig_hex = str(sig.get("sig") or "").strip()
    if alg not in SUPPORTED_ALGS:
        raise BundleSignatureError(
            f"bundle {bundle_dir.name!r}: unsupported signature alg {alg!r}; "
            f"supported: {list(SUPPORTED_ALGS)}"
        )
    if not key_id or not sig_hex:
        raise BundleSignatureError(
            f"bundle {bundle_dir.name!r}: hook.sig missing key_id or sig"
        )

    keyring = _load_keyring()
    secret = keyring.get(key_id)
    if secret is None:
        raise BundleSignatureError(
            f"bundle {bundle_dir.name!r}: key_id {key_id!r} not in local "
            f"keyring (set EC_HOOK_KEYRING or EC_HOOK_KEY_{key_id.upper().replace('-', '_')})"
        )

    found = _find_manifest_bytes(bundle_dir)
    if found is None:
        raise BundleSignatureError(
            f"bundle {bundle_dir.name!r}: no hook.yaml/json to verify against"
        )
    _, manifest_bytes = found

    expected = compute_hmac_sha256(manifest_bytes, secret)
    if not hmac.compare_digest(expected, sig_hex.lower()):
        raise BundleSignatureError(
            f"bundle {bundle_dir.name!r}: HMAC-SHA256 signature mismatch "
            f"for key_id={key_id!r}"
        )

    logger.info(
        f"[hook_signing] bundle {bundle_dir.name!r} verified "
        f"(key_id={key_id!r}, alg={alg!r})"
    )
    return sig


def enforce_trust(bundle_dir: Path) -> None:
    """Apply the current trust-mode gate to ``bundle_dir``.

    Raises ``BundleSignatureError`` if the bundle doesn't meet the bar.
    Callers should invoke this before importing any code from the
    bundle.  Signature verification itself is done as a side effect.
    """
    mode = get_trust_mode()
    in_tree = _is_in_tree(bundle_dir)

    # Permissive: verify if present, skip otherwise.
    if mode == "permissive":
        try:
            verify_bundle_signature(bundle_dir)
        except BundleSignatureError as e:
            # Present-but-broken is still an error — otherwise a tampered
            # signature would silently be ignored.
            raise
        return

    # In-tree bundles are always trusted in "strict" (they shipped with
    # the app binary).  Only "lockdown" forces them to be signed too.
    if in_tree and mode == "strict":
        logger.debug(
            f"[hook_signing] bundle {bundle_dir.name!r} is in-tree; "
            f"skipping signature check in strict mode"
        )
        return

    sig = verify_bundle_signature(bundle_dir)
    if sig is None:
        raise BundleSignatureError(
            f"bundle {bundle_dir.name!r} has no hook.sig but trust mode "
            f"is {mode!r}; either add a signature or relax "
            f"EC_HOOK_TRUST_MODE"
        )


# ---------------------------------------------------------------------------
# CLI — vendor-side signer.  Invoked as:
#   python -m agent.ec_skills.browser_use_extension.hook_signing \
#       <bundle_dir> <key_id>
# Secret is read from EC_HOOK_KEY_<KEY_ID> or argv[3].
# ---------------------------------------------------------------------------
def _cli(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: hook_signing <bundle_dir> <key_id> [<hex_secret>]\n"
            "       secret also read from EC_HOOK_KEY_<KEY_ID>",
            file=sys.stderr,
        )
        return 2
    bundle_dir = Path(argv[1]).resolve()
    key_id = argv[2].strip()
    secret_hex: str | None = argv[3] if len(argv) >= 4 else None
    if secret_hex is None:
        env_name = f"EC_HOOK_KEY_{key_id.upper().replace('-', '_')}"
        secret_hex = os.environ.get(env_name) or ""
        if not secret_hex:
            print(f"no secret provided (argv or {env_name})", file=sys.stderr)
            return 2

    secret_bytes = (
        bytes.fromhex(secret_hex) if _looks_hex(secret_hex) else secret_hex.encode("utf-8")
    )

    found = _find_manifest_bytes(bundle_dir)
    if found is None:
        print(f"no hook.yaml/json in {bundle_dir}", file=sys.stderr)
        return 1
    _, manifest_bytes = found

    digest = compute_hmac_sha256(manifest_bytes, secret_bytes)
    sig_obj = {"key_id": key_id, "alg": "hmac-sha256", "sig": digest}
    (bundle_dir / "hook.sig").write_text(
        json.dumps(sig_obj, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {bundle_dir / 'hook.sig'} (key_id={key_id}, "
        f"digest={digest[:16]}…)",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(_cli(sys.argv))


__all__ = [
    "BundleSignatureError",
    "TrustMode",
    "get_trust_mode",
    "compute_hmac_sha256",
    "verify_bundle_signature",
    "enforce_trust",
]

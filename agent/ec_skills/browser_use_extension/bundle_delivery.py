"""Step 5 — bundle signing/encryption/delivery for hybrid_cloud mode.

Closes the loop on the local_reactive bundle distribution problem:
in hybrid_cloud, only the cloud knows which bundles a given
``runEnvironment`` should run.  We can't ship every bundle to every
local agent at install time — the catalogue is operator-managed and
versioned per skill.  Instead, the cloud delivers bundles on demand
through the hybrid wire protocol.

Design
------

* **Cloud side** (:func:`pack_bundle_request`) — given a bundle
  directory, builds a :class:`BundleDeliveryRequest` containing every
  file and a HMAC-SHA256 signature over the manifest.  Signing reuses
  the existing :mod:`hook_signing` infrastructure verbatim — no new
  crypto is introduced.

* **Local side** (:class:`BundleDeliveryExecutor`) — receives the
  request, materialises the bundle to a sandbox dir, writes
  ``hook.sig``, and invokes :func:`hook_signing.enforce_trust` BEFORE
  any code import.  On signature failure, the sandbox dir is deleted
  and a structured error tag is returned.

* **Failure isolation** — the executor never raises out the top.
  Every error path returns a :class:`BundleDeliveryResponse` with a
  fixed-vocabulary ``error`` tag so cloud can categorise outcomes.

GraphQL schema additions (server-side, out of this module's scope)
-----------------------------------------------------------------

For production wiring, AppSync gains two operations:

.. code-block:: graphql

    type Mutation {
      publishHybridMessage(input: HybridMessageInput!): HybridMessage
    }
    type Subscription {
      onHybridMessage(runId: ID!, clientId: ID!): HybridMessage
    }
    input HybridMessageInput {
      runId: ID!
      clientId: ID!
      stepId: ID
      type: String!
      payload: AWSJSON!
    }

The ``type`` discriminator is one of the keys in
:data:`appsync_hybrid_transport.MESSAGE_TYPE_REGISTRY` — bundle
delivery uses ``"bundle_delivery_request"`` /
``"bundle_delivery_response"``.  Wire format is identical to the
other hybrid messages; no special-casing needed.

Encryption
----------

Bundle files are signed (HMAC-SHA256 over manifest bytes) but NOT
encrypted at this layer — the AppSync transport already terminates
TLS.  Add field-level encryption at the cloud-pack layer if a stricter
threat model demands it (e.g. for vendor-distributed bundles where
operators must not see the source).  Step 5 leaves a hook for this:
the ``files`` field accepts arbitrary dict-shaped values, so a future
``{"enc": "...", "iv": "..."}`` envelope is forward-compatible.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from agent.ec_skills.browser_use_extension.hybrid_protocol import (
    BundleDeliveryRequest,
    BundleDeliveryResponse,
)
from agent.ec_skills.browser_use_extension.hook_signing import (
    BundleSignatureError,
    compute_hmac_sha256,
    enforce_trust,
)

logger = logging.getLogger("ecan.bundle_delivery")

__all__ = [
    "pack_bundle_request",
    "BundleDeliveryExecutor",
    "DEFAULT_INSTALL_ROOT",
]


# Files larger than this are rejected at pack time — keeps a single
# AppSync mutation under the platform's payload cap (240 KB).
MAX_FILE_SIZE_BYTES = 200 * 1024

# Files that are never shipped (caches, repo metadata, transient artefacts).
_SKIP_PATTERNS: tuple[str, ...] = (
    "__pycache__/",
    ".pyc",
    ".pyo",
    ".git/",
    ".DS_Store",
)


def _should_skip(rel_path: str) -> bool:
    rp = rel_path.replace("\\", "/")
    return any(p in rp for p in _SKIP_PATTERNS)


def _read_file_for_pack(p: Path) -> Any:
    """Return either a utf-8 string or a base64-blob dict for a file.

    Text files (anything decodable as utf-8) ride as plain strings —
    cheap, diffable, AppSync-friendly.  Binaries get a
    ``{"b64": "..."}`` envelope so the JSON wire format stays clean.
    """
    data = p.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return {"b64": base64.b64encode(data).decode("ascii")}


def _materialize_file(target_dir: Path, rel: str, content: Any) -> None:
    """Inverse of :func:`_read_file_for_pack`.

    Uses ``write_bytes`` even for text payloads — ``write_text`` on
    Windows would translate ``\\n`` to ``\\r\\n``, mutating the
    manifest bytes and invalidating the HMAC signature.
    """
    out = target_dir / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        out.write_bytes(content.encode("utf-8"))
    elif isinstance(content, dict) and "b64" in content:
        out.write_bytes(base64.b64decode(content["b64"]))
    else:
        raise ValueError(
            f"unsupported file content type for {rel!r}: {type(content).__name__}"
        )


# ============================================================================
# Cloud side — pack a bundle for delivery
# ============================================================================


def pack_bundle_request(
    bundle_dir: str | Path,
    *,
    secret: bytes,
    key_id: str,
    run_id: str,
    step_id: str,
    install_hint: dict[str, Any] | None = None,
) -> BundleDeliveryRequest:
    """Read *bundle_dir* off disk and build a signed delivery request.

    Parameters
    ----------
    bundle_dir
        Path to a bundle directory containing ``hook.yaml``.
    secret
        The HMAC key bytes corresponding to *key_id*.  Operators
        manage these via ``EC_HOOK_KEY_<KEY_ID>`` env vars (see
        :mod:`hook_signing`).
    key_id
        The signing key identifier; embedded in the signature envelope
        so local can look up the matching verification key.
    run_id, step_id
        Correlation IDs for the transport layer.
    install_hint
        Optional dict passed through verbatim to the local executor.

    Raises
    ------
    FileNotFoundError
        When ``bundle_dir`` or its ``hook.yaml`` is missing.
    ValueError
        When a file exceeds :data:`MAX_FILE_SIZE_BYTES`.
    """
    root = Path(bundle_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"bundle directory not found: {root}")
    manifest = root / "hook.yaml"
    if not manifest.is_file():
        manifest = root / "hook.json"
    if not manifest.is_file():
        raise FileNotFoundError(
            f"bundle {root.name!r}: no hook.yaml or hook.json"
        )

    # Walk the bundle dir, collect every file.
    files: dict[str, Any] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if _should_skip(rel):
            continue
        if p.stat().st_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"file {rel!r} exceeds MAX_FILE_SIZE_BYTES "
                f"({p.stat().st_size} > {MAX_FILE_SIZE_BYTES})"
            )
        files[rel] = _read_file_for_pack(p)

    # Compute signature over manifest bytes (same algorithm
    # hook_signing uses on disk).
    manifest_bytes = manifest.read_bytes()
    digest = compute_hmac_sha256(manifest_bytes, secret)
    signature = {"key_id": key_id, "alg": "hmac-sha256", "sig": digest}

    # Try to read bundle name + version from the manifest, falling
    # back to dir name + 0.0.0.  We don't fully parse YAML here —
    # only what we need for the request envelope.
    bundle_name, bundle_version = _peek_manifest_meta(manifest)

    return BundleDeliveryRequest(
        run_id=run_id,
        step_id=step_id,
        bundle_name=bundle_name or root.name,
        bundle_version=bundle_version or "0.0.0",
        files=files,
        signature=signature,
        install_hint=dict(install_hint or {}),
    )


def _peek_manifest_meta(manifest_path: Path) -> tuple[str, str]:
    """Return ``(bundle_name, version)`` from a hook.yaml/json manifest.

    Best-effort — used only to populate the wire envelope's metadata.
    The authoritative parse happens in :mod:`hook_loader` after install.
    """
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except Exception:
        return "", ""
    if manifest_path.suffix.lower() == ".json":
        import json
        try:
            data = json.loads(text)
        except Exception:
            return "", ""
    else:
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text) or {}
        except Exception:
            return "", ""
    if not isinstance(data, dict):
        return "", ""
    return (
        str(data.get("bundle") or "").strip(),
        str(data.get("version") or "").strip(),
    )


# ============================================================================
# Local side — install a delivered bundle
# ============================================================================


# Default install root.  Production code passes
# ``app_info.appdata_path / 'hooks' / 'external'``; tests use a temp dir.
DEFAULT_INSTALL_ROOT: str = ""  # set by caller


class BundleDeliveryExecutor:
    """Local-side service that consumes :class:`BundleDeliveryRequest`
    and materialises the bundle to disk under a sandbox dir.

    The executor:

    1. Resolves the target dir (``install_root / bundle_name``).
    2. Writes every file from ``request.files`` into a fresh dir
       (existing contents are nuked first to prevent leftover-file
       attacks).
    3. Writes the signature blob to ``hook.sig``.
    4. Calls :func:`hook_signing.enforce_trust` to verify.  On failure,
       the dir is deleted and an error response is returned — the
       bundle never gets a chance to import.
    5. Returns a :class:`BundleDeliveryResponse` with the install path.

    Steps 2–4 happen in a temp dir first, then atomically renamed
    on success — partial installs never leave an importable but
    half-written bundle on disk.
    """

    def __init__(self, install_root: str | Path):
        self._root = Path(install_root).resolve()

    async def run_one(
        self, req: BundleDeliveryRequest,
    ) -> BundleDeliveryResponse:
        if not req.bundle_name:
            return BundleDeliveryResponse(
                run_id=req.run_id, step_id=req.step_id,
                ok=False, error="manifest_missing",
                error_detail="empty bundle_name in request",
            )
        if not req.signature.get("sig"):
            return BundleDeliveryResponse(
                run_id=req.run_id, step_id=req.step_id,
                ok=False, bundle_name=req.bundle_name,
                error="signature_invalid",
                error_detail="missing 'sig' in signature envelope",
            )

        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return BundleDeliveryResponse(
                run_id=req.run_id, step_id=req.step_id,
                ok=False, bundle_name=req.bundle_name,
                error="extract_failed",
                error_detail=f"could not create install root: {exc}",
            )

        # Stage to a temp dir first.
        try:
            staging = Path(
                tempfile.mkdtemp(prefix=f"_ecan_bundle_{req.bundle_name}_")
            )
        except Exception as exc:
            return BundleDeliveryResponse(
                run_id=req.run_id, step_id=req.step_id,
                ok=False, bundle_name=req.bundle_name,
                error="extract_failed",
                error_detail=f"mkdtemp failed: {exc}",
            )

        # Materialise files.
        try:
            for rel, content in req.files.items():
                # Refuse path-escape attempts (../, absolute paths).
                norm = rel.replace("\\", "/").lstrip("/")
                if ".." in norm.split("/"):
                    raise ValueError(f"refused path-escape: {rel!r}")
                _materialize_file(staging, norm, content)

            # Make sure the manifest landed.
            mf = staging / "hook.yaml"
            if not mf.is_file():
                mf = staging / "hook.json"
            if not mf.is_file():
                shutil.rmtree(staging, ignore_errors=True)
                return BundleDeliveryResponse(
                    run_id=req.run_id, step_id=req.step_id,
                    ok=False, bundle_name=req.bundle_name,
                    error="manifest_missing",
                    error_detail="bundle has no hook.yaml/json",
                )

            # Drop the signature so enforce_trust can verify it.
            # write_bytes (not write_text) — see _materialize_file note.
            import json as _json
            sig_payload = _json.dumps(req.signature, ensure_ascii=False) + "\n"
            (staging / "hook.sig").write_bytes(sig_payload.encode("utf-8"))
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return BundleDeliveryResponse(
                run_id=req.run_id, step_id=req.step_id,
                ok=False, bundle_name=req.bundle_name,
                error="extract_failed",
                error_detail=f"{type(exc).__name__}: {exc}",
            )

        # Verify signature BEFORE the bundle ever sees a Python import.
        try:
            enforce_trust(staging)
        except BundleSignatureError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return BundleDeliveryResponse(
                run_id=req.run_id, step_id=req.step_id,
                ok=False, bundle_name=req.bundle_name,
                error="signature_invalid",
                error_detail=str(exc),
            )
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return BundleDeliveryResponse(
                run_id=req.run_id, step_id=req.step_id,
                ok=False, bundle_name=req.bundle_name,
                error="signature_invalid",
                error_detail=f"unexpected: {type(exc).__name__}: {exc}",
            )

        # Atomic-ish rename into place.  On Windows this requires the
        # target not to exist, so we delete first.
        target = self._root / req.bundle_name
        try:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(staging), str(target))
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return BundleDeliveryResponse(
                run_id=req.run_id, step_id=req.step_id,
                ok=False, bundle_name=req.bundle_name,
                error="extract_failed",
                error_detail=f"final rename failed: {exc}",
            )

        logger.info(
            f"[bundle_delivery] installed {req.bundle_name!r} "
            f"v{req.bundle_version} to {target}"
        )
        return BundleDeliveryResponse(
            run_id=req.run_id, step_id=req.step_id,
            ok=True, bundle_name=req.bundle_name,
            installed_path=str(target),
            hooks_loaded=[],   # populated by a downstream loader if invoked
        )

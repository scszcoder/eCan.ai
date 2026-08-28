"""Multimodal task input for the browser-use Agent.

The front-desk hot path scrapes customer-attached images from the chat
thread, eagerly fetches them as data URIs, and forwards them in the
``send_chat`` payload as ``latest_message_attachments``.  See the chain:

    live-chat bundle dom_assets latest-customer-bubble JS
        →  scrape_latest_customer_bubble  (DOM image extraction)
    live-chat bundle image_fetch.fetch_attachments
        →  data: URI base64-encoding (timeout-bounded)
    live-chat bundle pre_dispatch_v2 / pre_dispatch_enrich
        →  item["last_message_attachments"]
    node_runtime.frontdesk_dispatch._build_assignment_payload
        →  payload["latest_message_attachments"]   (Q&A worker contract)

This module closes the loop on the worker side: it reads the inbound
payload from ``state["input"]`` and converts the data URIs into
browser-use ``ContentPartImageParam`` objects (``sample_images``).
Browser-use's ``AgentMessagePrompt`` appends ``sample_images`` to the
LLM's user-message content list on every step, so a vision-capable LLM
can actually *see* the customer's image.

Public API:

* :func:`build_sample_images_from_payload` — pure, side-effect-free.
  Takes the inbound JSON payload (parsed dict) and an optional LLM
  instance for vision-capability gating; returns a list of
  ``ContentPartImageParam`` (possibly empty).
* :func:`apply_multimodal_to_agent_kwargs` — call before constructing
  the ``Agent``.  Sets ``agent_kwargs["sample_images"]`` and forces
  ``use_vision=True`` when images are present (browser-use only emits
  ``sample_images`` when ``use_vision`` is on).
* :func:`refresh_agent_sample_images` — call after a *cached* Agent has
  been re-acquired for a new turn.  Mutates ``agent.sample_images``
  AND ``agent._message_manager.sample_images`` so the new turn's
  images flow through (the cached agent's constructor copy is stale).

All three functions are best-effort and never raise — failures fall
through to "no images this turn".  This is by design: a multimodal
helper failure must not break the Q&A worker's text-only path.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from utils.logger_helper import logger_helper as logger  # CN app logger is "eCan.cn"


# Mime media-type allowlist for browser-use's ``ImageURL.media_type``.
# Anthropic models reject anything outside this set; OpenAI is lenient
# but rejecting is safer than letting through ``image/svg+xml``.
_SUPPORTED_MEDIA_TYPES: frozenset[str] = frozenset({
    "image/jpeg", "image/png", "image/gif", "image/webp",
})


def _media_type_from_data_uri(data_uri: str) -> str:
    """Extract ``image/<format>`` from a ``data:image/<format>;base64,...`` URI.

    Returns ``"image/jpeg"`` as a safe default when the URI is malformed
    or the type isn't in the allowlist.
    """
    try:
        if not data_uri.startswith("data:"):
            return "image/jpeg"
        head = data_uri[5:].split(";", 1)[0].strip().lower()
        if head in _SUPPORTED_MEDIA_TYPES:
            return head
    except Exception:
        pass
    return "image/jpeg"


def _parse_input_payload(state: dict | None) -> dict | None:
    """Extract the JSON payload dict from ``state["input"]`` if present.

    The Q&A worker receives its turn-payload as a JSON string set on
    ``state["input"]`` by the upstream event/dispatch wiring.  Returns
    None when state isn't a dict, input isn't a string, or the string
    isn't a JSON object.
    """
    if not isinstance(state, dict):
        return None
    raw = state.get("input")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _resolve_attachment_data_uri(entry: dict) -> str:
    data_uri = entry.get("data_uri")
    if isinstance(data_uri, str) and data_uri.startswith("data:image/"):
        return data_uri
    image_ref = entry.get("image_ref")
    if image_ref:
        try:
            from agent.ec_skills import live_chat_dispatch as _lcd
            # Bridge None -> AttributeError -> same fallback as the old
            # failed lazy import (no image this turn).
            resolved = _lcd.runner_bridge().image_store.get_data_uri(str(image_ref))
            if isinstance(resolved, str) and resolved.startswith("data:image/"):
                return resolved
        except Exception:
            pass
    return ""


def build_sample_images_from_payload(
    payload: dict | None,
    *,
    llm: Any | None = None,
) -> list[Any]:
    """Build the ``sample_images`` list for ``Agent(sample_images=...)``.

    Args:
        payload: The parsed inbound JSON payload (e.g. from a Q&A
            worker's ``state["input"]``).  May contain a
            ``latest_message_attachments`` key — a list of dicts with
            either ``data_uri`` (success) or ``url`` + ``fetch_error``
            (URL-fallback).  This function only consumes ``data_uri``
            entries; URL-fallback retry is intentionally *not* done
            here to keep the helper pure and synchronous.
        llm: Optional LLM instance.  When provided and its
            ``supports_vision`` attribute is False, returns an empty
            list (drops attachments rather than sending them to a
            non-vision model that would error or silently ignore them).

    Returns a list of ``ContentPartImageParam`` (browser-use type).
    Returns ``[]`` for any of: missing payload, missing/empty
    attachments, vision-incapable LLM, import failure (browser-use not
    installed in test environment), or any per-entry parse error.
    Order is preserved from the payload list.
    """
    if not isinstance(payload, dict):
        return []
    atts = payload.get("latest_message_attachments")
    if not isinstance(atts, list) or not atts:
        return []

    # Vision capability gate.
    if llm is not None:
        try:
            if getattr(llm, "supports_vision", True) is False:
                logger.info(
                    "[multimodal] Skipping %d attachment(s): LLM does not "
                    "support vision (set supports_vision=True on the "
                    "model config to enable)", len(atts),
                )
                return []
        except Exception:
            pass  # be permissive — let the call through

    # Lazy import — keeps unit tests that don't need browser-use from
    # blowing up at module import time.
    try:
        from browser_use.llm.messages import (
            ContentPartImageParam,
            ImageURL,
        )
    except Exception as exc:
        logger.warning(
            f"[multimodal] browser-use import failed; cannot build "
            f"sample_images: {type(exc).__name__}: {exc}"
        )
        return []

    out: list[Any] = []
    image_ref_input_count = 0
    direct_data_uri_count = 0
    resolved_image_ref_count = 0
    fetch_error_count = 0
    for entry in atts:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") and entry["kind"] != "image":
            continue  # skip non-image entries (future: file kind)
        if entry.get("image_ref"):
            image_ref_input_count += 1
        if isinstance(entry.get("data_uri"), str) and entry.get("data_uri", "").startswith("data:image/"):
            direct_data_uri_count += 1
        data_uri = _resolve_attachment_data_uri(entry)
        if not data_uri:
            # URL-only fallback entries are intentionally dropped here;
            # the worker can retry the fetch via image_fetch if it cares
            # to (orthogonal to this helper).  Logged at debug level
            # only — fetch_error entries are a known soft failure mode.
            err = entry.get("fetch_error")
            if err:
                fetch_error_count += 1
                logger.debug(
                    f"[multimodal] Dropping attachment with fetch_error="
                    f"{err!r} (no data_uri); url={entry.get('url')!r}"
                )
            continue
        if entry.get("image_ref") and not entry.get("data_uri"):
            resolved_image_ref_count += 1
        try:
            media_type = _media_type_from_data_uri(data_uri)
            out.append(ContentPartImageParam(
                image_url=ImageURL(
                    url=data_uri,
                    detail="auto",
                    media_type=media_type,
                ),
            ))
        except Exception as exc:
            logger.warning(
                f"[multimodal] Failed to build ContentPartImageParam "
                f"for entry: {type(exc).__name__}: {exc}"
            )
    if out:
        logger.info(
            f"[multimodal] Built {len(out)} sample_images from payload "
            f"(of {len(atts)} attachment entries)"
        )
        logger.info(
            "[data-uri-mitigation] browser_sample_images_resolution "
            "attachments=%d image_refs=%d resolved_refs=%d direct_data_uri=%d "
            "fetch_errors=%d sample_images=%d",
            len(atts),
            image_ref_input_count,
            resolved_image_ref_count,
            direct_data_uri_count,
            fetch_error_count,
            len(out),
        )
    return out


def apply_multimodal_to_agent_kwargs(
    agent_kwargs: dict,
    *,
    state: dict | None,
    llm: Any | None,
) -> int:
    """Populate ``agent_kwargs["sample_images"]`` from the inbound payload.

    Forces ``agent_kwargs["use_vision"] = True`` when at least one
    image was built — browser-use's ``AgentMessagePrompt`` only emits
    ``sample_images`` to the LLM when ``use_vision`` is on (see
    ``browser_use/agent/prompts.py`` ~line 421).

    Returns the number of images appended (``0`` when no-op).  Never
    raises — internal failures fall through to a no-op.
    """
    try:
        payload = _parse_input_payload(state)
        images = build_sample_images_from_payload(payload, llm=llm)
        if not images:
            return 0
        # Merge with any pre-existing sample_images (rare but possible —
        # caller may have set their own; ours go first so the customer's
        # image is the most prominent reference).
        existing = agent_kwargs.get("sample_images") or []
        agent_kwargs["sample_images"] = list(images) + list(existing)
        # Force vision on for this turn — without this, browser-use's
        # prompt builder won't include sample_images at all.
        agent_kwargs["use_vision"] = True
        return len(images)
    except Exception as exc:
        logger.warning(
            f"[multimodal] apply_multimodal_to_agent_kwargs failed "
            f"(non-fatal, continuing without images): {type(exc).__name__}: {exc}"
        )
        return 0


def refresh_agent_sample_images(
    agent: Any,
    *,
    state: dict | None,
    llm: Any | None,
) -> int:
    """Refresh a *cached* Agent's sample_images for the current turn.

    The browser-use Agent caches its ``sample_images`` at construction
    time in two places: ``agent.sample_images`` AND
    ``agent._message_manager.sample_images``.  When we reuse a cached
    Agent across customer turns (see
    ``browser_node.runner.acquire_or_reuse_local_agent``), the original
    constructor list is stale by the time the next turn runs.  This
    helper rebuilds the list from the new turn's payload and writes it
    to BOTH locations so the next ``agent.run()`` step's prompt builder
    picks up the new images.

    Returns the number of images written (``0`` when no-op).  Never
    raises.  Safe to call on every turn — when there are no
    attachments, it actively *clears* any leftover ``sample_images``
    from a previous turn so a stale image doesn't bleed into the next
    customer's prompt.
    """
    try:
        payload = _parse_input_payload(state)
        images = build_sample_images_from_payload(payload, llm=llm)

        # Always reset both locations to keep the two in sync — even
        # when ``images`` is empty (clears stale state from previous
        # turn).  The agent attribute is set unconditionally; the
        # message_manager copy is set when present.
        try:
            agent.sample_images = images
        except Exception as exc:
            logger.debug(
                f"[multimodal] could not set agent.sample_images: "
                f"{type(exc).__name__}: {exc}"
            )
        mm = getattr(agent, "_message_manager", None)
        if mm is not None:
            try:
                mm.sample_images = images
            except Exception as exc:
                logger.debug(
                    f"[multimodal] could not set "
                    f"agent._message_manager.sample_images: "
                    f"{type(exc).__name__}: {exc}"
                )

        # When images are present, ensure use_vision is on for THIS run.
        # Browser-use stores it on agent.settings.use_vision; mutating
        # the public attribute is harmless when settings is read-only.
        if images:
            for attr_path in ("use_vision",):
                try:
                    setattr(agent, attr_path, True)
                except Exception:
                    pass
            settings = getattr(agent, "settings", None)
            if settings is not None:
                try:
                    settings.use_vision = True
                except Exception:
                    pass
        return len(images)
    except Exception as exc:
        logger.warning(
            f"[multimodal] refresh_agent_sample_images failed "
            f"(non-fatal): {type(exc).__name__}: {exc}"
        )
        return 0


__all__ = [
    "build_sample_images_from_payload",
    "apply_multimodal_to_agent_kwargs",
    "refresh_agent_sample_images",
]

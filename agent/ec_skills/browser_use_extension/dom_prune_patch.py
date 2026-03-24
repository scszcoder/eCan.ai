"""DOM text pruner for browser-use llm_representation output.

browser-use's serializer already strips non-interactive elements (script/style/meta/etc.).
Its output is a compact tree of interactive + structural nodes, e.g.:

    <div>
        [12345]<button type=submit>Place Order</button>
        [12346]<input placeholder=Email type=email>

Key design decisions:
- NEVER filter lines that contain an interactive index [N] – those are clickable targets.
- Only trim genuinely redundant content: blank lines, data-URI blobs, hash-like data-* values.
- The primary token saving comes from the max_chars hard-cap.
- Dedup is done on content MINUS the [id] prefix so repeated structural nodes collapse,
  while still keeping the first occurrence (with its id) so the agent can reference it.
"""

import re
from utils.logger_helper import logger_helper as logger

_patched = False
_original_llm_representation = None
_current_max_chars = 8000
_prune_calls = 0
_last_prune_log_signature = None

# Matches the interactive-element index that browser-use prefixes to clickable nodes.
# Lines containing this are NEVER filtered — they are action targets.
_INTERACTIVE_INDEX_RE = re.compile(r"\[\d+\]")

# data-* attributes whose values are hashes / tokens / base64 blobs add zero
# navigational value.  Replace the value with a short placeholder.
# Matches patterns like:  data-v-1a2b3c4d=abc123  or  data-react-key=xyz
_DATA_HASH_ATTR_RE = re.compile(
    r'\bdata-[a-z0-9_-]+=(?:[A-Za-z0-9+/]{16,}={0,2}|[a-f0-9]{8,}(?:-[a-f0-9]{4,}){2,}|[A-Za-z0-9_-]{20,})',
    re.IGNORECASE,
)

# base64 data URIs embedded as attribute values (src=data:image/png;base64,…)
_DATA_URI_RE = re.compile(r'(?:src|href|content)=data:[^,\s]{0,40},\S+', re.IGNORECASE)


def _compress_line(line: str) -> str:
    """Apply targeted attribute-level compression that is safe for all lines."""
    # Replace data-URI attribute values
    line = _DATA_URI_RE.sub(lambda m: m.group(0).split("=")[0] + "=[data-uri]", line)
    # Strip hash-like data-* attribute values
    line = _DATA_HASH_ATTR_RE.sub(lambda m: m.group(0).split("=")[0], line)
    return line


def _prune_dom_text(dom_text: str, max_chars: int):
    _EMPTY_STATS = {
        "raw_chars": len(dom_text) if isinstance(dom_text, str) else 0,
        "pruned_chars": len(dom_text) if isinstance(dom_text, str) else 0,
        "raw_lines": 0,
        "kept_lines": 0,
        "blank_filtered": 0,
        "dedup_filtered": 0,
        "cap_truncated": False,
    }
    if not isinstance(dom_text, str) or not dom_text:
        return dom_text, _EMPTY_STATS

    lines = dom_text.splitlines()
    cleaned = []
    # Dedup by content without the leading [id] index so that genuinely
    # repeated structural nodes (same tag/attrs/text) are collapsed while
    # keeping the first occurrence (including its interactive id).
    seen_content: set[str] = set()
    blank_filtered = 0
    dedup_filtered = 0
    cap_truncated = False

    # Estimate max lines we'll ever need to avoid building far more than max_chars.
    # Assumes average ~60 chars/line; we add 20% headroom.
    max_lines = max(200, (max_chars // 60) + (max_chars // 60) // 5) if max_chars > 0 else 2000

    for raw_line in lines:
        # Strip trailing whitespace; preserve leading tabs (tree indent).
        line = raw_line.rstrip()

        # Drop purely blank lines.
        stripped = line.strip()
        if not stripped:
            blank_filtered += 1
            continue

        # Apply safe attribute compression BEFORE dedup so the key is normalised.
        line = _compress_line(line)
        stripped = line.strip()

        # Dedup key: remove the leading interactive index (if any) to catch
        # structurally identical rows with different ids (e.g. repeated nav items).
        dedup_key = _INTERACTIVE_INDEX_RE.sub("", stripped).strip()
        if dedup_key and dedup_key in seen_content:
            # Only dedup non-interactive duplicates — interactive lines have
            # navigational value and must not be silently dropped.
            if not _INTERACTIVE_INDEX_RE.search(stripped):
                dedup_filtered += 1
                continue
        seen_content.add(dedup_key)
        cleaned.append(line)

        if len(cleaned) >= max_lines:
            break

    pruned = "\n".join(cleaned)
    # Do NOT fall back to dom_text if pruned is empty; return it as-is.
    # A genuinely empty result is valid (e.g. truly empty page).

    if max_chars > 0 and len(pruned) > max_chars:
        # Truncate at a newline boundary to avoid cutting mid-element.
        cutoff = pruned.rfind("\n", 0, max_chars)
        pruned = pruned[: cutoff if cutoff > max_chars // 2 else max_chars]
        cap_truncated = True

    stats = {
        "raw_chars": len(dom_text),
        "pruned_chars": len(pruned),
        "raw_lines": len(lines),
        "kept_lines": len(cleaned),
        "blank_filtered": blank_filtered,
        "dedup_filtered": dedup_filtered,
        "cap_truncated": cap_truncated,
    }
    return pruned, stats


def patch_dom_llm_representation(max_chars: int = 8000) -> bool:
    """Patch browser-use DOM llm_representation to prune low-value DOM noise.

    This reduces per-step context payload (current browser state) that message
    compaction cannot shrink (compaction only applies to history, not the live
    browser state injected each step).

    Args:
        max_chars: Hard character cap on the DOM text sent to the LLM per step.
                   NOTE: this should be a character count, NOT max_clickable_elements_length.
                   Typical useful range: 4000–12000.
    """
    global _patched, _original_llm_representation, _current_max_chars

    if isinstance(max_chars, int) and max_chars > 0:
        _current_max_chars = max_chars

    try:
        from browser_use.dom.views import SerializedDOMState

        if _patched and _original_llm_representation is not None:
            logger.info(
                "[DOMPrunePatch] max_chars updated to %s (patch already active)",
                _current_max_chars,
            )
            return True

        _original_llm_representation = SerializedDOMState.llm_representation

        def _wrapped_llm_representation(self, *args, **kwargs):
            global _prune_calls, _last_prune_log_signature
            raw = _original_llm_representation(self, *args, **kwargs)
            pruned, stats = _prune_dom_text(raw, _current_max_chars)

            _prune_calls += 1
            raw_chars = stats["raw_chars"]
            pruned_chars = stats["pruned_chars"]
            reduction_pct = (1 - pruned_chars / raw_chars) * 100 if raw_chars > 0 else 0.0

            log_sig = (raw_chars, pruned_chars, stats["cap_truncated"], _current_max_chars)
            if log_sig != _last_prune_log_signature:
                logger.info(
                    "[DOMPrunePatch] call=%s chars=%s->%s (%.1f%% off) lines=%s->%s "
                    "blank=%s dedup=%s cap=%s max=%s",
                    _prune_calls,
                    raw_chars,
                    pruned_chars,
                    reduction_pct,
                    stats["raw_lines"],
                    stats["kept_lines"],
                    stats["blank_filtered"],
                    stats["dedup_filtered"],
                    stats["cap_truncated"],
                    _current_max_chars,
                )
                _last_prune_log_signature = log_sig

            return pruned

        SerializedDOMState.llm_representation = _wrapped_llm_representation
        _patched = True
        logger.info(
            "[DOMPrunePatch] Enabled DOM pruning for llm_representation (max_chars=%s)",
            _current_max_chars,
        )
        return True
    except Exception as e:
        logger.error("[DOMPrunePatch] Failed to patch llm_representation: %s", e, exc_info=True)
        return False


def unpatch_dom_llm_representation() -> bool:
    """Restore the original llm_representation (useful for testing or hot-reload)."""
    global _patched, _original_llm_representation
    if not _patched or _original_llm_representation is None:
        return False
    try:
        from browser_use.dom.views import SerializedDOMState

        SerializedDOMState.llm_representation = _original_llm_representation
        _patched = False
        _original_llm_representation = None
        logger.info("[DOMPrunePatch] Restored original llm_representation")
        return True
    except Exception as e:
        logger.error("[DOMPrunePatch] Failed to unpatch: %s", e, exc_info=True)
        return False

"""Strip machine-local identity out of a skill graph before it leaves here.

A browser-automation node can name a fingerprint profile in `browserProfileId`.
That is a convenience for a skill you will never share -- it points at a
registered profile on THIS machine: a live logged-in seller session, the proxy
it egresses through, and the fingerprint it presents.

It must not travel, for two separate reasons:

* **Sharing.** A skill can be published or rented. Handing someone a skill that
  names your store's identity is a leak, and the first person to share a skill
  they configured for themselves would do it without noticing.
* **Correctness.** Profiles are registered per machine and deliberately never
  synced (see docs/OWN_FINGERPRINT_BROWSER.md). An id that arrives on another
  machine either names nothing -- and the run now fails closed rather than
  quietly degrading to an unprotected browser -- or, worse, happens to match a
  same-named local profile and silently runs as the wrong store.

So the rule is simply: **the node's profile id never leaves this machine.**
Which identity a run uses is a per-task decision
(`task.metadata["browser_identity"]["browser_profile_id"]`), and that lives on
the task, not in the shared artifact.

This is a pure function over the graph -- it never touches the file on disk,
so the local skill keeps its shortcut.
"""

import copy
import json
from typing import Any, Tuple

from utils.logger_helper import logger_helper as logger

# Node input keys that name a local identity. `browserProfileId` is ours;
# the vendor ids are an account-level credential for the same reason -- an
# AdsPower serial or a Ziniao shop id identifies someone's store login.
LOCAL_IDENTITY_KEYS = ("browserProfileId",)

# Anywhere in the graph, a persisted per-task identity block would carry the
# same thing under a different name.
LOCAL_IDENTITY_BLOCKS = ("browser_identity",)


def strip_local_identity(graph: Any, _copy: bool = True) -> Tuple[Any, int]:
    """Return (graph without local identity, how many values were removed).

    Walks the whole structure rather than assuming a shape: flowgram graphs
    nest nodes under `workFlow.nodes`, sheets, blocks and loop bodies, and the
    bundle format differs from the plain diagram JSON. A blind walk is cheap
    and cannot miss a nesting level someone adds later.
    """
    removed = 0

    def walk(node: Any) -> Any:
        nonlocal removed
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key in LOCAL_IDENTITY_BLOCKS:
                    removed += 1
                    continue
                if key == "inputsValues" and isinstance(value, dict):
                    cleaned = {}
                    for ik, iv in value.items():
                        if ik in LOCAL_IDENTITY_KEYS:
                            # Only count a value that was actually set; an
                            # empty field is not a leak and dropping it
                            # silently would make the diff confusing.
                            content = iv.get("content") if isinstance(iv, dict) else iv
                            if str(content or "").strip():
                                removed += 1
                                continue
                        cleaned[ik] = walk(iv)
                    out[key] = cleaned
                    continue
                out[key] = walk(value)
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    source = copy.deepcopy(graph) if _copy else graph
    return walk(source), removed


def sanitized_graph_bytes(file_path: str) -> Tuple[bytes, int]:
    """Read a skill graph file and return (bytes to upload, removed count).

    Returns the file's own bytes unchanged when there is nothing to strip or
    the file is not JSON we understand -- an unreadable graph is not a reason
    to fail an upload, and leaving it byte-identical keeps checksums stable.
    """
    try:
        with open(file_path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        logger.warning(f"[SkillSanitize] could not read {file_path}: {exc}")
        return b"", 0

    try:
        graph = json.loads(raw.decode("utf-8"))
    except Exception:
        return raw, 0  # not JSON (bundles may be packed) -- upload as-is

    cleaned, removed = strip_local_identity(graph)
    if not removed:
        return raw, 0

    logger.info(
        f"[SkillSanitize] removed {removed} machine-local browser identity "
        f"value(s) from {file_path} before upload; the local file is unchanged"
    )
    return json.dumps(cleaned, ensure_ascii=False).encode("utf-8"), removed

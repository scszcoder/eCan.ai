"""A shared skill must not carry the machine it was built on.

`browserProfileId` on a browser-automation node points at a fingerprint profile
registered on THIS machine -- a live logged-in seller session plus the proxy it
egresses through. A skill can be published or rented, so the first person to
share a skill they had configured for themselves would hand over their store
without noticing.

The rule under test: the node's profile id never leaves this machine. The local
file keeps it (it is a real convenience for a private skill); the uploaded copy
does not. Which identity a run uses is a per-task decision instead --
`task.metadata["browser_identity"]["browser_profile_id"]`.
"""

import json

import pytest

from agent.ec_skills.skill_share_sanitize import (
    sanitized_graph_bytes,
    strip_local_identity,
)


def _node(profile_id, title="Browser_1"):
    return {
        "id": "n1",
        "type": "browser-automation",
        "data": {
            "title": title,
            "inputsValues": {
                "browser": {"type": "constant", "content": "fingerprint"},
                "browserProfileId": {"type": "constant", "content": profile_id},
                "cdpPort": {"type": "constant", "content": "9228"},
            },
        },
    }


def _ids(graph):
    """Every browserProfileId still present anywhere in the graph."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            iv = o.get("inputsValues")
            if isinstance(iv, dict) and "browserProfileId" in iv:
                found.append(iv["browserProfileId"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(graph)
    return found


def test_the_profile_id_is_removed():
    graph = {"workFlow": {"nodes": [_node("etsy_main")]}}
    cleaned, removed = strip_local_identity(graph)
    assert removed == 1
    assert _ids(cleaned) == []


def test_everything_else_survives():
    """Only the identity goes; the node must still run for the new owner."""
    graph = {"workFlow": {"nodes": [_node("etsy_main")]}}
    cleaned, _ = strip_local_identity(graph)
    iv = cleaned["workFlow"]["nodes"][0]["data"]["inputsValues"]
    assert iv["browser"]["content"] == "fingerprint"   # capability is kept
    assert iv["cdpPort"]["content"] == "9228"
    assert cleaned["workFlow"]["nodes"][0]["data"]["title"] == "Browser_1"


def test_the_original_is_not_mutated():
    """The local skill keeps its shortcut -- we sanitize a copy."""
    graph = {"workFlow": {"nodes": [_node("etsy_main")]}}
    strip_local_identity(graph)
    assert _ids(graph)[0]["content"] == "etsy_main"


def test_an_empty_field_is_not_reported_as_a_leak():
    graph = {"workFlow": {"nodes": [_node("")]}}
    _, removed = strip_local_identity(graph)
    assert removed == 0


def test_nodes_nested_in_sheets_loops_and_blocks_are_reached():
    """Flowgram nests nodes several ways and the bundle differs from the
    plain diagram JSON, so the walk must not assume one shape."""
    graph = {
        "sheets": [{"document": {"nodes": [
            _node("store_a"),
            {"id": "loop", "blocks": [_node("store_b")]},
            {"id": "group", "data": {"nodes": [_node("store_c")]}},
        ]}}]
    }
    cleaned, removed = strip_local_identity(graph)
    assert removed == 3
    assert _ids(cleaned) == []


def test_a_persisted_task_identity_block_is_removed_too():
    graph = {"workFlow": {"nodes": [_node("etsy")]},
             "browser_identity": {"browser_profile_id": "etsy"}}
    cleaned, removed = strip_local_identity(graph)
    assert "browser_identity" not in cleaned
    assert removed == 2


def test_a_graph_with_nothing_local_is_left_alone():
    graph = {"workFlow": {"nodes": [{"id": "n", "data": {"inputsValues": {
        "browser": {"type": "constant", "content": "new chromium"}}}}]}}
    cleaned, removed = strip_local_identity(graph)
    assert removed == 0
    assert cleaned == graph


# ── the upload boundary ────────────────────────────────────────────────────

def test_upload_bytes_are_sanitized_and_the_file_is_untouched(tmp_path):
    path = tmp_path / "etsy_after_sales0_skill_bundle.json"
    original = {"workFlow": {"nodes": [_node("etsy_main")]}}
    path.write_text(json.dumps(original), encoding="utf-8")

    payload, removed = sanitized_graph_bytes(str(path))

    assert removed == 1
    assert "etsy_main" not in payload.decode("utf-8")
    # The local skill still works as before.
    assert "etsy_main" in path.read_text(encoding="utf-8")


def test_a_clean_graph_uploads_byte_identical(tmp_path):
    """No gratuitous reserialisation -- keeps checksums stable."""
    path = tmp_path / "s.json"
    raw = json.dumps({"workFlow": {"nodes": []}}, indent=2)
    path.write_text(raw, encoding="utf-8")

    payload, removed = sanitized_graph_bytes(str(path))
    assert removed == 0
    # Compare against the bytes on disk, not the string we wrote: text-mode
    # writes translate newlines on Windows.
    assert payload == path.read_bytes()


def test_a_non_json_file_uploads_unchanged(tmp_path):
    """Bundles may be packed; an unreadable graph must not fail the upload."""
    path = tmp_path / "packed.bin"
    path.write_bytes(b"\x00\x01not json")
    payload, removed = sanitized_graph_bytes(str(path))
    assert removed == 0
    assert payload == b"\x00\x01not json"


def test_both_skill_graph_uploads_opt_in():
    """The diagram JSON and the bundle both leave the machine; neither may
    skip sanitisation."""
    import inspect
    from agent.cloud_api import cloud_api

    src = inspect.getsource(cloud_api.upload_skill_files_with_upload_urls)
    assert src.count("sanitize_skill_graph=True") == 2, (
        "a skill graph upload is no longer sanitised -- a shared skill can "
        "now carry the sharer's store identity"
    )

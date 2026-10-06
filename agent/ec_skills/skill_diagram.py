"""The workflow dict ({"nodes": [...], "edges": [...]}) of a skill's diagram,
whatever shape it was stored in.

A skill's diagram reaches runtime in several shapes depending on where it was
loaded from: the on-disk file ({"workFlow": {...}}), the editor bundle
({"sheets": [{"document": {...}}]}), the DB row as an object ({"nodes": ...})
-- or the DB row as a JSON STRING, sometimes encoded twice. Readers that only
accept a dict with "nodes" silently saw nothing for a string: the 0.9.99yc
千牛 alpha (2026-10-07) ran its front desk with ZERO event-routing rules
because its skill was compiled from the DB copy.
"""
from __future__ import annotations

import json
from typing import Any, Optional


def as_workflow(diagram: Any) -> Optional[dict]:
    """The workflow dict holding "nodes", or None if *diagram* has none."""
    d = diagram
    for _ in range(3):                      # JSON strings, possibly double-encoded
        if not isinstance(d, str):
            break
        try:
            d = json.loads(d)
        except (TypeError, ValueError):
            return None
    if not isinstance(d, dict):
        return None
    wf = d.get("workFlow")
    if isinstance(wf, (dict, str)):
        inner = as_workflow(wf)
        if inner is not None:
            return inner
    sheets = d.get("sheets")
    if isinstance(sheets, list) and sheets:
        main = d.get("mainSheetId")
        sheet = next((s for s in sheets if isinstance(s, dict) and s.get("id") == main), sheets[0])
        doc = sheet.get("document") if isinstance(sheet, dict) else None
        if isinstance(doc, dict) and isinstance(doc.get("nodes"), list):
            return doc
    if isinstance(d.get("nodes"), list):
        return d
    return None

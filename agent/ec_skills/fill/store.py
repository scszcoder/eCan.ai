"""Versions of a platform's fill flow, kept in its experience folder (``fill/``).

- ``seed.json``: the flow the skill ships with. Its ``guards`` are the only
  guards ever used, whatever a later version says.
- ``flow_<n>.json``: every version; ``meta.json`` says which one is current and
  how each did (seed / candidate / verified / failed).
- ``working.json``: the explorer's working copy while it repairs the flow, and
  ``working_dry.json`` the last dry run of it (a copy is proposed only when its
  latest dry run reached the submit and matched the listing).
- ``uploads.json``: pictures already uploaded, so dry runs do not upload again.
- ``notes.md``: the platform playbook (what is known about its pages), seeded
  and extended by the explorer.

A new seed (the skill was regenerated) replaces the current version. A proposed
version runs on the next real listing; the read-back check of that listing
promotes it (verified) or retires it (failed: back to the last good version).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

EDITABLE = ("steps", "snippets", "report", "diag", "start_url")


def _hash(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def validate(flow: Any) -> str:
    """Why *flow* cannot run, or "" when its shape is right."""
    if not isinstance(flow, dict):
        return "the flow must be an object"
    if not isinstance(flow.get("steps"), list) or not flow["steps"]:
        return "steps must be a non-empty list"
    if not isinstance(flow.get("snippets") or {}, dict):
        return "snippets must be an object of name -> script"
    from .engine import OPS
    ids = set()

    def walk(steps, where):
        for k, s in enumerate(steps):
            if not isinstance(s, dict):
                return f"{where}[{k}] is not an object"
            if (s.get("op") or "js") not in OPS:
                return f"{where}[{k}] ({s.get('id')}): unknown op {s.get('op')!r} (ops: {', '.join(OPS)})"
            if not s.get("id"):
                return f"{where}[{k}] has no id"
            if s["id"] in ids:
                return f"step id {s['id']!r} is used twice"
            ids.add(s["id"])
            if s.get("op") == "foreach":
                bad = walk(s.get("steps") or [], f"{where}[{k}].steps")
                if bad:
                    return bad
        return ""
    bad = walk(flow["steps"], "steps")
    if bad:
        return bad
    if sum(1 for s in _all_steps(flow["steps"]) if s.get("op") == "submit") != 1:
        return "the flow must have exactly one submit step"
    return ""


def _all_steps(steps):
    for s in steps or []:
        if isinstance(s, dict):
            yield s
            if s.get("op") == "foreach":
                yield from _all_steps(s.get("steps"))


class FillStore:
    def __init__(self, experience_folder: str):
        self.experience = experience_folder
        self.folder = os.path.join(experience_folder, "fill")
        os.makedirs(self.folder, exist_ok=True)

    # ── files ─────────────────────────────────────────────────────────
    def _p(self, name: str) -> str:
        return os.path.join(self.folder, name)

    def _load(self, name: str, default: Any) -> Any:
        try:
            with open(self._p(name), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, name: str, value: Any) -> None:
        tmp = self._p(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._p(name))

    def meta(self) -> dict:
        return self._load("meta.json", {"versions": []})

    # ── seed and versions ─────────────────────────────────────────────
    def seed(self, flow: dict, notes: str = "") -> None:
        """Install the skill's own flow when it is new or changed (a regenerated skill)."""
        h = _hash(flow)
        meta = self.meta()
        if meta.get("seed_hash") == h and os.path.isfile(self._p("seed.json")):
            return
        self._save("seed.json", flow)
        n = self._add(flow, "seed", "the skill's own flow", "seed", meta)
        meta = self.meta()
        meta.update(seed_hash=h, current=n, good=n)
        self._save("meta.json", meta)
        if notes and not os.path.isfile(self._p("notes.md")):
            with open(self._p("notes.md"), "w", encoding="utf-8") as f:
                f.write(notes)
        for stale in ("working.json", "working_dry.json"):
            if os.path.isfile(self._p(stale)):
                os.remove(self._p(stale))

    def _add(self, flow: dict, by: str, note: str, status: str, meta: Optional[dict] = None) -> int:
        meta = meta or self.meta()
        n = max([v["n"] for v in meta["versions"]] or [0]) + 1
        self._save(f"flow_{n}.json", {k: flow[k] for k in flow if k != "guards"})
        meta["versions"].append({"n": n, "by": by, "at": time.time(), "note": str(note)[:600], "status": status,
                                 "hash": _hash({k: flow[k] for k in flow if k != "guards"})})
        meta["versions"] = meta["versions"][-30:]
        self._save("meta.json", meta)
        return n

    def guards(self) -> dict:
        return dict(self._load("seed.json", {}).get("guards") or {})

    def current(self) -> Tuple[dict, dict, int]:
        """(flow, guards, version) to run now; the seed's guards always."""
        seed = self._load("seed.json", {})
        meta = self.meta()
        n = int(meta.get("current") or 0)
        flow = self._load(f"flow_{n}.json", None) if n else None
        flow = flow or {k: v for k, v in seed.items() if k != "guards"}
        return flow, self.guards(), n

    # ── the explorer's working copy ───────────────────────────────────
    def working(self) -> dict:
        w = self._load("working.json", None)
        if w is None:
            w = copy.deepcopy(self.current()[0])
            self._save("working.json", w)
        return w

    def save_working(self, flow: dict) -> str:
        """Keep an edited working copy; "" or why it was refused."""
        flow = {k: v for k, v in (flow or {}).items() if k in EDITABLE}
        bad = validate(flow)
        if bad:
            return bad
        self._save("working.json", flow)
        return ""

    def note_dry_run(self, flow: dict, result: dict) -> None:
        self._save("working_dry.json", {"hash": _hash(flow), "at": time.time(), "ok": bool(result.get("ok")),
                                        "check_ok": bool((result.get("check") or {}).get("ok")),
                                        "stage": result.get("stage"), "error": result.get("error")})

    def propose(self, note: str) -> Tuple[int, str]:
        """Make the working copy current, if its last dry run reached the submit and the
        form matched the listing. (version, "") or (0, why not)."""
        w = self._load("working.json", None)
        if w is None:
            return 0, "nothing was edited"
        dry = self._load("working_dry.json", {})
        if dry.get("hash") != _hash(w):
            return 0, "the working copy changed after its last dry run: run fill_dry_run again"
        if not (dry.get("ok") and dry.get("check_ok")):
            return 0, f"its last dry run did not pass (stage {dry.get('stage')}: {dry.get('error') or 'form does not match the listing'})"
        meta = self.meta()
        if w == self.current()[0]:
            return 0, "the working copy is the same as the current flow"
        n = self._add(w, "explorer", note, "candidate", meta)
        meta = self.meta()
        meta["current"] = n
        self._save("meta.json", meta)
        for stale in ("working.json", "working_dry.json"):
            if os.path.isfile(self._p(stale)):
                os.remove(self._p(stale))
        return n, ""

    def grade(self, version: int, ok: bool) -> None:
        """The real listing that ran *version* passed (ok) or failed its read-back check."""
        meta = self.meta()
        for v in meta["versions"]:
            if v["n"] != version:
                continue
            if ok:
                v["status"] = "verified" if v["status"] != "seed" else "seed"
                v["passes"] = int(v.get("passes") or 0) + 1
                meta["good"] = version
            else:
                v["fails"] = int(v.get("fails") or 0) + 1
                if v["status"] == "candidate":
                    v["status"] = "failed"
                    meta["current"] = int(meta.get("good") or meta.get("current") or 0)
        self._save("meta.json", meta)

    # ── uploads cache, playbook ───────────────────────────────────────
    def uploads(self) -> dict:
        return self._load("uploads.json", {})

    def save_uploads(self, cache: dict) -> None:
        self._save("uploads.json", cache)

    def notes(self) -> str:
        try:
            return open(self._p("notes.md"), encoding="utf-8").read()
        except OSError:
            return ""

    def add_note(self, text: str) -> None:
        text = str(text or "").strip()
        if text:
            with open(self._p("notes.md"), "a", encoding="utf-8") as f:
                f.write("\n\n" + time.strftime("%Y-%m-%d") + "：" + text[:3000])

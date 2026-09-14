"""Check a skill diagram against what the compiler will actually accept.

The rules here are not opinions — each one is read off
`flowgram2langgraph.py` / `flowgram2langgraph_v2.py`, or off a failure that has
already cost a debugging session. The point is to move those failures forward
in time: today a bad diagram saves fine, runs to completion, and reports `done`
with zero tokens, because an unrecognised node silently becomes
`lambda state: state`. This says so before it is saved.

Usage:
    python -m agent.ec_skills.skill_graph_validator <file.json | directory> [-v]

Exit code is 1 if any ERROR-level finding is present, so it can gate a save.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

try:  # keep the module importable from a bare checkout / lambda bundle
    from agent.ec_skills.flowgram2langgraph import function_registry
    ACCEPTED_TYPES = {t for t in function_registry if t != "default"}
except Exception:  # pragma: no cover - fallback mirrors the registry
    ACCEPTED_TYPES = {
        "llm", "basic", "code", "http", "loop", "condition", "mcp", "tool",
        "event", "comment", "variable", "sheet-call", "pend_event_node",
        "chat_node", "rag_node", "rag", "browser-automation", "task",
        "tool-picker", "dummy",
    }

# Consumed by preprocessing; they never reach a builder, so an unknown-type
# warning about them would be noise.
STRUCTURAL_TYPES = {
    "start", "end", "block-start", "block-end", "group", "loop",
    "sheet-inputs", "sheet_inputs", "sheet-outputs", "sheet_outputs",
    "sheet-call", "sheet_call",
}

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"


@dataclass
class Finding:
    level: str
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"  [{self.level:<5}] {self.code:<22} {self.where:<28} {self.message}"


@dataclass
class Report:
    source: str
    findings: List[Finding] = field(default_factory=list)

    def add(self, level: str, code: str, where: str, message: str) -> None:
        self.findings.append(Finding(level, code, where, message))

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def ok(self) -> bool:
        return not self.errors


def _suggest(node_type: str) -> str:
    canon = str(node_type or "").replace("-", "_").strip().lower()
    for known in ACCEPTED_TYPES:
        k = known.replace("-", "_").lower()
        if canon in (k, k + "_node") or k in (canon, canon + "_node"):
            return known
    return ""


def resolve_graph(diagram: Any) -> Dict[str, Any]:
    """Both shapes are in production: a bare {nodes, edges} and a bundle whose
    graph hangs under `workFlow`. Readers that know only one see an empty graph
    — and an empty graph fails silently. Always resolve through here."""
    if isinstance(diagram, str):  # stored double-encoded in CN Postgres
        try:
            diagram = json.loads(diagram)
        except Exception:
            return {}
    if not isinstance(diagram, dict):
        return {}
    inner = diagram.get("workFlow")
    return inner if isinstance(inner, dict) else diagram


def _walk_nodes(nodes: Iterable[dict], depth: int = 0):
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        yield n, depth
        if n.get("blocks"):
            yield from _walk_nodes(n["blocks"], depth + 1)


def validate(diagram: Any, source: str = "<diagram>") -> Report:
    rep = Report(source)
    graph = resolve_graph(diagram)
    if not isinstance(graph, dict) or ("nodes" not in graph and "edges" not in graph):
        # Not a skill diagram at all (a data_mapping.json, a config, …). Say so
        # and move on rather than reporting a hundred phantom errors.
        rep.add(INFO, "not-a-diagram", "-", "no `nodes`/`edges` key — skipped")
        return rep

    nodes = [n for n in (graph.get("nodes") or []) if isinstance(n, dict)]
    edges = [e for e in (graph.get("edges") or []) if isinstance(e, dict)]
    malformed = len(graph.get("nodes") or []) - len(nodes)
    if malformed:
        rep.add(ERROR, "malformed-node", "-", f"{malformed} entr(y/ies) in `nodes` are not objects")

    if not nodes:
        rep.add(ERROR, "empty-graph", "-",
                "no nodes at diagram.workFlow.nodes or diagram.nodes — this runs to "
                "completion doing nothing")
        return rep

    ids = [str(n.get("id") or "") for n in nodes]
    dupes = {i for i in ids if i and ids.count(i) > 1}
    for d in sorted(dupes):
        rep.add(ERROR, "duplicate-id", d, "two nodes share this id")

    # --- top level: start -> loop/body -> end -----------------------------
    top_types = [n.get("type") for n in nodes]
    if "start" not in top_types:
        rep.add(ERROR, "no-start", "-", "no `start` node at the top level")
    if "end" not in top_types:
        rep.add(WARN, "no-end", "-", "no `end` node at the top level")

    # --- every node ---------------------------------------------------------
    for n, depth in _walk_nodes(nodes):
        nid = str(n.get("id") or "?")
        ntype = n.get("type")
        data = n.get("data") or {}

        if not ntype:
            rep.add(ERROR, "missing-type", nid,
                    "node has no `type` — the compiler will treat it as `code`")
            continue
        if ntype not in ACCEPTED_TYPES and ntype not in STRUCTURAL_TYPES:
            hint = _suggest(ntype)
            rep.add(ERROR, "unknown-type", nid,
                    f"type {ntype!r} is not in function_registry — it compiles to a "
                    f"silent no-op and executes NOTHING"
                    + (f". Did you mean {hint!r}?" if hint else ""))

        if ntype == "loop":
            _check_loop(rep, n, nid)
        elif ntype == "condition":
            _check_condition(rep, n, nid, edges)
        elif ntype == "llm":
            _check_llm(rep, data, nid)
        elif ntype == "code":
            if not (data.get("script") or data.get("code")):
                rep.add(WARN, "code-no-body", nid,
                        "code node has neither `script` nor `code`")

        # Inputs are wrapped, never bare.
        for key, val in (data.get("inputsValues") or {}).items():
            if isinstance(val, dict) and "type" not in val and "content" not in val:
                rep.add(WARN, "unwrapped-input", nid,
                        f"inputsValues.{key} is not a {{type, content}} wrapper")

    # --- edges --------------------------------------------------------------
    known_ids = {i for i, _ in ((str(n.get('id') or ''), d) for n, d in _walk_nodes(nodes))}
    for e in edges:
        src, tgt = str(e.get("sourceNodeID") or ""), str(e.get("targetNodeID") or "")
        if not src or not tgt:
            rep.add(ERROR, "edge-missing-end", f"{src or '?'}->{tgt or '?'}",
                    "edge is missing sourceNodeID or targetNodeID")
            continue
        if src not in known_ids:
            rep.add(ERROR, "edge-dangling", src, "edge source is not a node in this graph")
        if tgt not in known_ids:
            rep.add(ERROR, "edge-dangling", tgt, "edge target is not a node in this graph")

    # Unreachable top-level nodes (start is the root).
    reachable = {"start"}
    changed = True
    while changed:
        changed = False
        for e in edges:
            s_, t_ = str(e.get("sourceNodeID") or ""), str(e.get("targetNodeID") or "")
            if s_ in reachable and t_ and t_ not in reachable:
                reachable.add(t_)
                changed = True
    for n in nodes:
        nid = str(n.get("id") or "")
        if nid and nid not in reachable and n.get("type") not in ("start", "comment"):
            rep.add(WARN, "unreachable", nid, "no path from `start` reaches this node")

    return rep


def _check_loop(rep: Report, node: dict, nid: str) -> None:
    data = node.get("data") or {}
    blocks = node.get("blocks") or []
    inner_edges = node.get("edges") or data.get("internal_edges") or []

    if not blocks:
        rep.add(ERROR, "loop-empty", nid, "loop has no `blocks` — its body is missing")
    btypes = {b.get("type") for b in blocks}
    if blocks and "block-start" not in btypes:
        rep.add(ERROR, "loop-no-block-start", nid, "loop body has no `block-start` entry node")
    if blocks and "block-end" not in btypes:
        rep.add(ERROR, "loop-no-block-end", nid, "loop body has no `block-end` exit node")
    if blocks and not inner_edges:
        rep.add(ERROR, "loop-no-edges", nid,
                "loop has blocks but no inner edges — nothing in the body is wired")
    if data.get("internal_edges") and not node.get("edges"):
        rep.add(WARN, "loop-edges-key", nid,
                "inner edges are under data.internal_edges; the compiler reads the "
                "loop node's own `edges`")

    mode = data.get("loopMode")
    if not mode:
        rep.add(WARN, "loop-no-mode", nid, "loop has no `loopMode` (expected loopWhile / loopFor)")
    expr = (data.get("loopWhileExpr") or "").strip()
    if mode == "loopWhile" and not expr:
        rep.add(ERROR, "loop-no-condition", nid, "loopWhile with an empty `loopWhileExpr`")
    if expr and "state[" in expr and ".get(" not in expr:
        # 72 of 79 skills in my_skills/ do this; it raises on iteration one.
        rep.add(ERROR, "loop-unsafe-expr", nid,
                f"loopWhileExpr subscripts state directly ({expr[:60]!r}) — raises "
                "KeyError on the first iteration, before anything has populated it. "
                "Use state.get(\"result\", {}).get(...) with defaults")


def _check_condition(rep: Report, node: dict, nid: str, edges: List[dict]) -> None:
    data = node.get("data") or {}
    if not data.get("conditions"):
        rep.add(ERROR, "condition-empty", nid, "condition node has no `conditions`")
    out = [e for e in edges if str(e.get("sourceNodeID") or "") == nid]
    if not out:
        return
    unported = [e for e in out if not e.get("sourcePortID")]
    for _ in unported:
        rep.add(ERROR, "branch-no-port", nid,
                "outgoing edge has no `sourcePortID` — branch selection is by port, "
                "not by edge order, so this branch is unroutable")
    ports = {str(e.get("sourcePortID") or "").split("_")[0] for e in out if e.get("sourcePortID")}
    if ports and "if" in ports and "else" not in ports:
        rep.add(WARN, "branch-no-else", nid, "condition has an `if_` branch but no `else_` branch")


def _check_llm(rep: Report, data: dict, nid: str) -> None:
    iv = data.get("inputsValues") or {}

    def content(key):
        v = iv.get(key)
        return v.get("content") if isinstance(v, dict) else v

    if not content("modelName"):
        rep.add(WARN, "llm-no-model", nid, "llm node names no model")
    api_host = str(content("apiHost") or "")
    if "api.openai.com" in api_host:
        rep.add(ERROR, "llm-direct-host", nid,
                "apiHost points at api.openai.com — unreachable from China, every call "
                "times out at 45s unless ECAN_LLM_FORCE_PROXY rewrites it. Leave apiHost "
                "empty and let the proxy route it")
    key = str(content("apiKey") or "")
    if key and not key.startswith("sk-xxx"):
        rep.add(ERROR, "llm-embedded-key", nid,
                "an API key is embedded in the diagram — keys come from the server")


# ---------------------------------------------------------------------------


def validate_file(path: str) -> Report:
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        rep = Report(path)
        rep.add(ERROR, "unreadable", "-", f"{exc}")
        return rep
    return validate(payload, path)


def _iter_targets(target: str):
    if os.path.isfile(target):
        yield target
        return
    # A skill tree is full of caches, run logs and prompt dumps. The graphs are
    # the files sitting directly in a `diagram_dir`; walking everything turns a
    # 79-skill audit into 65k files of noise. Pass --all to override.
    only_diagrams = "--all" not in sys.argv
    for root, _dirs, files in os.walk(target):
        if only_diagrams and os.path.basename(root) != "diagram_dir":
            continue
        for f in files:
            if f.endswith(".json") and not f.endswith("_bundle.json"):
                yield os.path.join(root, f)


def main(argv: List[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    verbose = "-v" in argv
    target = [a for a in argv if not a.startswith("-")][0]

    reports = [validate_file(p) for p in sorted(_iter_targets(target))]
    bad = [r for r in reports if not r.ok]
    codes: Dict[str, int] = {}
    for r in reports:
        for f in r.findings:
            if f.level == ERROR or verbose:
                codes[f.code] = codes.get(f.code, 0) + 1

    for r in reports:
        shown = [f for f in r.findings if f.level == ERROR or verbose]
        if not shown:
            continue
        print(f"\n{os.path.basename(r.source)}")
        for f in shown:
            print(f)

    print(f"\n{len(reports)} diagram(s): {len(reports) - len(bad)} clean, {len(bad)} with errors")
    if codes:
        print("findings by code:")
        for code, n in sorted(codes.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>4}  {code}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

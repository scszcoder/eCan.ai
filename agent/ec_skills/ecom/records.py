"""Rule matches -> the spec's records: DecisionRecord + ProposedAction (actions) or findings
(audits). Ids are stable per (store, rule, entity, day), so a rerun the same day updates the
same proposal instead of adding a second one."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any, Dict, List, Optional


def _id(prefix: str, *parts: Any) -> str:
    return f"{prefix}-" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def _evidence(ev: Dict[str, Any], window: str, source: str) -> List[Dict[str, Any]]:
    out = []
    for k, v in ev.items():
        if isinstance(v, (list, dict)):
            v = str(v)
        out.append({"metric": k, "value": "" if v is None else (round(v, 4) if isinstance(v, float) else v),
                    "window": window, "source": source})
    return out


def to_actions(matches: List[Dict[str, Any]], *, store_id: str, platform: str, window: str, source: str,
               provenance: Optional[Dict[str, Any]] = None, review_days: int = 14,
               today: Optional[date] = None) -> Dict[str, List[Dict[str, Any]]]:
    today = today or date.today()
    decisions, actions = [], []
    for m in matches:
        act = m.get("action") or {}
        did = _id("dec", store_id, m["rule_id"], m["entity"]["id"], today)
        aid = _id("act", store_id, m["rule_id"], m["entity"]["id"], today)
        decisions.append({
            "id": did, "object": m["entity"], "judgment": m["judgment"],
            "evidence": _evidence(m.get("evidence") or {}, window, source), "action": "act",
            "action_ids": [aid], "confidence": "medium", "rule_id": m["rule_id"],
            "acceptance": {"metric": "roas", "target": "not below the store target",
                           "review_at": (today + timedelta(days=review_days)).isoformat()},
            "provenance": provenance or {}})
        actions.append({
            "action_id": aid, "type": act.get("type", "other"), "platform": platform, "target": m["entity"],
            "before": act.get("before"), "after": act.get("after"), "rationale_decision_id": did,
            "risk": act.get("risk", "medium"), "reversible": bool(act.get("reversible", True)),
            "required_level": act.get("required_level", 2), "execution": {"mode": "bulk_file"},
            "status": "proposed"})
    return {"decisions": decisions, "actions": actions}


def observations(items: List[Dict[str, Any]], *, store_id: str, window: str, source: str,
                 today: Optional[date] = None, review_days: int = 7) -> List[Dict[str, Any]]:
    """'observe' and 'skipped' rule results as no-action decisions with a review date."""
    today = today or date.today()
    return [{"id": _id("dec", store_id, m["rule_id"], m["entity"]["id"], today, "obs"), "object": m["entity"],
             "judgment": f"{m['judgment']} (not acted on: {m.get('reason')})",
             "evidence": _evidence(m.get("evidence") or {}, window, source), "action": "observe",
             "confidence": "low", "rule_id": m["rule_id"],
             "acceptance": {"metric": "sample", "target": "enough data to decide",
                            "review_at": (today + timedelta(days=review_days)).isoformat()}} for m in items]


def findings(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Audit matches (tracking/feed/readiness) as plain findings."""
    return [{"rule_id": m["rule_id"], "object": m["entity"], "detail": m["judgment"],
             **{k: v for k, v in (m.get("action") or {}).items()}, "evidence": m.get("evidence") or {}}
            for m in matches]

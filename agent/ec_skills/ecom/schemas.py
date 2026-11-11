"""The shared shapes every store skill reads and writes (TaskEnvelope, SkillResult,
DecisionRecord, ProposedAction, StoreProfile, ...), as JSON Schemas.

``get(name)`` returns one schema; ``validate(name, obj)`` returns a list of error strings
(empty when the object fits). Shapes allow extra keys so a newer skill can add fields
without breaking an older reader.
"""
from __future__ import annotations

from typing import Any, Dict, List

from jsonschema import Draft202012Validator

_STR = {"type": "string"}
_NUM = {"type": "number"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_OBJ = {"type": "object"}
_ANY: Dict[str, Any] = {}


def _ref(name: str) -> Dict[str, Any]:
    return {"$ref": f"#/$defs/{name}"}


def _arr(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "array", "items": item}


def _enum(*values: Any) -> Dict[str, Any]:
    return {"enum": list(values)}


def _shape(required: List[str], **props: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "required": required, "properties": props}


PLATFORMS = ("amazon", "tiktok_shop", "shopify", "etsy", "ebay", "walmart", "reddit", "google_ads",
             "meta", "multi")
ACTION_TYPES = ("bid_change", "budget_change", "placement_change", "negate_keyword", "add_keyword",
                "campaign_create", "campaign_pause", "listing_update", "price_change", "promo_create",
                "inventory_reorder", "message_send", "post_publish", "appeal_submit", "ticket_create",
                "label_change", "bidding_change", "other")
ENTITY_TYPES = ("store", "sku", "asin", "listing", "campaign", "ad_group", "keyword", "search_term",
                "placement", "video", "creator", "product", "subreddit", "thread", "page", "order",
                "review", "conversion_action", "account")

DEFS: Dict[str, Dict[str, Any]] = {
    "EntityRef": _shape(["type", "id"], type=_enum(*ENTITY_TYPES), id=_STR, name=_STR,
                        parent=_ref("EntityRef")),
    "Evidence": _shape(["metric", "value", "window", "source"], metric=_STR,
                       value={"type": ["number", "string"]}, baseline={"type": ["number", "string", "null"]},
                       window=_STR, source=_STR),
    "ArtifactRef": _shape(["id", "kind", "uri", "created_at"],
                          id=_STR, kind=_enum("csv", "xlsx", "json", "md", "html", "png", "jpg", "mp4", "pdf"),
                          uri=_STR, schema=_STR, rows=_INT, sha256=_STR, created_at=_STR, source=_STR,
                          date_range=_arr(_STR)),
    "DecisionRecord": _shape(
        ["id", "object", "judgment", "evidence", "action", "confidence"],
        id=_STR, object=_ref("EntityRef"), judgment=_STR, evidence=_arr(_ref("Evidence")), cause=_STR,
        action=_enum("act", "observe", "no_action", "escalate"), action_ids=_arr(_STR),
        acceptance=_shape(["metric", "target", "review_at"], metric=_STR, target=_STR, review_at=_STR),
        confidence=_enum("high", "medium", "low"), rule_id=_STR, provenance=_OBJ),
    "ProposedAction": _shape(
        ["action_id", "type", "platform", "target", "after", "rationale_decision_id", "risk", "reversible",
         "required_level", "execution", "status"],
        action_id=_STR, type=_enum(*ACTION_TYPES), platform=_STR, target=_ref("EntityRef"),
        before=_ANY, after=_ANY, rationale_decision_id=_STR, risk=_enum("low", "medium", "high"),
        reversible=_BOOL, rollback=_ANY, required_level=_enum(1, 2, 3),
        execution=_shape(["mode"], mode=_enum("bulk_file", "api", "browser", "manual"), artifact_id=_STR),
        status=_enum("proposed", "approved", "rejected", "executed", "failed", "rolled_back")),
    "Anomaly": _shape(["id", "class", "object", "metric", "value", "baseline", "delta_pct", "window",
                       "detected_at"],
                      id=_STR, **{"class": _enum("immediate", "same_day", "observe")}, object=_ref("EntityRef"),
                      metric=_STR, value=_NUM, baseline=_NUM, delta_pct=_NUM, window=_STR, detected_at=_STR,
                      hypothesis=_STR, owner_role=_STR, deadline=_STR, review_at=_STR),
    "FollowupRequest": _shape(["skill", "reason", "inputs", "priority"], skill=_STR, reason=_STR,
                              inputs=_OBJ, priority=_enum("p0", "p1", "p2")),
    "TaskEnvelope": _shape(
        ["task_id", "skill", "requested_by", "store_id", "platform", "inputs", "approval_level_max"],
        task_id=_STR, parent_task_id=_STR, playbook_id=_STR, skill=_STR, skill_version=_STR,
        requested_by=_enum("manager", "human", "schedule", "event"), store_id=_STR,
        platform=_enum(*PLATFORMS), marketplace=_STR, inputs=_OBJ, artifacts_in=_arr(_ref("ArtifactRef")),
        vars_override=_OBJ, approval_level_max=_enum(0, 1, 2, 3), mode=_enum("run", "explore"),
        deadline=_STR, dry_run=_BOOL, locale_out=_STR, tenant_id=_STR),
    "SkillResult": _shape(
        ["success", "task_id", "skill", "skill_version", "summary", "status", "result", "metrics", "all_done"],
        success=_BOOL, task_id=_STR, skill=_STR, skill_version=_STR, summary=_STR,
        status=_enum("done", "partial", "needs_input", "needs_approval", "failed"), result=_OBJ,
        decisions=_arr(_ref("DecisionRecord")), actions_proposed=_arr(_ref("ProposedAction")),
        anomalies=_arr(_ref("Anomaly")), artifacts=_arr(_ref("ArtifactRef")),
        followups=_arr(_ref("FollowupRequest")), warnings=_arr(_STR),
        errors=_arr(_shape(["code", "message"], code=_STR, message=_STR, details=_ANY)),
        metrics=_shape(["started_at", "ended_at"], started_at=_STR, ended_at=_STR, llm_tokens=_INT,
                       llm_cost_usd=_NUM, browser_steps=_INT, model_used=_STR, escalated_from=_STR,
                       escalation_trigger=_STR, fallback_used=_BOOL),
        all_done={"const": True}),
    "StoreProfile": _shape(
        ["store_id", "platform", "marketplace", "currency", "timezone", "languages", "legal_entity_id"],
        store_id=_STR, tenant_id=_STR, platform=_enum(*PLATFORMS), marketplace=_STR, currency=_STR,
        timezone=_STR, brand=_STR, categories=_arr(_STR), data_access=_arr(_STR),
        browser_profiles=_arr(_shape(["site", "profile"], site=_STR, profile=_STR)),
        targets=_shape([], monthly_revenue=_NUM, net_margin_min=_NUM, target_acos=_NUM, target_tacos=_NUM,
                       target_roas=_NUM),
        approval_policy_id=_STR,
        notify=_shape([], email=_arr(_STR), sms_e164=_arr(_STR), quiet_hours=_arr(_STR)),
        owners=_OBJ,
        languages=_shape(["owner", "customer"], owner=_STR, customer=_arr(_STR)),
        legal_entity_id=_STR, no_touch_profiles=_arr(_STR)),
    "ProductFacts": _shape(
        ["sku", "title_internal", "category"],
        sku=_STR, product_id=_STR, asin=_STR, title_internal=_STR, category=_STR, marketplaces=_arr(_STR),
        specs=_OBJ, features=_arr(_shape(["name", "detail"], name=_STR, detail=_STR)),
        claims=_arr(_shape(["text", "status"], text=_STR, evidence_ref=_STR,
                           status=_enum("verified", "needs_data", "banned"))),
        certifications=_arr(_OBJ), target_users=_arr(_STR), scenarios=_arr(_STR), differentiators=_arr(_STR),
        price=_shape([], list=_NUM, current=_NUM, floor=_NUM), cogs={"type": ["number", "null"]},
        cogs_source=_enum("discovered", "owner", "upload", "estimate", None),
        first_mile_per_unit=_NUM, fees=_OBJ, images_ref=_arr(_STR), restricted_flags=_arr(_STR)),
    "ProfitLedgerRow": _shape(
        ["date", "store_id", "platform", "currency", "gross_sales", "refunds", "platform_fees", "ad_spend",
         "cogs_est", "shipping_cost", "ai_cost", "other_costs", "contribution", "cogs_coverage", "completeness"],
        date=_STR, store_id=_STR, platform=_STR, currency=_STR, gross_sales=_NUM, refunds=_NUM,
        platform_fees=_NUM, ad_spend=_NUM, cogs_est=_NUM, shipping_cost=_NUM, ai_cost=_NUM, other_costs=_NUM,
        contribution=_NUM, cogs_coverage=_NUM, completeness=_enum("complete", "partial", "estimated"),
        source_refs=_arr(_STR)),
    "Goal": _shape(
        ["goal_id", "statement", "metric", "period", "scope", "constraints", "status"],
        goal_id=_STR, statement=_STR,
        metric=_enum("contribution_profit", "revenue", "orders", "roas", "custom"), target=_NUM,
        period=_enum("week", "month", "quarter"), scope=_OBJ,
        constraints=_shape([], ad_spend_cap_month=_OBJ, min_net_margin=_NUM, max_risk=_enum("low", "medium"),
                           health_must_not_degrade=_BOOL, exploration_share_max=_NUM,
                           max_concurrent_experiments_per_store=_INT, no_go=_arr(_STR)),
        priority=_NUM, status=_enum("active", "paused", "done"), created_from=_enum("chat", "onboarding"),
        updated_at=_STR),
    "UserInstruction": _shape(
        ["id", "text", "kind", "scope", "status"],
        id=_STR, text=_STR, kind=_enum("rule", "fact", "preference", "no_go", "budget"), scope=_OBJ,
        kb_key=_STR, value=_ANY, status=_enum("proposed", "confirmed", "revoked"), created_at=_STR),
}

_VALIDATORS: Dict[str, Draft202012Validator] = {}


def names() -> List[str]:
    return sorted(DEFS)


def get(name: str) -> Dict[str, Any]:
    """The JSON Schema for ``name``, self-contained (carries all $defs)."""
    if name not in DEFS:
        raise KeyError(f"unknown schema {name!r}; known: {', '.join(names())}")
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **DEFS[name], "$defs": DEFS}


def validate(name: str, obj: Any) -> List[str]:
    if name not in _VALIDATORS:
        _VALIDATORS[name] = Draft202012Validator(get(name))
    errors = sorted(_VALIDATORS[name].iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]

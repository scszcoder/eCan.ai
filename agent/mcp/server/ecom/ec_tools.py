"""MCP tools over the e-commerce L1 layer (``agent/ec_skills/ecom``): the numbers and rules
the store skills use. Deterministic: no LLM runs inside any of them.

  ec_kb               KB records (store profile, product facts, instructions, learnings) and
                      layered rule values (resolve / thresholds)
  ec_report_ingest    a downloaded report file -> canonical table rows in the local store
  ec_table_query      read-only SQL over the local store (the way an LLM step gets numbers)
  ec_unit_economics   margin and break-even ROAS / CPA per product
  ec_rules_eval       run a ruleset (gads_v1, tracking_v1, feed_v1, readiness_v1) -> decisions,
                      proposed actions or findings, recorded in the decision log
  ec_actions          list proposed actions; record the owner's approve / reject from chat
  ec_bulk_file_build  approved actions -> the platform's own upload file (a draft; nothing applied)
  ec_schemas_get      the JSON Schema of a shared shape

Wiring: ``add_ec_tool_schemas`` in tool_schemas.py, ``EC_TOOL_HANDLERS`` in server.py.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import mcp.types as types
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger, get_traceback


def _store(cfg: Dict[str, Any]):
    from agent.ec_skills.ecom.store import Store, DEFAULT_TENANT
    return Store(cfg.get("tenant_id") or DEFAULT_TENANT)


def _ok(data: Any) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str, indent=1))]


def _err(msg: str) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": msg}, ensure_ascii=False))]


def _wrap(name):
    def deco(fn):
        async def handler(mainwin, args):
            try:
                return _ok(fn((args or {}).get("input") or {}))
            except (ValueError, KeyError, PermissionError, FileNotFoundError) as e:
                return _err(f"{type(e).__name__}: {e}")
            except Exception as e:
                logger.error(get_traceback(e, f"Error_{name}"))
                return _err(f"{type(e).__name__}: {e}")
        handler.__name__ = name
        return handler
    return deco


# ---------------------------------------------------------------- handlers

@_wrap("ec_kb")
def ec_kb(cfg):
    from agent.ec_skills.ecom import kb
    store, op = _store(cfg), cfg.get("op")
    if op == "get":
        return store.kb_get(cfg["collection"], cfg["key"], cfg.get("version"))
    if op == "list":
        return store.kb_list(cfg["collection"])
    if op == "put":
        version = kb.put_record(store, cfg["collection"], cfg["key"], cfg["value"], source="agent")
        return {"collection": cfg["collection"], "key": cfg["key"], "version": version}
    if op == "resolve":
        return kb.resolve(cfg["key"], cfg.get("scope") or {}, store)
    if op == "thresholds":
        return kb.thresholds(cfg["key"], cfg.get("scope") or {}, store)
    raise ValueError("op must be get, list, put, resolve or thresholds")


@_wrap("ec_report_ingest")
def ec_report_ingest(cfg):
    from agent.ec_skills.ecom import reports
    return reports.ingest(_store(cfg), Path(cfg["file_path"]), cfg["store_id"], report_type=cfg.get("report_type"),
                          currency=cfg.get("currency") or "", tz=cfg.get("tz") or "")


@_wrap("ec_table_query")
def ec_table_query(cfg):
    store = _store(cfg)
    if cfg.get("list_tables"):
        return store.tables()
    return store.query(cfg["sql"], cfg.get("params") or [], int(cfg.get("limit") or 200))


@_wrap("ec_unit_economics")
def ec_unit_economics(cfg):
    from agent.ec_skills.ecom import kb, metrics
    store = _store(cfg)
    scope = {"store_id": cfg.get("store_id"), "platform": cfg.get("platform") or "shopify"}
    fee_pct = cfg.get("payment_fee_pct")
    fee_fixed = cfg.get("payment_fee_fixed")
    if fee_pct is None:
        fee_pct = kb.value("shopify.payment_fee_pct", scope, store, 0.0)
    if fee_fixed is None:
        fee_fixed = kb.value("shopify.payment_fee_fixed", scope, store, 0.0)
    items = cfg.get("items") or [cfg]
    out = []
    for it in items:
        if it.get("price") is None or it.get("cogs") is None:
            out.append({"id": it.get("id"), "error": "price and cogs are both needed; ask the owner for the cost"})
            continue
        ue = metrics.unit_economics(float(it["price"]), float(it["cogs"]), shipping=float(it.get("shipping") or 0),
                                    payment_fee_pct=float(fee_pct), payment_fee_fixed=float(fee_fixed),
                                    platform_fee_pct=float(it.get("platform_fee_pct") or 0),
                                    return_pct=float(it.get("return_pct") or 0),
                                    promo_pct=float(it.get("promo_pct") or 0), other=float(it.get("other") or 0))
        out.append({"id": it.get("id"), **ue})
    return {"items": out, "fees_used": {"payment_fee_pct": fee_pct, "payment_fee_fixed": fee_fixed}}


def _thresholds(prefix, scope, store):
    from agent.ec_skills.ecom import kb
    resolved = kb.thresholds(prefix, scope, store)
    return ({k: v["value"] for k, v in resolved.items()},
            {k: {"layer": v["layer"], "provenance_id": v["provenance_id"]} for k, v in resolved.items()})


@_wrap("ec_rules_eval")
def ec_rules_eval(cfg):
    from agent.ec_skills.ecom import prepare, records, rules
    store, rid, store_id = _store(cfg), cfg["ruleset_id"], cfg["store_id"]
    today = date.fromisoformat(cfg["today"]) if cfg.get("today") else date.today()
    ruleset = rules.load_ruleset(rid)
    scope = {"store_id": store_id, **(cfg.get("scope") or {})}
    t, provenance = _thresholds("thresholds.gads", scope, store)
    if rid == "gads_v1":
        window = int(cfg.get("window_days") or 14)
        ctx = prepare.gads_context(store, store_id, breakeven_roas=cfg.get("breakeven_roas"),
                                   target_roas=cfg.get("target_roas"), target_cpa=cfg.get("target_cpa"),
                                   aov=cfg.get("aov"))
        if ctx["missing"]:
            return {"status": "needs_input", "missing": ctx["missing"],
                    "message": "Set the break-even ROAS (from product costs via ec_unit_economics) or targets first"}
        tables = prepare.gads_tables(store, store_id, window_days=window, today=today,
                                     breakeven_roas=ctx["breakeven_roas"])
        ctx["in_learning"] = lambda c: tables["in_learning"].get(c, False)
        out = rules.run(ruleset, tables, t, ctx, mode=cfg.get("mode") or "optimize_weekly")
        recs = records.to_actions(out["matches"], store_id=store_id, platform="google_ads", window=f"{window}d",
                                  source="gads report tables", provenance=provenance, today=today)
        obs = records.observations(out["observe"] + out["skipped"], store_id=store_id, window=f"{window}d",
                                   source="gads report tables", today=today)
        for d in recs["decisions"] + obs:
            store.log("decision", d, store_id)
        for a in recs["actions"]:
            prior = next((x for x in store.log_query("action", store_id) if x["action_id"] == a["action_id"]), None)
            if prior and prior.get("status") != "proposed":
                a["status"] = prior["status"]        # a rerun never resets an approved or rejected action
            store.log("action", a, store_id)
        return {"status": "done", "targets": {k: ctx[k] for k in ("breakeven_roas", "target_roas", "target_cpa")},
                "in_learning": [c for c, v in tables["in_learning"].items() if v],
                "decisions": recs["decisions"], "actions": recs["actions"], "observe": obs,
                "counts": {"actions": len(recs["actions"]), "observe": len(obs)}}
    if rid == "tracking_v1":
        facts = prepare.tracking_facts(cfg.get("conversion_actions") or [], **(cfg.get("reconcile") or {}))
        tables = {"facts": [facts]}
    elif rid == "feed_v1":
        tables = prepare.feed_tables(store, store_id, cfg.get("policy_pages"), cfg.get("account_issues"))
        t.update({"title_max": tables["items"][0]["title_max"] if tables["items"] else 150})
    elif rid == "readiness_v1":
        tables = {"summary": [{"store_id": store_id, **(cfg.get("summary") or {})}]}
    else:
        tables = cfg.get("tables") or {}
    out = rules.run(ruleset, tables, t, cfg.get("ctx") or {})
    found = records.findings(out["matches"])
    severities = [f.get("severity") for f in found]
    verdict = ("fail" if any(s in ("fail", "immediate") for s in severities)
               else "warn" if found and rid != "readiness_v1" else "pass")
    if rid == "readiness_v1":
        verdict = "blocked" if found else "ready"
    result = {"status": "done", "ruleset": rid, "verdict": verdict, "findings": found}
    if rid == "tracking_v1":
        result["facts"] = facts
    if rid == "feed_v1":
        result.update({"approval_rate": tables.get("approval_rate"), "item_count": tables.get("item_count")})
    store.log("audit", {"id": f"audit-{rid}-{store_id}-{today}", "ruleset": rid, "verdict": verdict,
                        "findings": len(found), "date": today.isoformat()}, store_id)
    return result


@_wrap("ec_actions")
def ec_actions(cfg):
    store, store_id, op = _store(cfg), cfg["store_id"], cfg.get("op") or "list"
    actions = store.log_query("action", store_id)
    if op == "list":
        want = cfg.get("status")
        return [a for a in actions if not want or a.get("status") == want]
    if op == "decide":
        decision = cfg["decision"]
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be approved or rejected")
        note = (cfg.get("owner_words") or "").strip()
        if not note:
            raise ValueError("owner_words is required: quote what the owner said in chat")
        changed, refused = [], []
        for a in actions:
            if a["action_id"] not in (cfg.get("action_ids") or []):
                continue
            if decision == "approved" and a.get("risk") == "high":
                refused.append({"action_id": a["action_id"], "reason": "high-risk actions need the approval page + PIN"})
                continue
            a["status"] = decision
            a["decided"] = {"by": "owner (chat)", "owner_words": note, "on": date.today().isoformat()}
            store.log("action", a, store_id)
            changed.append(a["action_id"])
        return {"changed": changed, "refused": refused}
    raise ValueError("op must be list or decide")


@_wrap("ec_bulk_file_build")
def ec_bulk_file_build(cfg):
    from agent.ec_skills.ecom import bulk_files
    from agent.ec_skills.reports.report_store import report_dir
    store, store_id = _store(cfg), cfg["store_id"]
    actions = cfg.get("actions")
    if actions is None:
        wanted = set(cfg.get("action_ids") or [])
        actions = [a for a in store.log_query("action", store_id) if not wanted or a["action_id"] in wanted]
    names = {"google_ads": "google_ads_upload.csv", "gmc_supplemental": "gmc_supplemental.tsv",
             "shopify_products": "shopify_products_import.csv"}
    platform = cfg["platform"]
    if platform not in names:
        raise ValueError(f"platform must be one of {sorted(names)}")
    out = bulk_files.build(platform, actions, report_dir("bulk_files", store_id) / names[platform])
    out["note"] = "Draft only: upload it in the platform's own screen and check its preview before applying."
    return out


@_wrap("ec_schemas_get")
def ec_schemas_get(cfg):
    from agent.ec_skills.ecom import schemas
    return schemas.get(cfg["name"]) if cfg.get("name") else {"schemas": schemas.names()}


EC_TOOL_HANDLERS = {
    "ec_kb": ec_kb, "ec_report_ingest": ec_report_ingest, "ec_table_query": ec_table_query,
    "ec_unit_economics": ec_unit_economics, "ec_rules_eval": ec_rules_eval, "ec_actions": ec_actions,
    "ec_bulk_file_build": ec_bulk_file_build, "ec_schemas_get": ec_schemas_get,
}

# ---------------------------------------------------------------- schemas

_CAT = "<category>Ecommerce</category><sub-category>{}</sub-category>"
_TENANT = {"tenant_id": {"type": "string", "description": "Seller's data space; leave empty for this desktop's own"}}


def _tool(name, sub, description, required, props):
    return types.Tool(_meta={"run_in_cloud": False}, name=name, description=_CAT.format(sub) + description,
                      inputSchema={"type": "object", "required": ["input"], "properties": {"input": {
                          "type": "object", "required": required, "properties": {**props, **_TENANT}}}})


def add_ec_tool_schemas(tool_schemas):
    S, N, I, B, O, A = ({"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"},
                        {"type": "object"}, {"type": "array"})
    tool_schemas += [
        _tool("ec_kb", "Knowledge",
              "Seller knowledge records and rule values. op=get|list|put on a collection (store_profile, "
              "product_facts, user_instruction, learning, goal, ...); op=resolve gives one rule value with the "
              "layer it came from (owner instruction > learning > pack default); op=thresholds gives every value "
              "under a prefix such as 'thresholds.gads'. The immutable core cannot be written.",
              ["op"], {"op": {"type": "string", "enum": ["get", "list", "put", "resolve", "thresholds"]},
                       "collection": S, "key": {**S, "description": "record key, or the rule key / prefix"},
                       "value": {"description": "record to store (put)"}, "version": I,
                       "scope": {**O, "description": "{store_id, platform, category, sku}"}}),
        _tool("ec_report_ingest", "Reports",
              "Load a downloaded report (Google Ads campaign / search terms / shopping products, Shopify products "
              "export, Merchant Center products) into the store's local tables. Detects the report from its "
              "headers; re-loading the same dates replaces them, never doubles.",
              ["file_path", "store_id"], {"file_path": S, "store_id": S, "report_type": S, "currency": S, "tz": S}),
        _tool("ec_table_query", "Reports",
              "Read-only SQL (SELECT) over the local report tables and KB. Use this for every number you state. "
              "list_tables=true lists tables and columns. Rows carry _store_id.",
              [], {"sql": S, "params": A, "limit": I, "list_tables": B}),
        _tool("ec_unit_economics", "Profit",
              "Margin before ads and break-even ROAS / CPA for one product or a list (items). Needs price and the "
              "owner's cost (cogs); never estimate a cost yourself.",
              [], {"store_id": S, "platform": S, "price": N, "cogs": N, "shipping": N, "return_pct": N,
                   "promo_pct": N, "items": {**A, "items": O}, "payment_fee_pct": N, "payment_fee_fixed": N}),
        _tool("ec_rules_eval", "Rules",
              "Run a ruleset on the store's data. gads_v1 (mode optimize_daily|optimize_weekly; needs "
              "breakeven_roas or targets, and aov for the target CPA) returns decisions + proposed actions "
              "(status proposed). tracking_v1 takes conversion_actions + reconcile {shopify_orders, "
              "gads_conversions, ga4_purchases}; feed_v1 takes policy_pages {refund, shipping, privacy, terms, "
              "contact: bool} + account_issues; readiness_v1 takes summary {tracking, feed_approval_rate, "
              "feed_account_issues, policy_pages_ok, auto_apply_off}. Audits return verdict + findings.",
              ["ruleset_id", "store_id"],
              {"ruleset_id": {"type": "string", "enum": ["gads_v1", "tracking_v1", "feed_v1", "readiness_v1"]},
               "store_id": S, "mode": S, "window_days": I, "breakeven_roas": N, "target_roas": N, "target_cpa": N,
               "aov": N, "conversion_actions": {**A, "items": O}, "reconcile": O, "policy_pages": O,
               "account_issues": {**A, "items": O}, "summary": O, "today": S}),
        _tool("ec_actions", "Approvals",
              "Proposed actions for a store. op=list (optionally status=proposed|approved|rejected); op=decide "
              "records the OWNER's approve/reject for action_ids, with owner_words quoting what the owner said "
              "in chat. Only call decide after the owner has answered; never decide on your own. High-risk "
              "actions cannot be approved in chat.",
              ["store_id"], {"store_id": S, "op": {"type": "string", "enum": ["list", "decide"]}, "status": S,
                             "action_ids": {**A, "items": S},
                             "decision": {"type": "string", "enum": ["approved", "rejected"]}, "owner_words": S}),
        _tool("ec_bulk_file_build", "Approvals",
              "Write the platform's upload file from APPROVED actions only: google_ads (bulk upload CSV), "
              "gmc_supplemental (Merchant Center supplemental feed), shopify_products (Products CSV import, "
              "changed columns only; never price, inventory, variants or status). A draft: nothing is applied.",
              ["platform", "store_id"],
              {"platform": {"type": "string", "enum": ["google_ads", "gmc_supplemental", "shopify_products"]},
               "store_id": S, "action_ids": {**A, "items": S}, "actions": {**A, "items": O}}),
        _tool("ec_schemas_get", "Knowledge",
              "JSON Schema of a shared record shape (TaskEnvelope, SkillResult, DecisionRecord, ProposedAction, "
              "StoreProfile, ProductFacts, Goal, ...); no name lists them.", [], {"name": S}),
    ]

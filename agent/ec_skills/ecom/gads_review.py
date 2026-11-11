"""Google Ads period review: the files a browser step downloaded -> one report.

The browser step (skill google_ads_review) downloads the Campaigns, Search terms and
Products reports for the period and answers with JSON: the account it read, the date
range, the conversion actions as the Conversions page lists them, and what it could not
download. This module ingests the files, adds up the numbers (never the LLM's), runs the
tracking audit, runs gads_v1 when the break-even ROAS is known, and writes
report.md / report.json under <reports>/google_ads/<store>/<date>/.

A run that downloaded nothing is reported as "REVIEW DID NOT COMPLETE", never as an
account without problems.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.ec_skills.ecom import kb, prepare, records, reports, rules
from agent.ec_skills.ecom.metrics import ratio
from agent.ec_skills.ecom.store import Store

CATEGORY = "google_ads"
FILE_TYPES = (".csv", ".tsv", ".txt", ".xlsx", ".zip")


def parse_answer(final: Any) -> Optional[Dict[str, Any]]:
    if isinstance(final, dict):
        return final if set(final) & {"downloads", "conversion_actions", "account", "signin_required"} else None
    match = re.search(r"\{.*\}", str(final or ""), re.S)
    if not match:
        return None
    try:
        out = json.loads(match.group(0))
    except ValueError:
        return None
    return out if isinstance(out, dict) else None


def new_files(folder: Optional[str], since: float) -> List[Path]:
    """Report files that appeared in ``folder`` after ``since`` (epoch seconds); zips are unpacked."""
    if not folder or not Path(folder).is_dir():
        return []
    out: List[Path] = []
    for p in sorted(Path(folder).iterdir(), key=lambda x: x.stat().st_mtime):
        if not p.is_file() or p.suffix.lower() not in FILE_TYPES or p.stat().st_mtime < since - 5:
            continue
        if p.suffix.lower() == ".zip":
            import zipfile
            with zipfile.ZipFile(p) as z:
                for name in z.namelist():
                    if Path(name).suffix.lower() in FILE_TYPES[:-1] and ".." not in name:
                        target = p.with_name(f"{p.stem}__{Path(name).name}")
                        target.write_bytes(z.read(name))
                        out.append(target)
        else:
            out.append(p)
    return out


def _sum(store: Store, table: str, store_id: str, files: List[str], group: str = "") -> List[Dict[str, Any]]:
    have = store.tables().get(table)
    if not files or not have:
        return []
    marks = ",".join("?" * len(files))
    cols = f"{group}, " if group else ""
    sums = ", ".join(f"SUM({c}) {c}" if c in have else f"NULL {c}"
                     for c in ("impressions", "clicks", "cost", "conversions", "conv_value"))
    sql = (f"SELECT {cols}{sums} FROM {table} "
           f"WHERE _store_id = ? AND _source_file IN ({marks})" + (f" GROUP BY {group} ORDER BY cost DESC" if group else ""))
    res = store.query(sql, [store_id, *files], limit=500)
    rows = [dict(zip(res["columns"], r)) for r in res["rows"]]
    for r in rows:
        r.update({"ctr": ratio(r.get("clicks"), r.get("impressions")), "cpc": ratio(r.get("cost"), r.get("clicks")),
                  "roas": ratio(r.get("conv_value"), r.get("cost")), "cpa": ratio(r.get("cost"), r.get("conversions"))})
    return rows


def _tracking(answer: Dict[str, Any], store: Store, store_id: str) -> Dict[str, Any]:
    actions = []
    for c in answer.get("conversion_actions") or []:
        opt = str(c.get("optimization") or c.get("action_optimization") or "").lower()
        actions.append({**c, "primary": c.get("primary", opt.startswith("primary")),
                        "status": str(c.get("status") or "").lower().replace(" ", "_")})
    facts = prepare.tracking_facts(actions)
    t = {k: v["value"] for k, v in kb.thresholds("thresholds.gads", {"store_id": store_id}, store).items()}
    found = records.findings(rules.run(rules.load_ruleset("tracking_v1"), {"facts": [facts]}, t, {})["matches"])
    return {"facts": facts, "findings": found, "actions": actions}


def review(state_final: Any, store_id: str, folder: Optional[str], since: float,
           today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    store = Store()
    answer = parse_answer(state_final) or {}
    files = new_files(folder, since)
    ingested = [{"file": p.name, **reports.ingest(store, p, store_id)} for p in files]
    by_table: Dict[str, List[str]] = {}
    for i in ingested:
        if i.get("status") == "ingested":
            by_table.setdefault(i["table"], []).append(i["file"])
    out: Dict[str, Any] = {
        "store_id": store_id, "account": answer.get("account"), "date_range": answer.get("date_range"),
        "files": ingested, "not_downloaded": answer.get("not_downloaded") or [], "notes": answer.get("notes") or [],
        "signin_required": bool(answer.get("signin_required")),
        "totals": (_sum(store, "gads_campaign_rows", store_id, by_table.get("gads_campaign_rows", [])) or [{}])[0],
        "campaigns": _sum(store, "gads_campaign_rows", store_id, by_table.get("gads_campaign_rows", []), "campaign"),
        "search_terms": _sum(store, "gads_search_term_rows", store_id,
                             by_table.get("gads_search_term_rows", []), "search_term")[:40],
        "products": _sum(store, "gads_product_rows", store_id, by_table.get("gads_product_rows", []), "item_id")[:40],
    }
    out["tracking"] = _tracking(answer, store, store_id) if answer.get("conversion_actions") else None
    be = kb.value("gads.breakeven_roas", {"store_id": store_id}, store)
    out["breakeven_roas"] = be
    out["completed"] = bool(by_table)
    store.log("audit", {"id": f"gads-review-{store_id}-{today}", "kind": "gads_review", "date": today.isoformat(),
                        "completed": out["completed"], "files": [i["file"] for i in ingested]}, store_id)
    return out


def _money(v: Any) -> str:
    return "-" if v is None else f"${v:,.2f}"


def _num(v: Any, nd: int = 0) -> str:
    return "-" if v is None else f"{v:,.{nd}f}"


def render_markdown(r: Dict[str, Any]) -> str:
    rng = r.get("date_range") or "the period"
    if not r["completed"]:
        lines = [f"# Google Ads {r['store_id']}: REVIEW DID NOT COMPLETE", "",
                 "No report file was downloaded, so this says nothing about the account's performance.", ""]
        if r.get("signin_required"):
            lines += ["**Google asked to sign in again.** Sign in to Google Ads in the store's browser, then ask again.", ""]
        if r.get("not_downloaded"):
            lines += ["Not downloaded: " + "; ".join(map(str, r["not_downloaded"])), ""]
        lines += [f"- {n}" for n in r.get("notes") or []]
        return "\n".join(lines) + "\n"
    t = r["totals"]
    lines = [f"# Google Ads {r['store_id']}, {rng}: {_money(t.get('cost'))} spent, {_num(t.get('clicks'))} clicks, "
             f"{_num(t.get('conversions'), 1)} conversions", ""]
    if r.get("account"):
        lines += [f"Account: {r['account']}", ""]
    tr = r.get("tracking")
    lines += ["## Conversion tracking", ""]
    if tr is None:
        lines += ["**CHECK DID NOT COMPLETE:** the conversion actions were not read.", ""]
    else:
        lines += [f"- **{f.get('severity')}** {f.get('detail')}. Fix: {f.get('fix')}" for f in tr["findings"]]
        if not tr["findings"]:
            lines.append("- No tracking problem found.")
        lines += ["", "| Conversion action | Status | Primary | Category |", "|---|---|---|---|"]
        lines += [f"| {a.get('name')} | {a.get('status')} | {'yes' if a['primary'] else 'no'} | {a.get('category') or ''} |"
                  for a in tr["actions"]]
        lines.append("")
    if tr and any(f.get("severity") == "fail" for f in tr["findings"]):
        lines += ["Because tracking is wrong, the conversions and ROAS below are not sales; judge spend by clicks "
                  "and Shopify orders until it is fixed.", ""]

    def table(rows, key, label):
        out = [f"| {label} | Cost | Clicks | CTR | CPC | Conv. | Conv. value | ROAS |", "|---|---|---|---|---|---|---|---|"]
        for x in rows:
            ctr = "-" if x.get("ctr") is None else f"{x['ctr']:.1%}"
            out.append(f"| {x.get(key)} | {_money(x.get('cost'))} | {_num(x.get('clicks'))} | {ctr} | "
                       f"{_money(x.get('cpc'))} | {_num(x.get('conversions'), 1)} | {_money(x.get('conv_value'))} | "
                       f"{_num(x.get('roas'), 2)} |")
        return out
    if r["campaigns"]:
        lines += ["## Campaigns", ""] + table(r["campaigns"], "campaign", "Campaign") + [""]
    if r["search_terms"]:
        wasted = [s for s in r["search_terms"] if (s.get("cost") or 0) > 0 and not s.get("conversions")]
        lines += ["## Search terms (top by cost)", ""] + table(r["search_terms"][:20], "search_term", "Search term") + [""]
        if wasted:
            lines += [f"{len(wasted)} search terms cost {_money(sum(s['cost'] for s in wasted))} with no conversion.", ""]
    if r["products"]:
        lines += ["## Products (top by cost)", ""] + table(r["products"][:20], "item_id", "Item") + [""]
    if r.get("breakeven_roas") is None:
        lines += ["## Not yet judged", "", "Keep/cut calls need the break-even ROAS, which needs product cost and "
                  "shipping per order. Tell the agent the cost and it will add it.", ""]
    if r.get("not_downloaded"):
        lines += ["## Not downloaded", ""] + [f"- {x}" for x in r["not_downloaded"]] + [""]
    if r.get("notes"):
        lines += ["## Notes", ""] + [f"- {n}" for n in r["notes"]] + [""]
    return "\n".join(lines)


def chat_summary(r: Dict[str, Any], folder: str) -> str:
    if not r["completed"]:
        why = ("Google asked to sign in again; sign in to Google Ads in the store's browser, then ask again"
               if r.get("signin_required") else "no report was downloaded")
        return f"Google Ads review DID NOT COMPLETE: {why}. Details: {folder}"
    t = r["totals"]
    lines = [f"Google Ads {r.get('date_range') or ''}: {_money(t.get('cost'))} spent, {_num(t.get('clicks'))} clicks, "
             f"{_num(t.get('conversions'), 1)} conversions."]
    tr = r.get("tracking")
    if tr is None:
        lines.append("Tracking check did not complete.")
    elif tr["findings"]:
        lines.append("Tracking problems: " + "; ".join(f.get("detail") or f["rule_id"] for f in tr["findings"]))
    wasted = [s for s in r["search_terms"] if (s.get("cost") or 0) > 0 and not s.get("conversions")]
    if wasted:
        lines.append(f"{len(wasted)} search terms spent {_money(sum(s['cost'] for s in wasted))} with no conversion.")
    lines.append(f"Full report: {folder}")
    return "\n".join(lines)


def save_review(state: Dict[str, Any], store_id: str, folder: Optional[str], since: float,
                node: str = "", day: Optional[str] = None, answer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """*answer*: what the run read (account, date range, conversion actions...) when it came
    from more than one step; else the browser step *node*'s final answer."""
    from agent.ec_skills.reports.report_store import save_and_upload
    from agent.ec_skills.reports.store_report import browser_final
    final = answer if answer is not None else browser_final(state, node)
    r = review(final, store_id, folder, since or time.time() - 3 * 3600)
    files: Dict[str, Any] = {"report.md": render_markdown(r), "report.json": r}
    if not r["completed"]:
        files["raw_result.json"] = final if isinstance(final, (dict, list)) else {"final": str(final or "")}
    out = save_and_upload(CATEGORY, store_id, files, day)
    out["review"] = r
    out["message"] = chat_summary(r, out.get("folder", ""))
    return out

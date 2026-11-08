"""Turn a review-mining browser run into a report.

The browser step reads the leading competitor listings for a niche and ends with
a JSON answer (listings, themes, improvement ideas, market). This renders
report.md next to report.json under C:\\reports\\review_mining\\<niche>\\<date>\\.
A run that found nothing is reported as "MINING DID NOT COMPLETE", never as a
niche without complaints.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agent.ec_skills.reports.report_store import report_dir, save_and_upload
from agent.ec_skills.reports.store_report import _rows, browser_final

CATEGORY = "review_mining"


def parse_mining(final: Any) -> Optional[Dict[str, Any]]:
    """The mining answer, or None when the run produced none (no listings read)."""
    report = final
    if not isinstance(report, dict):
        match = re.search(r"\{.*\}", str(final or ""), re.S)
        if not match:
            return None
        try:
            report = json.loads(match.group(0))
        except ValueError:
            return None
    if not isinstance(report, dict) or not report.get("listings"):
        return None
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    listings: List[Dict[str, Any]] = report.get("listings") or []
    themes: List[Dict[str, Any]] = report.get("themes") or []
    ideas: List[Dict[str, Any]] = report.get("improvement_ideas") or []
    market: Dict[str, Any] = report.get("market") or {}
    complaints = [t for t in themes if t.get("kind") != "praise"]
    lines = [f"# {report.get('niche') or 'Niche'}: {len(listings)} competitors, "
             f"{len(complaints)} recurring complaints, {len(ideas)} improvement ideas", "",
             f"Read on {report.get('marketplace') or 'amazon.com'} at {report.get('checked_at') or ''}: "
             f"{sum(int(x.get('reviews_read') or 0) for x in listings)} reviews read.", ""]
    if report.get("signin_required"):
        lines += ["**Amazon asked for the research account's password again, so only the reviews on the "
                  "product pages were read.** Sign in again in the amazon_research_0 browser.", ""]
    if report.get("blocked"):
        lines += ["**Amazon showed a robot check and the run stopped early;** the findings below are partial.", ""]
    if market:
        lines += ["## Market", "",
                  f"- Price: {market.get('price_low') or '?'} to {market.get('price_high') or '?'} "
                  f"(median {market.get('price_median') or '?'})",
                  f"- Competition: {market.get('competition') or '?'}"
                  + (f" ({market['competition_reason']})" if market.get("competition_reason") else ""),
                  f"- Leaders: {', '.join(market.get('leaders') or []) or 'not named'}", ""]
    lines += ["## What buyers complain about", ""]
    if complaints:
        for t in complaints:
            quotes = "; ".join(f'"{q}"' for q in (t.get("quotes") or []) if q)
            lines.append(f"- **{t.get('theme')}** ({t.get('kind') or 'complaint'}): {t.get('products') or 0} products, "
                         f"{t.get('mentions') or 0} mentions" + (f". {quotes}" if quotes else ""))
    else:
        lines.append("_No recurring complaint was found in the reviews shown._")
    praise = [t for t in themes if t.get("kind") == "praise"]
    if praise:
        lines += ["", "## What buyers like (keep it)", ""]
        lines += [f"- {t.get('theme')} ({t.get('products') or 0} products)" for t in praise]
    lines += ["", "## Improvement ideas", ""]
    lines += _rows(ideas, ["idea", "fixes_theme", "why", "effort"]) if ideas else ["_None._"]
    lines += ["", "## Competitors read", ""]
    lines += _rows([{**l, "complaints": "; ".join(l.get("top_complaints") or [])} for l in listings],
                   ["asin", "title", "price", "rating", "ratings_count", "complaints", "reviews_read"])
    if report.get("notes"):
        lines += ["", "## Notes", ""] + [f"- {n}" for n in report["notes"]]
    return "\n".join(lines) + "\n"


def render_failure(final: Any, niche: str) -> str:
    error = final.get("error") if isinstance(final, dict) else None
    return "\n".join([
        f"# {niche or 'Niche'}: MINING DID NOT COMPLETE", "",
        "The browser run read no competitor listings, so this says nothing about the niche's reviews.", "",
        f"**Result:** {error or str(final or 'the browser step returned no answer')}", "",
        "The full browser result is in raw_result.json.", "",
    ])


def save_review_mining_report(state: Dict[str, Any], niche: str = "", node: str = "",
                              date: Optional[str] = None) -> Dict[str, Any]:
    final = browser_final(state, node)
    report = parse_mining(final)
    niche = niche or (report or {}).get("niche") or "unknown_niche"
    if report is None:
        raw = final if isinstance(final, (dict, list)) else {"final": str(final or "")}
        files = {"report.md": render_failure(final, niche), "raw_result.json": raw}
    else:
        files = {"report.md": render_markdown(report), "report.json": report}
    for stale in {"report.json", "raw_result.json"} - set(files):
        (report_dir(CATEGORY, niche, date) / stale).unlink(missing_ok=True)
    out = save_and_upload(CATEGORY, niche, files, date)
    out["parsed"] = report is not None
    out["report"] = report
    return out

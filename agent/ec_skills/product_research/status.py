"""Status of the Amazon product research crawl for get_agent_status: one report for the team
(the coordinator and its crawlers). Read-only: the queue and per-phrase status tables,
_queue/BLOCKED, and the newest product records for the data-quality checks.

The checks are the ones a person ran by hand on every "check now", plus the lesson of
2026-11-08: Amazon limited the account's review access for 8 days without one captcha, and
the crawl looked healthy while every product saved the same reviews as negative and positive.
"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from agent.ec_skills.product_research import store
from agent.status.providers import StatusContext, register, since_local

TEAM = "product_research"
PRODUCTS_PER_PHRASE = 20
QUALITY_SAMPLE = 50          # newest products whose reviews are checked for negative == positive
LOW_DISK_GB = 20
RECENT_MAX = 30


def _root(inputs: dict) -> Path:
    return Path(str(inputs.get("research_root") or store.DEFAULT_ROOT))


def _hours(since: str) -> float:
    return max((datetime.now() - datetime.strptime(since, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600, 1 / 60)


def _duplicate_reviews(pdir: Path, asin: str) -> bool:
    """Negative and positive reviews share a review: the star filters were ignored."""
    try:
        rec = json.loads((pdir / "raw" / f"{asin}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    neg = {r.get("id") for r in rec.get("neg_reviews") or []} - {None, ""}
    pos = {r.get("id") for r in rec.get("pos_reviews") or []} - {None, ""}
    return bool(neg & pos)


def status(ctx: StatusContext) -> dict:
    root = _root(ctx.inputs)
    if not (root / "_queue").is_dir():
        return {"health": "unknown", "headline": f"no research folder at {root}"}
    rows = store.queue_rows(root)
    seeds = {store.slug(p) for p in store._seeds(root) if p}
    states = Counter(r["state"] for r in rows.values())
    seed_states = Counter(r["state"] for sl, r in rows.items() if sl in seeds)
    since = since_local(ctx.since) or (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    products, finished, current = [], [], []
    for sl, r in rows.items():
        if r["state"] == "done" and (r.get("updated") or "") >= since:
            finished.append({"ts": r["updated"], "kind": "finished", "what": r["phrase"], "detail": r.get("note") or ""})
        if r["state"] != "crawling" and (r.get("updated") or "") < since:
            continue
        pdir = root / sl
        if r["state"] == "crawling":
            counts = store.product_counts(pdir)
            current.append({"what": r["phrase"], "detail": f"{counts.get('done', 0)}/{r.get('products') or '?'} products"
                                                           + (f", {counts['failed']} failed" if counts.get("failed") else "")})
        for p in store.read_table(store.status_path(pdir), store.PRODUCT_COLS):
            if (p.get("updated") or "") >= since and p["state"] in ("done", "failed"):
                products.append({**p, "pdir": pdir, "phrase": r["phrase"]})

    done = [p for p in products if p["state"] == "done"]
    failed = [p for p in products if p["state"] == "failed"]
    limited = [p for p in done if "reviews limited" in p.get("note", "")]
    reused = [p for p in done if "reused from" in p.get("note", "")]
    checked = sorted((p for p in done if p not in limited), key=lambda p: p["updated"], reverse=True)[:QUALITY_SAMPLE]
    dup = [p for p in checked if _duplicate_reviews(p["pdir"], p["asin"])]
    dup_fresh = [p for p in dup if "reused from" not in p.get("note", "")]
    hours = _hours(since)
    rate = round(len(done) / hours, 1)
    total, n_done = len(rows), states.get("done", 0)
    left = total - n_done
    pct = round(100 * n_done / total, 1) if total else 0.0
    free_gb = round(shutil.disk_usage(root).free / 1e9)

    anomalies = []
    blocked = store.blocked(root)
    if blocked:
        anomalies.append({"id": "blocked", "severity": "error", "needs_human": True,
                          "what": blocked.splitlines()[0][:300],
                          "impact": "every crawler and the coordinator wait",
                          "suggested_action": "solve the sign-in / captcha in that crawler's Chrome profile, "
                                              "then delete _queue/BLOCKED"})
    if limited:
        anomalies.append({"id": "amazon-review-limit", "severity": "warn", "needs_human": True,
                          "what": "Amazon limits review access on the shopper account",
                          "evidence": f"{len(limited)} of {len(done)} products since {since} saved with reviews_limited",
                          "impact": "these products need a reviews-only re-fetch once access is back",
                          "suggested_action": "send Amazon's verify request (on a reviews page) if not sent yet, and wait for its e-mail"})
    if dup_fresh:
        anomalies.append({"id": "duplicate-reviews", "severity": "error", "needs_human": True,
                          "what": "negative and positive reviews are the same reviews",
                          "evidence": f"{len(dup_fresh)} of the {len(checked)} newest checked products",
                          "impact": "the review filters are being ignored; review data is wrong",
                          "suggested_action": "open a product's reviews page in a crawler profile and look"})
    if len(dup) > len(dup_fresh):
        anomalies.append({"id": "reused-duplicate-reviews", "severity": "info", "needs_human": False,
                          "what": "reused records carry duplicated reviews from earlier crawls",
                          "evidence": f"{len(dup) - len(dup_fresh)} of the {len(checked)} newest checked products",
                          "impact": "covered by the planned reviews-only pass"})
    if failed:
        anomalies.append({"id": "product-failures", "severity": "warn" if len(failed) >= 3 else "info",
                          "needs_human": False, "what": f"{len(failed)} products failed since {since}",
                          "evidence": "; ".join(f"{p['phrase']} #{p['rank']}: {p.get('note', '')}" for p in failed[:5])})
    if states.get("crawling") and not done and not blocked and hours >= 1:
        anomalies.append({"id": "no-progress", "severity": "warn", "needs_human": False,
                          "what": f"no product finished in the last {hours:.1f} h while a phrase is crawling"})
    if free_gb < LOW_DISK_GB:
        anomalies.append({"id": "low-disk", "severity": "warn", "needs_human": True,
                          "what": f"{free_gb} GB free on the research drive"})

    health = ("blocked" if blocked else
              "degraded" if any(a["severity"] in ("warn", "error") for a in anomalies) else "ok")
    eta = None
    if rate > 0 and left:
        eta_h = left * PRODUCTS_PER_PHRASE / rate
        eta = {"at": (datetime.now() + timedelta(hours=eta_h)).date().isoformat(),
               "basis": f"{left} phrases left at {rate:g} products/h"}
    headline = (f"{pct:g}% of the planned crawl ({n_done}/{total} phrases); "
                f"{len(done)} products since {since[5:16]} (~{rate:g}/h)"
                + ("; BLOCKED" if blocked else "; review access limited" if limited else ""))
    recent = sorted(finished, key=lambda x: x["ts"], reverse=True)
    recent += [{"ts": p["updated"], "kind": "failed", "what": f"{p['phrase']} #{p['rank']} {p['asin']}",
                "detail": p.get("note", "")} for p in failed]
    return {
        "health": health, "headline": headline,
        "progress": {"unit": "phrases", "done": n_done, "in_progress": states.get("crawling", 0), "total": total,
                     "percent": pct, "total_is_moving": bool(seed_states.get("pending") or seed_states.get("crawling")),
                     "secondary": [{"label": "seeds", "done": seed_states.get("done", 0), "total": len(seeds),
                                    "percent": round(100 * seed_states.get("done", 0) / len(seeds), 1) if seeds else 0.0}]},
        "rate": {"value": rate, "unit": "products/h", "window": "since"},
        "eta": eta, "current": current, "recent": recent[:RECENT_MAX], "anomalies": anomalies,
        "resources": {"disk_free_gb": free_gb},
        "metrics": {"products_since": len(done), "failed_since": len(failed), "reviews_limited_since": len(limited),
                    "reused_since": len(reused), "phrases_finished_since": len(finished),
                    "pending": states.get("pending", 0), "since_local": since},
        "links": [{"label": "plan", "path": str(root / "plan.md")},
                  {"label": "queue", "path": str(store.queue_status_path(root))}],
    }


register(TEAM, status, skills=("product_crawler", "product_research_manager"), team=TEAM,
         team_name="Amazon product research crawl",
         description="phrase -> top 20 organic Amazon products: details, reviews, media, uploaded to the NAS",
         roots=lambda inputs: [_root(inputs)])

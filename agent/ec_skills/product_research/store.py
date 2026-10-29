"""Files of a product research run, shared by the coordinator and the crawlers.

<root>/_queue/phrases.txt     phrases, one per line ('#' comments)
<root>/_queue/status.md       per-phrase state: pending | crawling | done | failed
<root>/_queue/BLOCKED         written when Amazon shows a sign-in / captcha / bot page; every
                              agent stops until the user deletes it
<root>/<slug>/status.md       per-product state: pending | assigned | done | failed
<root>/<slug>/raw/search.json, raw/<ASIN>.json, texts/products.json, media/<ASIN>/...
Several crawlers (threads or processes) share the status files; every change goes through lock().
"""
from __future__ import annotations

import contextlib
import csv
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path, PurePosixPath

DEFAULT_ROOT = Path("C:/product_research")
NAS_DIR = "products"            # at the NAS share root, next to chips/
MAX_ATTEMPTS = 3
STALE_ASSIGNED_S = 30 * 60      # an assigned product whose crawler went away is handed out again
PRODUCT_COLS = ["rank", "asin", "state", "worker", "attempts", "updated", "note"]
QUEUE_COLS = ["phrase", "slug", "state", "products", "attempts", "updated", "note"]


def slug(phrase: str) -> str:
    """'Garden hose  reel' -> 'garden_hose_reel'."""
    return "_".join(re.sub(r"[^\w\s-]", " ", phrase.lower()).split())


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextlib.contextmanager
def lock(path: Path, timeout: float = 60):
    """Cross-process lock: an exclusive <path>.lock file (removed when older than 2 minutes)."""
    lk = path.with_name(path.name + ".lock")
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lk, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - lk.stat().st_mtime > 120:
                    lk.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.time() > deadline:
                raise TimeoutError(f"lock busy: {lk}")
            time.sleep(0.1)
    try:
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            lk.unlink()


# ── markdown tables ────────────────────────────────────────────────────────

def read_table(path: Path, cols: list[str]) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == cols[0] or len(cells) != len(cols):
            continue
        rows.append(dict(zip(cols, cells)))
    return rows


def write_table(path: Path, cols: list[str], rows: list[dict], heading: str) -> None:
    clean = lambda v: str(v if v is not None else "").replace("|", "/").replace("\n", " ")
    lines = [f"# {heading}", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(clean(r.get(c, "")) for c in cols) + " |" for r in rows]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Windows refuses the replace while anyone has the file open (a reader outside the lock, an
    # editor, a virus scanner): those reads are short, so try again for a few seconds
    for attempt in range(50):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.1)


# ── phrase queue ───────────────────────────────────────────────────────────

def read_phrases(root: Path) -> list[str]:
    f = root / "_queue" / "phrases.txt"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        p = " ".join(line.split("#", 1)[0].split())
        if p and p.upper() != "END" and slug(p) not in {slug(x) for x in out}:
            out.append(p)
    return out


def queue_status_path(root: Path) -> Path:
    return root / "_queue" / "status.md"


def queue_rows(root: Path) -> dict[str, dict]:
    """Every queued phrase's row (pending when the coordinator hasn't touched it yet)."""
    have = {r["slug"]: r for r in read_table(queue_status_path(root), QUEUE_COLS)}
    return {slug(p): have.get(slug(p)) or {"phrase": p, "slug": slug(p), "state": "pending", "products": "",
                                           "attempts": "0", "updated": "", "note": ""}
            for p in read_phrases(root)}


def update_phrase(root: Path, sl: str, **changes) -> dict:
    path = queue_status_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock(path):
        rows = queue_rows(root)
        row = rows[sl]
        row.update({k: str(v) for k, v in changes.items()}, updated=now())
        write_table(path, QUEUE_COLS, list(rows.values()), "Product research phrases")
        return row


def queue_finished(root: Path) -> bool:
    """Every queued phrase is done or failed (an empty queue counts as finished)."""
    return all(r["state"] in ("done", "failed") for r in queue_rows(root).values())


# ── blocked flag ───────────────────────────────────────────────────────────

def blocked(root: Path) -> str | None:
    f = root / "_queue" / "BLOCKED"
    return f.read_text(encoding="utf-8").strip() or "blocked" if f.exists() else None


def set_blocked(root: Path, reason: str, who: str, url: str) -> None:
    f = root / "_queue" / "BLOCKED"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"{now()} {who}: {reason} at {url}\n"
                 "Fix it in that crawler's Chrome profile (sign in / solve it), then delete this file.\n",
                 encoding="utf-8")


# ── per-phrase product status ──────────────────────────────────────────────

def status_path(pdir: Path) -> Path:
    return pdir / "status.md"


def write_products(pdir: Path, phrase: str, organic: list[dict]) -> None:
    rows = [{"rank": i + 1, "asin": t["asin"], "state": "pending", "worker": "", "attempts": 0,
             "updated": "", "note": ""} for i, t in enumerate(organic)]
    with lock(status_path(pdir)):
        write_table(status_path(pdir), PRODUCT_COLS, rows, phrase)


def _age_s(stamp: str) -> float:
    try:
        return time.time() - datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return float("inf")


def claim(root: Path, worker: str, skip=()) -> tuple[Path, dict] | None:
    """Hand the worker the next product of the first crawling phrase: its own unfinished one
    first, then a pending one, then one whose crawler went quiet. ``skip``: ASINs that already
    failed in this pass, so a failure isn't retried at once."""
    for row in queue_rows(root).values():
        if row["state"] != "crawling":
            continue
        pdir = root / row["slug"]
        path = status_path(pdir)
        with lock(path):
            rows = read_table(path, PRODUCT_COLS)
            free = [r for r in rows if r["asin"] not in skip]
            pick = (next((r for r in free if r["state"] == "assigned" and r["worker"] == worker), None)
                    or next((r for r in free if r["state"] == "pending"), None)
                    or next((r for r in free if r["state"] == "assigned"
                             and _age_s(r["updated"]) > STALE_ASSIGNED_S), None))
            if pick:
                pick.update(state="assigned", worker=worker, updated=now())
                write_table(path, PRODUCT_COLS, rows, row["phrase"])
                return pdir, dict(pick)
    return None


def finish(pdir: Path, asin: str, outcome: str, note: str = "") -> dict:
    """outcome: done | failed (retried until MAX_ATTEMPTS) | released (back to pending, no attempt)."""
    path = status_path(pdir)
    with lock(path):
        rows = read_table(path, PRODUCT_COLS)
        heading = path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
        r = next(x for x in rows if x["asin"] == asin)
        if outcome == "done":
            r.update(state="done", note=note)
        elif outcome == "failed":
            attempts = int(r["attempts"] or 0) + 1
            r.update(state="failed" if attempts >= MAX_ATTEMPTS else "pending", attempts=attempts, note=note[:200])
        else:
            r.update(state="pending", note=note[:200])
        r["updated"] = now()
        write_table(path, PRODUCT_COLS, rows, heading)
        return dict(r)


def product_counts(pdir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in read_table(status_path(pdir), PRODUCT_COLS):
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return counts


# ── merge + NAS ────────────────────────────────────────────────────────────

def merge(pdir: Path) -> dict:
    """texts/products.json from raw/search.json and every finished product's raw/<ASIN>.json."""
    search = json.loads((pdir / "raw" / "search.json").read_text(encoding="utf-8"))
    products = []
    for r in sorted(read_table(status_path(pdir), PRODUCT_COLS), key=lambda r: int(r["rank"])):
        f = pdir / "raw" / f"{r['asin']}.json"
        if r["state"] == "done" and f.exists():
            products.append(json.loads(f.read_text(encoding="utf-8")) | {"rank": int(r["rank"])})
        elif r["state"] == "failed":
            products.append({"rank": int(r["rank"]), "asin": r["asin"],
                             "url": f"https://www.amazon.com/dp/{r['asin']}", "error": r["note"]})
    out = {"phrase": search["phrase"], "slug": pdir.name, "marketplace": "amazon.com",
           "searched_at": search.get("searched_at", ""), "products": products}
    (pdir / "texts").mkdir(exist_ok=True)
    (pdir / "texts" / "products.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def rank_comparison(root: Path) -> Path:
    """<root>/_ranks/rank_comparison.{json,csv}: where every product found by any searched phrase
    ranks for each phrase (organic position among all organic results loaded, ads seen), products
    found by the most phrases first. Built from each phrase's raw/search.json. Returns the folder."""
    phrases, products = [], {}
    for row in queue_rows(root).values():
        f = root / row["slug"] / "raw" / "search.json"
        if not f.exists():
            continue
        search = json.loads(f.read_text(encoding="utf-8"))
        organic: list[str] = []
        for t in search.get("tiles", []):
            asin = t.get("asin")
            if not asin:
                continue
            p = products.setdefault(asin, {"asin": asin, "title": t.get("title", ""), "ranks": {}})
            r = p["ranks"].setdefault(row["phrase"], {"organic": None, "ad": False})
            if t["sponsored"]:
                r["ad"] = True
            elif asin not in organic:
                organic.append(asin)
                r["organic"] = len(organic)
        phrases.append({"phrase": row["phrase"], "searched_at": search.get("searched_at", ""),
                        "organic_results": len(organic)})
    names = [p["phrase"] for p in phrases]
    for p in products.values():
        ranked = [r["organic"] for r in p["ranks"].values() if r["organic"]]
        p["phrases_ranked"], p["best_rank"] = len(ranked), min(ranked, default=None)
    rows = sorted(products.values(), key=lambda p: (-p["phrases_ranked"], p["best_rank"] or 10 ** 6, p["asin"]))
    out = root / "_ranks"
    out.mkdir(parents=True, exist_ok=True)
    (out / "rank_comparison.json").write_text(json.dumps(
        {"updated": now(), "note": "organic = position among the organic results of the pages loaded "
                                   "(~49 on page 1); null = not among them; ad = shown as a sponsored result",
         "phrases": phrases, "products": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    cell = lambda r: "" if not r else "+".join(x for x in (str(r["organic"] or ""), "ad" if r["ad"] else "") if x)
    with open(out / "rank_comparison.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["asin", "title", "phrases_ranked", "best_rank"] + names)
        for p in rows:
            w.writerow([p["asin"], p["title"], p["phrases_ranked"], p["best_rank"] or ""]
                       + [cell(p["ranks"].get(n)) for n in names])
    return out


def mirror_to_nas(pdir: Path, dirs=("texts", "media"), refresh: bool = False) -> dict:
    """Upload ``dirs`` of pdir to products/<pdir name>/ (files already there with the same size are
    skipped unless ``refresh``: files rewritten in place), then list the NAS again and report
    anything missing."""
    from agent.ec_skills.nas import ugreen_nas

    files = sorted(p for d in dirs if (pdir / d).exists() for p in (pdir / d).rglob("*") if p.is_file())
    listings: dict[str, dict] = {}

    def listing(folder: str) -> dict:
        if folder not in listings:
            try:
                listings[folder] = {e["name"]: e["size"] for e in ugreen_nas.nas_list(folder, relative_to_base=False)}
            except Exception:
                listings[folder] = {}   # folder not there yet
        return listings[folder]

    uploaded = 0
    for f in files:
        remote = f"{NAS_DIR}/{pdir.name}/{f.relative_to(pdir).as_posix()}"
        folder = str(PurePosixPath(remote).parent)
        if refresh or listing(folder).get(f.name) != f.stat().st_size:
            ugreen_nas.nas_upload(str(f), remote, relative_to_base=False)
            uploaded += 1
    listings.clear()    # verify against fresh listings
    missing = [f.relative_to(pdir).as_posix() for f in files
               if listing(str(PurePosixPath(f"{NAS_DIR}/{pdir.name}/{f.relative_to(pdir).as_posix()}").parent))
               .get(f.name) != f.stat().st_size]
    return {"files": len(files), "uploaded": uploaded, "missing": missing}

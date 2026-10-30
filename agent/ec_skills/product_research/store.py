"""Files of a product research run, shared by the coordinator and the crawlers.

<root>/_queue/phrases.txt     phrases, one per line ('#' comments)
<root>/_queue/status.md       per-phrase state: pending | crawling | done | failed
<root>/_queue/BLOCKED         written when Amazon shows a sign-in / captcha / bot page; every
                              agent stops until the user deletes it
<root>/_queue/tree.md         subcategories found under the phrases: queued (crawled like a phrase,
                              after phrases.txt, biggest demand first) | rank-only | over budget
<root>/<slug>/status.md       per-product state: pending | assigned | done | failed
<root>/<slug>/related.md      the phrase's related phrases and subcategory probes (rank-only
                              searches, kind related | sub): pending | done | failed
<root>/<slug>/raw/search.json, raw/related/<slug>.json, raw/<ASIN>.json, media/<ASIN>/...,
              texts/products.json, texts/rank_comparison.{json,csv}
Several crawlers (threads or processes) share the status files; every change goes through lock().
"""
from __future__ import annotations

import contextlib
import csv
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path, PurePosixPath

DEFAULT_ROOT = Path("C:/product_research")
NAS_DIR = "products"            # at the NAS share root, next to chips/
MAX_ATTEMPTS = 3
STALE_ASSIGNED_S = 30 * 60      # an assigned product whose crawler went away is handed out again
PRODUCT_COLS = ["rank", "asin", "state", "worker", "attempts", "updated", "note"]
QUEUE_COLS = ["phrase", "slug", "state", "products", "attempts", "updated", "note", "bytes"]
RELATED_COLS = ["phrase", "slug", "state", "organic", "attempts", "updated", "note", "kind"]
TREE_COLS = ["phrase", "slug", "level", "parent", "state", "new_share", "demand", "updated", "note"]
RELATED_N = 10                  # related phrases per seed, searched rank-only
SUB_N = 5                       # subcategories probed per phrase (rank-only search first)
MAX_LEVEL = 2                   # phrases.txt seeds are level 1; their subcategories level 2, which don't expand
PROMOTE_SHARE = 0.6             # a probed subcategory is crawled when more than this share of its top 20 is new
BUDGET_BYTES = 6 * 10 ** 12     # texts + media uploaded to the NAS; no new phrase is started beyond it
MIN_FREE_BYTES = 25 * 10 ** 9   # local disk kept free (local media is removed once it's on the NAS)
SEARCH_GAP_S = 90               # at least this long between two searches
REUSE_DAYS = 7                  # a product crawled for another phrase this recently is copied


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
        if cells[0] == cols[0] or len(cells) > len(cols):
            continue
        rows.append(dict(zip(cols, cells + [""] * (len(cols) - len(cells)))))   # columns added later
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
    """phrases.txt in order, then the queued subcategories, biggest demand first."""
    f = root / "_queue" / "phrases.txt"
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    subs = sorted((r for r in read_table(tree_path(root), TREE_COLS) if r["state"] == "queued"),
                  key=lambda r: -int(r["demand"] or 0))
    out, seen = [], set()
    for p in [" ".join(line.split("#", 1)[0].split()) for line in lines] + [r["phrase"] for r in subs]:
        if p and p.upper() != "END" and slug(p) not in seen:
            seen.add(slug(p))
            out.append(p)
    return out


def tree_path(root: Path) -> Path:
    return root / "_queue" / "tree.md"


def tree_rows(root: Path) -> dict[str, dict]:
    return {r["slug"]: r for r in read_table(tree_path(root), TREE_COLS)}


def phrase_level(root: Path, sl: str) -> int:
    """phrases.txt seeds are level 1; a subcategory one more than its parent."""
    r = tree_rows(root).get(sl)
    return int(r["level"]) if r else 1


def add_tree_node(root: Path, phrase: str, parent: str, **fields) -> dict:
    """Record (or update) a subcategory found under ``parent``."""
    path = tree_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock(path):
        rows = read_table(path, TREE_COLS)
        r = next((x for x in rows if x["slug"] == slug(phrase)), None)
        if r is None:
            r = {"phrase": phrase, "slug": slug(phrase), "parent": parent}
            rows.append(r)
        r.update({k: str(v) for k, v in fields.items()}, updated=now())
        write_table(path, TREE_COLS, rows, "Subcategory tree")
        return dict(r)


def bytes_used(root: Path) -> int:
    """Texts + media of the finished phrases (what they took on the NAS)."""
    return sum(int(r.get("bytes") or 0) for r in read_table(queue_status_path(root), QUEUE_COLS))


def dir_bytes(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.exists() else 0


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


# ── related phrases (rank-only searches of a seed) ─────────────────────────

def _words(phrase: str) -> tuple[str, ...]:
    """Word set for spotting near-duplicates: word order and plural s don't matter."""
    return tuple(sorted({w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
                         for w in slug(phrase).split("_")}))


def pick_related(seed: str, suggestions: list[str], related: list[str], n: int = RELATED_N,
                 exclude: list[str] = ()) -> list[str]:
    """The seed's top ``n`` related phrases: ones both the search box suggests and the results page
    links first, then the suggestions (popularity order), then the related searches. Drops the seed,
    ``exclude`` (e.g. its subcategories), near-duplicates and broader phrases (only the seed's own
    words, e.g. 'garden hose')."""
    seed_words = set(_words(seed))
    both = [p for p in suggestions if _words(p) in {_words(r) for r in related}]
    out, seen = [], {_words(seed)} | {_words(p) for p in exclude}
    for p in both + suggestions + related:
        w = _words(p)
        if not p.strip() or w in seen or set(w) < seed_words:
            continue
        seen.add(w)
        out.append(" ".join(p.lower().split()))
    return out[:n]


def pick_subcategories(seed: str, ideas: list[str], n: int = SUB_N) -> list[str]:
    """Up to ``n`` of the results page's 'Popular Shopping Ideas' (Amazon's own narrower searches
    for the seed, e.g. 'retractable garden hose reel'), near-duplicates dropped."""
    return pick_related(seed, ideas, [], n)


def related_path(pdir: Path) -> Path:
    return pdir / "related.md"


def write_related(pdir: Path, phrases: list[str], kind: str = "related") -> None:
    """Add rank-only searches to the phrase's list (kind: related | sub)."""
    path = related_path(pdir)
    with lock(path):
        rows = read_table(path, RELATED_COLS)
        have = {r["slug"] for r in rows}
        rows += [{"phrase": p, "slug": slug(p), "state": "pending", "organic": "", "attempts": 0, "updated": "",
                  "note": "", "kind": kind} for p in phrases if slug(p) not in have]
        write_table(path, RELATED_COLS, rows, f"Related phrases and subcategory probes of {pdir.name} (rank only)")


def next_related(pdir: Path) -> dict | None:
    return next((r for r in read_table(related_path(pdir), RELATED_COLS) if r["state"] == "pending"), None)


def finish_related(pdir: Path, sl: str, outcome: str, **changes) -> None:
    """outcome: done | failed (retried until MAX_ATTEMPTS)."""
    path = related_path(pdir)
    with lock(path):
        rows = read_table(path, RELATED_COLS)
        r = next(x for x in rows if x["slug"] == sl)
        if outcome == "failed":
            attempts = int(r["attempts"] or 0) + 1
            outcome = "failed" if attempts >= MAX_ATTEMPTS else "pending"
            changes["attempts"] = attempts
        r.update({k: str(v)[:200] for k, v in changes.items()}, state=outcome, updated=now())
        write_table(path, RELATED_COLS, rows, path.read_text(encoding="utf-8").splitlines()[0].lstrip("# "))


def search_due(root: Path) -> bool:
    """Searches are spaced out: Amazon's bot check watches how often one shopper searches."""
    f = root / "_queue" / "last_search"
    return not f.exists() or time.time() - f.stat().st_mtime >= SEARCH_GAP_S


def mark_searched(root: Path) -> None:
    f = root / "_queue" / "last_search"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(now(), encoding="utf-8")


# ── reuse + videos ─────────────────────────────────────────────────────────

def reuse_product(root: Path, pdir: Path, asin: str, max_age_days: float = REUSE_DAYS) -> dict | None:
    """The product's record from another phrase crawled within ``max_age_days``, copied with its
    media into pdir (instead of crawling it again), or None."""
    best = None
    for f in root.glob(f"*/raw/{asin}.json"):
        if f.parent.parent == pdir:
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        try:
            age = (datetime.now() - datetime.fromisoformat(rec.get("crawled_at", ""))).total_seconds()
        except ValueError:
            continue
        if age <= max_age_days * 86400 and (best is None or rec["crawled_at"] > best[1]["crawled_at"]):
            best = (f.parent.parent, rec)
    if not best:
        return None
    src, rec = best
    if (src / "media" / asin).exists():
        shutil.copytree(src / "media" / asin, pdir / "media" / asin, dirs_exist_ok=True)
    else:       # only on the NAS now (local media is removed after the upload)
        from agent.ec_skills.nas import ugreen_nas
        try:
            for rel in rec["media"]["images"] + rec["media"]["videos"]:
                data = ugreen_nas.nas_read_bytes(f"{NAS_DIR}/{src.name}/{rel}", relative_to_base=False)
                (pdir / rel).parent.mkdir(parents=True, exist_ok=True)
                (pdir / rel).write_bytes(data)
        except Exception:
            return None     # crawl it instead
    return rec | {"reused_from": rec.get("reused_from") or src.name}


def crawled_asins(root: Path) -> set[str]:
    """Every product saved for any phrase (raw/ holds search.json and one <ASIN>.json per product)."""
    return {f.stem for f in root.glob("*/raw/*.json") if f.stem != "search"}


def video_topups(pdir: Path, top: int, n: int) -> list[str]:
    """ASINs among the ``top`` most reviewed crawled products that have fewer than ``n`` of their
    videos saved."""
    recs = []
    for r in read_table(status_path(pdir), PRODUCT_COLS):
        f = pdir / "raw" / f"{r['asin']}.json"
        if r["state"] == "done" and f.exists():
            recs.append(json.loads(f.read_text(encoding="utf-8")))
    recs.sort(key=lambda x: -(x.get("reviews") or 0))
    return [x["asin"] for x in recs[:top]
            if len(x["media"]["videos"]) < min(n, len(x["media"]["video_info"]))]


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


def rank_comparison(pdir: Path) -> Path:
    """texts/rank_comparison.{json,csv}: where every product found by the seed phrase or one of its
    related phrases ranks for each of them (organic position among all organic results loaded, ads
    seen), products found by the most phrases first. Built from raw/search.json and
    raw/related/<slug>.json. Returns the json file."""
    files = [pdir / "raw" / "search.json"] + [pdir / "raw" / "related" / f"{r['slug']}.json"
                                              for r in read_table(related_path(pdir), RELATED_COLS)]
    phrases, products = [], {}
    for f in files:
        if not f.exists():
            continue
        search = json.loads(f.read_text(encoding="utf-8"))
        phrase = search["phrase"]
        organic: list[str] = []
        for t in search.get("tiles", []):
            asin = t.get("asin")
            if not asin:
                continue
            p = products.setdefault(asin, {"asin": asin, "title": t.get("title", ""), "ranks": {}})
            r = p["ranks"].setdefault(phrase, {"organic": None, "ad": False})
            if t["sponsored"]:
                r["ad"] = True
            elif asin not in organic:
                organic.append(asin)
                r["organic"] = len(organic)
        phrases.append({"phrase": phrase, "searched_at": search.get("searched_at", ""),
                        "organic_results": len(organic)})
    names = [p["phrase"] for p in phrases]
    for p in products.values():
        ranked = [r["organic"] for r in p["ranks"].values() if r["organic"]]
        p["phrases_ranked"], p["best_rank"] = len(ranked), min(ranked, default=None)
    rows = sorted(products.values(), key=lambda p: (-p["phrases_ranked"], p["best_rank"] or 10 ** 6, p["asin"]))
    out = pdir / "texts"
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
    return out / "rank_comparison.json"


def mirror_to_nas(pdir: Path, dirs=("texts", "media"), refresh: bool = False, on_file=None) -> dict:
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
        if on_file:
            on_file()
    listings.clear()    # verify against fresh listings
    missing = [f.relative_to(pdir).as_posix() for f in files
               if listing(str(PurePosixPath(f"{NAS_DIR}/{pdir.name}/{f.relative_to(pdir).as_posix()}").parent))
               .get(f.name) != f.stat().st_size]
    return {"files": len(files), "uploaded": uploaded, "missing": missing}

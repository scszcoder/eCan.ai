"""Product research coordinator and crawlers: one pass per call of their skill's code node.

Coordinator (skill product_research_manager_00): takes the queued phrases in order; searches a
pending one (top organic products -> <slug>/status.md), waits while the crawlers work, then merges
texts/products.json, mirrors texts/ and media/ to the NAS, verifies and marks the phrase done.
Crawlers (skill product_crawler_00, task var ``worker``): claim products of the crawling phrase
one at a time, each in its own Chrome profile <root>/_profiles/amazon_<worker>.

CLI (the same passes, for trials):
  python -m agent.ec_skills.product_research.nodes status
  python -m agent.ec_skills.product_research.nodes coordinate [--once] [--no-nas]
  python -m agent.ec_skills.product_research.nodes crawl --worker crawler1 [--limit 3]
  python -m agent.ec_skills.product_research.nodes merge "garden hose reel" [--nas]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from agent.ec_skills.product_research import amazon, store
from agent.ec_skills.product_research.store import DEFAULT_ROOT
from agent.ec_tasks.progress import note_task_progress

IDLE_S = 30        # a pass with nothing to do sleeps this long, so the skill loop doesn't spin
STEP = 3           # products per crawler pass: the agent can be stopped between passes
HEARTBEAT_S = 60   # progress report interval while a pass runs


def profile_dir(root: Path, name: str) -> Path:
    return root / "_profiles" / name


async def worker_pass(root: Path, worker: str, profile: Path, limit: int = STEP) -> dict:
    """Crawl up to ``limit`` products. Returns {done, failed, blocked, idle}."""
    out = {"done": 0, "failed": 0, "blocked": store.blocked(root), "idle": False}
    failed: set[str] = set()
    if out["blocked"]:
        return out
    job = held = store.claim(root, worker)    # held: claimed and not finished yet
    if not job:
        out["idle"] = True
        return out
    try:
        async with amazon.browser(profile) as page:
            n = 0
            while job:
                pdir, row = job
                asin = row["asin"]
                try:
                    rec = await amazon.crawl_product(page, asin, pdir)
                    (pdir / "raw").mkdir(exist_ok=True)
                    (pdir / "raw" / f"{asin}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                                                               encoding="utf-8")
                    store.finish(pdir, asin, "done",
                                 f"{len(rec['neg_reviews'])} neg, {len(rec['pos_reviews'])} pos, "
                                 f"{len(rec['media']['images'])} img, {len(rec['media']['videos'])} vid")
                    out["done"] += 1
                except amazon.Blocked as e:
                    store.finish(pdir, asin, "released", f"blocked: {e}")
                    held = None
                    store.set_blocked(root, str(e), worker, page.url)
                    out["blocked"] = str(e)
                    return out
                except Exception as e:
                    store.finish(pdir, asin, "failed", f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}")
                    out["failed"] += 1
                    failed.add(asin)
                held = None
                n += 1
                if n >= limit or store.blocked(root):
                    break
                job = held = store.claim(root, worker, failed)
                if job:
                    await amazon.pause(20, 40)
    except Exception as e:
        # e.g. Chrome didn't start (the profile is open elsewhere): give the product back
        if held:
            store.finish(held[0], held[1]["asin"], "released", f"{type(e).__name__}: {e}")
        raise
    return out


async def coordinator_pass(root: Path, profile: Path, nas: bool = True) -> dict:
    """One step of the phrase queue. Returns {finished, blocked, waiting, msg}."""
    out = {"finished": False, "blocked": store.blocked(root), "waiting": False, "msg": ""}
    if out["blocked"]:
        out["msg"] = f"blocked: {out['blocked']}"
        return out
    for row in store.queue_rows(root).values():
        phrase, sl, pdir = row["phrase"], row["slug"], root / row["slug"]
        if row["state"] in ("done", "failed"):
            continue
        if row["state"] == "pending":
            try:
                async with amazon.browser(profile) as page:
                    res = await amazon.search(page, phrase)
            except amazon.Blocked as e:
                store.set_blocked(root, str(e), "coordinator", "search")
                out.update(blocked=str(e), msg=f"blocked searching '{phrase}': {e}")
                return out
            except Exception as e:
                attempts = int(row["attempts"] or 0) + 1
                store.update_phrase(root, sl, attempts=attempts, note=f"search: {type(e).__name__}: {e}"[:200],
                                    state="failed" if attempts >= store.MAX_ATTEMPTS else "pending")
                out["msg"] = f"search of '{phrase}' failed: {e}"
                return out
            if not res["organic"]:
                store.update_phrase(root, sl, state="failed", note="no organic results")
                out["msg"] = f"'{phrase}': no organic results"
                return out
            (pdir / "raw").mkdir(parents=True, exist_ok=True)
            (pdir / "raw" / "search.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            store.write_products(pdir, phrase, res["organic"])
            store.update_phrase(root, sl, state="crawling", products=len(res["organic"]), note="")
            out["msg"] = f"'{phrase}': {len(res['organic'])} products to crawl"
            return out
        counts = store.product_counts(pdir)
        if counts.get("pending", 0) + counts.get("assigned", 0):
            out.update(waiting=True, msg=f"'{phrase}' crawling: {counts}")
            return out
        merged = store.merge(pdir)
        total, ok = len(merged["products"]), sum(1 for p in merged["products"] if "error" not in p)
        note = f"{ok}/{total} products"
        if nas:
            try:
                m = await asyncio.to_thread(store.mirror_to_nas, pdir)
            except Exception as e:
                store.update_phrase(root, sl, note=f"NAS: {e}"[:200])
                out.update(waiting=True, msg=f"'{phrase}': NAS upload failed, retrying: {e}")
                return out
            if m["missing"]:
                store.update_phrase(root, sl, note=f"NAS missing {len(m['missing'])}: {m['missing'][:3]}")
                out.update(waiting=True, msg=f"'{phrase}': {len(m['missing'])} files missing on the NAS, retrying")
                return out
            note += f", NAS {m['files']} files"
        store.update_phrase(root, sl, state="done", products=f"{ok}/{total}", note=note)
        out["msg"] = f"'{phrase}' done: {note}"
        return out
    out.update(finished=True, msg="every queued phrase is done")
    return out


async def _with_heartbeat(coro):
    # the app's runner cancels a task that shows no progress for 5 minutes; a crawler pass
    # (several products) takes longer, so tell it every minute that this one is busy
    async def beat():
        while True:
            note_task_progress()
            await asyncio.sleep(HEARTBEAT_S)
    hb = asyncio.create_task(beat())
    try:
        return await coro
    finally:
        hb.cancel()


def _run(coro):
    # main.py sets WindowsSelectorEventLoopPolicy, whose loops can't start Chrome
    loop_factory = asyncio.ProactorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        return runner.run(_with_heartbeat(coro))


def _refs(state: dict) -> tuple[dict, Path]:
    refs = state.get("prompt_refs") or {}
    return refs, Path(str(refs.get("research_root") or DEFAULT_ROOT))


def _result(state: dict, all_done: bool, work_done: bool, summary: str) -> dict:
    state.setdefault("result", {})["llm_result"] = {"all_done": all_done, "work_done": work_done, "summary": summary}
    return state


def coordinator_main(state: dict) -> dict:
    """Code node of skill product_research_manager_00."""
    refs, root = _refs(state)
    r = _run(coordinator_pass(root, profile_dir(root, str(refs.get("profile") or "amazon_coordinator"))))
    if r["waiting"]:
        time.sleep(IDLE_S)
    return _result(state, r["finished"] or bool(r["blocked"]), not r["waiting"], r["msg"])


def worker_main(state: dict) -> dict:
    """Code node of skill product_crawler_00 (task var ``worker``, e.g. crawler1)."""
    refs, root = _refs(state)
    worker = str(refs.get("worker") or "crawler1")
    r = _run(worker_pass(root, worker, profile_dir(root, str(refs.get("profile") or f"amazon_{worker}"))))
    attrs = state.setdefault("attributes", {})
    attrs["products_done"] = int(attrs.get("products_done") or 0) + r["done"]
    attrs["products_failed"] = int(attrs.get("products_failed") or 0) + r["failed"]
    finished = r["idle"] and store.queue_finished(root)
    if r["idle"] and not finished:
        time.sleep(IDLE_S)
    summary = (f"{worker}: {attrs['products_done']} products saved, {attrs['products_failed']} failed this run"
               + (f"; BLOCKED: {r['blocked']}" if r["blocked"] else "") + ("; queue finished" if finished else ""))
    return _result(state, finished or bool(r["blocked"]), bool(r["done"] or r["failed"]), summary)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("coordinate")
    c.add_argument("--once", action="store_true")
    c.add_argument("--no-nas", action="store_true")
    w = sub.add_parser("crawl")
    w.add_argument("--worker", default="crawler1")
    w.add_argument("--limit", type=int, default=0, help="stop after this many products (0 = until idle)")
    m = sub.add_parser("merge")
    m.add_argument("phrase")
    m.add_argument("--nas", action="store_true")
    a = ap.parse_args()
    # the NAS upload roots (ECAN_NAS_UPLOAD_ROOTS) live in run.env, which only main.py loads
    from dotenv import load_dotenv
    from utils.run_env import run_env_path
    load_dotenv(run_env_path(), override=False)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = a.root
    if a.cmd == "status":
        print(f"blocked: {store.blocked(root)}")
        for r in store.queue_rows(root).values():
            print(f"{r['phrase']:<30} {r['state']:<9} {r['products']:<8} {r['note']}  "
                  f"{store.product_counts(root / r['slug']) if r['state'] == 'crawling' else ''}")
    elif a.cmd == "coordinate":
        while True:
            r = asyncio.run(coordinator_pass(root, profile_dir(root, "amazon_coordinator"), not a.no_nas))
            print(r["msg"], flush=True)
            if a.once or r["finished"] or r["blocked"]:
                break
            if r["waiting"]:
                time.sleep(IDLE_S)
    elif a.cmd == "crawl":
        total = 0
        while not a.limit or total < a.limit:
            step = min(STEP, a.limit - total) if a.limit else STEP
            r = asyncio.run(worker_pass(root, a.worker, profile_dir(root, f"amazon_{a.worker}"), step))
            total += r["done"] + r["failed"]
            print(f"{a.worker}: +{r['done']} done, +{r['failed']} failed"
                  + (f", BLOCKED {r['blocked']}" if r["blocked"] else "") + (", idle" if r["idle"] else ""), flush=True)
            if r["blocked"] or r["idle"]:
                break
    elif a.cmd == "merge":
        pdir = root / store.slug(a.phrase)
        out = store.merge(pdir)
        print(f"{len(out['products'])} products -> {pdir / 'texts' / 'products.json'}")
        if a.nas:
            print(store.mirror_to_nas(pdir))


if __name__ == "__main__":
    main()

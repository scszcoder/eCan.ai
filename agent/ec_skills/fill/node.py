"""The fill step of a listing skill, and the dry run the explorer tests repairs with.

``run_fill_node(state, seed)`` is what the skill's code node calls: it installs
the skill's flow (*seed*) in the platform's experience folder, runs the current
version against the store's browser and writes the outcome into the state the
way the rest of the skill expects (``attributes.fill_ok``, the publish node's
answer, ``attributes.fill_note`` for the agent that takes over on a failure).
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import os
import threading
import time
from typing import Any, Dict, List, Tuple

from utils.logger_helper import logger_helper as logger

from .check import compare
from .engine import run_flow
from .store import FillStore

FILL_TIMEOUT_S = 900


def product_files(listing: dict, file_map: Dict[str, str]) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    """(role -> file names, file name -> local path) for the listing's own files:
    names are those of the local copies (listing names map to them by *file_map*)."""
    roles: Dict[str, List[str]] = {}
    paths: Dict[str, str] = {}
    for role, v in (listing.get("files") or {}).items():
        names = list(v.values()) if isinstance(v, dict) else (v if isinstance(v, list) else [v])
        for name in names:
            p = file_map.get(str(name))
            if not p:
                continue
            base = os.path.basename(p)
            roles.setdefault(role, []).append(base)
            paths[base] = p
    return roles, paths


def experience_folder(attrs: dict) -> str:
    return os.path.dirname((attrs.get("listing_experience_files") or {}).get("platform") or "")


async def _open_and_run(port: int, flow: dict, guards: dict, listing: dict, roles: dict, paths: dict,
                        mode: str, cache: dict) -> Dict[str, Any]:
    from agent.ec_skills.explorer.page import PageSession
    page = await PageSession.open(port, flow.get("start_url") or "about:blank")
    try:
        out = await run_flow(page, flow, guards, listing, roles, paths, mode, cache)
        if mode == "dry_run":
            out["check"] = compare(listing, out.get("report") or {}) if out.get("ok") else {"ok": False}
        return out
    finally:
        try:
            await page.close()
        except Exception:
            pass


def _port(store_id: str, seed: dict, profile_id: str = "") -> int:
    """The store browser's debug port. A run that names its browser profile runs in
    it, as the browser nodes do: started when it is not running (an update closes it)."""
    if profile_id:
        from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_browser import launch_profile
        try:
            return int(launch_profile(profile_id).debug_port or 0)
        except Exception as exc:
            logger.warning(f"[listing-fill] could not start browser profile {profile_id!r}: {exc}")
            return 0
    from agent.ec_skills.explorer.page import browser_port, store_profiles
    port = browser_port(store_id)
    if port or store_profiles(store_id):
        # a store with its own browser profile is filled only there: the skill's fixed
        # port can be another Chrome, logged into who knows what (KEN 11-03: 9228)
        return port
    return int(seed.get("cdp_port") or 0)


def _profile_id(state: dict) -> str:
    """The task's browser profile, where the browser nodes read it (session.py)."""
    attrs = state.get("attributes") or {}
    return str(state.get("browser_profile_id") or attrs.get("browser_profile_id")
               or (attrs.get("params") or {}).get("browser_profile_id") or "").strip()


def _run_sync(coro_fn, timeout: float) -> Dict[str, Any]:
    ctx = contextvars.copy_context()
    box: Dict[str, Any] = {}

    def run():
        try:
            box["out"] = ctx.run(lambda: asyncio.run(coro_fn()))
        except Exception as exc:
            box["out"] = {"ok": False, "stage": "error", "error": f"{type(exc).__name__}: {exc}"}
    th = threading.Thread(target=run, name="listing-fill", daemon=True)
    th.start()
    th.join(timeout)
    return box.get("out") or {"ok": False, "stage": "timeout", "error": f"the fill did not finish in {int(timeout)} s"}


REPAIRS_PER_DAY = int(os.environ.get("ECAN_FILL_REPAIRS_PER_DAY", "3"))
# not the page's fault: no repair (a person logs in / starts the browser)
NOT_THE_PAGE = ("没有登录", "login", "browser is not running", "缺资料")


def _record_failure(store: FillStore, version: int, out: Dict[str, Any]) -> None:
    """Where the latest real fill stopped and what the page looked like (the repair starts from it)."""
    store._save("last_failure.json", {"at": time.time(), "version": version, "step": out.get("step"),
                                      "stage": out.get("stage"), "error": out.get("error"), "diag": out.get("diag"),
                                      "log": (out.get("log") or [])[-15:]})


def _may_repair(store: FillStore, out: Dict[str, Any]) -> str:
    """"" when a repair may start now, else why not."""
    err = f"{out.get('stage')} {out.get('error')}"
    if any(w in err for w in NOT_THE_PAGE):
        return "not a page problem: " + err[:160]
    meta = store.meta()
    today = [t for t in meta.get("repairs") or [] if time.time() - t < 86400]
    if len(today) >= REPAIRS_PER_DAY:
        return f"{len(today)} repairs in 24 h (cap {REPAIRS_PER_DAY})"
    meta["repairs"] = today + [time.time()]
    store._save("meta.json", meta)
    return ""


def _repair(store: FillStore, store_id: str, listing: dict, file_map: Dict[str, str], seed: dict, model: str,
            profile_id: str = "") -> int:
    """The explorer repairs the flow against the live page; the new version, or 0."""
    from agent.ec_skills.explorer import explore_sync
    from .explore import finish, repair_prompt
    note = json.dumps({k: listing.get(k) for k in ("title", "category", "attributes", "skus") if k in listing},
                      ensure_ascii=False)[:3000]
    flow = store.current()[0]
    res = explore_sync(repair_prompt(store, note), store_id=store_id, profile_id=profile_id, start_url=flow.get("start_url") or "about:blank",
                       domains=list(seed.get("domains") or []), model=model, max_turns=int(seed.get("repair_turns") or 120),
                       files={os.path.basename(p): p for p in file_map.values()},
                       fill={"store_id": store_id, "experience": store.experience,
                             "listing": listing, "file_map": file_map})
    n, why = finish(store.experience, res.get("final") or "") if res.get("final") else (0, "")
    logger.info(f"[listing-fill] repair: {res.get('turns')} turns, {res.get('calls')} calls"
                + (f"; new flow v{n}" if n else f"; no new flow ({why or res.get('error') or 'no verdict'})"))
    return n


def run_fill_node(state: dict, seed: dict, notes: str = "", explore_model: str = "") -> dict:
    """Fill and submit the listing with the platform's current flow (see module doc).
    With *explore_model*, a failure the page caused starts a repair (capped per day);
    a repaired flow that passed its dry run fills the listing again."""
    attrs = state.setdefault("attributes", {})
    pr = state.setdefault("prompt_refs", {})
    attrs["fill_note"] = ""
    folder = attrs.get("listing_dir") or ""
    try:
        listing = json.load(open(os.path.join(folder, "listing.json"), encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"[listing-fill] no listing.json: {exc}")
        return state
    file_map = dict(attrs.get("listing_file_map") or {}) or {
        os.path.basename(p): p for p in (pr.get("upload_files") or []) if isinstance(p, str)}
    roles, paths = product_files(listing, file_map)
    exp = experience_folder(attrs)
    store = FillStore(exp) if exp else None
    if store:
        store.seed(seed, notes)
        flow, guards, version = store.current()
    else:
        flow, guards, version = {k: v for k, v in seed.items() if k != "guards"}, dict(seed.get("guards") or {}), 0
    store_id = str(pr.get("store_id") or "")
    profile_id = _profile_id(state)

    def fill_once(flow, guards):
        port = _port(store_id, seed, profile_id)
        if not port:
            return {"ok": False, "stage": "browser", "error": "the store's browser is not running"}
        cache = store.uploads() if store else {}
        res = _run_sync(lambda: _open_and_run(port, flow, guards, listing, roles, paths, "publish", cache), FILL_TIMEOUT_S)
        if store:
            store.save_uploads(cache)
        return res
    out = fill_once(flow, guards)
    if not out.get("ok") and store and explore_model:
        _record_failure(store, version, out)
        why = _may_repair(store, out)
        if why:
            logger.info(f"[listing-fill] no repair: {why}")
        else:
            try:
                n = _repair(store, store_id, listing, file_map, seed, explore_model, profile_id)
            except Exception as exc:
                n = 0
                logger.warning(f"[listing-fill] repair failed: {type(exc).__name__}: {exc}")
            if n:
                flow, guards, version = store.current()
                out = fill_once(flow, guards)
                out["repaired"] = True
    out["version"] = version
    attrs["fill_result"], attrs["fill_version"] = out, version
    logger.info(f"[listing-fill] flow v{version}: {json.dumps(out, ensure_ascii=False, default=str)[:1500]}")
    v = out.get("vars") or {}
    a = v.get("attributes") if isinstance(v.get("attributes"), dict) else {}
    notes_out = list(a.get("skipped") or []) + [f"平台建议：{s}" for s in a.get("suggested") or []] \
        + list(a.get("page_guesses") or []) + list(v.get("notes") or [])
    pid = str(v.get("product_id") or "")
    attrs["fill_ok"] = bool(out.get("ok") and pid)
    if attrs["fill_ok"]:
        answer = {"product_id": pid, "status": "已提交", "reject_reason": "", "draft_id": "", "failed_section": "",
                  "filled_defaults": a.get("suggested") or [], "problems": list(v.get("problems") or []),
                  "data_notes": notes_out}
        state.setdefault("tool_result", {})["browser_publish"] = {
            "final": json.dumps(answer, ensure_ascii=False), "done": True, "trace": []}
        attrs["fill_note"] = "【这一步已由脚本完成，商品已提交】商品ID：" + pid + "。直接用 done 返回：" + json.dumps(answer, ensure_ascii=False)
    else:
        if store:
            _record_failure(store, version, out)
        attrs["fill_note"] = ("（脚本填表没有完成：" + str(out.get("stage")) + " " + str(out.get("error") or "")[:200]
                              + "；按下面的步骤自己发布。）")
    return state


def dry_run(store_id: str, experience: str, listing: dict, file_map: Dict[str, str],
            flow: dict = None) -> Dict[str, Any]:
    """Run *flow* (default: the explorer's working copy) up to the submit, read the
    form back and compare it with *listing*. Submit and autosave are blocked."""
    store = FillStore(experience)
    seed = store._load("seed.json", {})
    flow = flow if flow is not None else store.working()
    guards = store.guards()
    roles, paths = product_files(listing, file_map)
    port = _port(store_id, seed)
    if not port:
        return {"ok": False, "stage": "browser", "error": "the store's browser is not running"}
    cache = store.uploads()
    out = _run_sync(lambda: _open_and_run(port, flow, guards, listing, roles, paths, "dry_run", cache), FILL_TIMEOUT_S)
    store.save_uploads(cache)
    store.note_dry_run(flow, out)
    return out

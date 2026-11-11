"""Explore-and-learn for read-only site skills (reports, tables), after the 抖店 listing skill.

A site pack (``sites/<site>.json``) names the site's parts (a date range to set, reports to
download, tables to read), how each part is checked, the buttons never to press, and the
model roles. Each run:

1. ``prepare``: the experience folder (recipes, notes, failure counts) for the site, and
   whether a whole-site exploration is due (a new folder: no recipes yet).
2. ``explore_task`` + ``run_explore``: the DevTools explorer (agent/ec_skills/explorer)
   works out each part on the real page, read-only, and answers with recipes:
   ``{"part", "url", "steps": [{"click": text} | {"wait": s} | {"press": key} | {"js": expr}],
   "extract_js"}``. ``save_recipes`` keeps them as candidates.
3. ``replay``: the recipes run as a script, in order, guarded like the explorer.
4. A browser-use agent does the parts the script did not (``todo_input``).
5. ``check``: each part is judged from its result (a downloaded file parses as the
   expected report, the period matches, a table has its fields), not from what an agent
   said. ``grade`` scores the recipes and counts failures; a part that failed twice is
   explored after the run (``explore_after``).
6. ``learn``: the agent's step trail becomes site notes for the next run; verified lines
   are never lost to a failed run.

Nothing here knows about a particular site; the pack is data.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import os
import re
import threading
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

SITES = Path(__file__).parent / "sites"
VERIFIED = "[verified]"
NOTES_MAX = 7000
DOWNLOAD_WAIT_S = 25


def load_site(site: str) -> Dict[str, Any]:
    return json.loads((SITES / f"{site}.json").read_text(encoding="utf-8"))


def experience_dir(site: str) -> Path:
    from agent.ec_skills.ecom.store import home
    return home() / "experience" / site


def period_days(period: str) -> int:
    m = re.search(r"(\d+)\s*days?", period or "", re.I)
    return int(m.group(1)) if m else 30


def _fmt(text: str, period: str) -> str:
    return str(text or "").replace("{period}", period).replace("{period_days}", str(period_days(period)))


def _xs(site: str):
    from agent.ec_skills.experience import ExperienceStore
    return ExperienceStore(str(experience_dir(site)))


def live_recipes(site: str) -> Dict[str, dict]:
    """part -> its best live recipe (verified first, then the newest candidate)."""
    live = [r for r in _xs(site).recipes() if r.get("status") in ("verified", "candidate")]
    live.sort(key=lambda r: (r.get("status") != "verified", -float(r.get("added_at") or 0)))
    out: Dict[str, dict] = {}
    for r in live:
        out.setdefault(r["part"], r)
    return out


def notes(site: str) -> str:
    p = experience_dir(site) / "notes.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


# ── 1. prepare ─────────────────────────────────────────────────────────

def prepare(site: str, period: str) -> Dict[str, Any]:
    pack = load_site(site)
    xs = _xs(site)
    if not (experience_dir(site) / "recipes.json").exists() and "whole_form_pass" not in xs.settings():
        xs.set_setting("whole_form_pass", True)          # a new site: explore it whole before the first run
    sig = _signature(pack)
    whole = xs.whole_form_due(sig)
    return {"site": site, "period": period, "experience_dir": str(experience_dir(site)),
            "explore_first": bool(whole), "explore_parts": [p["part"] for p in pack["parts"]] if whole else [],
            "recipes": sorted(live_recipes(site))}


def _signature(pack: Dict[str, Any]) -> str:
    import hashlib
    blob = json.dumps([pack.get("models", {}).get("explore"), pack.get("version"), EXPLORE_RULES], sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


# ── 2. explore ─────────────────────────────────────────────────────────

EXPLORE_RULES = """Rules (code enforces them too):
- Read-only. Never press a button that changes the account ({never}). Close popups with X / Close / Not now / Cancel.
- Stay on {domains}. Never type into a sign-in, password or payment field; if the site asks you to sign in, stop and say so.
- Scripts (run_js) only read the page: no fetch / XMLHttpRequest, no clicks on forbidden buttons.
- A recipe must not depend on element positions or ids that change: click by visible text, wait for what you need to appear.
"""

EXPLORE_ANSWER = """Answer with `done` and only this JSON:
{{"flow": "the order that worked, one step per line",
  "parts": [{{"part": "<part name as given>", "url": "the address to open first (full URL as you saw it)",
             "steps": [{{"click": "visible text", "nth": 0}}, {{"wait": 3}}, {{"press": "Escape"}}, {{"js": "read-only expression"}}],
             "extract_js": "for a table part: an expression returning an array of row objects with the fields asked for (DOM only)",
             "when": "anything the replay must know (order, what must be visible first)",
             "test": "how you verified it (the downloaded file name, the rows read)",
             "findings": "facts learned, dead ends, what is still unclear"}}],
  "tool_issues": []}}
Give a recipe for a part only after you replayed its steps yourself and saw it work: the file in downloads(), or the rows from extract_js. Write {{period}} in a step where the period text goes. A part you could not do: steps [] and precise findings."""


def explore_task(site: str, period: str, parts: List[str], failures: Optional[Dict[str, List[str]]] = None,
                 trail: str = "") -> str:
    pack = load_site(site)
    xs = _xs(site)
    by = {p["part"]: p for p in pack["parts"]}
    lines = []
    for name in parts:
        p = by.get(name) or {"goal": name, "check": ""}
        extra = f" Fields: {', '.join(p['fields'])}." if p.get("fields") else ""
        bad = "; ".join((failures or {}).get(name) or [])
        lines.append(f"- {name}: {_fmt(p.get('goal'), period)}.{extra} It counts as done when {_fmt(p.get('check'), period)}."
                     + (f" Last run: {bad}." if bad else ""))
    found = "\n\n".join(f"[{n}]\n{xs.findings(n)}" for n in parts if xs.findings(n))
    return f"""Task: work out, on the real {pack['title']} pages in this signed-in browser, a reliable way to do each part below, and test it. A small model will later replay your recipes as a script, so solve every difficulty for it. Period: {period}.

Parts:
{chr(10).join(lines)}

Site notes from earlier runs:
{notes(site) or '(none yet)'}

Earlier explorations' findings:
{found or '(first exploration)'}

What the last run did (find where it went wrong):
{trail or '(no record)'}

Use snapshot/screenshot to see the page, click by visible text, network to see the page's own requests, downloads() to confirm a file arrived. Do the parts in the order given; the date range stays set for the later pages.

{EXPLORE_RULES.format(never='; '.join(pack.get('never') or []), domains=', '.join(pack['domains']))}
{EXPLORE_ANSWER}
(You may answer in English. Each turn you get the turn count; with fewer than 10 turns left, deliver what you have.)"""


def run_explore(site: str, task: str, profile_id: str, downloads: str, max_turns: int = 80) -> Dict[str, Any]:
    pack = load_site(site)
    try:
        from agent.ec_skills.explorer import explore_sync
    except ImportError:
        return {"final": "", "turns": 0, "calls": 0, "error": "this build has no devtools explorer"}
    return explore_sync(task, profile_id=profile_id, start_url=pack["start_url"], domains=pack["domains"],
                        model=(pack.get("models") or {}).get("explore") or "claude-opus-5-5", max_turns=max_turns,
                        forbidden=pack.get("forbidden") or "", downloads=downloads)


def parse_recipes(final: Any, parts: List[str]) -> Dict[str, Any]:
    """The explorer's recipes (only parts asked for, with steps or extract_js), notes per part."""
    text = final if isinstance(final, str) else json.dumps(final or {}, ensure_ascii=False)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        r = json.loads(m.group(0), strict=False) if m else {}
    except ValueError:
        return {"recipes": [], "findings": {}, "flow": ""}
    recipes, findings = [], {}
    for item in r.get("parts") or []:
        if not isinstance(item, dict) or item.get("part") not in parts:
            continue
        steps = [s for s in (item.get("steps") or []) if isinstance(s, dict)
                 and set(s) & {"click", "wait", "press", "js"}]
        if steps or item.get("extract_js"):
            recipes.append({"part": item["part"], "url": str(item.get("url") or "")[:600], "steps": steps[:30],
                            "extract_js": str(item.get("extract_js") or "")[:6000], "when": str(item.get("when") or "")[:300],
                            "test": str(item.get("test") or "")[:400]})
        text = "; ".join(str(item.get(k)) for k in ("findings", "when", "test") if item.get(k))
        if text:
            findings[item["part"]] = text[:2000]
    return {"recipes": recipes, "findings": findings, "flow": str(r.get("flow") or "")[:2000]}


def save_recipes(site: str, out: Dict[str, Any], parts: List[str]) -> Dict[str, Any]:
    """Keep what an exploration found; an explorer that never got a model answer gives its try back."""
    from agent.ec_skills.experience import WHOLE_FORM
    xs = _xs(site)
    final = out.get("final") or ""
    got = parse_recipes(final, parts)
    for r in got["recipes"]:
        xs.add_recipe(r)
    for name, text in got["findings"].items():
        xs.add_findings(name, text)
    if got["flow"]:
        xs.add_findings("flow", got["flow"])
    whole = set(parts) == {p["part"] for p in load_site(site)["parts"]}
    if not final:
        for name in ([WHOLE_FORM] if whole else parts):
            xs.unmark_explored(name)
    elif whole:
        xs.set_setting("whole_form_pass", False)
    logger.info(f"[site-explore] {site}: {len(got['recipes'])} recipes {[r['part'] for r in got['recipes']]}, "
                f"turns {out.get('turns')}, error {out.get('error') or '-'}")
    return {"recipes": [r["part"] for r in got["recipes"]], "error": out.get("error") or "", "turns": out.get("turns")}


# ── 3. replay ──────────────────────────────────────────────────────────

def _run(coro_fn: Callable[[], Any]) -> Any:
    ctx = contextvars.copy_context()
    box: Dict[str, Any] = {}

    def in_loop():
        # Own loop, not asyncio.run: see explorer.loop.explore_sync (nest_asyncio in the app).
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro_fn())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    def go():
        try:
            box["out"] = ctx.run(in_loop)
        except Exception as exc:
            box["out"] = {"error": f"{type(exc).__name__}: {exc}"}
    th = threading.Thread(target=go, name="site-replay", daemon=True)
    th.start()
    th.join()
    return box["out"]


def new_files(folder: str, since: float) -> List[Path]:
    if not folder or not os.path.isdir(folder):
        return []
    return sorted((p for p in Path(folder).iterdir() if p.is_file() and p.suffix != ".crdownload"
                   and p.stat().st_mtime >= since - 2), key=lambda p: p.stat().st_mtime)


def _with_query(url: str, account_url: str, keep: List[str]) -> str:
    """*url* with the account's own query values (which account, which user) from *account_url*."""
    if not url:
        return url
    acc = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(account_url).query))
    u = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(u.query))
    q.update({k: acc[k] for k in keep if k in acc})
    return urllib.parse.urlunsplit((u.scheme or "https", u.netloc, u.path, urllib.parse.urlencode(q), u.fragment))


async def _replay(pack: Dict[str, Any], recipes: Dict[str, dict], port: int, downloads: str, period: str,
                  page_cls=None) -> Dict[str, Any]:
    from agent.ec_skills.explorer import tools as T
    if page_cls is None:
        from agent.ec_skills.explorer.page import PageSession as page_cls
    ctx = {"domains": pack["domains"], "forbidden": re.compile(pack.get("forbidden") or r"(?!x)x", re.I)}
    out: Dict[str, Any] = {}
    page = await page_cls.open(port, pack["start_url"])
    try:
        if downloads:
            await page.allow_downloads(downloads)
        await asyncio.sleep(4)
        account_url = await page.url()
        out["_account_url"] = account_url
        out["_account"] = str(await page.evaluate("document.title") or "")
        for p in pack["parts"]:
            r = recipes.get(p["part"])
            if not r:
                continue
            res: Dict[str, Any] = {"recipe": r.get("status"), "since": time.time()}
            try:
                url = _with_query(r.get("url") or "", account_url, pack.get("keep_query") or [])
                if url:
                    if urllib.parse.urlsplit(url).hostname not in pack["domains"]:
                        raise RuntimeError(f"recipe url off the site: {url[:120]}")
                    await page.navigate(url)
                    await asyncio.sleep(4)
                for s in r.get("steps") or []:
                    if "wait" in s:
                        await asyncio.sleep(min(15.0, float(s["wait"] or 2)))
                    elif "press" in s:
                        await page.press(str(s["press"]))
                    elif "click" in s:
                        text = _fmt(s["click"], period)
                        found = None
                        for _ in range(8):                      # the page may still be drawing it
                            found = await page.evaluate(T.CLICK_JS % (json.dumps(text), json.dumps(""), int(s.get("nth") or 0)))
                            if isinstance(found, dict) and "x" in found:
                                break
                            await asyncio.sleep(1.5)
                        if not isinstance(found, dict) or "x" not in found:
                            raise RuntimeError(f"no {text!r} to click: {json.dumps(found)[:200]}")
                        if T.forbidden(str(found.get("label") or text), ctx):
                            raise RuntimeError(f"refused: {found.get('label')!r} is a button that changes the account")
                        await page.mouse_click(found["x"], found["y"])
                        await asyncio.sleep(1.0)
                    elif "js" in s:
                        code = _fmt(s["js"], period)
                        if T.script_writes(code) or (re.search(r"\.click\(|\.submit\(|dispatchEvent\(", code) and T.forbidden(code, ctx)):
                            raise RuntimeError("refused: the step's script may change something")
                        await page.evaluate(code)
                if p["kind"] == "download":
                    for _ in range(DOWNLOAD_WAIT_S):
                        if new_files(downloads, res["since"]):
                            break
                        await asyncio.sleep(1)
                    res["files"] = [f.name for f in new_files(downloads, res["since"])]
                if r.get("extract_js"):
                    code = _fmt(r["extract_js"], period)
                    if T.script_writes(code):
                        raise RuntimeError("refused: the extract script sends requests")
                    rows = await page.evaluate(code, 40)
                    res["rows"] = rows if isinstance(rows, list) else []
                    if not isinstance(rows, list):
                        res["error"] = str(rows)[:300]
            except Exception as exc:
                res["error"] = f"{type(exc).__name__}: {exc}"[:400]
            out[p["part"]] = res
    finally:
        await page.close()
    return out


async def _landing(port: int, url: str, page_cls=None) -> str:
    if page_cls is None:
        from agent.ec_skills.explorer.page import PageSession as page_cls
    page = await page_cls.open(port, url)
    try:
        await asyncio.sleep(4)
        return str(await page.url() or "")
    finally:
        await page.close()


def signin_needed(site: str, profile_id: str, page_cls=None) -> Dict[str, Any]:
    """Open the site's start page in the profile's browser: did it land on a sign-in page?
    A sign-in is the person's; nothing (explorer, script, agent) works on that page."""
    from agent.ec_skills.explorer.page import browser_port
    pack = load_site(site)
    port = browser_port("", profile_id)
    if not port:
        return {"needed": False, "error": f"the browser for profile {profile_id} is not running"}
    url = _run(lambda: _landing(port, pack["start_url"], page_cls))
    if not isinstance(url, str):
        return {"needed": False, "error": str((url or {}).get("error"))[:300]}
    host = urllib.parse.urlsplit(url).hostname or ""
    return {"needed": host in (pack.get("signin_hosts") or []), "host": host}


def replay(site: str, profile_id: str, downloads: str, period: str) -> Dict[str, Any]:
    """Run the site's live recipes as a script in the profile's browser."""
    from agent.ec_skills.explorer.page import browser_port
    pack, recipes = load_site(site), live_recipes(site)
    if not recipes:
        return {"_skipped": "no recipes yet"}
    port = browser_port("", profile_id)
    if not port:
        return {"_error": f"the browser for profile {profile_id} is not running"}
    out = _run(lambda: _replay(pack, recipes, port, downloads, period))
    logger.info(f"[site-replay] {site}: " + json.dumps({k: (v.get("error") or "ok") if isinstance(v, dict) else v
                                                        for k, v in out.items() if not k.startswith("_account")})[:600])
    return out


# ── 4. what is left for the browser agent ──────────────────────────────

def todo(site: str, period: str, downloads: str, since: float, replayed: Dict[str, Any]) -> List[str]:
    """Parts the replay did not get right (judged like ``check``)."""
    res = check(site, period, downloads, since, replayed, {})
    return [p for p, (ok, _) in res.items() if not ok]


def todo_input(site: str, store_id: str, site_url: str, period: str, parts: List[str]) -> str:
    pack = load_site(site)
    by = {p["part"]: p for p in pack["parts"]}
    lines = [f"- {n}: {_fmt(by[n]['goal'], period)}" for n in parts if n in by]
    return (f"Store: {store_id}\nSite: {site_url or 'unknown'}\nPeriod: {period}\n"
            f"Parts to do (only these; the others are done):\n" + "\n".join(lines)
            + f"\n\nNotes from earlier runs on {pack['title']} (follow the [verified] ones):\n" + (notes(site) or "(none yet)"))


# ── 5. check, grade, explore after ─────────────────────────────────────

def _file_part(pack: Dict[str, Any], path: Path) -> Optional[str]:
    from agent.ec_skills.ecom import reports
    try:
        rtype = reports.detect(path).get("report_type")
    except Exception:
        return None
    return next((p["part"] for p in pack["parts"] if p.get("report_type") and p["report_type"] == rtype), None)


def check(site: str, period: str, downloads: str, since: float, replayed: Dict[str, Any],
          answer: Dict[str, Any]) -> Dict[str, tuple]:
    """part -> (ok, note), from the files that arrived and the rows read; ``answer`` is the
    browser agent's (its conversion rows count, its word that a file downloaded does not)."""
    from agent.ec_skills.ecom import reports
    pack = load_site(site)
    files = new_files(downloads, since)
    by_part: Dict[str, List[Path]] = {}
    for f in files:
        part = _file_part(pack, f)
        if part:
            by_part.setdefault(part, []).append(f)
    out: Dict[str, tuple] = {}
    days = period_days(period)
    for p in pack["parts"]:
        name, kind = p["part"], p["kind"]
        if kind == "download":
            got = by_part.get(name) or []
            if got:
                out[name] = (True, got[-1].name)
            else:
                said = next((x for x in answer.get("not_downloaded") or [] if str(x).startswith(name)), "")
                err = (replayed.get(name) or {}).get("error") or said or "no file arrived"
                out[name] = (False, str(err)[:300])
        elif kind == "extract":
            rows = (replayed.get(name) or {}).get("rows") or answer.get(name) or []
            want = [f for f in (p.get("fields") or [])[:4] if f in ("name", "status", "optimization")] or ["name"]
            good = [r for r in rows if isinstance(r, dict) and all(r.get(f) for f in want)]
            out[name] = (bool(good) and len(good) == len(rows),
                         f"{len(good)}/{len(rows)} rows with {', '.join(want)}"
                         + (f"; {(replayed.get(name) or {}).get('error')}" if (replayed.get(name) or {}).get("error") else ""))
        elif kind == "period":
            spans = []
            for f in files:
                rng = reports.detect(f).get("date_range")
                if rng:
                    spans.append((date.fromisoformat(rng[1]) - date.fromisoformat(rng[0])).days + 1)
            if spans:
                ok = all(abs(s - days) <= 1 for s in spans)
                out[name] = (ok, f"reports cover {sorted(set(spans))} days, asked {days}")
            elif files:
                out[name] = (False, "the downloaded reports show no date range")
    return out


def grade(site: str, results: Dict[str, tuple], replayed: Dict[str, Any]) -> Optional[str]:
    """Score this run; returns a part to explore now (failed twice in a row), if any.
    A recipe is scored by what *it* produced: a part the agent rescued still counts
    against the recipe that failed it."""
    xs = _xs(site)
    used = {k for k, v in replayed.items() if isinstance(v, dict) and v.get("recipe")}
    scores = {}
    for part, (ok, note) in results.items():
        scores[part] = ok and not (part in used and (replayed[part].get("error") or (
            "files" in replayed[part] and not replayed[part]["files"])))
    xs.grade(scores, {p: [n] for p, (ok, n) in results.items() if not scores.get(p)})
    target = xs.explore_target(scores, signature=_signature(load_site(site)))
    logger.info(f"[site-check] {site}: {scores}; explore next: {target or '-'}")
    return target


# ── 6. learn ───────────────────────────────────────────────────────────

def _default_ask(model: str) -> Callable[[str], str]:
    def ask(prompt: str) -> str:
        from langchain_core.messages import HumanMessage
        from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
        reply = create_ecanai_chat_llm(model, temperature=0.0).invoke([HumanMessage(content=prompt)]).content
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
    return ask


def merge_notes(old: str, new: str, run_ok: bool) -> str:
    """A successful run may rewrite the notes but every [verified] line it dropped comes
    back; a failed run only adds lines. Capped at ``NOTES_MAX``, newest unverified first to go."""
    before = [l for l in (old or "").splitlines()]
    if run_ok or not before:
        out = (new or "").splitlines()
        kept = {l.strip() for l in out}
        lost = [l for l in before if VERIFIED in l and l.strip() not in kept]
        if lost:
            out += ["", "## Kept verified entries"] + lost
    else:
        have = {l.strip() for l in before if l.strip()}
        add = [l for l in (new or "").splitlines() if l.strip() and l.strip() not in have and not l.lstrip().startswith("#")
               and VERIFIED not in l]
        out = before + (["", "## Added by a run that did not finish (unverified)"] + add[:25] if add else [])
    while len("\n".join(out)) > NOTES_MAX:
        cut = next((k for k in range(len(out) - 1, -1, -1) if VERIFIED not in out[k] and not out[k].lstrip().startswith("#")), None)
        if cut is None:
            break
        out.pop(cut)
    return "\n".join(out).strip() + "\n"


def learn(site: str, trail: str, results: Dict[str, tuple], ask: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
    """Turn the browser agent's steps into site notes for the next run."""
    if not trail.strip():
        return {"skipped": "no agent steps this run"}
    pack = load_site(site)
    passed = [p for p, (ok, _) in results.items() if ok]
    failed = [f"{p} ({n})" for p, (ok, n) in results.items() if not ok]
    old = notes(site)
    prompt = (f"You keep the working notes of a read-only {pack['title']} skill. A browser agent just did some parts of the job; "
              "below are its steps and which parts the check passed. Update the notes so the next run is faster and makes fewer "
              "mistakes, and return only the notes (markdown, no code fences).\n"
              "Rules: one line per entry, each a direct instruction (where, what to click, in what order, what to wait for); "
              "turn detours into the direct way; put what failed under 'Don't'. Sections: 'How', 'Don't'. "
              f"Mark an entry {VERIFIED} only when it is about a part that passed this run ({', '.join(passed) or 'none'}); "
              f"keep old {VERIFIED} entries unless these steps prove them wrong. Never write account numbers, amounts, names "
              "or anything about one account; never write any step that changes the account. At most 2500 characters.\n\n"
              f"Parts that failed: {', '.join(failed) or 'none'}\n\nOld notes:\n{old or '(none)'}\n\nSteps:\n{trail[-30000:]}")
    try:
        new = (ask or _default_ask((pack.get("models") or {}).get("learn") or "gpt-6.1-terra"))(prompt)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    new = re.sub(r"^```\w*\n|```$", "", (new or "").strip())
    if not new.strip():
        return {"error": "empty reply"}
    folder = experience_dir(site)
    folder.mkdir(parents=True, exist_ok=True)
    if old:
        bak = folder / ".bak"
        bak.mkdir(exist_ok=True)
        (bak / f"{time.strftime('%Y%m%d_%H%M%S')}_notes.md").write_text(old, encoding="utf-8")
    (folder / "notes.md").write_text(merge_notes(old, new, not failed), encoding="utf-8")
    return {"notes_chars": len(notes(site)), "run_ok": not failed}


def trail_of(state: Dict[str, Any], node: str) -> str:
    from agent.ec_skills.experience import trail_text
    tr = ((state.get("tool_result") or {}).get(node) or {}).get("trace") or []
    return trail_text(tr) if tr else ""

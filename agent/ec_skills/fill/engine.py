"""Runs a fill flow: a platform's publish form filled by a list of steps (data),
each step a small page script or one guarded browser action.

The flow is data so the explorer can repair it when a platform changes (user
2026-11-03: "fix the explorer"), and this engine is the only code that runs it:
steps evaluate page scripts, click, type, press keys, put the product's own files
into file inputs and read the page's own answers to those uploads -- nothing
else. What the explorer may never change is the flow's ``guards``, always taken
from the seed (store.FillStore): the requests failed before they leave the
browser (the platform's draft autosave always, the real submit in a dry run)
and the button texts refused outside the submit step.

A step::

    {"id": "title", "stage": "标题", "op": "js", "js": "set_title"}

``js`` (and ``target``, ``items``, ``text``, ``if``, ``until``, ``input``) name a
snippet in ``flow["snippets"]`` or are a script themselves, run as
``(async (A) => { ... })(args)`` with ``A = {listing, files, vars, item, index,
mode}``; a script starting with a statement keyword must ``return``, anything
else is an expression. A step fails when its script returns null/false, an
object with ``error``, or throws.

ops: js, wait, click, type, press, sleep, upload, foreach, submit.
Common keys: if (skip when falsy), frame (address part: run in that frame),
save (keep the result in A.vars), error (what to say when it fails), optional
(a failure goes into A.vars.problems and the run goes on).
"""
from __future__ import annotations

import asyncio
import fnmatch
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

OPS = ("js", "wait", "click", "type", "press", "sleep", "upload", "foreach", "submit")
GIST = 300
_STATEMENT = re.compile(r"^\s*(return|const|let|var|if|for|while|try|switch|throw)\b")
DIAG_JS = ("({url: location.href.slice(0, 200), dialogs: [...document.querySelectorAll('.next-dialog,[role=dialog]')]"
           ".filter(e => e.getBoundingClientRect().width > 0).map(e => (e.innerText || '').trim().slice(0, 200)),"
           " tail: document.body.innerText.slice(-400)})")


class StepFailed(Exception):
    def __init__(self, step: dict, message: str):
        super().__init__(message)
        self.step, self.message = step, message


def _body(js: str) -> str:
    js = str(js or "").strip().rstrip(";")
    return js if _STATEMENT.match(js) else "return (" + js + "\n);"


def _gist(x: Any) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return s if len(s) <= GIST else s[:GIST] + "…"


def _failed(out: Any) -> Optional[str]:
    """Why a script's answer means the step failed, or None."""
    if out is None or out is False:
        return "the script returned " + json.dumps(out)
    if isinstance(out, str) and out.startswith("page error"):
        return out[:600]
    if isinstance(out, dict) and out.get("error"):
        return str(out["error"])[:600]
    return None


def _why(s: dict, detail: Any) -> str:
    return (str(s.get("error") or "") + (" -- " if s.get("error") else "") + str(detail or ""))[:900]


async def block_requests(page: Any, patterns: List[str], blocked: List[str]) -> None:
    """Fail the requests matching *patterns* before they leave *page*'s browser tab
    (CDP Fetch); each one failed is noted in *blocked*. An entry is a URL pattern,
    optionally after a method ("POST *://host/sell/v2/publish.htm*"): the page's own
    address can then load while a form posted back to it is failed."""
    client = getattr(page, "client", None)
    if not patterns or client is None:
        return
    rules = []
    for p in patterns:
        method, _, url = str(p).strip().partition(" ")
        rules.append((method.upper(), url.strip()) if url.strip() else ("", method))

    def on_paused(event, *_):
        req = (event or {}).get("request") or {}
        url, method = str(req.get("url") or ""), str(req.get("method") or "GET").upper()
        if any((not m or m == method) and fnmatch.fnmatchcase(url, u) for m, u in rules):
            blocked.append(f"{method} {url[:200]}")
            cmd, params = "Fetch.failRequest", {"requestId": event["requestId"], "errorReason": "BlockedByClient"}
        else:
            cmd, params = "Fetch.continueRequest", {"requestId": event["requestId"]}
        asyncio.get_running_loop().create_task(page.send(cmd, params))
    client.register.Fetch.requestPaused(on_paused)
    await page.send("Fetch.enable", {"patterns": [{"urlPattern": u} for _, u in rules]})


class FlowRun:
    """One run of *flow* on *page*. ``mode``: "publish" (the real submit) or "dry_run"
    (everything up to the submit, which is replaced by the flow's report)."""

    def __init__(self, page: Any, flow: dict, guards: dict, listing: dict, files: Dict[str, List[str]],
                 paths: Dict[str, str], mode: str = "publish", upload_cache: Optional[dict] = None):
        self.page, self.flow, self.guards = page, flow, guards or {}
        self.listing, self.files, self.paths = listing, files, paths
        self.mode = mode
        self.cache = upload_cache if upload_cache is not None else {}
        self.vars: Dict[str, Any] = {}
        self.log: List[dict] = []
        self.stage = ""
        self.blocked: List[str] = []
        self.forbid = re.compile(self.guards.get("forbid_click") or r"$^")

    # ── scripts ────────────────────────────────────────────────────────
    def _script(self, ref: Any) -> str:
        ref = str(ref or "null")
        return str((self.flow.get("snippets") or {}).get(ref, ref))

    def _args(self, item: Any = None, index: int = 0) -> str:
        return json.dumps({"listing": self.listing, "files": self.files, "vars": self.vars, "item": item,
                           "index": index, "mode": self.mode}, ensure_ascii=False, default=str)

    def _wrap(self, js: Any, item: Any, index: int, tail: str = "") -> str:
        """``(async (A) => {...})(args)``; with *tail*, the script's value is ``e`` and
        *tail* runs after it (element steps)."""
        if not tail:
            return "(async (A) => { " + _body(self._script(js)) + " })(" + self._args(item, index) + ")"
        return ("(async (A) => { const e = await (async () => { " + _body(self._script(js)) + " })(); "
                + tail + " })(" + self._args(item, index) + ")")

    # A script's value comes back as plain data: an element (or anything that cannot be
    # copied out of the page) becomes a short description, so conditions can return elements.
    _PLAIN = ("if (e === undefined) return null; if (e && e.nodeType) return {element: (e.tagName || '').toLowerCase(),"
              " label: ((e.innerText || e.value || '') + '').trim().slice(0, 60)};"
              " try { return JSON.parse(JSON.stringify(e)); } catch (x) { return String(e); }")

    async def eval(self, js: Any, item: Any = None, index: int = 0, frame: str = "", timeout: float = 60) -> Any:
        expr = self._wrap(js, item, index, self._PLAIN)
        return await (self._frame_eval(frame, expr) if frame else self.page.evaluate(expr, timeout))

    async def _frame_id(self, part: str) -> Optional[str]:
        tree = (await self.page.send("Page.getFrameTree")).get("frameTree") or {}
        found: List[str] = []

        def walk(n):
            if part in str((n.get("frame") or {}).get("url") or ""):
                found.append(n["frame"]["id"])
            for c in n.get("childFrames") or []:
                walk(c)
        walk(tree)
        return found[-1] if found else None

    async def _frame_eval(self, part: str, expr: str, by_value: bool = True) -> Any:
        fid = await self._frame_id(part)
        if not fid:
            return {"error": f"no frame whose address has {part!r}"}
        ctx = (await self.page.send("Page.createIsolatedWorld", {"frameId": fid, "worldName": "ecan-fill"}))["executionContextId"]
        res = await self.page.send("Runtime.evaluate", {"expression": expr, "contextId": ctx, "returnByValue": by_value,
                                                        "awaitPromise": True}, 60)
        if res.get("exceptionDetails"):
            ex = res["exceptionDetails"]
            return "page error: " + str((ex.get("exception") or {}).get("description") or ex.get("text"))[:600]
        r = res.get("result") or {}
        return r.get("value") if by_value else r.get("objectId")

    async def _object(self, js: Any, item: Any, index: int, frame: str) -> Optional[str]:
        """A remote handle on the element the script returns (a file input)."""
        expr = self._wrap(js, item, index)
        if frame:
            oid = await self._frame_eval(frame, expr, by_value=False)
            return oid if isinstance(oid, str) and not oid.startswith("page error") else None
        res = await self.page.send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": False})
        r = res.get("result") or {}
        return r.get("objectId") if r.get("subtype") == "node" else None

    _LABEL = "((e.closest('button,a,[role=button]') || e).innerText || e.value || '').trim().slice(0, 60)"

    async def _element_xy(self, js: Any, item: Any, index: int) -> Any:
        """Centre of the element the script returns (scrolled into view), or why not."""
        tail = ("if (!e || !e.getBoundingClientRect) return {error: 'no such element'};"
                " e.scrollIntoView({block: 'center'}); await new Promise(r => setTimeout(r, 250));"
                " const r = e.getBoundingClientRect(); if (!r.width) return {error: 'element not visible'};"
                " return {x: r.x + Math.min(r.width / 2, 40), y: r.y + r.height / 2, label: " + self._LABEL + "};")
        return await self.page.evaluate(self._wrap(js, item, index, tail), 30)

    async def _label_of(self, js: Any, item: Any, index: int, frame: str) -> Any:
        label_js = self._wrap(js, item, index, "if (!e || !e.click) return {error: 'no such element'}; return {label: " + self._LABEL + "};")
        return await (self._frame_eval(frame, label_js) if frame else self.page.evaluate(label_js, 30))

    async def _own_click(self, s: dict, js: Any, item: Any, index: int, frame: str) -> Any:
        """The element's own click(), in its frame: for frames and for presses that did
        not land. The label is checked against the guard before anything is clicked."""
        found = await self._label_of(js, item, index, frame)
        if _failed(found):
            return found
        self._check_label(s, found.get("label") or "")
        click_js = self._wrap(js, item, index, "if (e && e.click) e.click(); return true;")
        await (self._frame_eval(frame, click_js) if frame else self.page.evaluate(click_js, 30))
        return found

    # ── guards ─────────────────────────────────────────────────────────
    async def arm(self) -> None:
        """``block`` requests are failed before they leave the browser in every run, and
        ``dry_block`` ones in a dry run (the platform's submit), whatever a step does
        (see ``block_requests``): a fill that stopped, or whose submit raced the
        platform's draft autosave, left a draft behind (KEN 11-03 benchmark: 3 of 10)."""
        patterns = list(self.guards.get("block") or [])
        if self.mode == "dry_run":
            patterns += list(self.guards.get("dry_block") or [])
        if patterns:
            await block_requests(self.page, patterns, self.blocked)

    def _check_label(self, step: dict, label: str) -> None:
        if step.get("op") != "submit" and self.forbid.search(label or ""):
            raise StepFailed(step, f"refused: {label!r} looks like a publish/save/sign-up button; only the submit step may press it")

    # ── steps ──────────────────────────────────────────────────────────
    async def run_steps(self, steps: List[dict], item: Any = None, index: int = 0) -> Optional[dict]:
        """Runs *steps*; returns a dict when the run ends early (the dry-run report)."""
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("stage"):
                self.stage = str(step["stage"])
            if step.get("if") and _failed(await self.eval(step["if"], item, index, step.get("frame") or "")) is not None:
                self.log.append({"id": step.get("id"), "skipped": True})
                continue
            t0 = time.monotonic()
            try:
                try:
                    out = await self._run(step, item, index)
                except StepFailed:
                    raise
                except Exception as exc:
                    raise StepFailed(step, f"{type(exc).__name__}: {exc}")
            except StepFailed as exc:
                if not step.get("optional"):
                    raise
                # an optional part that did not work is reported, not fatal
                self.vars.setdefault("problems", []).append(str(step.get("error") or exc.message)[:300])
                self.log.append({"id": step.get("id"), "stage": self.stage, "failed_optional": exc.message[:300]})
                continue
            entry = {"id": step.get("id"), "stage": self.stage, "ms": int((time.monotonic() - t0) * 1000)}
            if isinstance(out, dict) and out.get("_end"):
                self.log.append(dict(entry, out="(dry run: stopped before the submit)"))
                return out
            self.log.append(dict(entry, out=_gist(out)))
            if step.get("save"):
                self.vars[str(step["save"])] = out
        return None

    async def _run(self, s: dict, item: Any, index: int) -> Any:
        op, frame = s.get("op") or "js", s.get("frame") or ""
        if op not in OPS:
            raise StepFailed(s, f"unknown op {op!r}")
        if op == "sleep":
            await asyncio.sleep(min(float(s.get("seconds") or 1), 30))
            return "ok"
        if op == "press":
            await self.page.press(str(s.get("key") or "Enter"))
            return "ok"
        if op == "js":
            out = await self.eval(s.get("js"), item, index, frame, float(s.get("timeout") or 60))
            why = None if s.get("allow_empty") else _failed(out)
            if why:
                raise StepFailed(s, _why(s, why))
            return out
        if op == "wait":
            end = time.monotonic() + min(float(s.get("seconds") or 15), 120)
            while True:
                out = await self.eval(s.get("js") or "false", item, index, frame)
                if _failed(out) is None:
                    return out
                if time.monotonic() > end:
                    raise StepFailed(s, _why(s, f"waited {s.get('seconds') or 15} s: {_failed(out)}"))
                await asyncio.sleep(0.5)
        if op in ("click", "submit"):
            return await self._click(s, item, index, frame)
        if op == "type":
            xy = await self._element_xy(s.get("target"), item, index)
            if _failed(xy):
                raise StepFailed(s, _why(s, f"nothing to type into: {_failed(xy)}"))
            await self.page.mouse_click(xy["x"], xy["y"])
            await asyncio.sleep(0.3)
            if s.get("select_all"):
                await self.eval("(() => { const e = document.activeElement; if (e && e.select) e.select(); return true })()")
            text = await self.eval(s.get("text") or "''", item, index)
            await self.page.insert_text(str(text if text is not None else ""))
            await asyncio.sleep(float(s.get("settle") or 0.5))
            if s.get("commit"):
                await self.page.press(str(s["commit"]))
                await asyncio.sleep(float(s.get("settle") or 0.5))
            if s.get("until"):
                end = time.monotonic() + float(s.get("seconds") or 5)
                while _failed(await self.eval(s["until"], item, index)) is not None:
                    if time.monotonic() > end:
                        raise StepFailed(s, _why(s, f"typed {text!r} but {str(s['until'])[:120]} never came true"))
                    await asyncio.sleep(0.5)
            return {"typed": text}
        if op == "foreach":
            items = await self.eval(s.get("items") or "[]", item, index)
            if not isinstance(items, list):
                raise StepFailed(s, f"items did not give a list: {_gist(items)}")
            for k, it in enumerate(items):
                end = await self.run_steps(s.get("steps") or [], it, k)
                if end:
                    return end
            return {"items": len(items)}
        return await self._upload(s, item, index, frame)

    async def _click(self, s: dict, item: Any, index: int, frame: str) -> Any:
        if s.get("op") == "submit" and self.mode == "dry_run":
            # the button is found (not pressed), so a dry run also proves the submit step
            found = await self._label_of(s.get("target"), item, index, frame)
            if _failed(found) is not None:
                raise StepFailed(s, _why(s, f"the submit button was not found: {_failed(found)}"))
            report = await self.eval(self.flow["report"]) if self.flow.get("report") else None
            return {"_end": "dry_run", "report": report, "submit_label": found.get("label")}
        tries = max(1, int(s.get("retries") or 1))
        target, last = s.get("target"), None
        if s.get("op") == "submit":
            seen = {r["id"] for r in getattr(self.page, "network", [])}
            # what the submit asked the server (addresses without their query): read on failure
            self.vars["submit_requests"] = sent = []
            try:
                return await self._click_until(s, item, index, frame, tries, target, last)
            finally:
                sent.extend(f"{r.get('status')} {str(r.get('url') or '').split('?')[0][:160]}"
                            for r in list(getattr(self.page, "network", []))
                            if r["id"] not in seen and r.get("type") in ("XHR", "Fetch", "Document"))
        return await self._click_until(s, item, index, frame, tries, target, last)

    async def _click_until(self, s: dict, item: Any, index: int, frame: str, tries: int, target: Any, last: Any) -> Any:
        for k in range(tries):
            if frame or s.get("js_click") or (k == tries - 1 and k > 0):
                # frames, and the last of several tries (a press that did not land: an overlay)
                last = _failed(await self._own_click(s, target, item, index, frame))
            else:
                xy = await self._element_xy(target, item, index)
                last = _failed(xy)
                if last is None:
                    self._check_label(s, xy.get("label") or "")
                    await self.page.mouse_click(xy["x"], xy["y"])
            if not s.get("until"):
                if last is None:
                    return {"clicked": True}
                continue
            end = time.monotonic() + float(s.get("seconds") or 8)
            while time.monotonic() < end:
                out = await self.eval(s["until"], item, index)
                if _failed(out) is None:
                    return out
                await asyncio.sleep(0.5)
            last = last or f"after the click, {str(s['until'])[:120]} never came true"
        raise StepFailed(s, _why(s, last))

    async def _upload(self, s: dict, item: Any, index: int, frame: str) -> Any:
        """The product's files of the given roles into a file input. In a dry run,
        files uploaded before (same name and size) are not uploaded again: dry runs
        must not fill the store's picture space."""
        names = [n for r in s.get("roles") or [] for n in (self.files.get(r) or [])]
        if not names:
            return {}
        if self.mode == "dry_run" and s.get("answers") and all(self._cache_key(n) in self.cache for n in names):
            return {n: self.cache[self._cache_key(n)] for n in names}
        if s.get("open"):
            await self.eval(s["open"], item, index, frame)
            await asyncio.sleep(1.5)
        oid = None
        for _ in range(20):
            oid = await self._object(s.get("input"), item, index, frame)
            if oid:
                break
            await asyncio.sleep(0.5)
        if not oid:
            raise StepFailed(s, _why(s, "no file input"))
        before = {r["id"] for r in getattr(self.page, "network", [])}
        await self.page.send("DOM.setFileInputFiles", {"objectId": oid, "files": [self.paths[n] for n in names]})
        if not s.get("answers"):
            await asyncio.sleep(2)
            return {"files": len(names)}
        spec = s["answers"]
        got = await self._answers(spec, before, len(names), float(s.get("seconds") or 60))
        key = spec.get("name_key") or "fileName"
        out = {str(o[key]): o for o in got if o.get(key)}
        missing = [n for n in names if n not in out]
        if missing:
            raise StepFailed(s, _why(s, f"no upload answer for {missing}"))
        for n in names:
            self.cache[self._cache_key(n)] = out[n]
        return {n: out[n] for n in names}

    async def _answers(self, spec: dict, before: set, want: int, seconds: float) -> List[dict]:
        """JSON answers of new requests whose address matches spec["url"], each reduced
        to spec["path"] (dotted)."""
        rx = re.compile(spec.get("url") or "$^")
        got: Dict[str, dict] = {}
        end = time.monotonic() + seconds
        while time.monotonic() < end and len(got) < want:
            await asyncio.sleep(1)
            for r in list(getattr(self.page, "network", [])):
                if r["id"] in before or r["id"] in got or not rx.search(str(r.get("url") or "")):
                    continue
                try:
                    o = json.loads(await self.page.response_body(r["id"]))
                except Exception:
                    continue
                for k in [p for p in str(spec.get("path") or "").split(".") if p]:
                    o = o.get(k) if isinstance(o, dict) else None
                if isinstance(o, dict):
                    got[r["id"]] = o
        return list(got.values())

    def _cache_key(self, name: str) -> str:
        try:
            return f"{name}|{os.path.getsize(self.paths.get(name) or '')}"
        except OSError:
            return name

    async def diag(self) -> Any:
        """Where the page is when a step failed: address, open dialogs, visible text."""
        try:
            return await self.eval(self.flow.get("diag") or DIAG_JS)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}


async def run_flow(page: Any, flow: dict, guards: dict, listing: dict, files: Dict[str, List[str]],
                   paths: Dict[str, str], mode: str = "publish", upload_cache: Optional[dict] = None) -> Dict[str, Any]:
    """Run *flow*; returns {"ok", "mode", "stage", "step", "error", "log", "vars", "report", "diag", "blocked"}.
    In a dry run ``ok`` means every step up to the submit worked."""
    run = FlowRun(page, flow, guards, listing, files, paths, mode, upload_cache)
    out: Dict[str, Any] = {"ok": False, "mode": mode}
    try:
        await run.arm()
        end = await run.run_steps(flow.get("steps") or [])
        out["ok"] = True
        if end:
            out["report"], out["submit_label"] = end.get("report"), end.get("submit_label")
    except StepFailed as exc:
        out.update(step=exc.step.get("id"), error=exc.message, diag=await run.diag())
        logger.info(f"[fill] {mode} stopped at {exc.step.get('id')!r} ({run.stage}): {exc.message[:300]}")
    out.update(stage=run.stage, log=run.log[-80:], blocked=run.blocked,
               vars={k: v for k, v in run.vars.items() if not k.startswith("_")})
    return out

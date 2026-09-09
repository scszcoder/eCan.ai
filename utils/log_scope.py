"""Run-scope tagging for log records (per agent / task / skill observability).

Every ``logger.*`` call made while a run scope is active gets a compact suffix
appended by the file/console formatters::

    ... - INFO - [EventMonitor][HB] label='新消息' status=ok ... [agent=前台小张 task=飞鸽客服前台001]

so "show me the front-desk agent's lines" is a substring filter (grep, or the
Help > 查看日志 viewer's Agent dropdown), and modules keep calling the logger
exactly as before — nothing in the 60+ browser_use_extension modules changes.

Mechanics
---------
* The scope lives in a :class:`contextvars.ContextVar`. ``set_scope`` /
  :func:`scope` install it; :class:`ScopeFilter` stamps ``record.ecan_scope``
  on each record **in the emitting thread** (it is attached to the QueueHandler
  the app logger uses, so the stamp happens before the record crosses the async
  queue — the listener thread has no context of its own).
* ContextVars flow into ``asyncio.create_task`` / ``call_soon_threadsafe`` /
  ``run_coroutine_threadsafe`` / ``asyncio.to_thread`` automatically. They do
  NOT flow into ``ThreadPoolExecutor.submit`` or ``threading.Thread`` — wrap
  those callables with :func:`wrap_context` at the handoff.
* Third-party records bridged through logger_helper (browser_use →
  ``[browser_use] ...``) are re-logged in the same thread, so they get the
  same stamp.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import logging
from typing import Any, Callable, Dict, Optional

_SCOPE: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar("ecan_log_scope", default=None)

# Suffix key order + the short labels used in the log line.
_KEYS = (("agent_name", "agent"), ("task_name", "task"), ("skill_name", "skill"), ("run_id", "run"))


def get_scope() -> Dict[str, Any]:
    """Current scope dict (empty when none is active)."""
    return dict(_SCOPE.get() or {})


_ATTR_HEADER_MAP = (
    ("X-Ecan-Agent-Id", "agent_id"),
    ("X-Ecan-Task-Id", "task_id"),
    ("X-Ecan-Skill-Id", "skill_id"),
    ("X-Ecan-Vehicle-Id", "vehicle_id"),
)


def attribution_headers() -> Dict[str, str]:
    """``X-Ecan-*`` token-attribution headers from the CURRENT scope.

    Read at REQUEST time (the scope is a ContextVar, so concurrent runs each see
    their own values — never the cross-attribution you'd get from stamping a
    shared/cached LLM instance). Sent as HEADERS, not body fields, so they can't
    leak to a model vendor: the llm_proxy builds its own upstream header set.

    Header-safe (latin-1) values pass through unchanged so the backend can match
    IDs exactly; only a value that isn't latin-1-encodable (e.g. a Chinese skill
    name) is percent-encoded, so it can't break HTTP header encoding. Only
    non-empty values are included.
    """
    sc = get_scope()
    out: Dict[str, str] = {}
    for hdr, key in _ATTR_HEADER_MAP:
        v = sc.get(key)
        if v:
            out[hdr] = _header_safe(str(v))
    # X-Ecan-Source is a deliberate SUBSYSTEM category (chat / skill_dev /
    # log_analysis / tool_picker / proxy_test …), set explicitly by each entry
    # point — it's the dimension that separates skill-dev and log-analysis spend
    # from ordinary chat once pricier models show up on the bill, which skill_id
    # alone can't. Falls back to the skill/agent name only when no category was
    # set, so nothing is ever unlabelled.
    src = sc.get("source") or sc.get("skill_name") or sc.get("agent_name")
    if src:
        out["X-Ecan-Source"] = _header_safe(str(src))
    return out


def apply_attribution_to_request(request) -> None:
    """httpx request event-hook: stamp X-Ecan-* from the CURRENT scope at SEND
    time. Use with an OpenAI-compatible client (ChatOpenAI / OpenAIEmbeddings /
    a raw rerank client) whose instance is cached/shared — reading the scope
    per-request is what keeps concurrent runs from cross-attributing."""
    try:
        for k, v in attribution_headers().items():
            request.headers[k] = v
    except Exception:
        pass


def attribution_http_clients(timeout: Any = None):
    """(sync httpx.Client, async httpx.AsyncClient) that inject X-Ecan-*
    attribution per request from the active scope. Returns (None, None) when
    httpx is unavailable so a caller can pass them straight through without
    guarding construction. Pass both to OpenAIEmbeddings / ChatOpenAI /
    OpenAI(...) as http_client= / http_async_client=."""
    try:
        import httpx

        async def _ahook(request):
            apply_attribution_to_request(request)

        kw = {"event_hooks": {"request": [apply_attribution_to_request]}}
        akw = {"event_hooks": {"request": [_ahook]}}
        if timeout is not None:
            kw["timeout"] = timeout
            akw["timeout"] = timeout
        return httpx.Client(**kw), httpx.AsyncClient(**akw)
    except Exception:
        return None, None


def _header_safe(s: str) -> str:
    """Return *s* unchanged when it's a valid latin-1 HTTP header value;
    otherwise percent-encode it (the backend can decodeURIComponent)."""
    try:
        s.encode("latin-1")
        return s
    except UnicodeEncodeError:
        from urllib.parse import quote
        return quote(s, safe="")


def set_scope(**fields: Any) -> contextvars.Token:
    """Replace the current scope; returns a token for :func:`reset_scope`.
    ``None``/empty values are dropped so the suffix only shows what is known."""
    clean = {k: v for k, v in fields.items() if v not in (None, "")}
    return _SCOPE.set(clean or None)


def update_scope(**fields: Any) -> contextvars.Token:
    """Merge fields into the current scope (e.g. add the task once known)."""
    cur = get_scope()
    cur.update({k: v for k, v in fields.items() if v not in (None, "")})
    return _SCOPE.set(cur or None)


def reset_scope(token: contextvars.Token) -> None:
    try:
        _SCOPE.reset(token)
    except Exception:  # token from another context — just clear
        _SCOPE.set(None)


@contextlib.contextmanager
def scope(**fields: Any):
    """``with scope(agent_name=..., task_name=...): ...`` — restored on exit,
    so pooled worker threads never leak a stale scope into the next job."""
    tok = set_scope(**fields)
    try:
        yield
    finally:
        reset_scope(tok)


def suffix(fields: Optional[Dict[str, Any]] = None) -> str:
    """Render the ``[agent=… task=…]`` suffix for *fields* (default: current scope)."""
    f = fields if fields is not None else (_SCOPE.get() or {})
    if not f:
        return ""
    parts = []
    for key, label in _KEYS:
        v = f.get(key)
        if v not in (None, ""):
            parts.append(f"{label}={str(v).replace(' ', '_')[:48]}")
    return f" [{' '.join(parts)}]" if parts else ""


class ScopeFilter(logging.Filter):
    """Stamp ``record.ecan_scope`` (never rejects). Keeps an existing stamp so a
    listener-side copy of the filter acts only as a safety net."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "ecan_scope"):
            try:
                record.ecan_scope = suffix()
            except Exception:
                record.ecan_scope = ""
        return True


class ScopedFormatter(logging.Formatter):
    """``logging.Formatter`` whose pattern may use ``%(ecan_scope)s`` even for
    records that never passed a :class:`ScopeFilter`."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "ecan_scope"):
            record.ecan_scope = ""
        return super().format(record)


def wrap_context(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Return *fn* bound to a copy of the CURRENT context — pass the result to
    ``ThreadPoolExecutor.submit`` / ``threading.Thread(target=...)`` so the run
    scope (and any other ContextVar) survives the thread handoff."""
    ctx = contextvars.copy_context()

    @functools.wraps(fn)
    def _runner(*args: Any, **kwargs: Any) -> Any:
        return ctx.run(fn, *args, **kwargs)

    return _runner

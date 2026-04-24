"""
SiteAdapter — the per-site selector bundle + verify policy.

This module is PURE DATA and PURE LOGIC (no DOM, no browser, no globals).
It provides:

  * ``SiteAdapter``              — pydantic model of the config shape
  * ``DEFAULT_FEIGE_SITE_ADAPTER`` — the current production Feige preset,
                                    used as a fallback when no adapter is
                                    supplied via the node editor.
  * ``normalize_site_adapter``   — tolerant loader; accepts a dict, a
                                    SiteAdapter, or None, returns a dict.
  * ``build_active_session_js``  — generic JS builder: given an adapter
                                    config, returns a JS snippet that
                                    reads the DOM and emits a JSON result
                                    identifying the currently active chat.
  * ``verify_active_session_match`` — policy evaluator: given the JSON
                                    result + expected customer name,
                                    returns ``(ok, reason)``.

Why here (as opposed to build_node.py)?
  * The inline block in ``build_node.py`` hard-codes Feige selectors
    (``wmvLQcpt39Hk9PSISrlN``, ``MP1bk3ccfHC9V2SnPCGD``, ``#topbar-left-info``).
    Moving that knowledge into config — with a default preset — lets the
    same code serve other customer-service sites by swapping one JSON
    field in the node editor.
  * Both the hook (``VerifyActiveSessionHook``) and any future "click-
    sidebar-row" helper need these selectors; keeping them in one place
    prevents them from drifting apart.

No side effects, no imports from ``build_node.py``.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models — documentation-by-type.
# ---------------------------------------------------------------------------
class NameReader(BaseModel):
    """Extracts a human name (or id) from a DOM element via one selector.

    ``source="attr"`` reads ``element.getAttribute(attr)``;
    ``source="text"`` reads ``element.textContent`` (trimmed).
    """

    selector: str = Field(..., description="CSS selector relative to the sidebar row.")
    source: Literal["attr", "text"] = "text"
    attr: str = ""  # only used when source == "attr"


class ActiveStrategy(BaseModel):
    """How to identify which sidebar row is currently active.

    Strategies are tried in order; the first one that uniquely identifies
    a row wins.  The generic JS builder iterates these at runtime.

    Known types:
      * ``class_token`` — any row whose classList contains ``token``.
      * ``aria_selected`` — row with ``aria-selected="true"``.
      * ``odd_one_out``  — the row whose classList differs from the
                           majority's.  Used when Feige rotates the
                           active-class hash and we don't know its value
                           yet.  Last-resort; expensive.
    """

    type: Literal["class_token", "aria_selected", "odd_one_out"]
    token: str = ""  # required when type == "class_token"


class SidebarCfg(BaseModel):
    item_selector: str
    name_readers: list[NameReader] = Field(default_factory=list)
    active_strategies: list[ActiveStrategy] = Field(default_factory=list)


class HeaderCfg(BaseModel):
    root_selector: str
    leaf_candidates: str = "div, span"
    exclude_texts: list[str] = Field(default_factory=list)
    max_text_len: int = 60
    fallback_attr: str = ""


VerifyPolicy = Literal[
    "affirmative_and_no_conflict",
    "strict_both",
    "sidebar_only",
    "header_only",
]


class SiteAdapter(BaseModel):
    """The full per-site adapter config read from the node editor."""

    name: str = "feige"
    sidebar: SidebarCfg
    header: HeaderCfg
    verify_policy: VerifyPolicy = "affirmative_and_no_conflict"


# ---------------------------------------------------------------------------
# Feige default preset.
# Selectors captured 2026-04-23 from the live Feige site + emulation.  The
# ``wmvLQcpt39Hk9PSISrlN`` class is a CSS-in-JS hash Feige rotates every few
# weeks; the ``odd_one_out`` strategy kicks in after it rotates so we don't
# hard-fail during the window between rotation and config update.
# ---------------------------------------------------------------------------
DEFAULT_FEIGE_SITE_ADAPTER: dict = {
    "name": "feige",
    "sidebar": {
        "item_selector": '[data-qa-id="qa-conversation-chat-item"]',
        "name_readers": [
            {"selector": ".MP1bk3ccfHC9V2SnPCGD", "source": "attr", "attr": "title"},
            {"selector": ".Jv6FtqUv5VoYARd2pp4y", "source": "text"},
            {"selector": '[data-qa-id="qa-conversation-nickname"]', "source": "text"},
        ],
        "active_strategies": [
            {"type": "class_token", "token": "active"},
            {"type": "aria_selected"},
            {"type": "class_token", "token": "wmvLQcpt39Hk9PSISrlN"},
            {"type": "odd_one_out"},
        ],
    },
    "header": {
        "root_selector": "#topbar-left-info",
        "leaf_candidates": "div, span",
        "exclude_texts": ["添加备注"],
        "max_text_len": 60,
        "fallback_attr": "data-btm-id",
    },
    "verify_policy": "affirmative_and_no_conflict",
}


# ---------------------------------------------------------------------------
# Loader — accept a dict, a SiteAdapter instance, or None.  Returns a plain
# dict (what everything downstream — JS builder, hooks — actually consumes).
# ---------------------------------------------------------------------------
def normalize_site_adapter(cfg: Any) -> dict:
    """Resolve user-supplied adapter config into a validated dict.

    ``cfg`` None / empty → returns a fresh copy of the Feige default.
    ``cfg`` a dict → validated via SiteAdapter and re-dumped (fills defaults).
    ``cfg`` a SiteAdapter → dumped.

    Raises ``pydantic.ValidationError`` for malformed input.  Callers that
    want graceful fallback-on-invalid should catch and substitute the
    default themselves (see build_node wiring in a future PR).
    """
    if cfg is None:
        return json.loads(json.dumps(DEFAULT_FEIGE_SITE_ADAPTER))  # deep copy
    if isinstance(cfg, SiteAdapter):
        return cfg.model_dump()
    if isinstance(cfg, dict):
        if not cfg:
            return json.loads(json.dumps(DEFAULT_FEIGE_SITE_ADAPTER))
        return SiteAdapter.model_validate(cfg).model_dump()
    raise TypeError(
        f"site_adapter must be dict/SiteAdapter/None, got {type(cfg).__name__}"
    )


# ---------------------------------------------------------------------------
# Generic active-session JS builder.
#
# The output JS is self-contained (no external helpers), idempotent, and
# returns a JSON-encoded string so the Python caller can json.loads() it.
# Result shape::
#
#     {
#       "ok": true|false,
#       "active": "<name from sidebar>",
#       "header": "<name from header>",
#       "strategy": "<which active-strategy matched>",
#       "diagnostics": {
#         "item_count": <int>,
#         "strategies_tried": ["class_token:active", ...],
#         "seen_names": ["客户A", "客户B", ...]
#       }
#     }
#
# When no strategy identifies an active row, ``ok=false`` and ``strategy=""``;
# the caller falls back to the header name alone for its policy decision.
# ---------------------------------------------------------------------------
def _js_str(s: str) -> str:
    """JSON-encode a Python string as a JS string literal (handles quotes)."""
    return json.dumps(s, ensure_ascii=False)


def build_active_session_js(cfg: dict) -> str:
    """Construct the generic active-session detection JS from *cfg*.

    *cfg* must be the normalised dict (see ``normalize_site_adapter``).
    No runtime validation is done here — malformed input results in
    malformed JS which fails at the browser.  Callers should always run
    config through ``normalize_site_adapter`` first.
    """
    sidebar = cfg.get("sidebar") or {}
    header = cfg.get("header") or {}
    item_sel = sidebar.get("item_selector") or ""
    name_readers = sidebar.get("name_readers") or []
    active_strategies = sidebar.get("active_strategies") or []
    header_root = header.get("root_selector") or ""
    header_leaves = header.get("leaf_candidates") or "div, span"
    header_excludes = header.get("exclude_texts") or []
    header_max = int(header.get("max_text_len") or 60)
    header_fallback_attr = header.get("fallback_attr") or ""

    # Serialize lists into JS literals via json.dumps so embedded strings
    # (which may contain quotes or CJK chars) round-trip safely.
    readers_js = json.dumps(name_readers, ensure_ascii=False)
    strategies_js = json.dumps(active_strategies, ensure_ascii=False)
    excludes_js = json.dumps(header_excludes, ensure_ascii=False)

    return f"""
(function() {{
  var ITEM_SEL = {_js_str(item_sel)};
  var READERS = {readers_js};
  var STRATEGIES = {strategies_js};
  var HEADER_ROOT = {_js_str(header_root)};
  var HEADER_LEAVES = {_js_str(header_leaves)};
  var HEADER_EXCLUDES = {excludes_js};
  var HEADER_MAX_LEN = {header_max};
  var HEADER_FALLBACK_ATTR = {_js_str(header_fallback_attr)};

  function readName(row) {{
    for (var i = 0; i < READERS.length; i++) {{
      var r = READERS[i];
      var el = row.querySelector(r.selector);
      if (!el) continue;
      var v = '';
      if (r.source === 'attr') {{
        v = el.getAttribute(r.attr || '') || '';
      }} else {{
        v = el.textContent || '';
      }}
      v = (v || '').trim();
      if (v) return v;
    }}
    return '';
  }}

  var items = ITEM_SEL ? Array.from(document.querySelectorAll(ITEM_SEL)) : [];
  var seenNames = [];
  for (var k = 0; k < items.length && seenNames.length < 20; k++) {{
    var nm = readName(items[k]);
    if (nm) seenNames.push(nm);
  }}

  // Strategy dispatch.
  var activeRow = null;
  var matchedStrategy = '';
  var tried = [];

  function trySt(st) {{
    var tag = st.type + (st.token ? ':' + st.token : '');
    tried.push(tag);
    if (st.type === 'class_token') {{
      var token = st.token || '';
      if (!token) return null;
      for (var i = 0; i < items.length; i++) {{
        var cls = items[i].className || '';
        if (typeof cls !== 'string') cls = String(cls);
        if (items[i].classList && items[i].classList.contains(token)) return items[i];
        if (cls.indexOf(token) >= 0) return items[i];
      }}
      return null;
    }}
    if (st.type === 'aria_selected') {{
      for (var i2 = 0; i2 < items.length; i2++) {{
        if (items[i2].getAttribute && items[i2].getAttribute('aria-selected') === 'true') {{
          return items[i2];
        }}
      }}
      return null;
    }}
    if (st.type === 'odd_one_out') {{
      if (items.length < 2) return null;
      var freq = {{}};
      var canonicals = [];
      for (var i3 = 0; i3 < items.length; i3++) {{
        var c = items[i3].className || '';
        if (typeof c !== 'string') c = String(c);
        var parts = c.split(/\\s+/).filter(function(x) {{ return x && x.length > 0; }}).sort();
        var key = parts.join(' ');
        freq[key] = (freq[key] || 0) + 1;
        canonicals.push(key);
      }}
      var oddIdx = -1;
      var oddCount = 0;
      for (var i4 = 0; i4 < canonicals.length; i4++) {{
        if (freq[canonicals[i4]] === 1) {{
          oddIdx = i4;
          oddCount++;
        }}
      }}
      // Only return a row if EXACTLY ONE row is odd; ties are ambiguous.
      if (oddCount === 1 && oddIdx >= 0) return items[oddIdx];
      return null;
    }}
    return null;
  }}

  for (var s = 0; s < STRATEGIES.length; s++) {{
    var row = trySt(STRATEGIES[s]);
    if (row) {{
      activeRow = row;
      matchedStrategy = STRATEGIES[s].type +
        (STRATEGIES[s].token ? ':' + STRATEGIES[s].token : '');
      break;
    }}
  }}

  var activeName = activeRow ? readName(activeRow) : '';

  // Header read — walks leaf elements inside HEADER_ROOT, skipping excludes.
  var headerName = '';
  if (HEADER_ROOT) {{
    var hroot = document.querySelector(HEADER_ROOT);
    if (hroot) {{
      var leaves = hroot.querySelectorAll(HEADER_LEAVES);
      for (var li = 0; li < leaves.length; li++) {{
        var t = (leaves[li].textContent || '').trim();
        if (!t) continue;
        if (t.length > HEADER_MAX_LEN) continue;
        var excluded = false;
        for (var xi = 0; xi < HEADER_EXCLUDES.length; xi++) {{
          if (t === HEADER_EXCLUDES[xi]) {{ excluded = true; break; }}
        }}
        if (excluded) continue;
        // Prefer leaf elements (no child elements) — they're most likely
        // the actual name as opposed to a container with mixed text.
        if (leaves[li].children && leaves[li].children.length === 0) {{
          headerName = t;
          break;
        }}
        if (!headerName) headerName = t;
      }}
      if (!headerName && HEADER_FALLBACK_ATTR) {{
        var fa = hroot.getAttribute(HEADER_FALLBACK_ATTR) || '';
        headerName = (fa || '').trim();
      }}
    }}
  }}

  return JSON.stringify({{
    ok: Boolean(activeRow),
    active: activeName,
    header: headerName,
    strategy: matchedStrategy,
    diagnostics: {{
      item_count: items.length,
      strategies_tried: tried,
      seen_names: seenNames
    }}
  }});
}})()
""".strip()


# ---------------------------------------------------------------------------
# Verify policy evaluator.
#
# Given the JSON dict (already json.loads-ed) returned by the JS above, and
# the ``expected_customer`` name we intend to type into, decide whether it
# is safe to proceed.  Returns ``(ok: bool, reason: str)``.
#
# Policies:
#   * ``affirmative_and_no_conflict`` (default, zero-risk):
#       - At least one signal (sidebar OR header) must equal expected.
#       - Neither signal may point at a DIFFERENT customer.
#       - Empty signals are silent and treated as "no conflict".
#   * ``strict_both``:
#       - Both sidebar and header must equal expected.  Any empty or
#         mismatched signal is a mismatch.
#   * ``sidebar_only``:  sidebar must equal expected; header ignored.
#   * ``header_only``:   header must equal expected; sidebar ignored.
# ---------------------------------------------------------------------------
def verify_active_session_match(
    cfg: dict, verify_result: dict, expected_customer: str
) -> tuple[bool, str]:
    """Evaluate an active-session verify result against an expected name."""
    policy = str(cfg.get("verify_policy") or "affirmative_and_no_conflict")
    expected = (expected_customer or "").strip()
    if not expected:
        return False, "verify:no_expected_customer"

    if not isinstance(verify_result, dict):
        return False, "verify:bad_result_shape"

    active = str(verify_result.get("active") or "").strip()
    header = str(verify_result.get("header") or "").strip()

    if policy == "strict_both":
        if active == expected and header == expected:
            return True, "verify:strict_both_match"
        return False, (
            f"verify:strict_both_mismatch "
            f"(expected={expected!r}, active={active!r}, header={header!r})"
        )

    if policy == "sidebar_only":
        if active == expected:
            return True, "verify:sidebar_match"
        return False, f"verify:sidebar_mismatch (expected={expected!r}, active={active!r})"

    if policy == "header_only":
        if header == expected:
            return True, "verify:header_match"
        return False, f"verify:header_mismatch (expected={expected!r}, header={header!r})"

    # affirmative_and_no_conflict (default)
    active_affirms = (active == expected)
    header_affirms = (header == expected)
    active_conflicts = (bool(active) and active != expected)
    header_conflicts = (bool(header) and header != expected)

    if active_conflicts or header_conflicts:
        return False, (
            f"verify:conflict "
            f"(expected={expected!r}, active={active!r}, header={header!r})"
        )
    if active_affirms or header_affirms:
        return True, (
            f"verify:affirmed "
            f"(active={active_affirms}, header={header_affirms})"
        )
    return False, (
        f"verify:no_affirmation "
        f"(expected={expected!r}, active={active!r}, header={header!r})"
    )


__all__ = [
    "NameReader",
    "ActiveStrategy",
    "SidebarCfg",
    "HeaderCfg",
    "SiteAdapter",
    "VerifyPolicy",
    "DEFAULT_FEIGE_SITE_ADAPTER",
    "normalize_site_adapter",
    "build_active_session_js",
    "verify_active_session_match",
]

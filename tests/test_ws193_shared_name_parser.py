"""ws193: the three Feige sidebar name parsers (front_desk scan, click-to-open,
active-verify) share ONE redesign-resilient reader so they can't drift apart —
the 96z cold-start stuck (scan saw names=['sc',...] but the click reader returned
seen_names=[] on the rebuilt frame → cold message never scraped)."""


from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    sidebar_preview_js as spjs,
    dom_assets,
)


def test_shared_name_reader_has_redesign_fallbacks():
    js = spjs.ROW_NAME_JS
    assert "function __ecanRowName(row)" in js
    # ws183: iterate ALL [title] descendants (the revisit-row variant's real
    # name is a later title, after the numeric badge).
    assert "querySelectorAll('[title]')" in js
    # skips numeric badges and time-ago strings.
    assert "分钟" in js and "小时" in js
    # ws110 broad data-qa-id fallback.
    assert "nickname" in js


def test_click_and_verify_use_shared_reader():
    for js_name in ("FEIGE_CLICK_SIDEBAR_ROW_JS", "FEIGE_ACTIVE_CUSTOMER_JS"):
        js = getattr(dom_assets, js_name)
        # the shared reader is injected (definition present)...
        assert "function __ecanRowName(row)" in js, js_name
        # ...exactly once (no duplicate copies to drift)...
        assert js.count("function __ecanRowName(row)") == 1, js_name
        # ...and readName delegates to it (checked first, ahead of the legacy
        # per-selector fallbacks in the readName body).
        assert "var _sn = (typeof __ecanRowName === 'function') ? __ecanRowName(row)" in js, js_name


def test_click_reader_dumps_on_parser_drift():
    js = dom_assets.FEIGE_CLICK_SIDEBAR_ROW_JS
    # rows present but zero names -> emit rows_dump (the drift signature).
    assert "rows_dump" in js
    assert "seenNames.length === 0" in js
    assert "outerHTML" in js


def test_send_side_open_and_list_use_shared_reader():
    # ws193 (97c): the SEND-side open-by-name + list JS also drifted (mt062
    # selectors → "Session not found" → the cold-start greeting was dropped).
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import site_tools
    for js_name in ("_FEIGE_OPEN_SESSION_JS", "_FEIGE_LIST_SESSIONS_JS"):
        js = getattr(site_tools, js_name)
        assert "function __ecanRowName(row)" in js, js_name
        assert js.count("function __ecanRowName(row)") == 1, js_name
        assert "__ecanRowName(" in js, js_name
    # the open-by-name loop must match via the shared reader, not the dead
    # mt062 name selector.
    open_js = site_tools._FEIGE_OPEN_SESSION_JS
    assert "var name = __ecanRowName(items[i])" in open_js


def test_scan_reader_still_has_all_title_iteration():
    # front_desk's ws108 scan parser (the one that already worked) is unchanged
    # and still carries the all-[title] iteration it shares in spirit with ws193.
    from pathlib import Path
    src = Path(
        "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/front_desk.py"
    ).read_text(encoding="utf-8")
    assert "querySelectorAll('[title]')" in src

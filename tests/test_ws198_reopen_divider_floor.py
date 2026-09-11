"""ws198: cold-reopen fresh-message drop (2026-09-09 '现在店铺有折扣吗').

On a manual-close reopen the fresh post-'以上为历史消息' message was walked past and
a stale pre-divider bubble was picked → perpetual msg-id dedup-skip → never
answered. Two safe changes (JS can't run in this harness — assert the source):
 1) the divider floor now scans the WRAPPERS list for the boundary (the prior
    element+compareDocumentPosition search silently failed);
 2) the WS170 dump captures outerHTML of bubbles _customerBubble can't classify,
    so the next reopen pins the fresh message's real structure.
"""

from pathlib import Path

DA = Path("agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py").read_text(encoding="utf-8")
PDE = Path("agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py").read_text(encoding="utf-8")


def test_floor_scans_wrappers_for_boundary():
    # the robust floor walks the wrappers list and floors after the boundary
    assert "for (var __bw = wrappers.length - 1; __bw >= scanStart; __bw--)" in DA
    assert "__BND__.test(wrappers[__bw].textContent" in DA
    assert "__dividerFloor__ = Math.min(wrappers.length - 1, __bw + 1)" in DA
    # legacy element search kept as a fallback
    assert "if (!__dividerFloor__)" in DA
    assert "var __BND__ = /以上为历史消息|关闭会话/;" in DA


def test_dump_captures_unrecognized_bubble_html():
    assert "rec.unrecognized = true" in PDE
    assert '[class*="messageIsMe"],[class*="messageNotMe"]' in PDE
    assert ".Ie29C7uLyEjZzd8JeS8A" in PDE

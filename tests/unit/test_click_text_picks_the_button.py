"""click_text picks the button that shows the text, not the first element that does.

Shopify's order page has 12 elements showing "Create shipping label"; the first was a
page-wide wrapper, so every click landed on the page frame (2026-11-18, shop1 #1001).
Runs CLICK_JS in a headless Chrome (installed Chrome, throwaway profile); skipped without one.
"""
import json

import pytest

from agent.ec_skills.explorer.tools import CLICK_JS

PAGE = """<html><body>
<div id="frame" role="link" style="display:block">Create shipping label<nav>Skip to content Search Home Orders 11 Drafts
  Shipping labels and a long page-wide navigation text that is not the button at all</nav></div>
<span style="visibility:hidden">Create shipping label</span>
<div aria-hidden="true"><span>Create shipping label</span></div>
<p>Unfulfilled (1)</p>
<s-internal-button id="real" style="display:contents">Create shipping label</s-internal-button>
<button>Mark as fulfilled</button>
<s-menu id="menu"></s-menu>
<script>
  // Like Shopify's More actions menu: its items live inside the menu's own shadow root.
  customElements.define('s-menu', class extends HTMLElement {
    constructor() { super(); this.attachShadow({mode: 'open'}).innerHTML =
      '<div role="menu"><button role="menuitem" id="reprint">Reprint label</button></div>'; }
  });
  // Like Shopify's admin: the host has no box (display:contents); the clickable <button>
  // lives in its shadow root and shows the host's text through a slot.
  customElements.define('s-internal-button', class extends HTMLElement {
    constructor() { super(); this.attachShadow({mode: 'open'}).innerHTML = '<button><slot></slot></button>'; }
  });
</script>
</body></html>"""


def _run(page, text, nth=0):
    return page.evaluate(CLICK_JS % (json.dumps(text), json.dumps(""), nth))


@pytest.fixture(scope="module")
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:                 # no installed Chrome on this machine
            pytest.skip(f"no Chrome: {e}")
        pg = browser.new_page()
        pg.set_content(PAGE)
        yield pg
        browser.close()


def test_the_real_button_wins_over_wrappers_and_hidden_copies(page):
    found = _run(page, "Create shipping label")
    assert found.get("tag") == "s-internal-button" and found.get("label") == "Create shipping label", found
    assert page.evaluate(f"document.elementFromPoint({found['x']}, {found['y']}).closest('#real') !== null")


def test_a_single_match_is_unchanged(page):
    assert _run(page, "Mark as fulfilled").get("label") == "Mark as fulfilled"
    assert "error" in _run(page, "No such text")


def test_a_menu_item_inside_a_shadow_root_is_found(page):
    found = _run(page, "Reprint label")
    assert found.get("label") == "Reprint label" and "error" not in found, found
    hit = page.evaluate(f"(() => {{ const h = document.elementFromPoint({found['x']}, {found['y']}); "
                        f"return h.shadowRoot.elementFromPoint({found['x']}, {found['y']}).id; }})()")
    assert hit == "reprint"

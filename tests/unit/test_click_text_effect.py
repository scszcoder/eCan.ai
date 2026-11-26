"""click_text says what the page did after the click, so a Buy click the site never received
can be told from one it did (Shopify's Buy shipping label sent nothing twice, 2026-11-25)."""
from agent.ec_skills.browser_use_extension.extension_tools_service import describe_click_effect


def test_a_click_that_sent_nothing_is_safe_to_repeat():
    msg = describe_click_effect({"sent": [], "url_changed": False, "url": "https://shop.test/purchase/1"})
    assert "sent nothing" in msg and "nothing was bought" in msg


def test_a_click_that_sent_requests_names_them():
    msg = describe_click_effect({"sent": ["/ShippingLabelUpdate", "/ShippingLabelsPurchase"],
                                 "url_changed": False, "url": "https://shop.test/purchase/1"})
    assert "sent 2 request(s)" in msg and "ShippingLabelsPurchase" in msg and "nothing was bought" not in msg


def test_a_page_that_moved_or_cannot_be_read_never_claims_nothing_happened():
    for effect in ({"sent": [], "url_changed": True, "url": "https://shop.test/orders/9"},
                   {"left": True, "url": "https://shop.test/x"}, {"sent": None}, None):
        assert "nothing was bought" not in describe_click_effect(effect)


def test_the_page_watcher_hears_a_request_and_its_silence():
    import pytest
    sync_api = pytest.importorskip("playwright.sync_api")
    from agent.ec_skills.browser_use_extension.extension_tools_service import _CLICK_EFFECT_JS, _WATCH_CLICK_JS
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:                 # no installed Chrome on this machine
            pytest.skip(f"no Chrome: {e}")
        pg = browser.new_page()
        pg.route("http://shop.test/**", lambda route: route.fulfill(body="ok"))
        pg.goto("http://shop.test/purchase/1")
        pg.evaluate(_WATCH_CLICK_JS)
        pg.wait_for_timeout(300)
        assert pg.evaluate(_CLICK_EFFECT_JS)["sent"] == []
        pg.evaluate(_WATCH_CLICK_JS)
        pg.evaluate("fetch('/api/operations/ShippingLabelsPurchase', {method: 'POST', body: '{}'})")
        pg.wait_for_timeout(500)
        sent = pg.evaluate(_CLICK_EFFECT_JS)["sent"]
        assert len(sent) == 1 and sent[0].endswith("/api/operations/ShippingLabelsPurchase"), sent
        browser.close()

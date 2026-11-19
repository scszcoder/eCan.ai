"""Which browser tabs may hold a shipping-label PDF (agent/ec_skills/label_utils/pdf_tabs.py)."""
from agent.ec_skills.label_utils.pdf_tabs import is_candidate


def test_label_tabs_are_candidates_and_the_store_admin_is_not():
    assert is_candidate("blob:https://admin.shopify.com/6b1f-label")            # print view's blob
    assert is_candidate("https://cdn.shopify.com/s/files/labels/1001-F1.pdf?sig=x")
    assert is_candidate("https://admin.shopify.com/store/shop1/labels/1001.pdf")
    assert not is_candidate("https://admin.shopify.com/store/shop1/orders/1234567890")
    assert not is_candidate("https://www.etsy.com/your/orders/sold")
    for u in ("", "about:blank", "chrome://newtab/", "chrome-extension://abc/index.html"):
        assert not is_candidate(u)

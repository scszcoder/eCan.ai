"""A store browser that restored a tiny window is enlarged before the agents use it.

The ushooa profile came back at 532x242; Shopify's page header covered the first order
row and the label step could not open an open order (2026-11-22).
"""
from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_browser import MIN_WINDOW, fix_window_size


def _cdp(bounds):
    calls = []

    def send(method, **params):
        calls.append((method, params))
        if method == "Browser.getWindowForTarget":
            return {"windowId": 7, "bounds": dict(bounds)}
        return {}
    return send, calls


def test_a_small_minimized_window_is_enlarged_and_stays_minimized():
    send, calls = _cdp({"width": 532, "height": 242, "windowState": "minimized"})
    assert fix_window_size(send, "T1")
    sets = [p["bounds"] for m, p in calls if m == "Browser.setWindowBounds"]
    assert sets == [{"windowState": "normal"}, {"width": MIN_WINDOW[0], "height": MIN_WINDOW[1]},
                    {"windowState": "minimized"}]


def test_a_big_enough_window_is_left_alone():
    send, calls = _cdp({"width": 1536, "height": 900, "windowState": "normal"})
    assert not fix_window_size(send, "T1")
    assert [m for m, _ in calls] == ["Browser.getWindowForTarget"]


def test_only_the_short_side_grows():
    send, calls = _cdp({"width": 1600, "height": 600, "windowState": "normal"})
    assert fix_window_size(send, "T1")
    assert calls[-1][1]["bounds"] == {"width": 1600, "height": MIN_WINDOW[1]}

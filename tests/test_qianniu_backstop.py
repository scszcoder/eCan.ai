"""千牛 backstop + notice product (yp alpha 2026-10-09).

大作战panda's 「这个质量怎么样」 never appeared in 千牛's memory and was never
answered (the cold sweep runs only at startup); xuboz71's question went out with
product=None because the 「当前用户来自 商品详情页」 notice carrying the product was
skipped whole.
"""
import contextlib

import agent.mcp.server.qianniu.qianniu_tools as qt
from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import observer as ob


def test_our_send_preview_matches_truncated_list_preview():
    ob.record_sent("麻烦发下商品链接或商品卡片，我帮您查现货。")
    assert ob._is_our_send_preview("麻烦发下商品链接…")
    assert ob._is_our_send_preview("麻烦发下商品链接..")
    assert not ob._is_our_send_preview("这个质量怎么样")
    assert not ob._is_our_send_preview("麻烦")          # too short to trust


class _Lock:
    def try_acquire(self, holder): return True
    def release(self, holder): pass
    def holder(self): return None


def _fake_screen(monkeypatch, rows, last):
    monkeypatch.setattr(qt, "_lock", lambda: _Lock())
    monkeypatch.setattr(qt, "_no_corner_failsafe", contextlib.nullcontext)
    monkeypatch.setattr(qt, "_foreground", lambda: True)
    monkeypatch.setattr(qt, "_read_qianniu", lambda: [])
    monkeypatch.setattr(qt, "_ensure_reception_tab", lambda d: (True, d))
    monkeypatch.setattr(qt, "_store_label", lambda: "倪好数码:小柒")
    monkeypatch.setattr(qt, "_humanize", lambda *a: None)
    opened, open_chat = [], [None]
    by_pt = {pt: name for name, _p, pt in rows}

    def click(x, y):
        opened.append((x, y))
        if open_chat[0] != "stuck":                 # "stuck": a click does not switch chats
            open_chat[0] = by_pt.get((x, y), open_chat[0])

    monkeypatch.setattr(qt, "_click", click)
    monkeypatch.setattr(qt, "conversation_rows", lambda d, limit=8: rows)
    monkeypatch.setattr(qt, "last_turn", lambda d, name, store: last[name])
    monkeypatch.setattr(qt, "verify_header_name", lambda name, d=None, quiet=False: type(
        "V", (), {"matched": open_chat[0] == name, "header_text": str(open_chat[0])})())
    monkeypatch.setattr(qt, "find_conversation_row_by_name",
                        lambda d, name: next(((pt, n) for n, _p, pt in rows if n == name), (None, "")))
    _fake_screen.open_chat = open_chat
    return opened


def test_backstop_answers_a_missed_buyer_message_and_skips_our_own(monkeypatch):
    rows = [("大作战panda", "这个质量怎么样", (10, 10)), ("xuboz71", "麻烦发下商品链接…", (10, 40))]
    opened = _fake_screen(monkeypatch, rows, {"大作战panda": ("buyer", "这个质量怎么样")})
    sent = {"麻烦发下商品链接或商品卡片"}
    dispatched, checked = [], set()
    stats = qt.backstop_sweep(lambda n, t: dispatched.append((n, t)), lambda n, t: False,
                              lambda p: any(s.startswith(p.rstrip("…")) for s in sent), checked)
    assert dispatched == [("大作战panda", "这个质量怎么样")]
    assert opened == [(10, 10)]                     # our own reply's row is never opened
    # Next pass: same rows, nothing re-opened.
    stats2 = qt.backstop_sweep(lambda n, t: dispatched.append((n, t)), lambda n, t: (n, t) in dispatched,
                               lambda p: False, checked)
    assert stats2["opened"] == 0 and len(dispatched) == 1


def test_ai_summary_toggle_is_not_a_buyer_name():
    from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import name_map
    assert not name_map.looks_like_buyer_name("展开")
    assert name_map.looks_like_buyer_name("xuboz71")
    assert name_map.looks_like_buyer_name("大作战panda")


def test_a_row_is_never_judged_on_another_buyers_chat(monkeypatch):
    """alpha 2026-10-21 15:00: the click left 大作战panda's chat open; tb398427493806's
    unanswered 「穿久了会不会掉色褪色」 was judged by panda's last turn (store) and
    left waiting under 待回复."""
    rows = [("tb398427493806", "穿久了会不会掉...", (10, 10)), ("大作战panda", "这边帮您核实一...", (10, 40))]
    opened = _fake_screen(monkeypatch, rows, {"tb398427493806": ("store", "这边帮您核实一下运费险情况"),
                                              "大作战panda": ("store", "这边帮您核实一下运费险情况")})
    _fake_screen.open_chat[0] = "stuck"
    dispatched, checked = [], set()
    stats = qt.backstop_sweep(lambda n, t: dispatched.append((n, t)), lambda n, t: False,
                              lambda p: p.startswith("这边帮您核实"), checked)
    assert dispatched == [] and stats["skipped"] == 1
    assert opened == [(10, 10), (10, 10)]                 # clicked, re-found and clicked once more
    assert ("tb398427493806", "穿久了会不会掉...") not in checked   # looked at again next pass

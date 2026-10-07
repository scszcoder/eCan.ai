"""千牛 observer + OCR diagnostics: the counters and one-time logs the alpha
logs are read with, and the cold-start baseline (memory holds chat HISTORY; the
first scan must not answer every old buyer message)."""
import json
import os
import time
from types import SimpleNamespace
from unittest.mock import patch

from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import mem_locator, observer
from agent.mcp.server.qianniu import qianniu_ocr
from utils import win_process_memory as mem


def _cand(uid, text, msg_id, send_time=None, outgoing=False):
    return mem_locator.MsgCandidate(uid=uid, sender_ids={uid}, text=text, msg_id=msg_id,
                                    send_time=send_time, has_ccode=outgoing)


def _observer_with_memory(snapshots):
    """An observer whose successive scans of pid 1 see the given candidate lists."""
    sent = []
    obs = observer.QianniuMemObserver(dispatch_fn=lambda item: sent.append(item) or 1)
    seq = iter(snapshots)

    def fake_scan_strings(pid, predicate, stats=None):
        if stats is not None:
            stats.update(regions=3, bytes=100, slices_matched=1)
        yield b"slice"

    def fake_extract(data, stats=None):
        return list(next(seq))

    return obs, sent, fake_scan_strings, fake_extract


def test_first_scan_is_a_baseline_and_only_new_buyer_messages_are_dispatched():
    history = [_cand("b1", "旧消息一", "m1"), _cand("b2", "旧消息二", "m2"),
               _cand("shop", "卖家回复", "m3", outgoing=True)]
    new = history + [_cand("b1", "这个有XL吗", "m4")]
    obs, sent, fake_scan, fake_extract = _observer_with_memory([history, new, new])
    with patch.object(mem, "scan_strings", fake_scan), \
            patch.object(mem_locator, "extract_candidates", fake_extract), \
            patch.object(observer.name_map, "name_for", return_value="小明"):
        assert obs._scan_once(1) is True
        assert sent == [] and obs.stats["baseline_seen"] == 2          # history: seen, not answered
        obs._scan_once(1)
        obs._scan_once(1)                                               # rescan: no duplicate
    assert [i["last_message"] for i in sent] == ["这个有XL吗"]
    assert obs.stats["new_incoming"] == 1 and obs.stats["dispatched"] == 1
    assert obs.last_scan["incoming_in_memory"] == 3 and obs.last_scan["outgoing_in_memory"] == 1


def test_an_empty_start_is_the_baseline_so_the_first_new_message_is_answered():
    # Alpha 2026-10-07 (0.9.99ya): memory held no buyer message at start; the
    # buyer's test message 有花生味牙线吗 appeared 12 min later and was swallowed
    # as "baseline". The first successful pass is the baseline, even when empty.
    obs, sent, fake_scan, fake_extract = _observer_with_memory(
        [[], [_cand("678614304", "有花生味牙线吗", "m1")]])
    with patch("psutil.process_iter", return_value=[SimpleNamespace(
                info={"pid": 17080, "ppid": 1, "name": "AliWorkbench.exe"})]), \
            patch.object(mem, "scan_strings", fake_scan), \
            patch.object(mem_locator, "extract_candidates", fake_extract), \
            patch.object(observer.name_map, "name_for", return_value=""):
        obs._scan_pass()
        assert obs._baselined and sent == []
        obs._scan_pass()
    assert [i["last_message"] for i in sent] == ["有花生味牙线吗"]
    assert obs.stats["baseline_seen"] == 0


def test_a_message_sent_after_start_is_answered_even_on_the_first_pass():
    now_ms = int(time.time() * 1000)
    obs, sent, fake_scan, fake_extract = _observer_with_memory(
        [[_cand("b1", "旧", "m1", send_time=now_ms - 3600_000), _cand("b2", "刚发的", "m2", send_time=now_ms)]])
    with patch.object(mem, "scan_strings", fake_scan), \
            patch.object(mem_locator, "extract_candidates", fake_extract), \
            patch.object(observer.name_map, "name_for", return_value=""):
        obs._scan_once(1)
    assert [i["last_message"] for i in sent] == ["刚发的"] and obs.stats["baseline_seen"] == 1


def test_a_start_with_qianniu_closed_is_not_the_baseline():
    obs = observer.QianniuMemObserver(dispatch_fn=lambda item: 0)
    with patch("psutil.process_iter", return_value=[]):
        obs._scan_pass()
    assert not obs._baselined   # 千牛 opened later: its history must still be baselined


def test_history_that_loads_later_is_skipped_as_stale():
    old_ms = int(time.time() * 1000) - 3600_000
    obs, sent, fake_scan, fake_extract = _observer_with_memory(
        [[_cand("b1", "x", "m1")], [_cand("b9", "一小时前", "m9", send_time=old_ms)]])
    with patch.object(mem, "scan_strings", fake_scan), \
            patch.object(mem_locator, "extract_candidates", fake_extract):
        obs._scan_once(1)
        obs._scan_once(1)
    assert sent == [] and obs.stats["stale_skipped"] == 1


def test_one_buyer_alone_in_memory_is_not_mistaken_for_the_seller():
    only_buyer = [_cand("b1", "在吗", "m1"), _cand("b1", "这个有XL吗", "m2")]
    assert mem_locator.seller_id_of(only_buyer) is None
    assert all(mem_locator.is_incoming(c, mem_locator.seller_id_of(only_buyer)) for c in only_buyer)
    with_reply = only_buyer + [_cand("shop", "在的", "m3", outgoing=True)]
    assert mem_locator.seller_id_of(with_reply) == "shop"


def test_a_qianniu_system_notice_is_never_dispatched():
    # Alpha 2026-10-07: this notice arrived as an incoming message object and was
    # dispatched to the front desk as if a buyer had asked it.
    notice = "【即将超时】您即将超超20分钟未回复买家，请您尽快妥善处理买家问题。若消极接待行为属实"
    obs, sent, fake_scan, fake_extract = _observer_with_memory(
        [[], [_cand("678614304", notice, "m1"), _cand("678614304", "有石榴味牙线吗", "m2")]])
    with patch.object(mem, "scan_strings", fake_scan), \
            patch.object(mem_locator, "extract_candidates", fake_extract), \
            patch.object(observer.name_map, "name_for", return_value=""):
        obs._scan_once(1)
        obs._baselined = True
        obs._scan_once(1)
    assert [i["last_message"] for i in sent] == ["有石榴味牙线吗"]
    assert obs.stats["system_notice_skipped"] == 1


def test_a_banner_is_never_learned_or_used_as_a_buyer_name(tmp_path):
    # Alpha 2026-10-07: "智能客服全新升级，助力客服高效接待！" (a promo in the
    # 接待中心 header band) was learned and saved as buyer 678614304's name.
    from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import name_map
    banner = "智能客服全新升级，助力客服高效接待！"
    assert not name_map.looks_like_buyer_name(banner)
    assert name_map.looks_like_buyer_name("sctisz") and name_map.looks_like_buyer_name("大作战panda")
    store = tmp_path / "names.json"
    store.write_text(json.dumps({"678614304": banner}, ensure_ascii=False), encoding="utf-8")
    with patch.object(name_map, "_store_path", return_value=str(store)), \
            patch.object(name_map, "_CACHE", None):
        assert name_map.name_for("678614304") == ""          # the saved bad entry is ignored
        assert name_map.learn("678614304", banner) is False
        assert name_map.learn("678614304", "sctisz") is True
        assert name_map.name_for("678614304") == "sctisz"
    rows = [{"text": banner, "loc": [100, 600, 120, 900]}, {"text": "sctisz", "loc": [120, 600, 140, 700]},
            {"text": "千牛", "loc": [0, 0, 10, 10]}, {"text": "发送", "loc": [790, 990, 800, 1000]}]
    assert qianniu_ocr.read_header_name(rows) == "sctisz"


def test_our_own_sent_reply_is_never_dispatched_and_names_the_store(tmp_path):
    # Alpha 2026-10-07 (0.9.99yf): our reply "这边帮您核实一下，稍后回复您。" came
    # back in memory from uid 2223147939796 with no outgoing marker, was
    # dispatched as a buyer message, answered and sent again (self-echo loop).
    from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import name_map
    reply = "这边帮您核实一下，稍后回复您。"
    store = tmp_path / "names.json"
    obs, sent, fake_scan, fake_extract = _observer_with_memory([
        [],
        [_cand("2223147939796", reply, "m9"), _cand("2223147939796", reply, "")],
        [_cand("2223147939796", "嗯嗯人工补充", "m10"), _cand("678614304", "有蓝色牙线吗？", "m11")],
    ])
    with patch.object(mem, "scan_strings", fake_scan), \
            patch.object(mem_locator, "extract_candidates", fake_extract), \
            patch.object(name_map, "_store_path", return_value=str(store)), \
            patch.object(name_map, "_CACHE", None):
        obs._scan_once(1)
        obs._baselined = True
        observer.record_sent(reply)
        obs._scan_once(1)
        assert sent == [] and name_map.store_self_id() == "2223147939796"
        obs._scan_once(1)      # the store's own (human-typed) message stays outgoing too
    assert [i["last_message"] for i in sent] == ["有蓝色牙线吗？"]


def test_a_dispatch_nobody_receives_is_counted():
    obs, _sent, fake_scan, fake_extract = _observer_with_memory(
        [[_cand("b1", "x", "m1")], [_cand("b1", "x", "m1"), _cand("b1", "新问题", "m2")]])
    obs._dispatch = lambda item: 0
    with patch.object(mem, "scan_strings", fake_scan), \
            patch.object(mem_locator, "extract_candidates", fake_extract), \
            patch.object(observer.name_map, "name_for", return_value="小明"):
        obs._scan_once(1)
        obs._scan_once(1)
    assert obs.stats["dispatched_to_nobody"] == 1


def test_an_unreadable_process_is_logged_once_not_every_poll():
    obs = observer.QianniuMemObserver(dispatch_fn=lambda item: 0)

    def denied(pid, predicate, stats=None):
        raise OSError("OpenProcess(7) failed (winerror 5)")
        yield  # pragma: no cover

    with patch.object(mem, "scan_strings", denied), \
            patch.object(observer.logger, "warning") as warn:
        for _ in range(5):
            assert obs._scan_once(7) is False
    assert warn.call_count == 1 and obs.stats["scan_errors"] == 5


def test_scan_strings_reports_what_it_read():
    regions = [mem.MemoryRegion(base=0, size=10, protect=4), mem.MemoryRegion(base=100, size=10, protect=4)]
    chunks = {0: b'.."sender"..', 100: b""}
    stats = {}
    with patch.object(mem, "available", return_value=True), \
            patch.object(mem, "open_process_readonly", return_value=1), \
            patch.object(mem, "close_handle"), \
            patch.object(mem, "iter_regions", return_value=iter(regions)), \
            patch.object(mem, "_read_chunk", side_effect=lambda h, base, off, n: chunks[base]):
        out = list(mem.scan_strings(5, mem_locator.region_has_messages, stats=stats))
    assert len(out) == 1
    assert stats["regions"] == 2 and stats["chunks"] == 2 and stats["chunk_read_failures"] == 1
    assert stats["slices_matched"] == 1 and stats["bytes"] == len(chunks[0]) and stats["capped"] is False


def test_extract_candidates_counts_why_objects_were_dropped():
    good = {"sender": {"targetId": "b1"}, "content": "这个有XL吗"}
    no_text = {"sender": {"targetId": "b2"}, "x9f3": "https://img.alicdn.com/a.png"}
    data = (json.dumps(good, ensure_ascii=False) + "   " + json.dumps(no_text)).encode("utf-8")
    stats = {}
    out = mem_locator.extract_candidates(data, stats=stats)
    assert [c.text for c in out] == ["这个有XL吗"]
    assert stats["kept"] == 1 and stats["no_text"] == 1
    assert stats["sample_no_text_keys"] == ["sender", "x9f3"]


def test_cards_and_memory_changes_are_logged_once():
    # 0.9.99yb alpha: 6 objects were dropped as cards and the log could not say
    # whether a new buyer message hid among them. Each card is now described once,
    # and a scan whose counts differ from the last one says so.
    card = {"sender": {"targetId": "sys"}, "layoutJson": "{}", "msgType": 101,
            "templateId": 9, "summary": "[卡片]物流通知", "code": {"messageId": "c1"}}
    one = json.dumps(card, ensure_ascii=False).encode("utf-8")
    two = one + b"   " + json.dumps({**card, "code": {"messageId": "c2"}, "summary": "新卡片"},
                                     ensure_ascii=False).encode("utf-8")
    slices = iter([one, one, two])
    obs = observer.QianniuMemObserver(dispatch_fn=lambda item: 0)

    def fake_scan(pid, predicate, stats=None):
        yield next(slices)

    with patch.object(mem, "scan_strings", fake_scan), patch.object(observer.logger, "info") as info:
        for _ in range(3):
            obs._scan_once(1)
    lines = [c.args[0] for c in info.call_args_list]
    assert sum("card in memory" in l for l in lines) == 2              # c1 once, then c2
    assert any("summary='新卡片'" in l for l in lines)
    assert sum("memory changed in pid 1" in l for l in lines) == 1      # only the 3rd scan changed


def test_ocr_dump_lists_lines_top_to_bottom_with_positions():
    data = [{"text": "发送", "loc": [500, 900, 520, 940]}, {"text": "小明同学", "loc": [100, 400, 120, 480]}]
    assert qianniu_ocr.ocr_dump(data) == "2 lines: 小明同学@(440,110) | 发送@(920,510)"


def test_failure_screenshots_keep_only_the_newest(tmp_path):
    shot = tmp_path / "tmp.png"
    shot.write_bytes(b"png")
    with patch.object(qianniu_ocr, "_TMP_SHOT", str(shot)), \
            patch.object(qianniu_ocr, "_SHOTS_KEEP", 2), \
            patch("config.app_info.app_info", SimpleNamespace(appdata_path=str(tmp_path))):
        folder = tmp_path / "runlogs" / "qianniu_ocr"
        folder.mkdir(parents=True)
        for name in ("20260101_000001_a.png", "20260101_000002_b.png"):
            (folder / name).write_bytes(b"old")
        path = qianniu_ocr.save_failure_shot("check none")
    assert os.path.basename(path).endswith("_check_none.png")
    assert sorted(os.listdir(folder)) == ["20260101_000002_b.png", os.path.basename(path)]

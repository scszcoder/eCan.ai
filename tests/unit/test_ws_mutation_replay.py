"""Does the WS schema watcher catch a protocol change? Measured on real frames.

The DOM half got a stress harness (`test_detector_stress.py`). This is the
other half, and it needs no WS server: `ws_protocol_watch.observe` takes a
decoded kv-map, so real maps can be lifted out of a capture, mutated, and
replayed. That gives labelled positives from production field distributions
rather than from what we imagine the protocol looks like.

Two tiers:

* **Synthetic** — always runs, covers the classes of change.
* **Real capture** — skipped where the capture is absent (it is git-ignored),
  and it is the tier that has already corrected the code twice: it found a key
  declared core that appears twice in 244 messages, and a cap this protocol
  saturates.
"""

import base64
import json
import pathlib

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    ws_protocol_watch as wpw,
    ws_reader as wr,
)

CAPTURE = (pathlib.Path(__file__).resolve().parents[2]
           / "customer_logs" / "eCan_feigecap.jsonl")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    wpw.reset()
    yield
    wpw.reset()
    dj.reset_incident_window()


# A map with the field distribution the real capture shows.
REALISTIC = {
    "type": "text",
    "sender_role": "1",
    "talk_id": "t-1",
    "pigeon_cid": "c-1",
    "nickname": "x",
    "s:client_message_id": "m-1",
    "s:need_bcp": "1",
    "s:msg_priority": "0",
    "displayType": "1",
    "shop_id": "9",
}


def _feed(maps, n=wpw._WINDOW_FRAMES):
    """Feed exactly one window."""
    for i in range(n):
        wpw.observe(dict(maps[i % len(maps)]))


def _replay_detects(before_maps, after_maps):
    """Baseline one window, then a second. True if a change was journalled."""
    wpw.reset()
    dj.forget_shape(wpw._SITE_LABEL, "ws_message_fields")
    dj.reset_incident_window()
    _feed(before_maps)                      # first window = baseline
    assert dj.read_events() == [], "baseline must not report"
    dj.reset_incident_window()
    _feed(after_maps)
    events = dj.read_events()
    return bool(events), (events[0]["evidence"]["changed"] if events else {})


# ── mutations ──────────────────────────────────────────────────────────────

def drop_core(kv):
    out = dict(kv)
    out.pop("nickname", None)
    return out


def rename_core(kv):
    out = dict(kv)
    out.pop("nickname", None)
    out["user_display_name"] = "x"
    return out


def empty_core(kv):
    return {**kv, "nickname": ""}


def drop_optional(kv):
    out = dict(kv)
    out.pop("goods_id", None)
    return out


def add_new_key(kv):
    return {**kv, "s:brand_new_field": "1"}


def reorder(kv):
    return dict(reversed(list(kv.items())))


def test_a_core_field_disappearing_is_caught():
    """The ws193 shape: frames still flow, the name is gone."""
    fired, changed = _replay_detects([REALISTIC], [drop_core(REALISTIC)])
    assert fired
    assert "nickname" in changed["core_populated"]["lost"]


def test_a_core_field_emptied_rather_than_removed_is_caught():
    """Harder to spot by eye, identical in effect."""
    fired, changed = _replay_detects([REALISTIC], [empty_core(REALISTIC)])
    assert fired
    assert "nickname" in changed["core_populated"]["lost"]


def test_a_rename_is_caught_as_a_loss_and_a_gain():
    fired, changed = _replay_detects([REALISTIC], [rename_core(REALISTIC)])
    assert fired
    assert "nickname" in changed["core_populated"]["lost"]
    assert "user_display_name" in changed["unexpected_ever_seen"]["gained"]


def test_a_brand_new_field_is_caught():
    fired, changed = _replay_detects([REALISTIC], [add_new_key(REALISTIC)])
    assert fired
    assert "s:brand_new_field" in changed["unexpected_ever_seen"]["gained"]


def test_identical_traffic_is_never_a_change():
    """The false-positive floor."""
    fired, _ = _replay_detects([REALISTIC], [REALISTIC])
    assert not fired


def test_key_order_is_not_a_change():
    fired, _ = _replay_detects([REALISTIC], [reorder(REALISTIC)])
    assert not fired


def test_an_optional_field_going_quiet_is_deliberately_not_caught():
    """A documented limit, not an oversight: `goods_id` rides product cards
    only, so its silence is indistinguishable from a quiet afternoon. The
    module says so rather than implying coverage."""
    with_card = {**REALISTIC, "goods_id": "g-1"}
    fired, _ = _replay_detects([with_card], [drop_optional(with_card)])
    assert not fired


def test_mixed_frame_types_do_not_flap():
    """A card frame and a text frame carry different keys; the window unions
    them. Judging per frame would alternate forever."""
    card = {"type": "template_card", "sender_role": "1", "talk_id": "t-1",
            "pigeon_cid": "c-1", "s:client_message_id": "m-2",
            "goods_id": "g-1", "generic_search_keywords": "{}"}
    fired, _ = _replay_detects([REALISTIC, card], [card, REALISTIC])
    assert not fired


# ── the real capture ───────────────────────────────────────────────────────

def _real_kv_maps(limit=400):
    """Lift decoded kv-maps out of the capture, the way extract_messages does."""
    maps = []
    with CAPTURE.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("k") != "ws" or rec.get("dir") != "recv":
                continue
            try:
                dec = wr.decode(base64.b64decode(rec["payload_b64"]))
            except Exception:
                continue
            if not dec:
                continue
            for f8 in wr._all(dec, 8):
                body = wr._sub(f8)
                if not body:
                    continue
                for f6 in wr._all(body, 6):
                    evt = wr._sub(f6)
                    if not evt:
                        continue
                    for (_fld, _wt, val) in evt:
                        struct = wr._sub(val)
                        if not struct:
                            continue
                        for m5 in wr._all(struct, 5):
                            msg = wr._sub(m5)
                            if msg:
                                maps.append(wr._kvmap(msg))
                                if len(maps) >= limit:
                                    return maps
    return maps


requires_capture = pytest.mark.skipif(
    not CAPTURE.exists(), reason="capture is git-ignored; dev box only")


@requires_capture
def test_every_declared_core_key_is_populated_in_real_traffic():
    """A key declared core but rarely populated would flap a false schema
    change every window. This already caught one: `security_sender_id` appears
    twice in 244 messages and is now optional."""
    maps = _real_kv_maps()
    assert maps, "capture yielded no kv-maps"
    populated = {k for kv in maps for k, v in kv.items() if v}
    missing = wpw.CORE_KEYS - populated
    assert not missing, (
        f"declared core but never populated in real traffic: {sorted(missing)} "
        f"-- these cannot serve as per-window detectors; move them to OPTIONAL")


@requires_capture
def test_real_traffic_alone_is_not_a_change():
    """Two windows of the same production traffic must be silent. If this fires,
    every run would write a phantom schema change."""
    maps = _real_kv_maps()
    fired, changed = _replay_detects(maps, maps)
    assert not fired, f"real traffic reported a phantom change: {changed}"


@requires_capture
def test_the_snapshot_is_independent_of_frame_order():
    """The `unexpected` set is monotonic and capped. When the cap was 40 this
    protocol saturated it, and WHICH keys survived depended on arrival order --
    so the set was not stable and would have reported phantom changes."""
    maps = _real_kv_maps()
    wpw.reset()
    _feed(maps)
    first = wpw.flush(force=True)

    wpw.reset()
    _feed(list(reversed(maps)))
    second = wpw.flush(force=True)

    assert first == second, "the snapshot depends on the order frames arrived in"


@requires_capture
def test_a_mutation_of_real_traffic_is_caught():
    """Labelled positive, on production field distributions."""
    maps = _real_kv_maps()
    fired, changed = _replay_detects(maps, [drop_core(kv) for kv in maps])
    assert fired
    assert "nickname" in changed["core_populated"]["lost"]


@requires_capture
def test_the_unexpected_cap_is_above_what_this_protocol_carries():
    """Saturation reintroduces order-dependence, so the cap must have headroom."""
    maps = _real_kv_maps()
    distinct = {k for kv in maps for k, v in kv.items()
                if v and k not in wpw.EXPECTED_KEYS}
    assert len(distinct) < wpw._MAX_UNEXPECTED, (
        f"{len(distinct)} undeclared keys vs a cap of {wpw._MAX_UNEXPECTED}")

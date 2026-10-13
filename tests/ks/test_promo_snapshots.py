"""Per-store current-promotions snapshots (knowledge/ks/promo_snapshots.py):
auto-applied, overwritten each refresh, and served to Q&A as a dated line."""
import time

import pytest

from knowledge.ks import promo_snapshots as ps


@pytest.fixture
def store(tmp_path):
    return ps.PromoSnapshots(str(tmp_path / "ks_data"))


def test_set_then_get_round_trip(store):
    store.set("shopA", promotions=[{"type": "满减", "detail": "满199减30"}],
              summary="满199减30；新人券立减10元", source="抖店营销中心")
    snap = store.get("shopA")
    assert snap["store_id"] == "shopA" and snap["source"] == "抖店营销中心"
    assert snap["summary"] == "满199减30；新人券立减10元"
    assert snap["promotions"] == [{"type": "满减", "detail": "满199减30"}]
    assert snap["captured_at"] > 0


def test_get_missing_store_is_none(store):
    assert store.get("nope") is None


def test_set_overwrites_so_the_latest_cycle_wins(store):
    store.set("shopA", summary="旧活动")
    store.set("shopA", summary="新活动")
    assert store.get("shopA")["summary"] == "新活动"


def test_line_is_dated_and_prefixed(store, monkeypatch):
    monkeypatch.setattr(ps.time, "time", lambda: time.mktime((2026, 10, 13, 9, 5, 0, 0, 0, -1)))
    store.set("shopA", summary="满199减30")
    assert store.line("shopA") == "[当前活动] 截至09:05：满199减30"


def test_line_empty_when_no_snapshot(store):
    assert store.line("nope") == ""


def test_line_empty_when_summary_blank(store):
    store.set("shopA", promotions=[], summary="")
    assert store.line("shopA") == ""


def test_no_activity_is_a_real_answerable_snapshot(store):
    store.set("shopA", promotions=[], summary="当前无活动")
    assert "当前无活动" in store.line("shopA")


def test_line_empty_when_too_old(store, monkeypatch):
    now = [10_000.0]
    monkeypatch.setattr(ps.time, "time", lambda: now[0])
    store.set("shopA", summary="满199减30")
    now[0] += 89 * 60                         # within the 90-min trust window
    assert store.line("shopA", stale_after_min=90) != ""
    now[0] += 2 * 60                          # now 91 min old
    assert store.line("shopA", stale_after_min=90) == ""


def test_store_id_with_slashes_is_filename_safe(store):
    store.set("shop/A:1", summary="x")        # must not escape the folder
    assert store.get("shop/A:1")["summary"] == "x"


def test_service_methods_round_trip(svc, tmp_path):
    svc.data_dir = str(tmp_path / "ks_data")
    svc.set_promos("shopA", promotions=[{"type": "券"}], summary="新人券立减10元", source="抖店营销中心")
    assert svc.get_promos("shopA")["summary"] == "新人券立减10元"
    assert svc.promo_line("shopA").startswith("[当前活动]")

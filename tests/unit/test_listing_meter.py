"""Per-listing billing events (eCan_lambda PRODUCT_LISTING_BILLING_FOR_CLIENT.md)."""

from unittest import mock

from agent.ec_skills import listing_meter as lm
from utils.log_scope import scope


def _emitted(**scope_fields):
    calls = []
    with mock.patch("agent.ec_skills.metering.emit",
                    side_effect=lambda *a, **k: calls.append((a, k)) or True), scope(**scope_fields):
        out = lm.record_listing("douyin", "SHOP123", "PRODUCT456", ["SKU1", "SKU2", "SKU3"], created_at=2000.0)
    return out, calls


def test_a_new_product_is_one_main_and_one_event_per_further_sku():
    out, calls = _emitted(run_started_at=1990.0, skill_id="skill_x")
    assert out["recorded"] == 3
    assert [(a[0], a[1]) for a, _ in calls] == [
        ("product_listing", "main_sku_listed"), ("product_listing", "variant_sku_added"),
        ("product_listing", "variant_sku_added")]
    assert [k["idempotency_key"] for _, k in calls] == [
        "listing:douyin:SHOP123:PRODUCT456", "listing_sku:douyin:SHOP123:SKU2", "listing_sku:douyin:SHOP123:SKU3"]
    assert calls[0][1]["evidence"]["base_sku_id"] == "SKU1"
    assert calls[1][1]["evidence"] == {"platform": "douyin", "shop_id": "SHOP123",
                                       "product_id": "PRODUCT456", "sku_id": "SKU2"}


def test_a_single_sku_product_is_one_event():
    assert [e["meter_code"] for e in lm.listing_events("pdd", "M1", "G1", ["S1"])] == ["main_sku_listed"]


def test_a_retry_repeats_the_same_keys():
    a = lm.listing_events("pdd", "M1", "G1", ["S1", "S2"])
    b = lm.listing_events("pdd", "M1", "G1", ["S1", "S2"])
    assert [e["idempotency_key"] for e in a] == [e["idempotency_key"] for e in b]


def test_a_test_run_records_nothing():
    out, calls = _emitted(run_started_at=1990.0, billing_test=True)
    assert calls == [] and out["test"] and out["would_charge"] == 3


def test_a_product_older_than_the_run_is_not_new():
    out, calls = _emitted(run_started_at=2000.0 + lm.CLOCK_SLACK_S + 60)
    assert calls == [] and "before this run" in out["skipped"]


def test_no_platform_ids_no_events():
    assert lm.listing_events("douyin", "", "P", ["S1"]) == []
    assert lm.listing_events("douyin", "S", "P", []) == []
    with mock.patch("agent.ec_skills.metering.emit") as emit:
        assert lm.record_listing("douyin", "S", "", ["S1"])["recorded"] == 0
    emit.assert_not_called()

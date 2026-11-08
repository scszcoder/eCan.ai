"""The 抖店 / 拼多多 confirm actions record only what the platform answered."""

import asyncio
import importlib
import json
from unittest import mock

import pytest

BUNDLES = "agent.ec_skills.browser_use_extension.hooks.external."


def _act(bundle, action, page_answer, product_id="3851334381767622817"):
    mod = importlib.import_module(BUNDLES + bundle + ".site_tools")
    fn = getattr(mod, action)
    fn = getattr(fn, "__wrapped__", fn)
    model = mod.ConfirmListingAction(product_id=product_id)
    with mock.patch.object(mod, "_run", new=mock.AsyncMock(return_value=json.dumps(page_answer))), \
            mock.patch("agent.ec_skills.listing_meter.record_listing",
                       return_value={"recorded": 2, "test": False}) as rec:
        res = asyncio.run(fn(model, browser_session=None))
    return res, rec


def test_both_actions_are_registered():
    from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
    importlib.import_module(BUNDLES + "douyin_listing")
    importlib.import_module(BUNDLES + "pdd_listing")
    names = set(custom_controller.registry.registry.actions)
    assert {"douyin_confirm_listing", "pdd_confirm_listing"} <= names


def test_both_bundles_declare_the_listing_meters():
    from agent.ec_skills.meter_registry import declared_meters
    meters = declared_meters(refresh=True)
    assert ("product_listing", "main_sku_listed") in meters
    assert ("product_listing", "variant_sku_added") in meters


@pytest.mark.parametrize("bundle,action", [("douyin_listing", "douyin_confirm_listing"),
                                           ("pdd_listing", "pdd_confirm_listing")])
def test_a_published_product_is_recorded_with_the_platform_ids(bundle, action):
    res, rec = _act(bundle, action, {"found": True, "published": True, "product_id": "P1", "shop_id": "S1",
                                     "sku_ids": ["K1", "K2"], "created_at": 1793419216})
    assert json.loads(res.extracted_content)["confirmed"] is True
    args = rec.call_args.args
    assert args[1:] == ("S1", "P1", ["K1", "K2"])


@pytest.mark.parametrize("bundle,action", [("douyin_listing", "douyin_confirm_listing"),
                                           ("pdd_listing", "pdd_confirm_listing")])
@pytest.mark.parametrize("answer", [{"found": False}, {"found": True, "published": False, "product_id": "P1"}])
def test_a_draft_or_missing_product_records_nothing(bundle, action, answer):
    res, rec = _act(bundle, action, answer)
    assert json.loads(res.extracted_content)["confirmed"] is False
    rec.assert_not_called()

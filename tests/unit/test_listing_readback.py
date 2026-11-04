"""Reading a listed product back from the platform (agent/ec_skills/listing_readback)."""
import asyncio

from agent.ec_skills import listing_readback as R


def test_unknown_platforms_and_missing_ids_are_reported_not_guessed():
    assert "no read-back" in asyncio.run(R.readback("taobao", "s", product_id="1"))["error"]
    assert "goods id" in asyncio.run(R.readback("pdd", "s", product_id=""))["error"]


def test_no_store_browser_is_an_answer_not_a_crash(monkeypatch):
    from agent.ec_skills.explorer import page
    monkeypatch.setattr(page, "browser_port", lambda *a, **k: 0)
    out = R.readback_sync("douyin", "douyin-x", product_id="3851450341539316685")
    assert out["found"] is False and "no running browser" in out["error"]


def test_the_scripts_take_their_arguments_as_json():
    assert R._DOUYIN_JS.count("%s") == 3 and R._PDD_JS.count("%s") == 1

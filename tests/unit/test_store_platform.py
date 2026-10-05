"""A store's platform is stored as its key. The Stores form's free-text entry
saved the Chinese name ("天猫"), and Fast Deploy 天猫客服 refused the store:
"店铺 tmall-小店四号 属于 天猫 平台，不是 tmall" (customer, 2026-10-05)."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import cli.deploy.commands as dc
from agent.ec_agents.store_catalog import _PLATFORMS, normalize_platform


@pytest.mark.parametrize("text,key", [
    ("天猫", "tmall"), ("tmall", "tmall"), ("T-Mall", "tmall"), (" TMALL ", "tmall"),
    ("抖店", "douyin"), ("拼多多", "pinduoduo"), ("我的平台", "我的平台"), ("", ""),
])
def test_names_map_to_the_key(text, key):
    assert normalize_platform(text) == key


def _ctx(platform):
    svc = SimpleNamespace(get_store=lambda sid: {"store_id": sid, "platform": platform})
    return SimpleNamespace(db=SimpleNamespace(store_service=svc))


def test_a_store_saved_as_tianmao_deploys_as_tmall():
    assert dc._store_record(_ctx("天猫"), "tmall-小店四号", "tmall")["store_id"] == "tmall-小店四号"


def test_a_real_platform_mismatch_is_still_refused():
    with pytest.raises(RuntimeError):
        dc._store_record(_ctx("抖店"), "tmall-小店四号", "tmall")


def test_backend_list_matches_the_frontend_platforms():
    src = Path(__file__).resolve().parents[2] / "gui_v2/src/components/FastDeploy/scenarios.tsx"
    block = src.read_text(encoding="utf-8").split("export const PLATFORMS", 1)[1].split("];", 1)[0]
    fe = re.findall(r"\{\s*value:\s*'([^']*)',\s*nameEn:\s*'([^']*)',\s*nameZh:\s*'([^']*)'\s*\}", block)
    assert fe and [tuple(x) for x in fe] == [tuple(x) for x in _PLATFORMS]

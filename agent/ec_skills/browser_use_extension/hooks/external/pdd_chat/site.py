"""Where Pinduoduo's merchant chat lives, for the site probe.

Deliberately broad until the first capture says which hosts and paths carry
the chat: every page of the merchant backend (mms) is attached, and every API
call on a pinduoduo/yangkeduo host is recorded (static assets excluded). Narrow
these once the capture shows the real endpoints -- env overrides let an
operator do that without a release.
"""

import os

from agent.ec_skills.browser_use_extension.site_probe import ProbePreset


def _env_list(name: str, default: list) -> list:
    raw = os.environ.get(name, "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


PROBE_PRESET = ProbePreset(
    name="pdd_chat",
    # 商家后台 (mms), incl. the chat workbench (chat-merchant).
    page_markers=_env_list("ECAN_PDD_PAGE_MARKERS", ["mms.pinduoduo.com"]),
    api_markers=_env_list("ECAN_PDD_API_MARKERS", ["pinduoduo.com", "yangkeduo.com"]),
)

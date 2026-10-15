"""CONFIG vault for store browser profiles: off by default; ships ONLY the descriptor."""

import json
import os
from unittest import mock

from agent.ec_agents import profile_vault


_SENSITIVE_PROFILE = {
    "id": "douyin-dB-login", "label": "店B", "store_id": "douyin-店B",
    "machine_id": "m1", "domain_name": "im.jinritemai.com",
    "fingerprint_profile": "win_chrome_01", "locale": "zh-CN",
    # The parts that must NEVER leave the machine:
    "user_data_dir": r"C:\ecan_browser_data\douyin-dB_salt",
    "install_salt": "salt",
    "proxy": {"host": "p.example", "port": 1080, "username": "u", "password_ref": "ref"},
}


def _off_env():
    return {k: v for k, v in os.environ.items() if k != "ECAN_PROFILE_VAULT"}


def test_disabled_by_default_pull_is_noop():
    with mock.patch.dict(os.environ, _off_env(), clear=True), \
         mock.patch.object(profile_vault, "_get_cloud_context") as ctx:
        assert profile_vault.pull_descriptor("douyin-店B") is None
        ctx.assert_not_called()  # no cloud context fetched, no network


def test_disabled_by_default_push_is_noop():
    with mock.patch.dict(os.environ, _off_env(), clear=True), \
         mock.patch.object(profile_vault, "_get_cloud_context") as ctx:
        profile_vault.push_descriptor(_SENSITIVE_PROFILE)
        ctx.assert_not_called()


def test_push_uploads_only_the_descriptor_no_secrets():
    captured = {}

    def _fake_put(url, data=None, headers=None, timeout=None):
        captured["body"] = data
        return mock.Mock(status_code=200)

    with mock.patch.dict(os.environ, {"ECAN_PROFILE_VAULT": "1"}), \
         mock.patch.object(profile_vault, "_get_cloud_context",
                           return_value={"session": object(), "token": "t", "endpoint": "e", "owner": "o"}), \
         mock.patch.object(profile_vault, "_request_upload_url",
                           return_value={"uploadUrl": "https://presigned", "s3Key": "k", "expiresIn": 60}), \
         mock.patch.object(profile_vault.http_requests, "put", side_effect=_fake_put):
        profile_vault.push_descriptor(_SENSITIVE_PROFILE)
        # push runs on a daemon thread — join it
        for t in __import__("threading").enumerate():
            if t.name == "profile-vault-push":
                t.join(timeout=5)

    assert "body" in captured, "nothing was uploaded"
    payload = captured["body"].decode("utf-8")
    sent = json.loads(payload)
    # The safe fields are present…
    assert sent["store_id"] == "douyin-店B"
    assert sent["fingerprint_profile"] == "win_chrome_01"
    assert sent["has_proxy"] is True
    # …and NOTHING sensitive ever leaves.
    assert "user_data_dir" not in payload
    assert "install_salt" not in payload
    assert "password_ref" not in payload
    assert "p.example" not in payload  # proxy host
    assert "1080" not in payload       # proxy port


def test_pull_returns_descriptor_when_present():
    desc = {"store_id": "douyin-店B", "fingerprint_profile": "win_chrome_02", "locale": "zh-CN"}
    with mock.patch.dict(os.environ, {"ECAN_PROFILE_VAULT": "1"}), \
         mock.patch.object(profile_vault, "_get_cloud_context",
                           return_value={"session": object(), "token": "t", "endpoint": "e", "owner": "o"}), \
         mock.patch.object(profile_vault, "_request_download_url",
                           return_value={"downloadUrl": "https://presigned", "s3Key": "k", "expiresIn": 60}), \
         mock.patch.object(profile_vault.http_requests, "get",
                           return_value=mock.Mock(status_code=200,
                                                  content=json.dumps(desc).encode("utf-8"))):
        got = profile_vault.pull_descriptor("douyin-店B")
    assert got == desc

"""The local server's DEBUG log printed login variables in clear text, password
included (2026-10-22)."""
from gui.LocalServer import _redact_secrets


def test_login_password_is_masked():
    v = {"email": "someone@example.com", "password": "hunter2!", "role": "Commander"}
    out = _redact_secrets(v)
    assert out == {"email": "someone@example.com", "password": "***", "role": "Commander"}
    assert v["password"] == "hunter2!"                      # the request itself is untouched


def test_nested_and_other_secret_keys_are_masked():
    v = {"input": {"newPassword": "a", "verification_code": "123456", "apiKey": "sk-1",
                   "items": [{"accessToken": "t", "name": "n"}]}}
    out = _redact_secrets(v)
    assert out["input"]["newPassword"] == "***" and out["input"]["verification_code"] == "***"
    assert out["input"]["apiKey"] == "***" and out["input"]["items"][0] == {"accessToken": "***", "name": "n"}


def test_ordinary_values_pass_through():
    v = {"skillId": "skill_1", "description": "a token of thanks", "count": 3, "empty_password": ""}
    assert _redact_secrets(v) == v

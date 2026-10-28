"""Secrets never reach a log line (2026-10-22 scan of real logs). Every case
below is the SHAPE of a line found in clear text; values are made up."""
import pytest

from utils.log_redact import MASK, scrub

# Built at run time so the source never holds a key-shaped string (the
# pre-commit secret scanner rightly refuses those).
FAKE_SK = "sk-" + "proj-" + "AbCdEf" + "1234567890abcdef"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"


@pytest.mark.parametrize("line,secret", [
    ("[GraphQL] Variables: {'email': 'a@b.com', 'password': 'Hunter2!x', 'role': 'Commander'}", "Hunter2!x"),
    (f"llm config: model_name=gpt-5 api_host= api_key={FAKE_SK} model_provider=openai", FAKE_SK),
    ("[create_browser_use_llm] provider_type:openai, model_name:gpt-5, api_key: abcd1234efgh5678ijkl", "abcd1234efgh5678ijkl"),
    (f"[wan_chat:TCB-WS] connecting wss://x.tcloudbase.com/283f7e32/@@/{JWT}", JWT),
    (f"[_build_login_response] 'tokens': {{'access_token': '{JWT}', 'refresh_token': 'r-1234567890abcdef'}}", "r-1234567890abcdef"),
    ('reqApiKey response: {"data": {"reqApiKey": {"apiKey": "ak_live_9f8e7d6c5b4a3210"}}}', "ak_live_9f8e7d6c5b4a3210"),
    ('"x-tt-passport-csrf-token": "a1b2c3d4e5f6a7b8c9d0", "accept": "*/*"', "a1b2c3d4e5f6a7b8c9d0"),
    ("GET https://im.jinritemai.com/x?biz=4&msToken=AbCdEf123456_-xyz&a_bogus=QwErTy0987", "AbCdEf123456_-xyz"),
    ("[NODE_OUTPUT] https://b-1.cos.ap-shanghai.myqcloud.com/m/0.png?q-sign-algorithm=sha1&q-ak=AKIDabcdefghijklmnop1234&q-signature=0123456789abcdef0123&x-cos-security-token=Tok_Abc123xyz", "AKIDabcdefghijklmnop1234"),
    ("[Skill ADD] https://s3.amazonaws.com/b/k?X-Amz-Expires=900&X-Amz-Security-Token=FwoGZXIvYXdzEJr//////////wEaD&X-Amz-Signature=abc123def456", "FwoGZXIvYXdzEJr"),
    ("[agent_handler] request: {'params': {'id': 1}, 'source': 'graphql', 'token': 'f3a9c1e2-77b0-4c1d-9e1a-2b3c4d5e6f70'}", "f3a9c1e2-77b0-4c1d-9e1a-2b3c4d5e6f70"),
    ("[GraphQL] Variables: {'env': {'NEO4J_PASSWORD': 'neo4jpass123', 'EMBEDDING_BINDING_API_KEY': 'emb-key-0987654321'}}", "neo4jpass123"),
    ("[BrowserAutomation] proxy user=o3YB, token=9f8e7d6c5b4a39281706", "9f8e7d6c5b4a39281706"),
    ("Authorization: Bearer abcdefghijklmnop1234567890", "abcdefghijklmnop1234567890"),
    ("cookie: sessionid=abc123def456ghi789; passport_csrf_token=zzz999yyy888", "abc123def456ghi789"),
    ("LANGCHAIN_API_KEY=lsv2_pt_0123456789abcdef HOMEPATH=\\Users\\x", "lsv2_pt_0123456789abcdef"),
])
def test_secret_is_masked(line, secret):
    out = scrub(line)
    assert secret not in out, out
    assert MASK in out


def test_the_rest_of_the_line_stays_readable():
    out = scrub("[GraphQL] Variables: {'email': 'a@b.com', 'password': 'Hunter2!x', 'role': 'Commander'}")
    assert out == "[GraphQL] Variables: {'email': 'a@b.com', 'password': '***', 'role': 'Commander'}"


@pytest.mark.parametrize("line", [
    "[LLM] usage: input_tokens=1200 output_tokens=340 total_tokens=1540",
    "[TaskStatus] token_source=mainwin.get_auth_token",
    "max_tokens=4096 temperature=0.5",
    "[qianniu] OCR remote/direct window='xuboz71-接待中心' lines=38",
    "apiKey: {type: 'constant', content: 'sk-xxxxxxxxxxxxxxxxxxxxxxxx'}",
    "password: ''",
    "[GraphQL] ✅ Success: get_last_login",
])
def test_ordinary_lines_are_left_alone(line):
    assert scrub(line) == line


def test_never_raises_on_odd_input():
    assert scrub("") == "" and scrub(None) is None
    scrub("eyJ" * 10000)


def test_the_log_formatters_mask_what_they_write():
    import logging
    from utils.logger_helper import _redacting
    from utils.log_scope import ScopedFormatter
    rec = logging.LogRecord("eCan", logging.DEBUG, __file__, 1,
                            "[GraphQL] Variables: {'email': 'a@b.com', 'password': 'Hunter2!x'}", None, None)
    for cls in (logging.Formatter, ScopedFormatter):
        out = _redacting(cls)("%(levelname)s - %(message)s").format(rec)
        assert "Hunter2!x" not in out and "'password': '***'" in out

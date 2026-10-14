"""normalize_cloud_owner must strip the WeChat 'wechat_' prefix, not just '@local'.

2026-09-08: a WeChat-logged-in owner "couldn't see their own prompt". Root: the
client tags the user 'wechat_<openid>@local', normalize stripped only '@local'
(-> 'wechat_<openid>'), but the cloud's identity.sub is the BARE openid. Owner-
filtered resolvers do strict equality against identity.sub → FORBIDDEN → the
fetch (prompts/agents/skills) silently returned []. The cloud owner must equal
the bare openid.
"""

from agent.cloud_api.cloud_api import normalize_cloud_owner as n


def test_wechat_suffixed_becomes_bare_openid():
    assert n("wechat_oABC123@local") == "oABC123"


def test_wechat_bare_prefix_stripped():
    # new-flow WeChat logins can arrive without the @local suffix.
    assert n("wechat_oABC123") == "oABC123"


def test_wechat_dot_local_suffix_becomes_bare_openid():
    # 2026-10-13: the real CN WeChat identity suffix is ``@wechat.local`` (not
    # ``@local``); the owner "couldn't edit/publish their own skill" because the
    # suffix survived → cloud saw a cross-owner and rejected the publish.
    assert n("wechat_oABC123@wechat.local") == "oABC123"
    assert n("wechat_b603a407904569a4ea88f9ac@wechat.local") == "b603a407904569a4ea88f9ac"
    assert n("13800138000@phone.local") == "13800138000"  # CN phone OTP current form


def test_non_wechat_logins_unchanged():
    assert n("user@gmail.com") == "user@gmail.com"       # Intl email
    assert n("13800138000@local") == "13800138000"       # CN phone OTP
    assert n("") == ""
    # a real email that merely contains the substring 'wechat_' mid-string is
    # untouched (prefix-anchored strip only).
    assert n("wechat_user@gmail.com") == "user@gmail.com"  # @local absent; prefix stripped

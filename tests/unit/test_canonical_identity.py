"""Login must persist ONE CN WeChat suffix form so the same person isn't two
identities downstream (owner/publish checks). _canonical_identity folds the
server's `@wechat.local` onto the `@local` form the DB rows/data dir use."""

from auth.auth_manager import _canonical_identity as c


def test_wechat_dot_local_folded_to_local():
    assert c("wechat_o3YBk2dxaRe3LKqJXCf5z3PfvD5M@wechat.local") == \
        "wechat_o3YBk2dxaRe3LKqJXCf5z3PfvD5M@local"
    # base identifier case is preserved; only the suffix changes
    assert c("wechat_B603aBC@wechat.local") == "wechat_B603aBC@local"


def test_already_local_unchanged():
    assert c("wechat_o3YB@local") == "wechat_o3YB@local"


def test_email_and_phone_untouched():
    assert c("user@gmail.com") == "user@gmail.com"      # real email
    assert c("13800138000@phone.local") == "13800138000@phone.local"  # phone keeps its dir suffix


def test_empty_and_whitespace():
    assert c("") == ""
    assert c(None) == ""
    assert c("  wechat_x@wechat.local  ") == "wechat_x@local"

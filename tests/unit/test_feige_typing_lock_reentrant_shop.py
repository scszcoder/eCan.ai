"""抖店 alpha 2026-10-21 cold start: HOT-PATH-B held the default typing-lock slot,
feige_send_message re-acquired per shop and (seeing "already holding") never
released the shop entry that acquire had created -- the shop stayed locked for
the 50 s TTL after every guarded send; other buyers' first messages waited."""
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import typing_lock as tl

SHOP = "profile:fp-douyin-55b2a7fb-login"


def setup_function():
    tl.reset()


def test_a_nested_shop_acquire_leaves_nothing_behind():
    assert tl.try_acquire("肽斯特")                       # HOT-PATH-B (default slot)
    already = tl.holder(SHOP) == "肽斯特"                  # feige_send_message's check
    assert already and tl.try_acquire("肽斯特", SHOP)     # re-entrant
    # the send does not release (it was "already holding"); HOT-PATH-B does:
    tl.release("肽斯特")
    assert tl.holder(SHOP) == "" and tl.holder() == ""
    assert tl.try_acquire("packet", SHOP)                 # the next buyer gets in at once


def test_another_buyer_is_still_kept_out_while_held():
    assert tl.try_acquire("肽斯特")
    assert not tl.try_acquire("sc", SHOP)


def test_two_shops_still_do_not_block_each_other():
    assert tl.try_acquire("a", "shop1")
    assert tl.try_acquire("b", "shop2")

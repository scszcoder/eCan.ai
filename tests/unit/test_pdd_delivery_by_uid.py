"""拼多多 alpha 2026-10-21: the Q&A reply carried the masked nickname as
customer_name ({"customer_id": "5664669982013", "customer_name": "B***n"});
direct delivery sent to "B***n" and 拼多多's send, which finds a conversation
only by uid, failed every time ("no conversation row for B***n")."""
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.runner_bridge import FeigeRunnerBridge
from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat.runner_bridge import PddRunnerBridge
from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat.runner_bridge import QianniuRunnerBridge


def test_pdd_replies_go_to_the_buyer_uid_not_the_masked_nickname():
    reply = {"customer_id": "5664669982013", "customer_name": "B***n", "response_text": "是纯棉的"}
    assert PddRunnerBridge.delivery_customer(reply) == "5664669982013"


def test_pdd_falls_back_to_customer_name_when_there_is_no_id():
    assert PddRunnerBridge.delivery_customer({"customer_name": "5664669982013"}) == "5664669982013"


def test_other_sites_keep_addressing_by_customer_name():
    assert not hasattr(FeigeRunnerBridge, "delivery_customer")
    assert not hasattr(QianniuRunnerBridge, "delivery_customer")

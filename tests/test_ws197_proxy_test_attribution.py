"""ws197: the LLM proxy self-test carries attribution, so clicking it validates
the token-attribution pipeline end-to-end (tracked row under source 'proxy_test')."""

from utils import log_scope as ls
import gui.ipc.w2p_handlers.llm_proxy_test_handler as h


def test_proxy_test_scope_marker():
    sc = h._proxy_test_scope()
    assert sc["agent_id"] == "proxy_test"
    assert sc["skill_id"] == "proxy_test"


def test_test_scope_yields_attribution_headers():
    with ls.scope(**{k: v for k, v in h._proxy_test_scope().items() if v}):
        hd = ls.attribution_headers()
    assert hd["X-Ecan-Agent-Id"] == "proxy_test"
    assert hd["X-Ecan-Skill-Id"] == "proxy_test"
    assert hd["X-Ecan-Source"] == "proxy_test"

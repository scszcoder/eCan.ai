"""A node can narrow how far beyond the viewport the page's elements enter the
prompt (browser-use: 1000 px) -- the element list is the largest per-step part
of a publish prompt -- and every other node gets browser-use's default back."""
from types import SimpleNamespace

from agent.ec_skills.browser_node.runner import RunContext, apply_dom_viewport_margin


def _agent(threshold=1000):
    ds = SimpleNamespace(viewport_threshold=threshold)
    return SimpleNamespace(browser_session=SimpleNamespace(_dom_watchdog=SimpleNamespace(_dom_service=ds))), ds


def test_a_node_margin_is_applied_once():
    agent, ds = _agent()
    assert apply_dom_viewport_margin(agent, 300) is True and ds.viewport_threshold == 300
    assert apply_dom_viewport_margin(agent, 300) is False


def test_a_node_without_a_margin_gets_the_default_back():
    agent, ds = _agent(300)
    assert apply_dom_viewport_margin(agent, None) is True and ds.viewport_threshold == 1000


def test_no_dom_service_yet_is_a_no_op():
    assert apply_dom_viewport_margin(SimpleNamespace(browser_session=None), 300) is False
    assert apply_dom_viewport_margin(None, 300) is False


def test_browser_use_reads_the_attribute_this_sets():
    import inspect
    from browser_use.dom.service import DomService
    assert "viewport_threshold" in inspect.signature(DomService.__init__).parameters
    assert "self.viewport_threshold" in inspect.getsource(DomService)
    assert RunContext.__dataclass_fields__["node_dom_viewport_margin"].default is None

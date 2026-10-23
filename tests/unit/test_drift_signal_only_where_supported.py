"""pend_event marked a drift-recovery signal on whatever live-chat bridge was
active; the PDD bridge has none, so every resume warned
"'PddRunnerBridge' object has no attribute 'drift_recovery'" (2026-10-23)."""
import inspect

import agent.ec_skills.build_node as bn


def test_bridges_without_drift_recovery_are_skipped_quietly():
    src = inspect.getsource(bn)
    i = src.index("drift-recovery signal mark failed")
    block = src[i - 1500:i]
    assert 'getattr(_lcd.runner_bridge(), "drift_recovery", None)' in block
    assert "if _drift is not None:" in block


def test_pdd_bridge_really_has_no_drift_recovery():
    from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import runner_bridge as rb
    bridges = [v for v in vars(rb).values() if isinstance(v, type) and v.__module__ == rb.__name__]
    assert bridges and not any(hasattr(b, "drift_recovery") for b in bridges)

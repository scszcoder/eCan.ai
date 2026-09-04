"""[AGENT-STATUS] readiness ledger (utils/agent_status.py)."""

import json

import pytest

from utils import agent_status as st
from utils import log_scope as ls


@pytest.fixture(autouse=True)
def _clean():
    st.clear()
    yield
    st.clear()


def _emitted(monkeypatch):
    lines = []
    monkeypatch.setattr(st.logger, "info", lambda msg, *a, **k: lines.append(str(msg)))
    return lines


def test_report_attributes_to_scope_and_emits_on_change(monkeypatch):
    lines = _emitted(monkeypatch)
    with ls.scope(agent_id="agent_1", agent_name="前台小张"):
        st.report(chrome="attached_existing", chrome_port=9228)
        st.report(chrome="attached_existing", chrome_port=9228)   # no change -> no emit
        st.report(site_tab="missing")
    assert len(lines) == 2
    payload = json.loads(lines[-1].split("[AGENT-STATUS] ", 1)[1])
    assert payload["agent_id"] == "agent_1" and payload["agent_name"] == "前台小张"
    assert payload["chrome"] == "attached_existing" and payload["site_tab"] == "missing"
    snap = st.snapshot("agent_1")
    assert snap["chrome_port"] == 9228 and "updated_at" in snap


def test_explicit_agent_id_and_unscoped_bucket(monkeypatch):
    _emitted(monkeypatch)
    st.report(agent_id="agent_9", monitor="running")
    st.report(dom_items=3)  # no scope, no id
    assert st.snapshot("agent_9")["monitor"] == "running"
    assert st.snapshot_all()[st.UNSCOPED]["dom_items"] == 3


def test_heartbeat_reemits_after_interval(monkeypatch):
    lines = _emitted(monkeypatch)
    st.report(agent_id="a", monitor="running")
    st.report(agent_id="a", monitor="running")
    assert len(lines) == 1
    st._last_emit["a"] -= st.HEARTBEAT_S + 1   # pretend a minute passed
    st.report(agent_id="a", monitor="running")
    assert len(lines) == 2


def test_report_never_raises(monkeypatch):
    monkeypatch.setattr(st, "_agent_key", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    assert st.report(chrome="x") == {}

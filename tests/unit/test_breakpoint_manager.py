"""Unit tests for BreakpointManager."""

import pytest

pytestmark = pytest.mark.unit


class TestBreakpointManager:
    """Tests for BreakpointManager state management."""

    def test_set_and_has_breakpoint(self):
        """Setting a breakpoint makes has_breakpoint return True."""
        from agent.ec_skills.dev_defs import BreakpointManager

        bm = BreakpointManager()
        assert bm.has_breakpoint("node_1") is False

        bm.set_breakpoint("node_1")
        assert bm.has_breakpoint("node_1") is True

    def test_clear_breakpoint(self):
        """Clearing a breakpoint makes has_breakpoint return False."""
        from agent.ec_skills.dev_defs import BreakpointManager

        bm = BreakpointManager()
        bm.set_breakpoint("node_1")
        bm.set_breakpoint("node_2")

        bm.clear_breakpoint("node_1")
        assert bm.has_breakpoint("node_1") is False
        assert bm.has_breakpoint("node_2") is True

    def test_get_breakpoints(self):
        """get_breakpoints returns all set breakpoint names."""
        from agent.ec_skills.dev_defs import BreakpointManager

        bm = BreakpointManager()
        bm.set_breakpoint("node_a")
        bm.set_breakpoint("node_b")

        bps = bm.get_breakpoints()
        assert "node_a" in bps
        assert "node_b" in bps
        assert len(bps) == 2

    def test_set_breakpoints_batch(self):
        """set_breakpoints adds multiple at once."""
        from agent.ec_skills.dev_defs import BreakpointManager

        bm = BreakpointManager()
        bm.set_breakpoints(["x", "y", "z"])

        assert bm.has_breakpoint("x") is True
        assert bm.has_breakpoint("y") is True
        assert bm.has_breakpoint("z") is True
        assert len(bm.get_breakpoints()) == 3

    def test_clear_breakpoints_batch(self):
        """clear_breakpoints removes multiple at once."""
        from agent.ec_skills.dev_defs import BreakpointManager

        bm = BreakpointManager()
        bm.set_breakpoints(["a", "b", "c"])
        bm.clear_breakpoints(["a", "c"])

        assert bm.has_breakpoint("a") is False
        assert bm.has_breakpoint("b") is True
        assert bm.has_breakpoint("c") is False

    def test_clear_all(self):
        """clear_all removes all breakpoints."""
        from agent.ec_skills.dev_defs import BreakpointManager

        bm = BreakpointManager()
        bm.set_breakpoints(["p", "q", "r"])
        bm.clear_all()

        assert len(bm.get_breakpoints()) == 0

    def test_idempotent_set(self):
        """Setting the same breakpoint twice is idempotent."""
        from agent.ec_skills.dev_defs import BreakpointManager

        bm = BreakpointManager()
        bm.set_breakpoint("node_x")
        bm.set_breakpoint("node_x")
        bm.set_breakpoint("node_x")

        # Should only appear once
        assert bm.get_breakpoints().count("node_x") == 1

    def test_idempotent_clear(self):
        """Clearing a non-existent breakpoint is idempotent."""
        from agent.ec_skills.dev_defs import BreakpointManager

        bm = BreakpointManager()
        bm.clear_breakpoint("nonexistent")  # Should not raise
        assert len(bm.get_breakpoints()) == 0

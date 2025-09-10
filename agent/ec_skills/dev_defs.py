from langgraph.types import Interrupt

class BreakpointManager:
    def __init__(self):
        self.breakpoints = set()
        self.pending_interrupt = None

    def set_breakpoint(self, node_name: str):
        self.breakpoints.add(node_name)

    def set_breakpoints(self, node_names: list[str]):
        self.breakpoints.update(node_names)

    def clear_breakpoint(self, node_name: str):
        self.breakpoints.discard(node_name)

    def clear_breakpoints(self, node_names: list[str]):
        self.breakpoints.difference_update(node_names)

    def clear_all(self):
        self.breakpoints.clear()

    def has_breakpoint(self, node_name: str) -> bool:
        return node_name in self.breakpoints

    def get_breakpoints(self) -> list[str]:
        return list(self.breakpoints)

    def capture_interrupt(self, interrupt: Interrupt):
        self.pending_interrupt = interrupt

    def resume(self):
        if self.pending_interrupt:
            self.pending_interrupt.resume()
            self.pending_interrupt = None
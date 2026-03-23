from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class NormalizedBrowserEvent:
    event_id: str
    session_id: str
    monitor_id: str
    label: str
    source_type: str
    scope: str = "session"
    tab_id: Optional[str] = None
    url: Optional[str] = None
    detected_at: str = ""
    change_summary: Dict[str, Any] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_workflow_input(self) -> Dict[str, Any]:
        return {
            "type": "browser_event",
            "event": self.to_dict(),
        }

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SessionCapabilityRegistry:
    capabilities: Dict[str, Any] = field(default_factory=dict)

    def get(self, name: str) -> Optional[Any]:
        return self.capabilities.get(name)

    def set(self, name: str, capability: Any) -> Any:
        self.capabilities[name] = capability
        return capability


def get_or_create_session_capability_registry(session: Any) -> SessionCapabilityRegistry:
    registry = getattr(session, "_ecan_capability_registry", None)
    if registry is None:
        registry = SessionCapabilityRegistry()
        setattr(session, "_ecan_capability_registry", registry)
    return registry

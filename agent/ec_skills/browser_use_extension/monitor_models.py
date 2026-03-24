from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MonitorTargetConfig:
    url_patterns: List[str] = field(default_factory=list)
    title_patterns: List[str] = field(default_factory=list)
    tab_ids: List[str] = field(default_factory=list)


@dataclass
class ExtractorConfig:
    type: str = ""
    roots: List[str] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)
    identity: Dict[str, Any] = field(default_factory=dict)
    empty_text_patterns: List[str] = field(default_factory=list)


@dataclass
class EmitPolicyConfig:
    mode: str = "added"
    top_n: Optional[int] = None
    dedupe_window_sec: Optional[int] = None
    emit_empty: bool = False


@dataclass
class MonitorConfigRecord:
    id: str
    label: str
    enabled: bool
    source_type: str
    scope: str = "session"
    targets: MonitorTargetConfig = field(default_factory=MonitorTargetConfig)
    extractor: Optional[ExtractorConfig] = None
    emit_policy: EmitPolicyConfig = field(default_factory=EmitPolicyConfig)
    routing: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MonitorInstanceState:
    monitor_id: str
    status: str = "idle"
    attached_tab_ids: List[str] = field(default_factory=list)
    last_snapshot_keys: List[str] = field(default_factory=list)
    last_snapshot_items: List[Dict[str, Any]] = field(default_factory=list)
    last_emitted_at: Optional[str] = None
    error: Optional[str] = None


@dataclass
class EventMonitorCapabilityState:
    enabled: bool = False
    status: str = "idle"
    monitor_configs: List[MonitorConfigRecord] = field(default_factory=list)
    instances: Dict[str, MonitorInstanceState] = field(default_factory=dict)
    queued_event_ids: List[str] = field(default_factory=list)
    last_error: str = ""

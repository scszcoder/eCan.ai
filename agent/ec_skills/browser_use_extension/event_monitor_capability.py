from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any, List, Optional

from utils.logger_helper import logger_helper as logger

from .monitor_models import EventMonitorCapabilityState, MonitorConfigRecord
from .session_capabilities import get_or_create_session_capability_registry


_COMPAT_MONITOR_ATTR = "_ecan_event_monitors"


def _dedupe_monitor_configs(configs: List[Any]) -> List[Any]:
    deduped: List[Any] = []
    seen_keys = set()
    for cfg in reversed(list(configs or [])):
        label = str(getattr(cfg, "label", "") or "").strip()
        cfg_id = str(getattr(cfg, "id", "") or "").strip()
        source_type = str(getattr(cfg, "source_type", "") or "").strip()
        if label == "chat_message_added":
            key = ("label", label, source_type or "dom_mutation")
        else:
            key = ("id", cfg_id or label, source_type)
        if key in seen_keys:
            logger.warning(
                f"[EventMonitorCapability] Dropping duplicate monitor config: "
                f"id={cfg_id}, label={label}, source_type={source_type}"
            )
            continue
        seen_keys.add(key)
        deduped.append(cfg)
    deduped.reverse()
    return deduped


def get_attached_monitor_set(session: Any) -> Any:
    return getattr(session, _COMPAT_MONITOR_ATTR, None)


def set_attached_monitor_set(session: Any, monitor_set: Any) -> None:
    setattr(session, _COMPAT_MONITOR_ATTR, monitor_set)
    capability = get_event_monitor_capability(session, create=True)
    capability.set_active_monitor_set(monitor_set)


def clear_attached_monitor_set(session: Any) -> None:
    if hasattr(session, _COMPAT_MONITOR_ATTR):
        try:
            delattr(session, _COMPAT_MONITOR_ATTR)
        except Exception:
            pass
    capability = get_event_monitor_capability(session, create=False)
    if capability:
        capability.set_active_monitor_set(None)


class EventMonitorCapability:
    capability_name = "event_monitor"

    def __init__(self, session: Any):
        self.session = session
        self.state = EventMonitorCapabilityState()
        self._active_monitor_set = get_attached_monitor_set(session)

    def set_active_monitor_set(self, monitor_set: Any) -> None:
        self._active_monitor_set = monitor_set
        self.state.enabled = bool(monitor_set and getattr(monitor_set, "monitors", None))
        self.state.status = "running" if self.state.enabled else "idle"

    def get_active_monitor_set(self) -> Any:
        if self._active_monitor_set is None:
            self._active_monitor_set = get_attached_monitor_set(self.session)
        return self._active_monitor_set

    def configure(self, configs: List[Any]) -> None:
        configs = _dedupe_monitor_configs(configs)
        records: List[MonitorConfigRecord] = []
        for cfg in configs or []:
            record = MonitorConfigRecord(
                id=str(getattr(cfg, "id", "") or getattr(cfg, "label", "") or "monitor"),
                label=str(getattr(cfg, "label", "") or ""),
                enabled=bool(getattr(cfg, "enabled", True)),
                source_type=str(getattr(cfg, "source_type", "") or ""),
                raw=getattr(cfg, "__dict__", {}).copy() if hasattr(cfg, "__dict__") else {},
            )
            record.targets.url_patterns = list(getattr(cfg, "url_patterns", []) or [])
            records.append(record)
        self.state.monitor_configs = records

    def get_configs(self) -> List[dict]:
        return [asdict(item) for item in self.state.monitor_configs]

    def _config_signature(self, configs: List[Any]) -> str:
        configs = _dedupe_monitor_configs(configs)
        normalized = []
        for cfg in configs or []:
            raw = getattr(cfg, "__dict__", {}).copy() if hasattr(cfg, "__dict__") else {}
            normalized.append(raw)
        try:
            return json.dumps(normalized, sort_keys=True, default=str)
        except Exception:
            return str(normalized)

    async def ensure_started(self, configs: List[Any], agent_id: str = "") -> Any:
        configs = _dedupe_monitor_configs(configs)
        self.configure(configs)
        current = self.get_active_monitor_set()
        desired_sig = self._config_signature(configs)
        current_sig = self._config_signature(list(getattr(current, "configs", []) or [])) if current else ""
        if current and getattr(current, "monitors", None):
            logger.info(
                f"[EventMonitorCapability] Active monitor set present: "
                f"set_id={getattr(current, 'monitor_set_id', '')} "
                f"active_count={len(getattr(current, 'monitors', []) or [])} "
                f"config_changed={desired_sig != current_sig}"
            )
            try:
                for idx, cfg in enumerate(list(getattr(current, "configs", []) or []), start=1):
                    logger.info(
                        f"[EventMonitorCapability] Active cfg[{idx}]: "
                        f"id={getattr(cfg, 'id', '')} "
                        f"label={getattr(cfg, 'label', '')} "
                        f"source_type={getattr(cfg, 'source_type', '')} "
                        f"dom_check_interval_ms={getattr(cfg, 'dom_check_interval_ms', '')} "
                        f"url_patterns={list(getattr(cfg, 'url_patterns', []) or [])} "
                        f"cdp_filter_expr={str(getattr(cfg, 'cdp_filter_expr', '') or '')[:400]}"
                    )
            except Exception:
                pass
            if desired_sig != current_sig:
                logger.info("[EventMonitorCapability] Desired monitor config differs from active set; replacing monitors")
                return await self.replace_monitors(configs, agent_id=agent_id)
            self.state.enabled = True
            self.state.status = "running"
            return current

        self.state.status = "starting"
        try:
            from agent.ec_skills.browser_use_extension.event_monitor import start_monitors

            monitor_set = await start_monitors(self.session, configs=configs, agent_id=agent_id)
            self.set_active_monitor_set(monitor_set)
            return monitor_set
        except Exception as exc:
            self.state.status = "error"
            self.state.last_error = str(exc)
            logger.warning(f"[EventMonitorCapability] Failed to start monitors: {exc}")
            raise

    async def stop(self) -> None:
        monitor_set = self.get_active_monitor_set()
        if not monitor_set:
            self.state.status = "stopped"
            self.state.enabled = False
            return
        from agent.ec_skills.browser_use_extension.event_monitor import stop_monitors

        await stop_monitors(monitor_set, session=self.session)
        self.set_active_monitor_set(None)
        self.state.status = "stopped"
        self.state.enabled = False

    async def replace_monitors(self, configs: List[Any], agent_id: str = "") -> Any:
        current = self.get_active_monitor_set()
        if current:
            await self.stop()
        return await self.ensure_started(configs, agent_id=agent_id)

    async def check_dom_monitors(self) -> None:
        from agent.ec_skills.browser_use_extension.event_monitor import check_dom_monitors_periodically

        await check_dom_monitors_periodically()

    def snapshot(self) -> dict:
        active = self.get_active_monitor_set()
        instances = {}
        for monitor in list(getattr(active, "monitors", []) or []):
            state = getattr(monitor, "state", None)
            if not isinstance(state, dict):
                continue
            cfg = state.get("config")
            monitor_id = str(
                getattr(cfg, "id", "") or
                getattr(cfg, "label", "") or
                state.get("monitor_set_id") or
                f"monitor_{len(instances) + 1}"
            )
            instances[monitor_id] = {
                "label": str(getattr(cfg, "label", "") or ""),
                "source_type": str(getattr(cfg, "source_type", "") or ""),
                "enabled": bool(state.get("enabled", False)),
                "status": str(state.get("last_status") or ("running" if state.get("enabled", False) else "idle")),
                "current_url": str(state.get("last_current_url") or ""),
                "last_customer_count": int(state.get("last_customer_count") or 0),
                "last_keys_count": len(state.get("last_keys") or []),
                "last_removed_count": len(state.get("last_removed_keys") or []),
                "last_reordered_count": len(state.get("last_reordered_keys") or []),
                "last_top_changed": bool(state.get("last_top_changed", False)),
                "check_interval_ms": int(state.get("check_interval_ms") or 0),
                "monitor_set_id": str(state.get("monitor_set_id") or ""),
            }
        return {
            "enabled": self.state.enabled,
            "status": self.state.status,
            "configured_count": len(self.state.monitor_configs),
            "active_count": len(getattr(active, "monitors", []) or []),
            "monitor_configs": [asdict(item) for item in self.state.monitor_configs],
            "instances": instances,
            "last_error": self.state.last_error,
        }


def get_event_monitor_capability(session: Any, create: bool = True) -> Optional[EventMonitorCapability]:
    registry = get_or_create_session_capability_registry(session) if create else getattr(session, "_ecan_capability_registry", None)
    if registry is None:
        return None
    capability = registry.get(EventMonitorCapability.capability_name)
    if capability is None and create:
        capability = EventMonitorCapability(session)
        registry.set(EventMonitorCapability.capability_name, capability)
    return capability

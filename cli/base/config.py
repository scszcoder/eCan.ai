#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Configuration - Manages CLI-specific settings.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class CLIConfig:
    """
    CLI configuration management.

    Handles:
    - Global CLI settings
    - Command aliases
    - Output preferences
    - Cache settings
    """

    config_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "ecan")
    config_file: Path = field(init=False)

    defaults: Dict[str, Any] = field(default_factory=lambda: {
        "output_format": "table",
        "color": True,
        "pager": True,
        "confirm_destructive": True,
        "log_level": "info",
        "aliases": {
            "l": "list",
            "ls": "list",
            "rm": "remove",
            "rmi": "remove",
            "get": "show",
            "s": "server",
            "st": "status",
        },
        "default_limit": 50,
        "max_limit": 1000,
    })

    _settings: Dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self):
        self.config_file = self.config_dir / "cli.json"
        self._load()

    def _load(self):
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    user_settings = json.load(f)
                    self._settings = {**self.defaults, **user_settings}
            except Exception:
                self._settings = self.defaults.copy()
        else:
            self._settings = self.defaults.copy()

    def _save(self):
        """Save configuration to file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(self._settings, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        """Set a configuration value."""
        self._settings[key] = value
        self._save()

    def get_alias(self, cmd: str) -> Optional[str]:
        """Get command alias."""
        aliases = self._settings.get("aliases", {})
        return aliases.get(cmd)

    def set_alias(self, alias: str, command: str):
        """Set a command alias."""
        aliases = self._settings.get("aliases", {})
        aliases[alias] = command
        self._settings["aliases"] = aliases
        self._save()

    def reset(self):
        """Reset configuration to defaults."""
        self._settings = self.defaults.copy()
        self._save()


_global_config: Optional[CLIConfig] = None


def get_config() -> CLIConfig:
    """Get or create global config instance."""
    global _global_config
    if _global_config is None:
        _global_config = CLIConfig()
    return _global_config

"""<appdata>/run.env: environment switches main.py loads at startup (a real OS env var wins).

Used for settings that must be in place before any module reads them -- e.g.
which live-chat site this process serves (bundles register at import).
"""

import os
import re
from typing import Optional

_KEY = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def run_env_path() -> str:
    from config.envi import getECBotDataHome
    return os.path.join(getECBotDataHome(), "run.env")


def read_value(key: str) -> Optional[str]:
    """The value *key* has in run.env, or None when it is not set there."""
    path = run_env_path()
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        for line in f.read().splitlines():
            m = _KEY.match(line)
            if m and m.group(1) == key:
                return m.group(2).strip().strip('"').strip("'")
    return None


def set_value(key: str, value: Optional[str]) -> None:
    """Set *key* in run.env, or remove it when *value* is None/empty. Other lines are kept."""
    path = run_env_path()
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    out, placed = [], False
    for line in lines:
        m = _KEY.match(line)
        if m and m.group(1) == key:
            if value and not placed:
                out.append(f"{key}={value}")
                placed = True
            continue
        out.append(line)
    if value and not placed:
        out.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + ("\n" if out else ""))

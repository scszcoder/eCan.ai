"""status_diagnose (L3): a log tail or a file excerpt for one subject, scrubbed on this machine
before anything leaves it. It never runs by itself: the Manager asks the user first.

- ``log_tail``: the newest app log lines that mention the subject's agents (or the last lines).
- ``file``: a text file under a folder the subject's status provider declares (``roots``).
  Credential-looking files (.env, keys, password/token files, the NAS password file, the
  login state) are refused, whatever folder they are in.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAX_LINES = 400
MAX_BYTES = 32_000
READ_TAIL_BYTES = 4_000_000

_SECRET_FILE = re.compile(r"(^\.env(\..*)?$|^run\.env$|^uli\.json$|^nas\.txt$|^id_(rsa|ed25519|ecdsa)"
                          r"|\.(pem|key|p12|pfx|kdbx)$|secret|credential|passw|token|api[_-]?key)", re.I)
_SCRUB: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer ***"),
    (re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), "***jwt***"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "***aws-key***"),
    (re.compile(r"(?i)\b(sk|pk|rk)-[A-Za-z0-9_-]{16,}"), "***key***"),
    (re.compile(r"(?i)([\"']?(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|authorization|cookie|"
                r"session[_-]?id|refresh[_-]?token|id[_-]?token)[\"']?\s*[:=]\s*[\"']?)([^\s\"',;}]+)"), r"\1***"),
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "***@***"),
]


def scrub(text: str) -> Tuple[str, int]:
    """(text with secrets and e-mail addresses masked, number of replacements)."""
    n = 0
    for rx, repl in _SCRUB:
        text, k = rx.subn(repl, text)
        n += k
    return text, n


def _tail_lines(path: Path, n: int) -> List[str]:
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - READ_TAIL_BYTES))
        data = f.read().decode("utf-8", errors="replace")
    return data.splitlines()[-n:] if n else data.splitlines()


def log_tail(log_path: Path, names: List[str], lines: int = 200) -> str:
    lines = max(1, min(int(lines or 200), MAX_LINES))
    keys = [k.lower() for k in names if k]
    all_lines = _tail_lines(log_path, 0)
    hits = [ln for ln in all_lines if any(k in ln.lower() for k in keys)] if keys else []
    return "\n".join((hits or all_lines)[-lines:])


def read_file(path: Path, roots: List[Path], lines: int = 200) -> str:
    p = path.resolve()
    if _SECRET_FILE.search(p.name):
        raise PermissionError(f"{p.name} looks like a credential file; it is never sent")
    if not any(p == r.resolve() or r.resolve() in p.parents for r in roots):
        raise PermissionError(f"{p} is outside the folders this agent's status covers")
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return "\n".join(_tail_lines(p, max(1, min(int(lines or 200), MAX_LINES))))


def diagnose(task: Dict[str, Any], members: List[dict], roots: List[Path],
             log_path: Optional[Path] = None) -> Dict[str, Any]:
    """{"what", "text", "scrubbed", "truncated"}; raises PermissionError / ValueError when refused."""
    what = str(task.get("what") or "log_tail")
    if what == "log_tail":
        if log_path is None:
            from utils.logger_helper import get_log_path
            log_path = Path(get_log_path())
        names = [m.get("name") or "" for m in members] + [m.get("id") or "" for m in members]
        text = log_tail(log_path, names, task.get("lines") or 200)
    elif what == "file":
        if not task.get("path"):
            raise ValueError("status_diagnose file needs a path")
        text = read_file(Path(str(task["path"])), roots, task.get("lines") or 200)
    else:
        raise ValueError(f"unknown diagnosis {what!r} (log_tail | file)")
    text, n = scrub(text)
    raw = text.encode("utf-8")
    truncated = len(raw) > MAX_BYTES
    if truncated:
        text = raw[-MAX_BYTES:].decode("utf-8", errors="ignore")
    return {"what": what, "text": text, "scrubbed": n, "truncated": truncated}

"""status_diagnose (L3): a log tail or a file excerpt for one subject, scrubbed on this machine
before anything leaves it. It never runs by itself: the Manager asks the user first, and it
is off unless this machine's owner puts it on the gateway allowlist (agent/a2a/gateway.py).

- ``log_tail``: the newest app log lines that mention the subject's agents; nothing when no
  line does (never the tail of the whole log: other agents' buyer chats are in it). Chinese
  text is masked except the subject's own agent, skill and task names, so buyer messages,
  names and addresses don't leave the machine.
- ``file``: a text file under a folder the subject's status provider declares (``roots``).
  Credential-looking files (.env, keys, password/token files, the NAS password file, the
  login state) are refused, whatever folder they are in.

Both mask tokens, keys, passwords, cookies, e-mail addresses, phone numbers and ID numbers.
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
    # ID card numbers before phones: an ID number has a phone-like run inside it
    (re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])\d{5}[\dXx](?![\dXx])"), "***id***"),
    (re.compile(r"(?<![\d+])(?:\+?86[-\s]?)?1[3-9]\d(?:[-\s]?\d{4}){2}(?!\d)"), "***phone***"),
]
_CJK = re.compile(r"(?:[㐀-鿿豈-﫿]|\\u(?:3[4-9a-f]|[4-9][0-9a-f])[0-9a-f]{2})+", re.I)


def scrub(text: str) -> Tuple[str, int]:
    """(text with secrets, e-mail addresses, phone and ID numbers masked, number of replacements)."""
    n = 0
    for rx, repl in _SCRUB:
        text, k = rx.subn(repl, text)
        n += k
    return text, n


def mask_chinese(text: str, keep: List[str]) -> Tuple[str, int]:
    """Chinese text masked (raw or \\u-escaped), except runs that are exactly a Chinese run of one
    of ``keep`` (a buyer's "小店" is masked even when an agent is called "前台-小店一号")."""
    kept = {run for k in keep if k for run in _CJK.findall(k)}
    n = 0

    def repl(m: "re.Match") -> str:
        nonlocal n
        if m.group(0) in kept:
            return m.group(0)
        n += 1
        return "***"
    return _CJK.sub(repl, text), n


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
    return "\n".join(hits[-lines:])


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
    masked = 0
    if what == "log_tail":
        if log_path is None:
            from utils.logger_helper import get_log_path
            log_path = Path(get_log_path())
        names = [m.get("name") or "" for m in members] + [m.get("id") or "" for m in members]
        text = log_tail(log_path, names, task.get("lines") or 200)
        keep = names + [s for m in members for s in (m.get("skills") or [])] + \
            [str(t.get(k) or "") for m in members for t in (m.get("tasks") or []) if isinstance(t, dict)
             for k in ("name", "skill")]
        text, masked = mask_chinese(text, keep)
    elif what == "file":
        if not task.get("path"):
            raise ValueError("status_diagnose file needs a path")
        text = read_file(Path(str(task["path"])), roots, task.get("lines") or 200)
    else:
        raise ValueError(f"unknown diagnosis {what!r} (log_tail | file)")
    text, n = scrub(text)
    n += masked
    raw = text.encode("utf-8")
    truncated = len(raw) > MAX_BYTES
    if truncated:
        text = raw[-MAX_BYTES:].decode("utf-8", errors="ignore")
    return {"what": what, "text": text, "scrubbed": n, "truncated": truncated}

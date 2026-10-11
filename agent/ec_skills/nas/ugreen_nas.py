"""UGREEN NAS (UGOS Pro) read/write over SMB.

A small, dependency-light engine the MCP tool and the browser-use action both
sit on top of. It writes to the NAS over SMB2/3 (``smbprotocol``'s
``smbclient``) -- no drive mapping, cross-platform.

Credentials are resolved at runtime and NEVER hard-coded, committed, or logged:

    1. Env vars ECAN_NAS_USER / ECAN_NAS_PASSWORD (preferred).
    2. Otherwise a credentials file (``user: ...`` / ``passwd: ...`` lines),
       path from ECAN_NAS_CREDS_FILE, else the first ``nas.txt`` found next to
       the project or in the user's home.

Target location (all overridable by env):

    host   ECAN_NAS_HOST   default 192.168.0.2
    share  ECAN_NAS_SHARE  default personal_folder
    base   ECAN_NAS_BASE   default chips/microchip   (relative paths join here)

Paths passed to the functions below are RELATIVE to ``base`` by default; pass
``relative_to_base=False`` to address the share root instead.

Uploads only take local files from known folders (``nas_upload``): the app's
``daily_work`` (browser downloads), the user's Downloads, and any folder listed
in ECAN_NAS_UPLOAD_ROOTS (``;``-separated, e.g. the chip crawler's docs root,
which ``ecan tasks chip-pilot`` adds). An agent steered by a web page can't
copy arbitrary files (credentials, the database) to the NAS.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

_DEFAULT_HOST = "192.168.0.2"
_DEFAULT_SHARE = "personal_folder"
_DEFAULT_BASE = "chips/microchip"

_session_lock = threading.Lock()
_session_ready: Dict[str, bool] = {}


# ── configuration ──────────────────────────────────────────────────────────

def _find_creds_file() -> Optional[Path]:
    env = os.getenv("ECAN_NAS_CREDS_FILE")
    if env and Path(env).is_file():
        return Path(env)
    candidates = [
        Path.cwd() / "nas.txt",
        Path.cwd().parent / "nas.txt",
        Path(__file__).resolve().parents[3].parent / "nas.txt",  # project parent
        Path.home() / "nas.txt",
    ]
    for c in candidates:
        try:
            if c.is_file():
                return c
        except Exception:
            continue
    return None


def _creds() -> tuple[str, str]:
    """(username, password). Env wins; otherwise parse a nas.txt-style file.
    Raises RuntimeError with a clear, secret-free message when unavailable."""
    user = os.getenv("ECAN_NAS_USER")
    pwd = os.getenv("ECAN_NAS_PASSWORD")
    if user and pwd:
        return user, pwd
    f = _find_creds_file()
    if f is not None:
        try:
            text = f.read_text(encoding="utf-8")
            u = re.search(r"user:\s*(\S+)", text)
            p = re.search(r"passwd:\s*(\S+)", text)
            if u and p:
                return u.group(1), p.group(1)
        except Exception as e:
            raise RuntimeError(f"NAS credentials file unreadable: {e}") from e
    raise RuntimeError(
        "NAS credentials not found. Set ECAN_NAS_USER / ECAN_NAS_PASSWORD, or "
        "provide a nas.txt (user:/passwd: lines) via ECAN_NAS_CREDS_FILE."
    )


def nas_configured() -> bool:
    """Credentials are available on this machine (env or a nas.txt). Without
    them the NAS actions aren't offered to browser agents at all."""
    if os.getenv("ECAN_NAS_USER") and os.getenv("ECAN_NAS_PASSWORD"):
        return True
    return _find_creds_file() is not None


def upload_roots() -> List[Path]:
    """Local folders files may be uploaded from (see the module docstring)."""
    roots: List[Path] = []
    try:
        from config.envi import getECBotDataHome
        roots.append(Path(getECBotDataHome()) / "daily_work")
    except Exception:
        pass
    roots.append(Path.home() / "Downloads")
    for part in re.split(r"[;\n]", os.getenv("ECAN_NAS_UPLOAD_ROOTS", "")):
        if part.strip():
            roots.append(Path(part.strip()))
    return roots


def _check_upload_source(lp: Path) -> None:
    try:
        real = lp.resolve()
    except Exception as e:
        raise PermissionError(f"local file not allowed for NAS upload: {lp} ({e})") from e
    for root in upload_roots():
        try:
            if real.is_relative_to(root.resolve()):
                return
        except Exception:
            continue
    raise PermissionError(
        f"local file not allowed for NAS upload: {lp} -- only files under the downloads folders "
        f"or ECAN_NAS_UPLOAD_ROOTS can be uploaded")


def nas_config() -> Dict[str, str]:
    return {
        "host": os.getenv("ECAN_NAS_HOST", _DEFAULT_HOST),
        "share": os.getenv("ECAN_NAS_SHARE", _DEFAULT_SHARE),
        "base": os.getenv("ECAN_NAS_BASE", _DEFAULT_BASE).strip("/\\"),
    }


# ── session + path helpers ─────────────────────────────────────────────────

def _ensure_session():
    cfg = nas_config()
    host = cfg["host"]
    with _session_lock:
        if _session_ready.get(host):
            return
        import smbclient  # imported lazily so the module imports without the dep
        user, pwd = _creds()
        smbclient.register_session(host, username=user, password=pwd)
        _session_ready[host] = True
        logger.info(f"[nas] SMB session registered for \\\\{host} as '{user}'")


def _unc(relpath: str = "", *, relative_to_base: bool = True) -> str:
    """Build a UNC path. ``relpath`` uses / or \\ separators; '..' is rejected."""
    cfg = nas_config()
    parts = [p for p in re.split(r"[\\/]+", str(relpath or "").strip()) if p]
    if any(p == ".." for p in parts):
        raise ValueError("NAS path must not contain '..'")
    prefix = PurePosixPath(cfg["base"]) if relative_to_base and cfg["base"] else PurePosixPath()
    rel = prefix.joinpath(*parts) if parts else prefix
    tail = str(rel).replace("/", "\\")
    root = rf"\\{cfg['host']}\{cfg['share']}"
    return f"{root}\\{tail}" if tail and tail != "." else root


# ── operations ─────────────────────────────────────────────────────────────

def nas_makedirs(reldir: str = "", *, relative_to_base: bool = True) -> str:
    """Create a directory (and parents) on the NAS. Idempotent. Returns the UNC."""
    _ensure_session()
    import smbclient
    path = _unc(reldir, relative_to_base=relative_to_base)
    try:
        smbclient.makedirs(path, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"NAS makedirs failed for '{reldir}': {e}") from e
    return path


def nas_write_bytes(relpath: str, data: bytes, *, relative_to_base: bool = True) -> Dict[str, Any]:
    """Write bytes to a file on the NAS, creating parent dirs. Overwrites."""
    _ensure_session()
    import smbclient
    path = _unc(relpath, relative_to_base=relative_to_base)
    parent = str(PurePosixPath(path.replace("\\", "/")).parent).replace("/", "\\")
    try:
        smbclient.makedirs(parent, exist_ok=True)
    except Exception:
        pass
    try:
        with smbclient.open_file(path, mode="wb") as f:
            f.write(data)
    except Exception as e:
        raise RuntimeError(f"NAS write failed for '{relpath}': {e}") from e
    return {"path": path, "bytes": len(data)}


def nas_write_text(relpath: str, text: str, *, encoding: str = "utf-8",
                   relative_to_base: bool = True) -> Dict[str, Any]:
    return nas_write_bytes(relpath, text.encode(encoding), relative_to_base=relative_to_base)


def nas_read_bytes(relpath: str, *, relative_to_base: bool = True) -> bytes:
    _ensure_session()
    import smbclient
    path = _unc(relpath, relative_to_base=relative_to_base)
    try:
        with smbclient.open_file(path, mode="rb") as f:
            return f.read()
    except Exception as e:
        raise RuntimeError(f"NAS read failed for '{relpath}': {e}") from e


def nas_read_text(relpath: str, *, encoding: str = "utf-8", relative_to_base: bool = True) -> str:
    return nas_read_bytes(relpath, relative_to_base=relative_to_base).decode(encoding, errors="replace")


def nas_upload(local_path: str, relpath: Optional[str] = None, *,
               relative_to_base: bool = True) -> Dict[str, Any]:
    """Upload a local file to the NAS. ``relpath`` defaults to the basename
    (placed under ``base``). Streams in chunks so large PDFs don't load fully
    into memory."""
    lp = Path(local_path)
    if not lp.is_file():
        raise FileNotFoundError(f"local file not found: {local_path}")
    _check_upload_source(lp)
    rel = relpath if relpath else lp.name
    _ensure_session()
    import smbclient
    path = _unc(rel, relative_to_base=relative_to_base)
    parent = str(PurePosixPath(path.replace("\\", "/")).parent).replace("/", "\\")
    try:
        smbclient.makedirs(parent, exist_ok=True)
    except Exception:
        pass
    total = 0
    try:
        with open(lp, "rb") as src, smbclient.open_file(path, mode="wb") as dst:
            while True:
                chunk = src.read(1024 * 256)
                if not chunk:
                    break
                dst.write(chunk)
                total += len(chunk)
    except Exception as e:
        raise RuntimeError(f"NAS upload failed for '{local_path}': {e}") from e
    return {"path": path, "bytes": total, "source": str(lp)}


def nas_list(reldir: str = "", *, relative_to_base: bool = True) -> List[Dict[str, Any]]:
    """List a directory. Returns [{name, is_dir, size}], empty list if the dir
    does not exist."""
    _ensure_session()
    import smbclient
    from smbprotocol.exceptions import SMBOSError
    path = _unc(reldir, relative_to_base=relative_to_base)
    out: List[Dict[str, Any]] = []
    try:
        for e in smbclient.scandir(path):
            try:
                is_dir = e.is_dir()
                size = 0 if is_dir else e.stat().st_size
            except Exception:
                is_dir, size = False, 0
            out.append({"name": e.name, "is_dir": is_dir, "size": size})
    except SMBOSError:
        return []
    except Exception as e:
        raise RuntimeError(f"NAS list failed for '{reldir}': {e}") from e
    return out


def nas_delete(relpath: str, *, relative_to_base: bool = True) -> Dict[str, Any]:
    """Delete a file on the NAS. Missing file is treated as success."""
    _ensure_session()
    import smbclient
    from smbprotocol.exceptions import SMBOSError
    path = _unc(relpath, relative_to_base=relative_to_base)
    try:
        smbclient.remove(path)
    except SMBOSError:
        return {"path": path, "deleted": False, "reason": "not found"}
    except Exception as e:
        raise RuntimeError(f"NAS delete failed for '{relpath}': {e}") from e
    return {"path": path, "deleted": True}


def nas_self_test() -> Dict[str, Any]:
    """Write -> read -> delete a probe file under ``base``. Returns a result
    dict; never raises (reports the failure instead)."""
    name = "_ecan_nas_selftest.txt"
    payload = "ecan nas self-test"
    try:
        nas_write_text(name, payload)
        back = nas_read_text(name)
        nas_delete(name)
        return {"ok": back == payload, "readback_match": back == payload,
                "target": _unc(name)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

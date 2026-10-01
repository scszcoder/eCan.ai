"""Read-only Windows process-memory scanner (platform primitive).

Business-agnostic mechanism for reading another process's memory **read-only**
and extracting candidate strings. A site bundle supplies the predicate/locator
that recognises its own message objects (e.g. the 千牛 sender-anchored scan);
this module knows nothing about any site.

Scope and boundaries (deliberate):
  * READ-ONLY. Opens the target with ``PROCESS_QUERY_INFORMATION |
    PROCESS_VM_READ`` only. No ``WriteProcessMemory``, no injection, no handle
    that could modify the target.
  * Windows-only. Every entry point no-ops / raises ``OSError`` elsewhere so
    callers degrade cleanly on mac/linux CI.

This is the net-new primitive flagged in docs/QIANNIU_PLUGIN_PLAN.md §2; it is
the mechanism, not a policy — see the bundle's ``mem_locator.py`` for the 千牛
schema and noise filter that decide which extracted strings are messages.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from utils.logger_helper import logger_helper as logger

_IS_WINDOWS = sys.platform == "win32"

# Win32 constants
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
# Readable protections (committed, non-guard, non-noaccess pages)
_READABLE = (0x02, 0x04, 0x08, 0x20, 0x40, 0x80)  # RO, RW, WC, EX-R, EX-RW, EX-WC


@dataclass
class MemoryRegion:
    base: int
    size: int
    protect: int


def available() -> bool:
    """True iff process-memory reading is supported on this platform."""
    return _IS_WINDOWS


def open_process_readonly(pid: int):
    """Open *pid* read-only. Returns a handle (int) or raises ``OSError``.

    Caller must ``close_handle`` the result.
    """
    if not _IS_WINDOWS:
        raise OSError("process-memory reading is Windows-only")
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    handle = k32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, int(pid)
    )
    if not handle:
        err = ctypes.get_last_error()
        raise OSError(f"OpenProcess({pid}) failed (winerror {err})")
    return handle


def close_handle(handle) -> None:
    if not _IS_WINDOWS or not handle:
        return
    import ctypes

    ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)


def iter_regions(handle) -> Iterator[MemoryRegion]:
    """Yield committed, readable memory regions of the opened process.

    Skips guard/no-access pages; only ``MEM_COMMIT`` regions with a readable
    protection are returned.
    """
    if not _IS_WINDOWS:
        return
    import ctypes
    from ctypes import wintypes

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", wintypes.DWORD),
            ("__alignment1", wintypes.DWORD),
            ("RegionSize", ctypes.c_size_t),
            ("State", wintypes.DWORD),
            ("Protect", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("__alignment2", wintypes.DWORD),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    k32.VirtualQueryEx.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p,
        ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t,
    ]

    mbi = MEMORY_BASIC_INFORMATION()
    addr = 0
    max_addr = 0x7FFFFFFFFFFF  # user-space ceiling on 64-bit Windows
    while addr < max_addr:
        got = k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                 ctypes.sizeof(mbi))
        if not got:
            break
        base = mbi.BaseAddress or 0
        size = int(mbi.RegionSize or 0)
        if size <= 0:
            break
        protect = int(mbi.Protect or 0)
        guarded = bool(protect & PAGE_GUARD) or bool(protect & PAGE_NOACCESS)
        readable = (protect & 0xFF) in _READABLE
        if mbi.State == MEM_COMMIT and readable and not guarded:
            yield MemoryRegion(base=int(base), size=size, protect=protect)
        addr = int(base) + size


def read_region(handle, region: MemoryRegion, max_bytes: int = 64 * 1024 * 1024) -> bytes:
    """Read a region's bytes read-only. Returns b"" on failure or over-size."""
    if not _IS_WINDOWS or region.size <= 0 or region.size > max_bytes:
        return b""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.ReadProcessMemory.restype = wintypes.BOOL
    k32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
    ]
    buf = ctypes.create_string_buffer(region.size)
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(handle, ctypes.c_void_p(region.base), buf,
                               region.size, ctypes.byref(read))
    if not ok:
        return b""
    return buf.raw[: read.value]


def scan_strings(
    pid: int,
    predicate: Callable[[bytes], bool],
    *,
    region_filter: Optional[Callable[[MemoryRegion], bool]] = None,
    max_region_bytes: int = 32 * 1024 * 1024,
) -> Iterator[bytes]:
    """Walk *pid*'s readable regions and yield raw region bytes that *predicate*
    accepts. The predicate (and any further decoding/locating) is the caller's
    — this module just delivers readable bytes cheaply and read-only.

    The caller decides UTF-8 vs UTF-16 decoding and how to carve message
    objects out of a region; keeping that out here is what keeps this file
    site-agnostic.
    """
    if not available():
        logger.warning("[win_mem] process-memory scan requested on a non-Windows host")
        return
    handle = None
    try:
        handle = open_process_readonly(pid)
        for region in iter_regions(handle):
            if region.size > max_region_bytes:
                continue
            if region_filter is not None and not region_filter(region):
                continue
            data = read_region(handle, region, max_bytes=max_region_bytes)
            if data and predicate(data):
                yield data
    finally:
        close_handle(handle)


def find_pid_by_process_name(name: str) -> Optional[int]:
    """First running pid whose process name matches *name* (case-insensitive),
    or None. Uses psutil (already a repo dependency)."""
    try:
        import psutil
    except Exception:
        logger.warning("[win_mem] psutil unavailable; cannot resolve pid by name")
        return None
    low = name.lower()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if pname == low or pname == low + ".exe":
                return int(proc.info["pid"])
        except Exception:
            continue
    return None

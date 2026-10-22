"""Cross-platform advisory file locking (``flock`` / ``msvcrt``).

Two callers need the same primitive:

* ``utils/task_lease.py`` -- serialise lease mutations across processes, so
  two workers cannot both decide "the lease is free" and both write one;
* ``utils/app_watchdog.py`` -- make the watchdog a singleton.

Why an OS lock rather than a lock *file*
----------------------------------------
The tempting design is "create the file to take the lock, delete it to
release it". It cannot survive a crash: the file outlives the process
that created it, so the next start finds a lock nobody holds. Every
variant of that scheme needs a staleness heuristic (is the pid alive?
has the TTL passed?), and every such heuristic is a guess that fails
exactly when it matters -- a process that died without cleaning up.

An advisory OS lock has no guess in it. The kernel owns the lock and
drops it when the holder dies, for any reason. "Can I take it?" has
exactly one answer, and the answer is always correct.

Byte 0 is the lock byte on Windows
----------------------------------
``msvcrt.locking`` takes a *byte range*, and a locked range cannot be
written by another handle -- so a caller that keeps metadata in the same
file must not put that metadata in byte 0. On POSIX ``flock`` does not
have this constraint, but the layout is kept identical on both platforms
so a file written on one is readable on the other.
"""
from __future__ import annotations

import errno
import os
import time
from pathlib import Path
from typing import Optional

#: How long to wait between attempts when the lock is contended.
LOCK_POLL_S = 0.02
#: The byte reserved for the lock itself. Callers keep their payload
#: starting at byte 1.
LOCK_BYTE = 0
#: Where the payload begins: the byte right after the reserved lock byte.
PAYLOAD_OFFSET = 1


def _try_lock(handle) -> Optional[bool]:
    """Try to take the lock on an open file.

    Returns True when the lock was taken, False when somebody else holds
    it, and None when this platform/filesystem cannot lock at all.

    The three outcomes are distinct on purpose: "contended" means "try
    again later", "unsupported" means "do not pretend to hold a lock".
    """
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(LOCK_BYTE)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        code = getattr(exc, "errno", None)
        if code in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
            return False            # somebody else holds it
        return None                 # locking is not available here
    except Exception:
        return None


def _unlock(handle) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(LOCK_BYTE)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


class FileLock:
    """An advisory exclusive lock backed by the OS.

    The lock is held by the *kernel*, not by the file: when the owning
    process dies the lock is released automatically, so a crashed holder
    never wedges the resource it was protecting.
    """

    def __init__(self, path) -> None:
        self.path = Path(path)
        self._handle = None

    # -- state ---------------------------------------------------------

    @property
    def held(self) -> bool:
        """True when this object currently holds the lock."""
        return self._handle is not None

    # -- acquire / release --------------------------------------------

    def acquire(self, timeout: float = 0.0) -> Optional[bool]:
        """Try to take the lock.

        Returns True when the lock was taken, False when it is held by
        somebody else (after waiting up to *timeout* seconds), and None
        when locking is unsupported on this platform or filesystem.

        ``None`` is not a failure to report to the caller as "not
        acquired": it means the caller should carry on *without* a lock,
        exactly as it did before this primitive existed.
        """
        if self._handle is not None:
            return True

        # NOT "a+b": append mode ignores the seek offset on every write,
        # so a payload written through this handle would be appended
        # rather than replacing the previous one. Open for read/write
        # instead, creating the file only when it is not there yet.
        try:
            try:
                handle = open(self.path, "r+b")
            except FileNotFoundError:
                handle = open(self.path, "w+b")
        except Exception:
            return None

        # Windows needs at least one byte to lock. Keep byte 0 reserved
        # for the lock itself and never overwrite it.
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.seek(0)
                handle.write(b"\0")
                handle.flush()
        except Exception:
            pass

        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            result = _try_lock(handle)
            if result is True:
                self._handle = handle
                return True
            if result is None:
                self._close(handle)
                return None
            if time.monotonic() >= deadline:
                self._close(handle)
                return False
            time.sleep(LOCK_POLL_S)

    def release(self) -> None:
        """Release the lock (if held). Safe to call more than once.

        The lock *file* is deliberately left on disk. Deleting it would
        be a correctness bug, not housekeeping: a peer that already
        opened the same path and is waiting for the lock would go on
        locking the old inode, while a third caller creates a fresh file
        and locks that one instead -- two holders at once. The kernel
        drops the lock when the last handle closes; the empty file it
        leaves behind is inert.
        """
        handle, self._handle = self._handle, None
        if handle is None:
            return
        _unlock(handle)
        self._close(handle)

    @staticmethod
    def _close(handle) -> None:
        try:
            handle.close()
        except Exception:
            pass

    # -- payload ------------------------------------------------------

    def write_payload(self, payload: str) -> bool:
        """Write metadata after the lock byte, through the locked handle.

        Writing through the *same* handle avoids the trouble of a second
        handle on Windows, where a lock on one byte range can conflict
        with an unrelated handle's write.
        """
        handle = self._handle
        if handle is None:
            return False
        try:
            handle.seek(PAYLOAD_OFFSET)
            handle.write(payload.encode("utf-8"))
            handle.truncate()
            handle.flush()
            return True
        except Exception:
            return False

    def read_payload(self) -> Optional[str]:
        """Read the metadata stored after the lock byte."""
        handle = self._handle
        try:
            if handle is not None:
                handle.seek(PAYLOAD_OFFSET)
                raw = handle.read()
            else:
                with open(self.path, "rb") as fh:
                    fh.seek(PAYLOAD_OFFSET)
                    raw = fh.read()
        except Exception:
            return None
        if not raw.strip():
            return None
        return raw.decode("utf-8", errors="replace")

    # -- context manager ----------------------------------------------

    def __enter__(self) -> "FileLock":
        """Acquire the lock on entry.

        A failed acquire does not raise: callers read :attr:`held` (or the
        result of an explicit :meth:`acquire`) to decide whether the body
        may proceed.
        """
        self.acquire()
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()

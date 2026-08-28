#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Monitor — periodic RSS tracking, leak detection via tracemalloc snapshots.

Usage:
    from utils.memory_monitor import get_memory_monitor

    monitor = get_memory_monitor()
    monitor.start()          # begin background logging
    monitor.stop()           # stop background logging
    monitor.snapshot_diff()  # on-demand: compare current vs previous snapshot
    monitor.dump_top_objects()  # on-demand: show most common object types

Logs are written to {appdata}/runlogs/memory.log (separate from main app log).
Summary warnings also go to the main app logger when thresholds are exceeded.

Key metrics tracked:
    - Process RSS (Resident Set Size) every interval
    - RSS growth rate — warns if growth exceeds threshold
    - tracemalloc snapshot diffs — top allocations by file:line
    - Object type counts via objgraph (if installed)
"""

import os
import sys
import time
import logging
import threading
import tracemalloc
import gc
from typing import Optional, List, Dict, Any
from logging.handlers import RotatingFileHandler

import psutil

# Main app logger for warnings/errors visible in eCan.log
_app_logger = logging.getLogger('eCan.memory')

# Dedicated memory logger (writes to memory.log only)
_mem_logger = logging.getLogger('memory_monitor')
_mem_logger.propagate = False  # don't bubble up to root/app logger


def _live_chat_protect_env_mb() -> str:
    """Read the live-chat RSS protection threshold from the environment.

    Canonical knob: ``ECAN_RSS_LIVE_CHAT_PROTECT_MB``.  Falls back to any
    legacy site-branded spelling still set by operator run-scripts
    (``ECAN_RSS_<SITE>_PROTECT_MB``, single-token site name), so existing
    configs keep working.  utils/ must not import agent.* (cycle risk),
    hence this tiny local scan instead of live_chat_env().
    """
    import re
    val = os.getenv("ECAN_RSS_LIVE_CHAT_PROTECT_MB")
    if val is not None:
        return val
    pat = re.compile(r"^ECAN_RSS_[A-Z0-9]+_PROTECT_MB$")
    for key, value in os.environ.items():
        if pat.match(key):
            return value
    return "6000"


def _setup_mem_logger(log_dir: str):
    """Configure the dedicated memory.log file handler."""
    if _mem_logger.handlers:
        return  # already set up

    log_path = os.path.join(log_dir, 'memory.log')
    handler = RotatingFileHandler(
        log_path, maxBytes=20 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    ))
    _mem_logger.addHandler(handler)
    _mem_logger.setLevel(logging.DEBUG)


class MemoryMonitor:
    """Background memory usage tracker with leak detection."""

    def __init__(
        self,
        interval: int = 60,
        snapshot_interval: int = 300,
        rss_warn_mb: float = 1500,
        growth_warn_mb_per_min: float = 50,
        top_n: int = 15,
        enable_tracemalloc: bool = False,
        tracemalloc_frames: int = 5,
        rss_live_chat_protect_mb: Optional[float] = None,
        rss_protect_mb: Optional[float] = None,
        rss_critical_mb: Optional[float] = None,
    ):
        """
        Args:
            interval: Seconds between RSS checks (default 60).
            snapshot_interval: Seconds between tracemalloc snapshot diffs (default 300).
            rss_warn_mb: Warn when RSS exceeds this (MB).
            growth_warn_mb_per_min: Warn when RSS grows faster than this (MB/min).
            top_n: Number of top allocations to show in snapshot diffs.
            enable_tracemalloc: Enable tracemalloc (disabled by default — adds significant CPU overhead).
            tracemalloc_frames: Number of frames to capture when tracemalloc is enabled (default 5).
        """
        self.interval = interval
        self.snapshot_interval = snapshot_interval
        self.rss_warn_mb = rss_warn_mb
        self.growth_warn_mb_per_min = growth_warn_mb_per_min
        self.top_n = top_n
        try:
            self.rss_live_chat_protect_mb = float(
                rss_live_chat_protect_mb
                if rss_live_chat_protect_mb is not None
                else _live_chat_protect_env_mb()
            )
        except Exception:
            self.rss_live_chat_protect_mb = 6000.0
        try:
            self.rss_protect_mb = float(
                rss_protect_mb
                if rss_protect_mb is not None
                else os.getenv("ECAN_RSS_PROTECT_MB", "7500")
            )
        except Exception:
            self.rss_protect_mb = 7500.0
        try:
            self.rss_critical_mb = float(
                rss_critical_mb
                if rss_critical_mb is not None
                else os.getenv("ECAN_RSS_CRITICAL_MB", "9000")
            )
        except Exception:
            self.rss_critical_mb = 9000.0
        if self.rss_critical_mb < self.rss_protect_mb:
            self.rss_critical_mb = self.rss_protect_mb
        if self.rss_live_chat_protect_mb > self.rss_protect_mb:
            self.rss_live_chat_protect_mb = self.rss_protect_mb
        self._rss_live_chat_protect_fired = False
        self._rss_protect_fired = False
        self._rss_critical_fired = False

        self._process = psutil.Process(os.getpid())
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started = False

        # RSS history for growth detection: list of (timestamp, rss_mb)
        self._rss_history: List[tuple] = []
        self._max_history = 60  # keep last 60 data points

        # tracemalloc state
        self._prev_snapshot: Optional[tracemalloc.Snapshot] = None
        self._baseline_snapshot: Optional[tracemalloc.Snapshot] = None
        self._last_snapshot_time: float = 0
        self._tracemalloc_enabled = False
        self._enable_tracemalloc = enable_tracemalloc
        self._tracemalloc_frames = tracemalloc_frames

        # Thread-category snapshot for delta detection.  Keys are
        # category labels (extracted from ``Thread.name`` via
        # :meth:`_thread_category`); values are last-seen counts.
        self._prev_thread_categories: Dict[str, int] = {}
        self._thread_breakdown_first_seen: Dict[str, int] = {}
        # Periodic full-census: re-log the *entire* thread breakdown (not
        # just deltas) every N checks, so memory.log always has a recent
        # "here's the full thread map" snapshot even when nothing changed.
        self._thread_breakdown_check_count: int = 0
        try:
            self._thread_breakdown_full_every = max(
                1, int(os.getenv("ECAN_THREAD_CENSUS_EVERY_CHECKS", "20"))
            )
        except Exception:
            self._thread_breakdown_full_every = 20
        # ws180 gc-census state (no-tracemalloc leak triage): previous
        # type->count histogram + last-run timestamp for throttling.
        self._census_counts: Dict[str, int] = {}
        self._last_census_ts: float = 0.0
        # tracemalloc: how often (in snapshot intervals) to also emit a
        # ``vs baseline`` diff (total growth since start) in addition to
        # the per-interval ``vs previous`` diff.
        self._snapshot_count: int = 0
        try:
            self._snapshot_baseline_every = max(
                1, int(os.getenv("ECAN_TRACEMALLOC_BASELINE_EVERY", "5"))
            )
        except Exception:
            self._snapshot_baseline_every = 5

    def start(self, log_dir: Optional[str] = None):
        """Start the background monitoring thread."""
        if self._started:
            _app_logger.warning('[MemoryMonitor] Already running')
            return

        # Resolve log dir
        if not log_dir:
            try:
                from config.app_info import app_info
                log_dir = os.path.join(app_info.appdata_path, 'runlogs')
            except Exception:
                log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'runlogs')
        os.makedirs(log_dir, exist_ok=True)
        _setup_mem_logger(log_dir)

        # Start tracemalloc only if explicitly enabled (adds significant CPU overhead)
        if self._enable_tracemalloc:
            if not tracemalloc.is_tracing():
                tracemalloc.start(self._tracemalloc_frames)
                self._tracemalloc_enabled = True
                _mem_logger.info(f'tracemalloc started ({self._tracemalloc_frames} frames)')
            else:
                self._tracemalloc_enabled = True
                _mem_logger.info('tracemalloc was already running')

            # Take baseline snapshot
            self._baseline_snapshot = tracemalloc.take_snapshot()
            self._prev_snapshot = self._baseline_snapshot
            self._last_snapshot_time = time.time()
        else:
            _mem_logger.info('tracemalloc disabled (use enable_tracemalloc=True to enable)')
            self._last_snapshot_time = time.time()

        # Log initial state
        mem = self._process.memory_info()
        rss_mb = mem.rss / (1024 * 1024)
        vms_mb = mem.vms / (1024 * 1024)
        _mem_logger.info(f'=== Memory Monitor Started === PID={os.getpid()} RSS={rss_mb:.1f}MB VMS={vms_mb:.1f}MB')
        _app_logger.info(f'[MemoryMonitor] Started — RSS={rss_mb:.1f}MB, logging to {log_dir}/memory.log')

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name='MemoryMonitor', daemon=True)
        self._thread.start()
        self._started = True

    def stop(self):
        """Stop the background monitoring thread."""
        if not self._started:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._started = False
        _mem_logger.info('=== Memory Monitor Stopped ===')
        _app_logger.info('[MemoryMonitor] Stopped')

    def _run_loop(self):
        """Main monitoring loop — runs in a daemon thread."""
        while not self._stop_event.is_set():
            try:
                self._check_rss()

                # Snapshot diff at longer intervals
                now = time.time()
                if now - self._last_snapshot_time >= self.snapshot_interval:
                    self.snapshot_diff()  # vs previous — incremental growth
                    self._snapshot_count += 1
                    # Periodically also diff vs the startup baseline so we see
                    # *total* growth since process start, not just deltas.
                    if (
                        self._tracemalloc_enabled
                        and self._snapshot_count % self._snapshot_baseline_every == 0
                    ):
                        try:
                            self.snapshot_diff(vs_baseline=True)
                        except Exception:
                            pass
                    self._last_snapshot_time = now

            except Exception as e:
                _mem_logger.error(f'Monitor loop error: {e}', exc_info=True)

            self._stop_event.wait(self.interval)

    def _check_rss(self):
        """Log current RSS and check thresholds."""
        try:
            mem = self._process.memory_info()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return

        rss_mb = mem.rss / (1024 * 1024)
        vms_mb = mem.vms / (1024 * 1024)
        now = time.time()

        # Thread count
        try:
            thread_count = self._process.num_threads()
        except Exception:
            thread_count = threading.active_count()

        # tracemalloc current/peak
        tm_current, tm_peak = 0, 0
        if self._tracemalloc_enabled:
            tm_current, tm_peak = tracemalloc.get_traced_memory()
            tm_current /= (1024 * 1024)
            tm_peak /= (1024 * 1024)

        _mem_logger.info(
            f'RSS={rss_mb:.1f}MB  VMS={vms_mb:.1f}MB  '
            f'traced={tm_current:.1f}MB  peak={tm_peak:.1f}MB  '
            f'threads={thread_count}'
        )

        # ── Thread-category breakdown (always on) ──
        # Confirmed live regression 2026-04-26 22:18-22:34: thread count
        # grew from 37 → 169 during a 16-minute customer run, while RSS
        # rose at 160 MB/min.  Per-name aggregation is essential to
        # pinpoint WHICH category is leaking (asyncio worker, MCP HTTP,
        # browser-use page session, qasync task, etc.) without needing
        # tracemalloc.  Cheap: ``threading.enumerate()`` is O(N) and
        # snapshot uses minimal per-thread metadata.
        #
        # Logging cadence: every check (default 30 s) but ONLY when a
        # category's count CHANGED since the previous check OR the
        # totals delta vs first-seen exceeds 10.  Prevents memory.log
        # from drowning under the same baseline categories.
        try:
            self._log_thread_breakdown(thread_count)
        except Exception as _tb_exc:
            _mem_logger.debug(f'thread breakdown skipped: {_tb_exc}')

        # Track history
        self._rss_history.append((now, rss_mb))
        if len(self._rss_history) > self._max_history:
            self._rss_history = self._rss_history[-self._max_history:]

        # Check absolute threshold
        if rss_mb > self.rss_warn_mb:
            msg = f'[MemoryMonitor] WARNING: RSS={rss_mb:.1f}MB exceeds threshold {self.rss_warn_mb}MB'
            _mem_logger.warning(msg)
            _app_logger.warning(msg)
            # First-warning forensic dump: identify the top retainers so we
            # can pinpoint the leak/structural-allocation source (skill build,
            # LLM client caches, prompt templates, etc.) without having to
            # reproduce the issue interactively. Guarded so we only dump once
            # per process lifetime to avoid log spam.
            if self._tracemalloc_enabled and not getattr(self, '_first_warn_dumped', False):
                self._first_warn_dumped = True
                try:
                    diff_text = self.snapshot_diff(vs_baseline=True)
                    by_file_text = self.snapshot_diff_by_file(vs_baseline=True)
                    _app_logger.warning(
                        f'[MemoryMonitor] First-warning forensic dump '
                        f'(RSS={rss_mb:.1f}MB). Top growers since baseline '
                        f'and by-file breakdown have been written to '
                        f'memory.log — search "tracemalloc diff (vs baseline)".'
                    )
                    _mem_logger.warning(
                        f'[MemoryMonitor] === FORENSIC DUMP at RSS={rss_mb:.1f}MB ===\n'
                        f'{diff_text}\n\n{by_file_text}'
                    )
                except Exception as _fd_err:
                    _mem_logger.warning(
                        f'[MemoryMonitor] Forensic dump failed (ignored): {_fd_err}'
                    )
            # ws180: no-tracemalloc census on the absolute-threshold warning too
            self._gc_type_census(rss_mb, trigger='rss_warn')

        if (
            self.rss_live_chat_protect_mb > 0
            and rss_mb >= self.rss_live_chat_protect_mb
            and not self._rss_live_chat_protect_fired
        ):
            self._rss_live_chat_protect_fired = True
            self._handle_live_chat_high_rss(rss_mb)

        if self.rss_protect_mb > 0 and rss_mb >= self.rss_protect_mb and not self._rss_protect_fired:
            self._rss_protect_fired = True
            self._handle_high_rss(rss_mb, critical=False)

        if self.rss_critical_mb > 0 and rss_mb >= self.rss_critical_mb and not self._rss_critical_fired:
            self._rss_critical_fired = True
            self._handle_high_rss(rss_mb, critical=True)

        # Check growth rate (need at least 5 data points spanning > 2 min)
        if len(self._rss_history) >= 5:
            t0, rss0 = self._rss_history[0]
            elapsed_min = (now - t0) / 60.0
            if elapsed_min > 2:
                growth_rate = (rss_mb - rss0) / elapsed_min
                if growth_rate > self.growth_warn_mb_per_min:
                    msg = (
                        f'[MemoryMonitor] WARNING: RSS growing at {growth_rate:.1f}MB/min '
                        f'({rss0:.1f}MB → {rss_mb:.1f}MB over {elapsed_min:.1f}min)'
                    )
                    _mem_logger.warning(msg)
                    _app_logger.warning(msg)
                    # ws180: name the growing types while the leak is live
                    self._gc_type_census(rss_mb, trigger='growth_rate')

        # Periodically dump global cache sizes (every 5 minutes) to track memory leaks
        if not hasattr(self, '_last_cache_dump_time'):
            self._last_cache_dump_time = now
        elif now - self._last_cache_dump_time >= 300:  # 5 minutes
            self.dump_global_caches()
            self._last_cache_dump_time = now

    def _gc_type_census(self, rss_mb: float, trigger: str, top_n: int = 20) -> None:
        """ws180: leak triage WITHOUT tracemalloc (which hooks every allocation —
        vetoed for perf). One O(N) pass over gc-tracked objects, count by type,
        diff vs the previous census, log the top growers to the MAIN app log so
        the histogram ships inside eCan.log (memory.log stays on the run box).

        Motivation: both 2026-07-16 runs leaked ~45MB/min and DIED at ~1.17GB
        RSS (~18min into a 1-vs-3 run) with no allocation-site evidence.

        Cost: a single list+loop over live objects (~0.5-1.5s at millions of
        objects), no per-allocation overhead, nothing stays enabled between
        calls. Fires only from the RSS warning branches and at most once per
        ECAN_MEM_CENSUS_MIN_GAP_S (default 240s). Kill: ECAN_MEM_CENSUS=0.
        """
        if os.getenv("ECAN_MEM_CENSUS", "1") == "0":
            return
        try:
            min_gap = float(os.getenv("ECAN_MEM_CENSUS_MIN_GAP_S", "240") or 240)
        except (TypeError, ValueError):
            min_gap = 240.0
        now = time.time()
        if now - self._last_census_ts < min_gap:
            return
        self._last_census_ts = now
        try:
            t0 = time.time()
            counts: Dict[str, int] = {}
            objs = gc.get_objects()
            total = len(objs)
            for o in objs:
                t = type(o)
                mod = t.__module__
                name = t.__name__ if mod in ("builtins", None) else f"{mod}.{t.__name__}"
                counts[name] = counts.get(name, 0) + 1
            del objs  # drop the giant list before doing anything else
            prev, self._census_counts = self._census_counts, counts
            took_ms = (time.time() - t0) * 1000.0
            if not prev:
                top = sorted(counts.items(), key=lambda kv: -kv[1])[:top_n]
                lines = [f"{n}={c}" for n, c in top]
                _app_logger.warning(
                    f"[MemoryMonitor] GC-CENSUS baseline (trigger={trigger} rss={rss_mb:.1f}MB "
                    f"objects={total} took={took_ms:.0f}ms) top-count: " + "  ".join(lines))
                return
            deltas = sorted(
                ((n, c, c - prev.get(n, 0)) for n, c in counts.items()),
                key=lambda x: -x[2])[:top_n]
            lines = [f"{n}={c}({d:+d})" for n, c, d in deltas if d > 0]
            _app_logger.warning(
                f"[MemoryMonitor] GC-CENSUS growers (trigger={trigger} rss={rss_mb:.1f}MB "
                f"objects={total} took={took_ms:.0f}ms) count(+delta): "
                + ("  ".join(lines) if lines else "none — leak is NOT gc-tracked Python "
                   "objects (suspect native buffers / bytes held by few objects)"))
        except Exception as _gce:
            _mem_logger.warning(f"[MemoryMonitor] gc census failed (ignored): {_gce}")

    def _handle_live_chat_high_rss(self, rss_mb: float) -> None:
        msg = (
            f"[MemoryMonitor] LIVE_CHAT_PROTECT: RSS={rss_mb:.1f}MB crossed "
            f"{self.rss_live_chat_protect_mb:.1f}MB; cooling live-chat CDP and "
            "releasing browser cache pressure"
        )
        _mem_logger.warning(msg)
        _app_logger.warning(msg)
        try:
            from utils.crash_boundary import set_crash_boundary_phase
            set_crash_boundary_phase(f"memory:live_chat_protect_rss_{rss_mb:.0f}mb")
        except Exception:
            pass
        try:
            # Runtime-only, cycle-safe: resolve the live-chat bundle's
            # runner bridge and open its site-send CDP health cooldown;
            # no-op when no live-chat bundle is loaded in this process.
            from agent.ec_skills import live_chat_dispatch as _lcd
            bridge = _lcd.runner_bridge()
            if bridge is not None:
                bridge.mark_cdp_unhealthy(f"high_rss:{rss_mb:.0f}mb")
        except Exception:
            pass
        try:
            from agent.ec_skills.browser_node import build_helpers as _bh
            removed = _bh.release_browser_cache_pressure(reason="memory_live_chat_protect", aggressive=False)
            _mem_logger.warning(f"[MemoryMonitor] live-chat browser cache pressure cleanup removed={removed}")
        except Exception as exc:
            _mem_logger.warning(f"[MemoryMonitor] live-chat browser cache pressure cleanup failed: {exc}")
        try:
            collected = gc.collect()
            _mem_logger.warning(f"[MemoryMonitor] live-chat gc.collect reclaimed={collected}")
        except Exception:
            pass

    def _handle_high_rss(self, rss_mb: float, *, critical: bool) -> None:
        level = "CRITICAL" if critical else "PROTECT"
        msg = (
            f"[MemoryMonitor] {level}: RSS={rss_mb:.1f}MB crossed "
            f"{self.rss_critical_mb if critical else self.rss_protect_mb:.1f}MB; "
            "running self-protection cleanup"
        )
        _mem_logger.warning(msg)
        _app_logger.warning(msg)
        try:
            from utils.crash_boundary import set_crash_boundary_phase
            set_crash_boundary_phase(f"memory:{level.lower()}_rss_{rss_mb:.0f}mb")
        except Exception:
            pass
        try:
            from agent.ec_skills.browser_node import build_helpers as _bh
            removed = _bh.release_browser_cache_pressure(reason=f"memory_{level.lower()}", aggressive=critical)
            _mem_logger.warning(f"[MemoryMonitor] browser cache pressure cleanup removed={removed}")
        except Exception as exc:
            _mem_logger.warning(f"[MemoryMonitor] browser cache pressure cleanup failed: {exc}")

        # Clean up WebEngine profile cache (QtWebEngine is known to leak memory)
        try:
            cleaned = self._cleanup_webengine_memory()
            if cleaned:
                _mem_logger.warning(f"[MemoryMonitor] WebEngine memory cleanup triggered")
        except Exception as web_exc:
            _mem_logger.warning(f"[MemoryMonitor] WebEngine cleanup failed: {web_exc}")

        # Clean up build_node module caches
        try:
            from agent.ec_skills import build_node
            if hasattr(build_node, '_cleanup_build_node_caches'):
                removed = build_node._cleanup_build_node_caches()
                if removed:
                    _mem_logger.warning(f"[MemoryMonitor] build_node caches cleaned: {removed}")
        except Exception as build_exc:
            _mem_logger.debug(f"[MemoryMonitor] build_node cache cleanup skipped: {build_exc}")

        try:
            collected = gc.collect()
            _mem_logger.warning(f"[MemoryMonitor] gc.collect reclaimed={collected}")
        except Exception:
            pass

    # ── Thread-category breakdown (always on, no tracemalloc dependency) ──

    @staticmethod
    def _thread_category(name: str) -> str:
        """Bucket a ``Thread.name`` into a stable category label.

        Many of eCan's leaking threads are auto-named with worker indices
        (e.g. ``ThreadPoolExecutor-2_3``, ``SkillExec_7``, ``asyncio_4``,
        ``BrowserSession-Loop-12345``).  Indices and addresses change every
        run, so we strip them down to the prefix to make per-run trends
        comparable.

        Conservative rules:
        * ``ThreadPoolExecutor-N_M`` → ``ThreadPoolExecutor``
        * ``Anything-NNNN`` (>=4 digit suffix) → ``Anything``
        * ``Foo_<digits>`` → ``Foo``
        * ``RepeatingTimerLoop`` / ``MemoryMonitor`` etc. → unchanged
        * Empty / ``MainThread`` → unchanged
        """
        if not name:
            return '<unnamed>'
        # ThreadPoolExecutor-N_M -> ThreadPoolExecutor
        # SkillExec_7 -> SkillExec
        # asyncio_0 -> asyncio
        import re as _re
        # Strip trailing _<digits>(_<digits>)*
        stripped = _re.sub(r'(_\d+)+$', '', name)
        # Strip trailing -<long-digits> (object id / port / pid)
        stripped = _re.sub(r'-\d{4,}$', '', stripped)
        # ThreadPoolExecutor-N_M handled by both rules above; trim
        # anything left over after a dash if it's now empty.
        return stripped or name

    def _log_thread_breakdown(self, total: int) -> None:
        """Aggregate live threads by category and log when something CHANGED.

        First call after start() establishes the baseline (always logged
        in full so we know what 'normal' looks like).  Subsequent calls
        log a delta line listing only categories whose count changed,
        followed by the new total.  This keeps memory.log compact while
        making leaks visible immediately.
        """
        # Build current snapshot.
        live = threading.enumerate()
        cur: Dict[str, int] = {}
        for t in live:
            cat = self._thread_category(t.name)
            cur[cat] = cur.get(cat, 0) + 1

        self._thread_breakdown_check_count += 1

        def _full_census(label: str) -> None:
            sorted_cats = sorted(cur.items(), key=lambda kv: -kv[1])
            pretty = ', '.join(f'{name}={count}' for name, count in sorted_cats[:25])
            extra = len(sorted_cats) - 25
            if extra > 0:
                pretty += f', …(+{extra} more categories)'
            _mem_logger.info(f'{label} ({total} total): {pretty}')

        # First check: log full breakdown as baseline.
        if not self._prev_thread_categories:
            self._prev_thread_categories = dict(cur)
            self._thread_breakdown_first_seen = dict(cur)
            _full_census('thread-baseline')
            return

        # Periodic full census (every Nth check ≈ a few minutes), so
        # memory.log always has a recent complete picture, not just deltas.
        if self._thread_breakdown_check_count % self._thread_breakdown_full_every == 0:
            _full_census('thread-census')

        # Compute deltas vs previous check + vs first-seen.
        all_cats = set(cur) | set(self._prev_thread_categories)
        deltas_now: List[tuple] = []   # (cat, prev, curr, delta_now)
        deltas_first: List[tuple] = []  # (cat, first, curr, delta_first)
        for cat in all_cats:
            prev = self._prev_thread_categories.get(cat, 0)
            curr = cur.get(cat, 0)
            first = self._thread_breakdown_first_seen.get(cat, 0)
            if curr != prev:
                deltas_now.append((cat, prev, curr, curr - prev))
            if curr - first >= 5:
                # Cumulative growth flag: this category has at least 5
                # more live threads than at first-seen.  Strong leak signal.
                deltas_first.append((cat, first, curr, curr - first))

        # Update snapshot for next round.
        self._prev_thread_categories = dict(cur)

        # Skip logging when nothing changed (steady state).
        if not deltas_now and not deltas_first:
            return

        if deltas_now:
            deltas_now.sort(key=lambda r: -abs(r[3]))
            tick = ', '.join(
                f'{c}:{p}->{n}({d:+d})' for c, p, n, d in deltas_now[:10]
            )
            _mem_logger.info(f'thread-delta tick ({total} total): {tick}')

        if deltas_first:
            deltas_first.sort(key=lambda r: -r[3])
            cum = ', '.join(
                f'{c}:+{d}/since-start (first={f}, now={n})'
                for c, f, n, d in deltas_first[:10]
            )
            _mem_logger.warning(
                f'[MemoryMonitor] thread-leak suspects ({total} total): {cum}'
            )

    def snapshot_diff(self, vs_baseline: bool = False) -> str:
        """Take a tracemalloc snapshot and diff against previous (or baseline).

        Returns a human-readable diff string.
        """
        if not self._tracemalloc_enabled:
            return 'tracemalloc not enabled'

        current = tracemalloc.take_snapshot()
        # Filter out importlib and tracemalloc internals
        current = current.filter_traces([
            tracemalloc.Filter(False, '<frozen importlib._bootstrap>'),
            tracemalloc.Filter(False, '<frozen importlib._bootstrap_external>'),
            tracemalloc.Filter(False, tracemalloc.__file__),
        ])

        compare_to = self._baseline_snapshot if vs_baseline else self._prev_snapshot
        label = 'vs baseline' if vs_baseline else 'vs previous'

        if compare_to is None:
            self._prev_snapshot = current
            return 'No previous snapshot to compare'

        stats = current.compare_to(compare_to, 'lineno')

        lines = [f'--- tracemalloc diff ({label}) — top {self.top_n} growing allocations ---']
        for i, stat in enumerate(stats[:self.top_n]):
            lines.append(
                f'  #{i+1}  {stat.traceback}  '
                f'size={stat.size / 1024:.1f}KB  '
                f'delta={stat.size_diff / 1024:+.1f}KB  '
                f'count={stat.count}  delta_count={stat.count_diff:+d}'
            )

        # Total
        total_size = sum(s.size for s in stats)
        total_diff = sum(s.size_diff for s in stats)
        lines.append(
            f'  TOTAL: {total_size / (1024*1024):.1f}MB  '
            f'delta={total_diff / (1024*1024):+.1f}MB  '
            f'({len(stats)} entries)'
        )

        result = '\n'.join(lines)
        _mem_logger.info(result)

        # Warn in main log if significant growth
        if total_diff > 10 * 1024 * 1024:  # > 10MB growth
            _app_logger.warning(
                f'[MemoryMonitor] Significant memory growth: {total_diff / (1024*1024):+.1f}MB '
                f'({label}). Check memory.log for details.'
            )

        self._prev_snapshot = current
        return result

    def snapshot_diff_by_file(self, vs_baseline: bool = False) -> str:
        """Like snapshot_diff but grouped by filename — easier to spot leaky modules."""
        if not self._tracemalloc_enabled:
            return 'tracemalloc not enabled'

        current = tracemalloc.take_snapshot()
        current = current.filter_traces([
            tracemalloc.Filter(False, '<frozen importlib._bootstrap>'),
            tracemalloc.Filter(False, '<frozen importlib._bootstrap_external>'),
        ])

        compare_to = self._baseline_snapshot if vs_baseline else self._prev_snapshot
        label = 'vs baseline' if vs_baseline else 'vs previous'

        if compare_to is None:
            self._prev_snapshot = current
            return 'No previous snapshot to compare'

        stats = current.compare_to(compare_to, 'filename')

        lines = [f'--- tracemalloc diff BY FILE ({label}) — top {self.top_n} ---']
        for i, stat in enumerate(stats[:self.top_n]):
            lines.append(
                f'  #{i+1}  {stat.traceback}  '
                f'size={stat.size / 1024:.1f}KB  '
                f'delta={stat.size_diff / 1024:+.1f}KB  '
                f'count={stat.count}'
            )

        result = '\n'.join(lines)
        _mem_logger.info(result)
        self._prev_snapshot = current
        return result

    def dump_top_objects(self, top_n: int = 20) -> str:
        """Show the most common object types in memory (requires objgraph)."""
        try:
            import objgraph
        except ImportError:
            msg = 'objgraph not installed — run: pip install objgraph'
            _mem_logger.warning(msg)
            return msg

        growth = objgraph.growth(limit=top_n, shortnames=True)
        if not growth:
            msg = 'No object growth detected since last call'
            _mem_logger.info(msg)
            return msg

        lines = ['--- Object growth (top types) ---']
        for name, count, delta in growth:
            lines.append(f'  {name:40s}  count={count:>8d}  delta={delta:+d}')

        result = '\n'.join(lines)
        _mem_logger.info(result)
        return result

    def dump_backrefs(self, type_name: str, max_depth: int = 5) -> str:
        """Show what's keeping objects of a given type alive (requires objgraph).

        Args:
            type_name: Class name to inspect, e.g. 'dict', 'EC_Agent', 'QWidget'.
            max_depth: How deep to traverse the reference chain.
        """
        try:
            import objgraph
        except ImportError:
            return 'objgraph not installed'

        objects = objgraph.by_type(type_name)
        if not objects:
            return f'No objects of type {type_name} found'

        # Pick a sample (the newest one)
        sample = objects[-1]
        import io
        buf = io.StringIO()
        objgraph.show_backrefs(
            sample, max_depth=max_depth, output=buf,
            too_many=10, shortnames=True
        )
        result = f'--- Backrefs for {type_name} (1 of {len(objects)}) ---\n{buf.getvalue()}'
        _mem_logger.info(result)
        return result

    def dump_global_caches(self) -> Dict[str, int]:
        """Log the sizes of critical global caches to help identify memory leaks.

        This method checks and logs the sizes of:
        - cached_bu_agents (browser-use agents, ~860MB each)
        - cached_browser_sessions
        - _cached_passive_agents
        - fieldLinks (network connections)
        - response_dict (pending async responses)

        Returns a dict with the cache names and their sizes.
        """
        cache_sizes: Dict[str, int] = {}

        # Browser automation caches
        try:
            from agent.ec_skills.browser_node import build_helpers as _bh
            cache_sizes['cached_bu_agents'] = len(_bh.cached_bu_agents)
            cache_sizes['cached_browser_sessions'] = len(_bh.cached_browser_sessions)
        except Exception:
            pass

        try:
            from agent.ec_skills.browser_node.session import _cached_passive_agents
            cache_sizes['_cached_passive_agents'] = len(_cached_passive_agents)
        except Exception:
            pass

        try:
            from agent.ec_skills.build_node import _cached_passive_agents as _bh_cpa
            cache_sizes['_cached_passive_agents (build_node)'] = len(_bh_cpa)
        except Exception:
            pass

        # Network connections
        try:
            from agent.network.network import fieldLinks
            cache_sizes['fieldLinks'] = len(fieldLinks)
        except Exception:
            pass

        # LocalServer response dict
        try:
            from gui.LocalServer import response_dict
            cache_sizes['response_dict'] = len(response_dict)
        except Exception:
            pass

        # WebSocket connections
        try:
            from gui.LocalServer import AppWebSocketManager
            ws_manager = AppWebSocketManager()
            cache_sizes['websocket_total_connections'] = len(ws_manager._all_connections)
            cache_sizes['websocket_channels'] = len(ws_manager._connections)
        except Exception:
            pass

        # Log the sizes
        cache_lines = [f'--- Global Cache Sizes ---']
        for name, size in sorted(cache_sizes.items()):
            cache_lines.append(f'  {name}: {size}')
            # Warn about suspicious sizes
            if 'bu_agents' in name and size > 6:
                _mem_logger.warning(f"[MemoryMonitor] WARNING: {name} has {size} entries (>6 is suspicious, each ~860MB)")
            elif 'browser_sessions' in name and size > 10:
                _mem_logger.warning(f"[MemoryMonitor] WARNING: {name} has {size} entries (>10 is suspicious)")

        _mem_logger.info('\n'.join(cache_lines))
        return cache_sizes

    def _cleanup_webengine_memory(self) -> bool:
        """Clean up QtWebEngine memory by clearing profile caches.

        This targets the specific leak source: QtWebEngine's HTTP cache,
        cookie store, and temp pages accumulating over time.

        Returns:
            True if cleanup was performed, False if no WebEngine found
        """
        cleaned = False

        # Try to clean WebEngine profile cache
        try:
            from app_context import AppContext
            web_gui = AppContext.get_web_gui()
            if web_gui and hasattr(web_gui, 'web_engine_view'):
                web_engine = web_gui.web_engine_view
                if hasattr(web_engine, 'clear_profile_cache'):
                    web_engine.clear_profile_cache()
                    cleaned = True
                    _mem_logger.info("[MemoryMonitor] WebEngine profile cache cleared")
        except Exception as e:
            _mem_logger.debug(f"[MemoryMonitor] WebEngine cleanup skipped: {e}")

        # Try to trigger cleanup on any BrowserAutomation sessions
        try:
            from agent.ec_skills.browser_node import build_helpers as _bh
            # Check if there are browser sessions that might hold temp pages
            if hasattr(_bh, 'cached_browser_sessions'):
                session_count = len(_bh.cached_browser_sessions)
                if session_count > 0:
                    _mem_logger.debug(f"[MemoryMonitor] {session_count} browser sessions active")
        except Exception:
            pass

        return cleaned

    def get_summary(self) -> Dict[str, Any]:
        """Return current memory stats as a dict (for API/IPC use)."""
        try:
            mem = self._process.memory_info()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {'error': 'process not accessible'}

        rss_mb = mem.rss / (1024 * 1024)
        vms_mb = mem.vms / (1024 * 1024)

        tm_current, tm_peak = 0, 0
        if self._tracemalloc_enabled:
            tm_current, tm_peak = tracemalloc.get_traced_memory()

        growth_rate = None
        if len(self._rss_history) >= 5:
            t0, rss0 = self._rss_history[0]
            elapsed_min = (time.time() - t0) / 60.0
            if elapsed_min > 1:
                growth_rate = round((rss_mb - rss0) / elapsed_min, 2)

        return {
            'rss_mb': round(rss_mb, 1),
            'vms_mb': round(vms_mb, 1),
            'traced_mb': round(tm_current / (1024 * 1024), 1),
            'traced_peak_mb': round(tm_peak / (1024 * 1024), 1),
            'growth_rate_mb_per_min': growth_rate,
            'threads': threading.active_count(),
            'rss_history_len': len(self._rss_history),
        }


# ── Singleton ──

_monitor: Optional[MemoryMonitor] = None


def get_memory_monitor(**kwargs) -> MemoryMonitor:
    """Get or create the singleton MemoryMonitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = MemoryMonitor(**kwargs)
    return _monitor


def start_memory_monitor(log_dir: Optional[str] = None, **kwargs) -> MemoryMonitor:
    """Convenience: create, configure, and start the monitor in one call."""
    monitor = get_memory_monitor(**kwargs)
    monitor.start(log_dir=log_dir)
    return monitor

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
from typing import Optional, List, Dict, Any
from logging.handlers import RotatingFileHandler

import psutil

# Main app logger for warnings/errors visible in eCan.log
_app_logger = logging.getLogger('eCan.memory')

# Dedicated memory logger (writes to memory.log only)
_mem_logger = logging.getLogger('memory_monitor')
_mem_logger.propagate = False  # don't bubble up to root/app logger


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
                    self.snapshot_diff()
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

        # Track history
        self._rss_history.append((now, rss_mb))
        if len(self._rss_history) > self._max_history:
            self._rss_history = self._rss_history[-self._max_history:]

        # Check absolute threshold
        if rss_mb > self.rss_warn_mb:
            msg = f'[MemoryMonitor] WARNING: RSS={rss_mb:.1f}MB exceeds threshold {self.rss_warn_mb}MB'
            _mem_logger.warning(msg)
            _app_logger.warning(msg)

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

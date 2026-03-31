"""IPC handlers for memory monitoring and diagnostics."""

import traceback
from typing import Any, Optional, Dict

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _get_monitor():
    from utils.memory_monitor import get_memory_monitor
    return get_memory_monitor()


@IPCHandlerRegistry.handler('get_memory_stats')
def handle_get_memory_stats(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get current memory usage summary.

    Returns:
        { rss_mb, vms_mb, traced_mb, traced_peak_mb, growth_rate_mb_per_min, threads }
    """
    try:
        monitor = _get_monitor()
        return create_success_response(request, monitor.get_summary())
    except Exception as e:
        logger.error(f"[memory_handler] Error: {e}")
        return create_error_response(request, 'MEMORY_ERROR', str(e))


@IPCHandlerRegistry.handler('memory_snapshot_diff')
def handle_memory_snapshot_diff(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Take a tracemalloc snapshot diff (vs previous or baseline).

    Params:
        vs_baseline: bool (optional, default false) — compare against startup baseline
        by_file: bool (optional, default false) — group by filename instead of line
    Returns:
        { diff: str }
    """
    try:
        monitor = _get_monitor()
        vs_baseline = (params or {}).get('vs_baseline', False)
        by_file = (params or {}).get('by_file', False)
        if by_file:
            diff = monitor.snapshot_diff_by_file(vs_baseline=vs_baseline)
        else:
            diff = monitor.snapshot_diff(vs_baseline=vs_baseline)
        return create_success_response(request, {'diff': diff})
    except Exception as e:
        logger.error(f"[memory_handler] Snapshot error: {e}")
        return create_error_response(request, 'MEMORY_ERROR', str(e))


@IPCHandlerRegistry.handler('memory_dump_objects')
def handle_memory_dump_objects(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Show top growing object types (requires objgraph).

    Params:
        top_n: int (optional, default 20)
    Returns:
        { dump: str }
    """
    try:
        monitor = _get_monitor()
        top_n = (params or {}).get('top_n', 20)
        dump = monitor.dump_top_objects(top_n=top_n)
        return create_success_response(request, {'dump': dump})
    except Exception as e:
        logger.error(f"[memory_handler] Dump error: {e}")
        return create_error_response(request, 'MEMORY_ERROR', str(e))

import hashlib
import asyncio
import json
import logging
import os
import shutil
import subprocess
import threading
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional, List
from pathlib import Path
from config.app_info import app_info
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionResult
from browser_use import BrowserSession, Controller
from agent.mcp.server.code_utils.code_tools import run_code, run_shell_script
from agent.ec_skills.live_chat_dispatch import live_chat_env
from agent.ec_skills.browser_use_extension.extension_tools_views import (
    ConvertFileFormatAction,
    DownloadFileAction,
    DiffNormalizedStateAction,
    DiscoverChatAdapterAction,
    ExtractDomAction,
    FileRenameAction,
    FilesPrintAction,
    GetSessionMonitorSnapshotAction,
    InspectDomRegionsAction,
    InstallChromeAction,
    LaunchChromeDebugAction,
    LabelInputFile,
    LabelsReformatAction,
    ListSessionMonitorsAction,
    SelectAgentsAction,
    NormalizePageStateAction,
    PersistSessionMonitorsToSkillAction,
    RagQueryAction,
    RagReplaceDocumentAction,
    RagifyAction,
    RagifyAsyncAction,
    RemoveSessionMonitorAction,
    ReconfigureEventMonitorAction,
    RunCodeAction,
    RunShellScriptAction,
    SendChatAction,
    SendEmailAction,
    SendSmsAction,
    UpsertSessionMonitorAction,
)

try:
    _CDP_EVALUATE_TIMEOUT_S = float(os.getenv("ECAN_CDP_EVALUATE_TIMEOUT_S", "6.0"))
except Exception:
    _CDP_EVALUATE_TIMEOUT_S = 6.0
try:
    _CDP_EVALUATE_TRACE_SLOW_MS = float(os.getenv("ECAN_CDP_EVALUATE_TRACE_SLOW_MS", "500"))
except Exception:
    _CDP_EVALUATE_TRACE_SLOW_MS = 500.0
_CDP_RUNTIME_ENABLE_BEFORE_EVALUATE = str(
    os.getenv("ECAN_CDP_RUNTIME_ENABLE_BEFORE_EVALUATE", "")
).strip().lower() in {"1", "true", "yes", "on"}
_CDP_EVALUATE_TRACE_ALL = str(
    os.getenv("ECAN_CDP_EVALUATE_TRACE_ALL", "")
).strip().lower() in {"1", "true", "yes", "on"}
try:
    _LIVE_CHAT_TARGET_RESOLVE_TIMEOUT_S = float(
        (live_chat_env("ECAN_LIVE_CHAT_TARGET_RESOLVE_TIMEOUT_S") or "2.0")
    )
except Exception:
    _LIVE_CHAT_TARGET_RESOLVE_TIMEOUT_S = 2.0
try:
    _LIVE_CHAT_SEND_CDP_TIMEOUT_COOLDOWN_S = max(
        0.0, float((live_chat_env("ECAN_LIVE_CHAT_SEND_CDP_TIMEOUT_COOLDOWN_S") or "3.0"))
    )
except Exception:
    _LIVE_CHAT_SEND_CDP_TIMEOUT_COOLDOWN_S = 3.0
try:
    # 2026-05-11 (flood-test fix): bumped 2 → 3.  The browser session is
    # *shared* between the front-desk agent loop, HOT-PATH-B direct
    # delivery, and the pre-dispatch DOM scrape — invalidating it on a
    # couple of transient eval timeouts blows away in-flight work for all
    # three.  Read-only callers (the scrape) now opt out of the recovery
    # signal entirely via ``read_only=True`` (see ``_evaluate_js``), so
    # this counter is dominated by write ops; 3 strikes is a saner bar.
    _CDP_EVALUATE_RECOVERY_THRESHOLD = max(
        0, int(os.getenv("ECAN_CDP_EVALUATE_RECOVERY_THRESHOLD", "3"))
    )
except Exception:
    _CDP_EVALUATE_RECOVERY_THRESHOLD = 3
try:
    # 2026-05-11 (flood-test fix): bumped 1 → 3.  One slow live-chat send eval
    # (17 KB JS on a hammered renderer can legitimately take >6s) should
    # not nuke the shared BrowserSession the moment it times out — that
    # produced the ``missing_browser_session`` cascade that knocked out
    # HOT-PATH-B for ~13 customers in the 2026-05-11 16:11 flood run.
    _LIVE_CHAT_CDP_EVALUATE_RECOVERY_THRESHOLD = max(
        0, int((live_chat_env("ECAN_LIVE_CHAT_CDP_EVALUATE_RECOVERY_THRESHOLD") or "3"))
    )
except Exception:
    _LIVE_CHAT_CDP_EVALUATE_RECOVERY_THRESHOLD = 3
try:
    # 2026-05-11: 25.0 → 8.0 → 4.0.  A single Runtime.evaluate timeout on
    # the live-chat send tool used to park every subsequent send for 25s (then
    # 8s), cascading into mass "tool_failed:<send tool> / 0
    # tool_success" windows.  During a 20-customer flood even an 8s global
    # send-freeze per timeout death-spirals; 4s keeps the protective wait
    # meaningful (lets a transient renderer blip pass) while letting the
    # direct-delivery queue drain within a single retry cycle.  The real
    # backstop is now the read-only-scrape / no-invalidate change plus the
    # focus-tax removal, not a long freeze.
    _LIVE_CHAT_CDP_HEALTH_COOLDOWN_S = max(
        0.0, float((live_chat_env("ECAN_LIVE_CHAT_CDP_HEALTH_COOLDOWN_S") or "4.0"))
    )
except Exception:
    _LIVE_CHAT_CDP_HEALTH_COOLDOWN_S = 4.0
try:
    # Per-label evaluate timeout for the site's send tool.  The send JS is
    # ~17 KB and has to poke the site's DOM, type the reply into the editor,
    # click send, and wait for the DOM to echo back — legitimately slow
    # when the renderer is loaded.  6s (the global default) is too tight
    # and trips false timeouts.  15s gives the happy-path plenty of
    # head-room while still surfacing real hangs.  All other evaluate
    # calls (including scrape) continue to use _CDP_EVALUATE_TIMEOUT_S.
    #
    # Fix 18 (2026-05-13): 15.0 → 22.0.  Round-2 of the 21:39 flood
    # stalled 11/12 customers with this exact error
    # ``CDP Runtime.evaluate timed out after 15.0s (phase=Runtime.evaluate)``.
    # The live-chat page accumulates more DOM / pending listeners as more
    # chats open, so the same JS that completes in 4-6 s during Round 1
    # routinely takes 12-18 s by Round 2.  22 s gives the loaded
    # renderer head-room; the new Fix 17 / Fix 18 retry path catches
    # any straggler that genuinely hangs.  Bump
    # ECAN_HOT_PATH_TOOL_TIMEOUT_S accordingly (default 25.0 from
    # hot_path.py) so the outer Python timeout never fires before the
    # CDP one does.
    # 2026-05-14: bumped 22 -> 45.  REVERTED on 2026-05-18 to 15.0
    # (v0.9.79 default) after the regression survey found this bump,
    # combined with the HOT_PATH_TOOL_TIMEOUT_S bump (8→50), was
    # capping success-path latency under sustained 1-on-8 chat load.
    # 2026-05-18 (later): re-raised 15 → 30.  The flood-test run at
    # 16:47-16:49 caught 客户04/05/09 with exactly this 15-s timeout
    # under 20-customer flood load, each triggering the 4-s shared
    # CDP-health cooldown that then dropped customers 12/06/17/19/02
    # back-to-back with cdp_timeout_cooldown_active errors.  30 s is
    # the middle ground: high enough to absorb page contention from
    # ~10 concurrent CDP evaluates, low enough that a genuinely hung
    # renderer doesn't stall the queue.  Product-listing / scrape
    # skills that genuinely need longer can still bump per-node via
    # state.metadata.browser_auto_overrides (the site bundle's send-timeout
    # override key — see runner_bridge.node_tunable_number_fields).
    _LIVE_CHAT_SEND_CDP_EVALUATE_TIMEOUT_S = max(
        1.0, float((live_chat_env("ECAN_LIVE_CHAT_SEND_CDP_EVALUATE_TIMEOUT_S") or "30.0"))
    )
except Exception:
    _LIVE_CHAT_SEND_CDP_EVALUATE_TIMEOUT_S = 30.0
try:
    # Per-family evaluate timeout for any live-chat site trace_label that does
    # *not* set its own ``timeout_s``.  2026-05-11 11:45 reproduced a
    # cooldown cascade driven by the site's open-session tool (a tiny 1.6 KB
    # JS) timing out at 6.0s with ``session_ms=2995.8`` and
    # ``lock_wait_ms=1005.2`` — i.e. CDP session setup + operation-lock
    # contention ate 4s of the 6s budget before the evaluate could
    # complete.  That single timeout opened the 8s health cooldown,
    # which in turn rejected every subsequent open-session
    # call with the CDP-health-cooldown error and stalled 14+ customers
    # behind 3 unanswered ones.  12s lets a site evaluate absorb a
    # fully contended CDP setup (session_ms ≈ 3s + lock_wait ≈ 1-5s)
    # without false-positive timeouts that would re-arm the cooldown.
    # Non-site evaluates (e.g. the DOM scrape) keep the tight 6s
    # global default so they stay snappy.
    _LIVE_CHAT_CDP_EVALUATE_TIMEOUT_S = max(
        1.0, float((live_chat_env("ECAN_LIVE_CHAT_CDP_EVALUATE_TIMEOUT_S") or "12.0"))
    )
except Exception:
    _LIVE_CHAT_CDP_EVALUATE_TIMEOUT_S = 12.0
_CDP_EVALUATE_TIMEOUT_RECOVERY_LOCK = threading.Lock()
_CDP_EVALUATE_TIMEOUT_RECOVERY: Dict[int, int] = {}
_LIVE_CHAT_SEND_CDP_TIMEOUT_LOCK = threading.Lock()
_LIVE_CHAT_SEND_CDP_TIMEOUT_UNTIL = 0.0
_LIVE_CHAT_CDP_HEALTH_LOCK = threading.Lock()
_LIVE_CHAT_CDP_HEALTH_UNHEALTHY_UNTIL = 0.0
_LIVE_CHAT_CDP_HEALTH_REASON = ""
from agent.ec_skills import live_chat_dispatch
from agent.ec_skills.label_utils.print_label import (
    print_labels_async,
    reformat_labels_async,
)

from agent.ec_skills.llm_utils.llm_utils import try_parse_json
from app_context import AppContext

# Create a shared controller with custom actions for browser_use
custom_controller = Controller()

# Global registry to track current agent instance for file path authorization
_current_agent_instance = None
_current_runtime_context: Dict[str, Any] = {}

# ── bu_send_chat dedup cache ──
# Prevents the same message from being dispatched to the same recipient for the
# same customer within a short time window.  Keyed on (recipient_id, customer_id);
# value is the timestamp of the last send.  Entries older than the window are
# lazily pruned on each check.
import time as _time
_SEND_CHAT_DEDUP_WINDOW_S = 60  # seconds, keyed on (recipient, customer)
_send_chat_dedup_cache: Dict[str, float] = {}  # key → timestamp

# Per-customer dispatch cache (ANY recipient). Used by front-desk
# actionable_items filter so a customer with an in-flight dispatch is not
# re-queued by the DOM monitor just because its pending_timer hasn't cleared
# yet (pending_timer only clears after the reply reaches the customer).
_SEND_CHAT_CUSTOMER_WINDOW_S = 45  # seconds (reduced from 90 — shorter recovery when responder fails)
_send_chat_customer_last: Dict[str, float] = {}  # customer_id → timestamp


def customer_recently_dispatched(customer_id: str, window_s: float = None) -> float:
    """Return seconds-since-last-dispatch for this customer if within window,
    else 0.0. Used by front-desk actionable_items filter (Fix A)."""
    if not customer_id:
        return 0.0
    window = window_s if window_s is not None else _SEND_CHAT_CUSTOMER_WINDOW_S
    now = _time.time()
    # Normalize: strip message-preview suffix (e.g. "sc|有紫色款吗？" → "sc")
    _norm_id = str(customer_id).strip()
    if "|" in _norm_id:
        _prefix = _norm_id.split("|", 1)[0].strip()
        if _prefix:
            _norm_id = _prefix
    last = _send_chat_customer_last.get(_norm_id)
    if last is None:
        return 0.0
    age = now - last
    if age < window:
        return age
    return 0.0



def set_current_agent(agent):
    """Set the current agent instance for fi
    le path authorization."""
    global _current_agent_instance
    _current_agent_instance = agent
    logger.debug(f"[ExtensionTools] Set current agent instance: {type(agent).__name__}")

def get_current_agent():
    """Get the current agent instance."""
    return _current_agent_instance


def _authorize_output_files_for_upload(file_paths: list[str]) -> None:
    """Allow converted files to be uploaded by browser-use upload tools."""
    if not file_paths:
        return
    agent = get_current_agent()
    if not agent or not hasattr(agent, "available_file_paths"):
        return
    if agent.available_file_paths is None:
        agent.available_file_paths = []
    for path in file_paths:
        if path not in agent.available_file_paths:
            agent.available_file_paths.append(path)


@custom_controller.action(
    "Download a remote file to a local path. Use for saving images or assets from URLs.",
    param_model=DownloadFileAction,
)
async def download_file(params: DownloadFileAction) -> ActionResult:
    url = (params.url or "").strip()
    path = (params.path or "").strip()
    if not url:
        return ActionResult(error="download_file: url is required")
    if not path:
        return ActionResult(error="download_file: path is required")

    # Try the requested path first
    out_dir = os.path.dirname(path)
    
    # Check if the requested directory is writable
    fallback_dir = None
    if out_dir and not _is_directory_writable(out_dir):
        # Fallback to system temp directory
        import tempfile
        fallback_dir = os.path.join(tempfile.gettempdir(), "ecan_images")
        logger.warning(
            f"[download_file] Requested directory '{out_dir}' is not writable. "
            f"Falling back to '{fallback_dir}'"
        )
        out_dir = fallback_dir
        path = os.path.join(out_dir, os.path.basename(path))
    
    try:
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # Some sources block requests without UA.
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 eCan-AI downloader"},
        )
        with urllib.request.urlopen(req, timeout=float(params.timeout or 30.0)) as r:
            data = r.read()
        with open(path, "wb") as wf:
            wf.write(data)

        _authorize_output_files_for_upload([path])
        result_msg = f"Downloaded file successfully: {url} -> {path} ({len(data)} bytes)"
        if fallback_dir:
            result_msg += f" (note: saved to fallback directory because {fallback_dir.replace(tempfile.gettempdir(), '$TMPDIR')} is writable)"
        return ActionResult(extracted_content=result_msg)
    except Exception as e:
        return ActionResult(error=f"download_file failed: {e}")


def _is_directory_writable(dir_path: str) -> bool:
    """Check if a directory is writable by attempting to create and remove a test file."""
    if not dir_path:
        return False
    test_file = os.path.join(dir_path, f".write_test_{os.getpid()}")
    try:
        os.makedirs(dir_path, exist_ok=True)
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception:
        return False


def _build_target_path(src: str, target_format: str, output_dir: Optional[str]) -> str:
    base_name = os.path.splitext(os.path.basename(src))[0]
    out_dir = output_dir or os.path.dirname(src)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{base_name}_converted.{target_format.lower()}")


def _normalize_ext(ext: str) -> str:
    e = (ext or "").strip().lower().lstrip(".")
    aliases = {
        "jpeg": "jpg",
        "markdown": "md",
    }
    return aliases.get(e, e)


def _collect_source_files(directory: str, source_format: str) -> list[str]:
    src_files: list[str] = []
    sf = _normalize_ext(source_format)
    for root, _, files in os.walk(directory):
        for name in files:
            ext = _normalize_ext(os.path.splitext(name)[1])
            if ext == sf:
                src_files.append(os.path.join(root, name))
    return src_files


def _convert_image_with_pillow(src: str, dst: str, target_format: str, quality: int) -> None:
    from PIL import Image  # type: ignore

    img = Image.open(src)
    fmt = target_format.upper()
    if fmt in ("JPG", "JPEG"):
        # JPEG cannot store alpha channel
        img = img.convert("RGB")
        img.save(dst, "JPEG", quality=quality)
        return
    if fmt == "PNG":
        img.save(dst, "PNG")
        return
    if fmt == "WEBP":
        img.save(dst, "WEBP", quality=quality)
        return
    raise ValueError(f"Unsupported image target format with Pillow: {target_format}")


def _convert_image_with_sips(src: str, dst: str, target_format: str) -> None:
    # macOS fallback converter when Pillow is unavailable.
    # sips supports common image conversions.
    cmd = ["sips", "-s", "format", target_format.lower(), src, "--out", dst]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "sips conversion failed")


@custom_controller.action(
    "Find Google Chrome on this computer (adding it to PATH when needed) and launch it "
    "with remote debugging enabled (CDP port, dedicated user-data-dir) so automation can "
    "connect — the user doesn't have to start Chrome manually. Returns JSON status "
    "already_running/launched/launch_timeout/not_installed. On not_installed, DO NOT "
    "install — ask the user for permission first, then use install_chrome.",
    param_model=LaunchChromeDebugAction,
)
async def launch_chrome_debug(params: LaunchChromeDebugAction) -> ActionResult:
    import asyncio as _asyncio
    from agent.mcp.server.chrome_launcher import launch_chrome_debug as _launch

    result = await _asyncio.to_thread(
        _launch, port=int(params.port or 9228),
        user_data_dir=(params.user_data_dir or "").strip())
    return _json_result(result)


@custom_controller.action(
    "Download and silently install Google Chrome. ONLY call after the user has "
    "EXPLICITLY agreed in the conversation (pass confirmed_by_user=true). "
    "Never install software unprompted. Can take several minutes.",
    param_model=InstallChromeAction,
)
async def install_chrome(params: InstallChromeAction) -> ActionResult:
    import asyncio as _asyncio
    from agent.mcp.server.chrome_launcher import install_chrome as _install

    if not params.confirmed_by_user:
        return _json_result({
            "status": "consent_required",
            "message": ("Refused: installing Chrome requires the user's explicit "
                        "permission. Ask the user, then call again with "
                        "confirmed_by_user=true."),
        })
    result = await _asyncio.to_thread(_install)
    return _json_result(result)


@custom_controller.action(
    "Convert one or more files to a target format. Use this when user asks things like "
    "'convert webp to jpg', 'turn png into jpg', 'convert all webp in a folder', "
    "or 'change file format'.",
    param_model=ConvertFileFormatAction,
)
async def convert_file_format(params: ConvertFileFormatAction) -> ActionResult:
    target_format = _normalize_ext(params.target_format or "")
    if not target_format:
        return ActionResult(error="target_format is required")

    source_files = list(params.source_files or [])
    if not source_files and params.directory and params.source_format:
        source_files = _collect_source_files(params.directory, params.source_format)
    if not source_files:
        return ActionResult(
            error=(
                "No source files provided. "
                "Pass source_files, or pass both directory and source_format."
            )
        )

    quality = max(1, min(100, int(params.quality or 90)))
    success_rows: list[str] = []
    error_rows: list[str] = []
    produced_files: list[str] = []

    image_exts = {"jpg", "jpeg", "png", "webp", "bmp", "gif", "tiff", "heic"}

    for src in source_files:
        try:
            if not os.path.exists(src):
                error_rows.append(f"{src} -> NOT_FOUND")
                continue

            src_ext = _normalize_ext(os.path.splitext(src)[1])
            dst = _build_target_path(src, target_format, params.output_dir)

            if src_ext in image_exts and target_format in {"jpg", "jpeg", "png", "webp"}:
                try:
                    _convert_image_with_pillow(src, dst, target_format, quality)
                except Exception:
                    # Fallback for environments without Pillow.
                    _convert_image_with_sips(src, dst, target_format)
            elif src_ext in {"txt", "md"} and target_format in {"txt", "md"}:
                # Plain-text conversions (txt<->md) are content-preserving.
                with open(src, "r", encoding="utf-8", errors="ignore") as rf:
                    content = rf.read()
                with open(dst, "w", encoding="utf-8") as wf:
                    wf.write(content)
            else:
                # Generic fallback: copy when same format was requested.
                # Keeps the extension API generic while clearly reporting unsupported transforms.
                if src_ext == target_format:
                    shutil.copy2(src, dst)
                else:
                    raise ValueError(f"Unsupported conversion: {src_ext} -> {target_format}")

            if not params.keep_original and src != dst:
                try:
                    os.remove(src)
                except Exception:
                    pass

            produced_files.append(dst)
            success_rows.append(f"{src} -> {dst}")
        except Exception as e:
            error_rows.append(f"{src} -> ERROR: {e}")

    _authorize_output_files_for_upload(produced_files)

    if success_rows and not error_rows:
        return ActionResult(
            extracted_content="Conversion completed:\n" + "\n".join(success_rows)
        )
    if success_rows and error_rows:
        return ActionResult(
            extracted_content=(
                "Conversion partially completed.\n"
                "Succeeded:\n" + "\n".join(success_rows) + "\n\n"
                "Failed:\n" + "\n".join(error_rows)
            )
        )
    return ActionResult(error="All conversions failed:\n" + "\n".join(error_rows))
def set_current_runtime_context(**kwargs):
    """Set runtime context for browser-use extension tools."""
    global _current_runtime_context
    _current_runtime_context = dict(kwargs or {})
    logger.debug(
        "[ExtensionTools] Set runtime context: "
        f"agent_id={_current_runtime_context.get('agent_id', '')}, "
        f"task_id={_current_runtime_context.get('task_id', '')}, "
        f"skill_name={_current_runtime_context.get('skill_name', '')}, "
        f"node_id={_current_runtime_context.get('node_id', '')}"
    )


def get_current_runtime_context() -> Dict[str, Any]:
    """Get runtime context for browser-use extension tools."""
    return dict(_current_runtime_context or {})


def _json_result(data: Any) -> ActionResult:
    return ActionResult(extracted_content=json.dumps(data, ensure_ascii=False, indent=2))


def _compact_monitor_summary_line(raw: Dict[str, Any]) -> str:
    item_id = str(raw.get("id") or raw.get("label") or "").strip() or "<unnamed>"
    label = str(raw.get("label") or "").strip() or "<no-label>"
    source_type = str(raw.get("sourceType") or raw.get("source_type") or "").strip() or "<unknown>"
    url_patterns = raw.get("urlPatterns") or raw.get("url_patterns") or []
    if isinstance(url_patterns, str):
        url_patterns = [v.strip() for v in url_patterns.split(",") if v.strip()]
    methods = raw.get("methods") or []
    if isinstance(methods, str):
        methods = [v.strip() for v in methods.split(",") if v.strip()]
    dom_selector = str(raw.get("domSelector") or "").strip()
    dom_interval = raw.get("domCheckIntervalMs")

    detail_bits = []
    if url_patterns:
        detail_bits.append(f"url_patterns={url_patterns}")
    if methods:
        detail_bits.append(f"methods={methods}")
    if dom_selector:
        detail_bits.append(f"dom_selector={dom_selector}")
    if dom_interval not in (None, ""):
        detail_bits.append(f"dom_interval_ms={dom_interval}")

    cdp_expr = str(raw.get("cdpFilterExpr") or raw.get("cdp_filter_expr") or "").strip()
    if cdp_expr:
        try:
            expr = json.loads(cdp_expr)
            page_url_patterns = expr.get("page_url_patterns") or []
            roots = expr.get("roots") or []
            item_selector = ""
            items = expr.get("items") or []
            if items and isinstance(items[0], dict):
                item_selector = str(items[0].get("selector") or "").strip()
            key_field = str(expr.get("key_field") or "").strip()
            identity = expr.get("identity") or {}
            key_fields = identity.get("key_fields") if isinstance(identity, dict) else None
            emit_on = str(expr.get("emit_on") or "").strip()
            if page_url_patterns:
                detail_bits.append(f"page_url_patterns={page_url_patterns}")
            if roots:
                detail_bits.append(f"roots={roots}")
            if item_selector:
                detail_bits.append(f"item_selector={item_selector}")
            if key_fields:
                detail_bits.append(f"key_fields={key_fields}")
            elif key_field:
                detail_bits.append(f"key_field={key_field}")
            if emit_on:
                detail_bits.append(f"emit_on={emit_on}")
        except Exception:
            detail_bits.append("extractor_json=<unparseable>")

    return f"- id={item_id}, label={label}, source_type={source_type}" + (
        f", {'; '.join(detail_bits)}" if detail_bits else ""
    )


def _compact_monitor_summary_text(snapshot: Dict[str, Any], include_configs: bool = True) -> str:
    lines = [
        "Session monitor summary:",
        f"- status={snapshot.get('status', 'unknown')}",
        f"- configured_count={snapshot.get('configured_count', 0)}",
        f"- active_count={snapshot.get('active_count', 0)}",
    ]
    if snapshot.get("queued_event_count") is not None:
        lines.append(f"- queued_event_count={snapshot.get('queued_event_count', 0)}")

    if include_configs:
        configs = snapshot.get("monitor_configs") or []
        if configs:
            lines.append("Configured monitors:")
            for cfg in configs:
                raw = (cfg or {}).get("raw") or cfg or {}
                if isinstance(raw, dict):
                    lines.append(_compact_monitor_summary_line(raw))
        else:
            lines.append("Configured monitors:\n- none")

    runtime = snapshot.get("instances") or {}
    if isinstance(runtime, dict) and runtime:
        lines.append("Runtime instances:")
        for monitor_id, instance in runtime.items():
            if not isinstance(instance, dict):
                continue
            rt_bits = [
                f"id={monitor_id}",
                f"label={instance.get('label', '')}",
                f"source_type={instance.get('source_type', '')}",
                f"status={instance.get('status', 'unknown')}",
            ]
            current_url = instance.get("current_url") or ""
            if current_url:
                rt_bits.append(f"current_url={current_url}")
            if instance.get("check_interval_ms") not in (None, 0, ""):
                rt_bits.append(f"check_interval_ms={instance.get('check_interval_ms')}")
            rt_bits.append(f"last_customer_count={instance.get('last_customer_count', 0)}")
            rt_bits.append(f"last_keys_count={instance.get('last_keys_count', 0)}")
            rt_bits.append(f"last_removed_count={instance.get('last_removed_count', 0)}")
            rt_bits.append(f"last_reordered_count={instance.get('last_reordered_count', 0)}")
            rt_bits.append(f"last_top_changed={instance.get('last_top_changed', False)}")
            lines.append("- " + ", ".join(rt_bits))

    return "\n".join(lines)


def _get_frontdesk_dispatch_latch(session: Any) -> Dict[str, Any]:
    state = getattr(session, "_ecan_frontdesk_dispatch_latch", None)
    if not isinstance(state, dict):
        state = {}
        setattr(session, "_ecan_frontdesk_dispatch_latch", state)
    return state


def _get_frontdesk_dispatch_state(session: Any) -> Dict[str, Any]:
    state = getattr(session, "_ecan_frontdesk_dispatch_state", None)
    if not isinstance(state, dict):
        state = {
            "assigned_sessions": {},
        }
        setattr(session, "_ecan_frontdesk_dispatch_state", state)
    return state


def _is_frontdesk_runtime_context() -> tuple[bool, str]:
    runtime_ctx = get_current_runtime_context()
    skill_name = str(runtime_ctx.get("skill_name") or "").strip()
    task_id = str(runtime_ctx.get("task_id") or "").strip()
    return (skill_name == "customer_front_desk"), task_id


def _extract_control_monitor_instance(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    instances = snapshot.get("instances") or {}
    if not isinstance(instances, dict):
        return {}
    for instance in instances.values():
        if not isinstance(instance, dict):
            continue
        if str(instance.get("label") or "").strip() != "conversation_became_active":
            continue
        return instance
    return {}


def _mark_frontdesk_dispatch_ready(session: Any, snapshot: Dict[str, Any], task_id: str) -> None:
    if not task_id:
        return
    latch = _get_frontdesk_dispatch_latch(session)
    instance = _extract_control_monitor_instance(snapshot)
    latch[task_id] = {
        "ready": True,
        "status": str(instance.get("status") or snapshot.get("status") or ""),
        "current_url": str(instance.get("current_url") or ""),
        "customer_count": int(instance.get("last_customer_count") or 0),
    }


def _extract_frontdesk_visible_sessions(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    instance = _extract_control_monitor_instance(snapshot)
    raw_items = instance.get("items") or []
    if not isinstance(raw_items, list):
        return []

    sessions: List[Dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        session_id = str(
            item.get("session")
            or item.get("session_id")
            or item.get("customer_id")
            or ""
        ).strip()
        if not session_id:
            continue
        customer_name = str(
            item.get("customer_name")
            or item.get("name")
            or item.get("customer")
            or ""
        ).strip()
        chat_url = str(item.get("chat_url") or "").strip() or f"http://127.0.0.1:9877/chat?session={session_id}"
        sessions.append({
            "customer_id": session_id,
            "session_id": session_id,
            "chat_url": chat_url,
            "customer_name": customer_name,
        })
    return sessions


def _find_frontdesk_open_tab_id(browser_session: BrowserSession, chat_url: str) -> str:
    try:
        sm = getattr(browser_session, "session_manager", None)
        all_targets = sm.get_all_targets() if sm else {}
        for tid, target in (all_targets or {}).items():
            if getattr(target, "target_type", "") not in ("page", "tab"):
                continue
            target_url = str(getattr(target, "url", "") or "").strip()
            if target_url == chat_url:
                return str(tid or "")
    except Exception:
        return ""
    return ""


def _maybe_frontdesk_auto_assign(snapshot: Dict[str, Any], browser_session: BrowserSession, task_id: str) -> Dict[str, Any]:
    is_frontdesk, runtime_task_id = _is_frontdesk_runtime_context()
    if not is_frontdesk or not runtime_task_id or runtime_task_id != task_id:
        return {"attempted": False}

    latch = _get_frontdesk_dispatch_latch(browser_session)
    latch_state = latch.get(task_id) if isinstance(latch, dict) else None
    if not isinstance(latch_state, dict) or not latch_state.get("ready"):
        return {"attempted": False}

    visible_sessions = _extract_frontdesk_visible_sessions(snapshot)
    if not visible_sessions:
        return {"attempted": False}

    runtime_ctx = get_current_runtime_context()
    sender_agent_id = str(runtime_ctx.get("agent_id") or "").strip()
    if not sender_agent_id:
        logger.info("[ExtensionTools] Front-desk auto-assign skipped: missing runtime sender agent id")
        return {"attempted": False, "reason": "missing_sender"}

    dispatch_state = _get_frontdesk_dispatch_state(browser_session)
    assigned_sessions = dispatch_state.setdefault("assigned_sessions", {})
    recipient_agent_id = "agent_b31f281332104b93"

    from agent.mcp.server.chat_utils.chat_tools import send_chat

    assigned_rows: List[str] = []
    failure_rows: List[str] = []
    tab_rows: List[str] = []
    pending_sessions: List[str] = []
    open_session_items: List[Tuple[Dict[str, Any], str]] = []

    for item in visible_sessions:
        session_id = item["session_id"]
        chat_url = item["chat_url"]
        tab_id = _find_frontdesk_open_tab_id(browser_session, chat_url)
        if tab_id:
            tab_rows.append(f"{session_id}->{tab_id[-4:]}")
            if not assigned_sessions.get(session_id):
                open_session_items.append((item, tab_id))
        else:
            if not assigned_sessions.get(session_id):
                pending_sessions.append(session_id)

    if not open_session_items and pending_sessions:
        logger.info(
            f"[ExtensionTools] Front-desk auto-assign waiting for tabs: "
            f"visible={len(visible_sessions)} tab_hits={len(tab_rows)} pending={len(pending_sessions)}"
        )
        return {
            "attempted": True,
            "visible_count": len(visible_sessions),
            "tab_rows": tab_rows,
            "assigned_rows": [],
            "failure_rows": [],
            "pending_sessions": pending_sessions,
            "waiting_for_tabs": True,
        }

    for item, tab_id in open_session_items:
        session_id = item["session_id"]
        chat_url = item["chat_url"]

        payload = {
            "customer_id": item["customer_id"],
            "session_id": session_id,
            "tab_id": tab_id,
            "chat_url": chat_url,
        }
        if item.get("customer_name"):
            payload["customer_name"] = item["customer_name"]

        result = send_chat(
            AppContext.login.main_win,
            {
                "sender_agent_id": sender_agent_id,
                "recipient_agent_id": recipient_agent_id,
                "chat_id": session_id,
                "message": json.dumps(payload, ensure_ascii=False),
                "message_type": "text",
                "async_send": False,
            },
        )
        if result.get("success"):
            assigned_sessions[session_id] = {
                "recipient_agent_id": recipient_agent_id,
                "message_id": str(result.get("message_id") or ""),
                "timestamp": int(result.get("timestamp") or 0),
            }
            assigned_rows.append(f"{session_id}->{recipient_agent_id[-6:]}")
        else:
            failure_rows.append(f"{session_id}: {result.get('error', 'assignment failed')}")

    if assigned_rows or failure_rows:
        logger.info(
            f"[ExtensionTools] Front-desk auto-assign: visible={len(visible_sessions)} "
            f"tab_hits={len(tab_rows)} assigned={len(assigned_rows)} "
            f"failures={len(failure_rows)} pending={len(pending_sessions)}"
        )

    return {
        "attempted": True,
        "visible_count": len(visible_sessions),
        "tab_rows": tab_rows,
        "assigned_rows": assigned_rows,
        "failure_rows": failure_rows,
        "pending_sessions": pending_sessions,
        "waiting_for_tabs": bool(pending_sessions),
    }


def _frontdesk_dispatch_notice(session: Any, task_id: str) -> str:
    if not task_id:
        return ""
    latch = _get_frontdesk_dispatch_latch(session)
    state = latch.get(task_id) if isinstance(latch, dict) else None
    if not isinstance(state, dict) or not state.get("ready"):
        return ""
    customer_count = int(state.get("customer_count") or 0)
    current_url = str(state.get("current_url") or "http://127.0.0.1:9877/control")
    status = str(state.get("status") or "ok")
    return (
        "CONTROL MONITOR ALREADY VALIDATED FOR THIS INVOCATION.\n"
        f"- current_url={current_url}\n"
        f"- runtime_status={status}\n"
        f"- visible_customer_count={customer_count}\n"
        "Dispatch phase is unlocked now.\n"
        "Do not call monitor-validation tools again in this invocation.\n"
        "Next allowed work is only:\n"
        "- extract actionable visible sessions\n"
        "- open required chat tabs\n"
        "- send assignments\n"
        "- done()\n"
    )


def _clip_text(value: str, limit: int) -> str:
    value = str(value or "").strip().replace("\r", " ").replace("\n", " ")
    return value if len(value) <= limit else (value[: limit - 3] + "...")


def _compact_dom_region_summary_text(summary: Dict[str, Any], max_regions: int = 8) -> str:
    """Return a compact DOM-region summary suitable for LLM context.

    Raw JSON with html snippets is expensive and caused large browser-use inputs.
    Keep only the structural hints the model actually uses for page reasoning.
    """
    if not isinstance(summary, dict):
        return json.dumps(summary, ensure_ascii=False)

    url = str(summary.get("url") or "")
    title = str(summary.get("title") or "")
    regions = summary.get("regions") or []
    if not isinstance(regions, list):
        regions = []

    lines = [
        "DOM region summary:",
        f"- url={url}",
        f"- title={title}",
        f"- region_count={len(regions)}",
    ]

    for idx, region in enumerate(regions[: max(1, min(max_regions, 8))]):
        if not isinstance(region, dict):
            continue
        bits = [
            f"path={region.get('path', '')}",
            f"tag={region.get('tag', '')}",
            f"score={region.get('score', 0)}",
            f"children={region.get('child_count', 0)}",
            f"clickable={region.get('clickable_children', 0)}",
            f"repeated={region.get('repeated_groups', 0)}",
            f"timestamps={region.get('timestamps', 0)}",
            f"avatars={region.get('avatars', 0)}",
            f"text={_clip_text(region.get('text_sample', ''), 140)}",
        ]
        html_hint = _clip_text(region.get("html_hint", ""), 100)
        if html_hint:
            bits.append(f"html_hint={html_hint}")
        lines.append(f"- [{idx}] " + "; ".join(bits))

    return "\n".join(lines)


def _read_json_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _iter_workflow_nodes(nodes: List[Dict[str, Any]]):
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        yield node
        for child in _iter_workflow_nodes(node.get("blocks") or []):
            yield child


def _find_node_by_id(nodes: List[Dict[str, Any]], node_id: str) -> Dict[str, Any] | None:
    for node in _iter_workflow_nodes(nodes):
        if str(node.get("id") or "") == str(node_id):
            return node
    return None


def _resolve_skill_file_paths(skill_name: str) -> tuple[Path, Path | None]:
    """Resolve skill file paths using unified resolution from extern_skills."""
    from agent.ec_skills.extern_skills.extern_skills import resolve_skill_diagram_dir
    
    diagram_dir = resolve_skill_diagram_dir(skill_name)
    skill_dir = diagram_dir.parent
    
    # Resolve core and bundle paths
    core_candidates = [
        diagram_dir / f"{skill_name}_skill.json",
        diagram_dir / f"{skill_name}.json",
    ]
    core_path = next((p for p in core_candidates if p.exists()), None)
    
    # Fallback: try glob patterns
    if not core_path and skill_dir.exists():
        core_path = next(iter(skill_dir.glob("*_skill.json")), None)
        if not core_path:
            core_path = next(iter(skill_dir.glob("*.json")), None)
    
    if not core_path:
        raise FileNotFoundError(f"Could not locate skill JSON for skill '{skill_name}' under {skill_dir}")
    
    bundle_candidates = [
        diagram_dir / f"{skill_name}_skill_bundle.json",
        diagram_dir / f"{skill_name}_bundle.json",
    ]
    bundle_path = next((p for p in bundle_candidates if p.exists()), None)
    
    return core_path, bundle_path


def _normalize_monitor_raw_for_skill(record_raw: Dict[str, Any]) -> Dict[str, Any]:
    raw = dict(record_raw or {})
    cleaned = {k: v for k, v in raw.items() if v not in (None, "")}
    if "source_type" in cleaned and "sourceType" not in cleaned:
        cleaned["sourceType"] = cleaned.pop("source_type")
    return cleaned


def _canonicalize_monitor_raw_for_skill(record_raw: Dict[str, Any]) -> Dict[str, Any]:
    raw = _normalize_monitor_raw_for_skill(record_raw)
    label = str(raw.get("label") or "").strip()
    if label != "chat_message_added":
        return raw

    enabled = raw.get("enabled")
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
    if enabled is None:
        enabled = True

    extractor_cfg = {
        "page_url_patterns": ["/chat?session="],
        "roots": ["#messages"],
        "item_selector": ".msg",
        "fields": {
            "msg_id": {"attr": "data-msg-id"},
            "from": {"attr": "data-from"},
            "text": {"text": True},
            "timestamp": {"attr": "data-ts"},
        },
        "key_field": "msg_id",
        "emit_on": "added",
        "filters": {"from_equals": "customer"},
    }
    # Apply canonicalized defaults for chat_message_added monitors:
    # preserve caller-supplied url_patterns (session-specific) but fill in
    # sensible defaults for fields the LLM typically leaves empty.
    raw.setdefault("sourceType", "dom_mutation")
    raw.setdefault("domSelector", "#messages")
    raw.setdefault("domChildList", True)
    raw.setdefault("domSubtree", True)
    raw.setdefault("domCheckIntervalMs", 2000)
    if not raw.get("cdpFilterExpr"):
        raw["cdpFilterExpr"] = json.dumps(extractor_cfg, ensure_ascii=False, separators=(",", ":"))
    return raw


def _dedupe_monitor_raws(raw_monitors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen_keys = set()
    for item in reversed(list(raw_monitors or [])):
        raw = _canonicalize_monitor_raw_for_skill(item or {})
        label = str(raw.get("label") or "").strip()
        item_id = str(raw.get("id") or "").strip()
        source_type = str(raw.get("sourceType") or raw.get("source_type") or "").strip()
        if label == "chat_message_added":
            key = ("label", label, source_type or "dom_mutation")
        else:
            key = ("id", item_id or label, source_type)
        if key in seen_keys:
            logger.warning(
                f"[ExtensionTools] Dropping duplicate monitor raw before apply: "
                f"id={item_id}, label={label}, source={source_type}"
            )
            continue
        seen_keys.add(key)
        deduped.append(raw)
    deduped.reverse()
    return deduped


def _update_skill_node_monitors(payload: Dict[str, Any], node_id: str, monitor_raws: List[Dict[str, Any]]) -> bool:
    workflow = payload.get("workFlow") if isinstance(payload, dict) else None
    if not isinstance(workflow, dict):
        return False
    node = _find_node_by_id(workflow.get("nodes") or [], node_id)
    if not node:
        return False
    data = node.setdefault("data", {})
    inputs_values = data.setdefault("inputsValues", {})
    inputs_values["eventMonitors"] = {"type": "constant", "content": monitor_raws}
    return True


def _update_bundle_node_monitors(bundle_payload: Dict[str, Any], node_id: str, monitor_raws: List[Dict[str, Any]]) -> bool:
    updated = False
    for sheet in bundle_payload.get("sheets") or []:
        document = (sheet or {}).get("document") or {}
        node = _find_node_by_id(document.get("nodes") or [], node_id)
        if not node:
            continue
        data = node.setdefault("data", {})
        inputs_values = data.setdefault("inputsValues", {})
        inputs_values["eventMonitors"] = {"type": "constant", "content": monitor_raws}
        updated = True
    return updated


def _build_monitor_raw_from_params(params: UpsertSessionMonitorAction) -> Dict[str, Any]:
    return {
        "id": (params.id or params.label or "").strip() or f"monitor_{params.source_type}",
        "label": params.label,
        "enabled": params.enabled,
        "sourceType": params.source_type,
        "urlPatterns": params.url_patterns,
        "methods": params.methods,
        "contentFilters": params.content_filters,
        "minBodyLength": params.min_body_length,
        "frameDirection": params.frame_direction,
        "sseEventTypes": params.sse_event_types,
        "domSelector": params.dom_selector,
        "domAttributes": params.dom_attributes,
        "domChildList": params.dom_child_list,
        "domSubtree": params.dom_subtree,
        "domCheckIntervalMs": params.dom_check_interval_ms,
        "cdpDomain": params.cdp_domain,
        "cdpEventMethod": params.cdp_event_method,
        "cdpFilterExpr": params.extractor_json or "",
    }


def _stable_hash(parts: List[str]) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _safe_pending_request_count(cdp_client: Any) -> int:
    try:
        pending = getattr(cdp_client, "pending_requests", None)
        return len(pending) if pending is not None else -1
    except Exception:
        return -1


def _prune_cdp_pending_requests(cdp_client: Any) -> int:
    try:
        pending = getattr(cdp_client, "pending_requests", None)
        if not isinstance(pending, dict):
            return 0
        pruned = 0
        for key, future in list(pending.items()):
            done = getattr(future, "done", None)
            cancelled = getattr(future, "cancelled", None)
            if (
                (callable(cancelled) and bool(cancelled()))
                or (callable(done) and bool(done()))
            ):
                pending.pop(key, None)
                pruned += 1
        return pruned
    except Exception:
        return 0


def _live_chat_trace_label(label: str) -> bool:
    """True when ``label`` belongs to the live-chat site's tool family.

    The site bundle exposes its trace-label prefix on the runner bridge
    (``trace_label_prefix``); with no live-chat bundle loaded there are no
    site trace labels, so this returns False.
    """
    text = str(label or "")
    if not text:
        return False
    try:
        bridge = live_chat_dispatch.runner_bridge()
        prefix = str(getattr(bridge, "trace_label_prefix", "") or "")
    except Exception:
        return False
    return bool(prefix) and text.startswith(prefix)


def _live_chat_send_cdp_timeout_remaining() -> float:
    now = _time.monotonic()
    with _LIVE_CHAT_SEND_CDP_TIMEOUT_LOCK:
        remaining = _LIVE_CHAT_SEND_CDP_TIMEOUT_UNTIL - now
    return remaining if remaining > 0.0 else 0.0


def _record_live_chat_send_cdp_timeout() -> float:
    global _LIVE_CHAT_SEND_CDP_TIMEOUT_UNTIL
    if _LIVE_CHAT_SEND_CDP_TIMEOUT_COOLDOWN_S <= 0.0:
        return 0.0
    now = _time.monotonic()
    with _LIVE_CHAT_SEND_CDP_TIMEOUT_LOCK:
        _LIVE_CHAT_SEND_CDP_TIMEOUT_UNTIL = max(
            _LIVE_CHAT_SEND_CDP_TIMEOUT_UNTIL,
            now + _LIVE_CHAT_SEND_CDP_TIMEOUT_COOLDOWN_S,
        )
        return max(0.0, _LIVE_CHAT_SEND_CDP_TIMEOUT_UNTIL - now)


def _record_live_chat_send_cdp_success() -> None:
    global _LIVE_CHAT_SEND_CDP_TIMEOUT_UNTIL
    with _LIVE_CHAT_SEND_CDP_TIMEOUT_LOCK:
        _LIVE_CHAT_SEND_CDP_TIMEOUT_UNTIL = 0.0


def live_chat_cdp_health_cooldown_remaining() -> float:
    now = _time.monotonic()
    with _LIVE_CHAT_CDP_HEALTH_LOCK:
        remaining = _LIVE_CHAT_CDP_HEALTH_UNHEALTHY_UNTIL - now
    return remaining if remaining > 0.0 else 0.0


def mark_live_chat_cdp_unhealthy(reason: str = "", *, cooldown_s: float | None = None) -> float:
    global _LIVE_CHAT_CDP_HEALTH_REASON
    global _LIVE_CHAT_CDP_HEALTH_UNHEALTHY_UNTIL
    cooldown = _LIVE_CHAT_CDP_HEALTH_COOLDOWN_S if cooldown_s is None else max(0.0, float(cooldown_s))
    if cooldown <= 0.0:
        return 0.0
    now = _time.monotonic()
    until = now + cooldown
    with _LIVE_CHAT_CDP_HEALTH_LOCK:
        _LIVE_CHAT_CDP_HEALTH_UNHEALTHY_UNTIL = max(_LIVE_CHAT_CDP_HEALTH_UNHEALTHY_UNTIL, until)
        if reason:
            _LIVE_CHAT_CDP_HEALTH_REASON = str(reason)
        remaining = _LIVE_CHAT_CDP_HEALTH_UNHEALTHY_UNTIL - now
    logger.warning(
        f"[LIVE-CHAT] CDP health cooldown active for {remaining:.1f}s "
        f"reason={_LIVE_CHAT_CDP_HEALTH_REASON!r}"
    )
    return remaining if remaining > 0.0 else 0.0


def mark_live_chat_cdp_healthy() -> None:
    global _LIVE_CHAT_CDP_HEALTH_REASON
    global _LIVE_CHAT_CDP_HEALTH_UNHEALTHY_UNTIL
    with _LIVE_CHAT_CDP_HEALTH_LOCK:
        _LIVE_CHAT_CDP_HEALTH_UNHEALTHY_UNTIL = 0.0
        _LIVE_CHAT_CDP_HEALTH_REASON = ""


# ── Slow-CDP-eval tracker (Fix 12, 2026-05-13) ─────────────────────────
# Background: in extended flood-test runs (10+ minutes of sustained
# concurrent CDP load) the Chrome renderer accumulates state and
# Runtime.evaluate latency creeps from ~0.5s baseline → 8-12s by the
# end.  Observed in the 15:40-16:08 run: first-half CDP avg 384ms,
# second-half avg 8016ms (21× slower).  Once latency exceeds the
# 8-second HOT-PATH-B tool timeout, deliveries start failing.
#
# This tracker counts consecutive "slow" live-chat CDP evals (>3s).  When
# the count hits the threshold, it applies a longer-than-usual health
# cooldown (15s instead of 4s) which gives the renderer breathing room
# to release accumulated state.  All live-chat site operations pause for the
# cooldown duration.  After the cooldown expires, the counter resets
# on the next fast eval.
#
# Tunable via env: ``ECAN_LIVE_CHAT_SLOW_CDP_THRESHOLD_MS`` (default 6000),
# ``ECAN_LIVE_CHAT_SLOW_CDP_COUNT`` (default 6), and
# ``ECAN_LIVE_CHAT_SLOW_CDP_RECOVERY_COOLDOWN_S`` (default 5.0).
#
# 2026-05-14 retune after the MAX_BUBBLES short-circuit and source_guard
# budget cap landed: send-tool wall-clock dropped from 7-10s
# to 1-5s under 20-customer flood. The old threshold (3000ms) and
# cooldown (15s) were calibrated for the pre-optimization regime where
# 3s was unusually fast; now occasional 5s evals are normal-not-broken
# and tripped the cooldown inappropriately, stalling all site ops for
# 15s and producing 4+ minute round-2 hangs. Threshold raised to 6000ms
# (only count >6s evals as "renderer in trouble"), cooldown shrunk to
# 5s (give the renderer a brief breather without bottlenecking the
# whole queue), and count raised to 6 (more evidence before triggering).
try:
    _LIVE_CHAT_SLOW_CDP_THRESHOLD_MS = max(
        500.0, float((live_chat_env("ECAN_LIVE_CHAT_SLOW_CDP_THRESHOLD_MS") or "6000"))
    )
except (TypeError, ValueError):
    _LIVE_CHAT_SLOW_CDP_THRESHOLD_MS = 6000.0
try:
    _LIVE_CHAT_SLOW_CDP_COUNT = max(
        2, int((live_chat_env("ECAN_LIVE_CHAT_SLOW_CDP_COUNT") or "6"))
    )
except (TypeError, ValueError):
    _LIVE_CHAT_SLOW_CDP_COUNT = 6
try:
    _LIVE_CHAT_SLOW_CDP_RECOVERY_COOLDOWN_S = max(
        1.0, float((live_chat_env("ECAN_LIVE_CHAT_SLOW_CDP_RECOVERY_COOLDOWN_S") or "5.0"))
    )
except (TypeError, ValueError):
    _LIVE_CHAT_SLOW_CDP_RECOVERY_COOLDOWN_S = 5.0
_LIVE_CHAT_SLOW_CDP_COUNTER: int = 0
_LIVE_CHAT_SLOW_CDP_LAST_REFRESH_TS: float = 0.0  # gates repeated triggers
_LIVE_CHAT_SLOW_CDP_LOCK = threading.Lock()


def _record_live_chat_cdp_eval_timing(total_ms: float, trace_label: str) -> None:
    """Track per-eval timing for the slow-CDP recovery mechanism.

    Increments a counter on slow live-chat evals; resets on fast ones.  When
    the counter hits :data:`_LIVE_CHAT_SLOW_CDP_COUNT`, triggers a longer
    health cooldown so the renderer gets idle time to recover.
    Suppresses repeated triggers within the cooldown window.

    Called from :func:`_evaluate_js`'s success path with the measured
    total_ms; failures and timeouts go through the existing recovery
    signal path.
    """
    global _LIVE_CHAT_SLOW_CDP_COUNTER, _LIVE_CHAT_SLOW_CDP_LAST_REFRESH_TS
    label = str(trace_label or "")
    if not _live_chat_trace_label(label):
        return
    try:
        ms = float(total_ms)
    except (TypeError, ValueError):
        return
    with _LIVE_CHAT_SLOW_CDP_LOCK:
        if ms < 1000.0:
            # Fast eval — renderer is healthy.  Reset the counter.
            if _LIVE_CHAT_SLOW_CDP_COUNTER > 0:
                _LIVE_CHAT_SLOW_CDP_COUNTER = 0
            return
        if ms <= _LIVE_CHAT_SLOW_CDP_THRESHOLD_MS:
            # Moderately slow but not a red flag.  Don't reset, don't
            # increment.  The counter only moves on clearly-slow evals.
            return
        # Slow eval — increment.
        _LIVE_CHAT_SLOW_CDP_COUNTER += 1
        if _LIVE_CHAT_SLOW_CDP_COUNTER < _LIVE_CHAT_SLOW_CDP_COUNT:
            return
        # Threshold reached.  Suppress if we just triggered.
        now = _time.monotonic()
        if (now - _LIVE_CHAT_SLOW_CDP_LAST_REFRESH_TS) < _LIVE_CHAT_SLOW_CDP_RECOVERY_COOLDOWN_S:
            return
        _LIVE_CHAT_SLOW_CDP_LAST_REFRESH_TS = now
        triggered_count = _LIVE_CHAT_SLOW_CDP_COUNTER
        _LIVE_CHAT_SLOW_CDP_COUNTER = 0
    # Apply the extended cooldown.  Log loudly so ops can see it.
    cooldown_applied = mark_live_chat_cdp_unhealthy(
        reason=(
            f"slow_cdp_evals_threshold_reached "
            f"(count={triggered_count}, last_total_ms={int(ms)})"
        ),
        cooldown_s=_LIVE_CHAT_SLOW_CDP_RECOVERY_COOLDOWN_S,
    )
    logger.warning(
        f"[CDP-EVAL][RECOVERY-COOLDOWN] {triggered_count} consecutive "
        f"slow live-chat CDP evals (>{int(_LIVE_CHAT_SLOW_CDP_THRESHOLD_MS)}ms each; "
        f"last={int(ms)}ms label={label!r}).  Applying "
        f"{cooldown_applied:.1f}s health cooldown to give the Chrome renderer "
        f"idle time.  All live-chat site operations will pause for the cooldown. "
        f"If this fires repeatedly, restart Chrome / refresh the live-chat tab."
    )


def _record_cdp_evaluate_recovery_signal(browser_session: Any, trace_label: str, phase: str) -> None:
    label = str(trace_label or "")
    threshold = (
        _LIVE_CHAT_CDP_EVALUATE_RECOVERY_THRESHOLD
        if _live_chat_trace_label(label)
        else _CDP_EVALUATE_RECOVERY_THRESHOLD
    )
    if threshold <= 0 or browser_session is None:
        return
    session_key = id(browser_session)
    with _CDP_EVALUATE_TIMEOUT_RECOVERY_LOCK:
        count = _CDP_EVALUATE_TIMEOUT_RECOVERY.get(session_key, 0) + 1
        if count < threshold:
            _CDP_EVALUATE_TIMEOUT_RECOVERY[session_key] = count
            return
        _CDP_EVALUATE_TIMEOUT_RECOVERY.pop(session_key, None)
    try:
        from agent.ec_skills.browser_node import build_helpers as _browser_helpers
        removed = _browser_helpers.invalidate_browser_session_for_recovery(
            browser_session,
            reason=f"cdp_runtime_evaluate_timeouts:{trace_label or 'unknown'}:{phase}",
        )
        logger.warning(
            f"[CDP-EVAL] recovery invalidated browser session removed={removed} "
            f"label={trace_label!r} phase={phase!r} timeout_count={count}"
        )
    except Exception as exc:
        logger.warning(f"[CDP-EVAL] recovery invalidation failed: {exc}")


def _live_chat_send_page_timing_fields(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    fields: dict[str, Any] = {}

    def _number(value: Any) -> float | None:
        try:
            return round(float(value), 1)
        except (TypeError, ValueError):
            return None

    total_ms = _number(data.get("page_total_ms"))
    if total_ms is not None:
        fields["page_total_ms"] = total_ms
    phase = str(data.get("page_phase") or "").strip()
    if phase:
        fields["page_phase"] = phase
    timing = data.get("page_timing_ms")
    if isinstance(timing, dict):
        compact_timing: dict[str, float] = {}
        for key, value in timing.items():
            number = _number(value)
            if number is not None:
                compact_timing[str(key)] = number
        if compact_timing:
            fields["page_timing_ms"] = json.dumps(
                compact_timing,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for name in (
                "initial_sidebar_scanned",
                "open_click_wait_done",
                "active_customer_verified",
                "source_guard_verified",
                "final_active_verified",
                "input_found",
                "input_set_done",
                "send_triggered",
                "verified_input_cleared",
                "verified_outgoing_bubble",
                # Probable-success outcome: input was cleared by the site (so the
                # send was accepted) but the outgoing bubble didn't render in
                # time.  Logged with ``verified=input_cleared_no_bubble`` so
                # ops can grep how often this happens vs the strong success.
                "verified_input_cleared_no_bubble_probable_success",
                # Pre-click active-customer guard (Fix 8): inserted right
                # before sendBtn.click() to catch drift that happened during
                # the typing delay (await sleep(80) can stretch to 1+s under
                # flood-load JS event-loop congestion).  Aborts the send if
                # drift detected so we don't mis-deliver into the wrong chat.
                "pre_click_active_verified",
                "active_customer_mismatch_before_click",
                # Fix 9 phase: drift detected during source_guard.  Means
                # the chat thread DOM is showing a different customer's
                # messages than the one we're trying to deliver to —
                # before any typing happened.  Triggers HOT-PATH-B's
                # transient-failure retry path (Fix 7b clears
                # last_dispatched_msg_id → PreDispatch re-dispatches).
                "active_customer_drifted_during_source_guard",
                "send_verify_timeout",
                "active_customer_mismatch_after_open",
                "active_customer_mismatch_before_send",
                "source_guard_stale",
                "source_turn_not_found",
                "input_not_found",
                "input_set_failed",
                "dedup_latest_agent_bubble",
            ):
                if name in compact_timing:
                    fields[f"page_ms_{name}"] = compact_timing[name]
    counters = data.get("page_counters")
    if isinstance(counters, dict):
        compact_counters: dict[str, int] = {}
        for key, value in counters.items():
            try:
                compact_counters[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        if compact_counters:
            fields["page_counters"] = json.dumps(
                compact_counters,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for key, value in compact_counters.items():
                fields[f"page_{key}"] = value
    return fields


def _safe_handler_loop_id(cdp_client: Any) -> int:
    loop = _safe_handler_loop(cdp_client)
    if loop is not None:
        return id(loop)
    return 0


def _safe_handler_loop(cdp_client: Any) -> Any:
    try:
        task = getattr(cdp_client, "_message_handler_task", None)
        if task is not None and hasattr(task, "get_loop"):
            loop = task.get_loop()
            if (
                loop is not None
                and getattr(loop, "is_running", lambda: False)()
                and not getattr(loop, "is_closed", lambda: True)()
            ):
                return loop
    except Exception:
        pass
    return None


def _log_cdp_eval_trace(
    *,
    trace_label: str,
    trace_fields: dict[str, Any] | None,
    ok: bool,
    timed_out: bool,
    phase: str,
    phase_elapsed_ms: float,
    total_ms: float,
    timings: dict[str, float],
    target_id: str | None,
    focus: bool,
    session_id: str,
    expression: str,
    current_loop_id: int,
    handler_loop_id: int,
    pending_at_log: int,
    error: str = "",
    lock_holder_blocking: str = "",
    lock_holder_blocking_held_ms: float = 0.0,
    lock_held_ms: float = 0.0,
) -> None:
    try:
        label = str(trace_label or "").strip() or "unknown"
        cross_loop = bool(handler_loop_id and current_loop_id and handler_loop_id != current_loop_id)
        slow = total_ms >= _CDP_EVALUATE_TRACE_SLOW_MS
        should_log = (
            _CDP_EVALUATE_TRACE_ALL
            or slow
            or timed_out
            or not ok
            or cross_loop
            or _live_chat_trace_label(label)
        )
        if not should_log:
            return
        fields: dict[str, Any] = {}
        if isinstance(trace_fields, dict):
            fields.update(trace_fields)
        fields.update({
            "action": label,
            "ok": bool(ok),
            "timed_out": bool(timed_out),
            "phase": phase,
            "phase_elapsed_ms": round(float(phase_elapsed_ms), 1),
            "total_ms": round(float(total_ms), 1),
            "lock_wait_ms": round(float(timings.get("lock_wait_ms", 0.0)), 1),
            "lock_holder_blocking": str(lock_holder_blocking or ""),
            "lock_holder_blocking_held_ms": round(float(lock_holder_blocking_held_ms or 0.0), 1),
            "lock_held_ms": round(float(lock_held_ms or 0.0), 1),
            "session_ms": round(float(timings.get("session_ms", 0.0)), 1),
            "runtime_enable_ms": round(float(timings.get("runtime_enable_ms", 0.0)), 1),
            "runtime_evaluate_ms": round(float(timings.get("runtime_evaluate_ms", 0.0)), 1),
            "pending_before_enable": int(timings.get("pending_before_enable", -1)),
            "pending_before_evaluate": int(timings.get("pending_before_evaluate", -1)),
            "pending_after_evaluate": int(timings.get("pending_after_evaluate", -1)),
            "pending_pruned_on_timeout": int(timings.get("pending_pruned_on_timeout", 0)),
            "owner_loop_handoff": bool(timings.get("owner_loop_handoff", 0.0)),
            "pending_at_log": int(pending_at_log),
            "target_suffix": str(target_id or "")[-8:],
            "session_suffix": str(session_id or "")[-8:],
            "focus": bool(focus),
            "current_loop_id": int(current_loop_id or 0),
            "handler_loop_id": int(handler_loop_id or 0),
            "cross_loop": cross_loop,
            "expression_len": len(str(expression or "")),
            "expression_hash": _stable_hash([str(len(str(expression or ""))), str(expression or "")[:400]]),
        })
        if error:
            fields["error"] = str(error)[:240]
        level = logging.WARNING if timed_out or not ok or slow or cross_loop else logging.INFO
        contention_suffix = ""
        if fields["lock_holder_blocking"]:
            contention_suffix = (
                f" blocked_by={fields['lock_holder_blocking']}"
                f" blocker_held_ms={fields['lock_holder_blocking_held_ms']}"
            )
        if fields["lock_held_ms"] > 0.0:
            contention_suffix += f" lock_held_ms={fields['lock_held_ms']}"
        msg = (
            f"[CDP-EVAL] action={label} ok={ok} timeout={timed_out} "
            f"phase={phase} total_ms={fields['total_ms']} "
            f"lock_wait_ms={fields['lock_wait_ms']} session_ms={fields['session_ms']} "
            f"runtime_enable_ms={fields['runtime_enable_ms']} "
            f"runtime_evaluate_ms={fields['runtime_evaluate_ms']} "
            f"pending_at_log={pending_at_log} cross_loop={cross_loop} "
            f"target=...{fields['target_suffix']} focus={focus}{contention_suffix}"
        )
        if level >= logging.WARNING:
            logger.warning(msg)
        else:
            logger.info(msg)
        if _live_chat_trace_label(label):
            try:
                live_chat_dispatch.runner_bridge().trace_ledger.log_event(
                    "cdp_evaluate_trace", level=level, **fields
                )
            except Exception:
                pass
    except Exception:
        return


async def _evaluate_js(
    browser_session: BrowserSession,
    expression: str,
    *,
    target_id: str | None = None,
    focus: bool = True,
    trace_label: str = "",
    trace_fields: dict[str, Any] | None = None,
    timeout_s: float | None = None,
    read_only: bool = False,
    lock_free: bool = False,
) -> Any:
    """Run a CDP Runtime.evaluate with a configurable timeout.

    ``read_only=True`` marks the eval as a non-mutating read (e.g. the
    pre-dispatch DOM scrape).  On timeout such calls **do not** mark the
    live-chat CDP transport unhealthy and **do not** record a
    browser-session-recovery signal — the caller is expected to fall back
    gracefully (e.g. to the sidebar preview), and a read timing out is
    never a reason to nuke the shared BrowserSession that the front-desk
    agent and HOT-PATH-B send path depend on.

    ``timeout_s`` overrides the global ``_CDP_EVALUATE_TIMEOUT_S`` for this
    single call.  Used by long-running evaluates (notably
    the site send tool's 17 KB send JS) so they don't trip a timeout
    that was sized for small scrape calls.

    When ``timeout_s`` is ``None`` the resolution order is:

    1. If ``trace_label`` is a live-chat site label → the more generous
       ``_LIVE_CHAT_CDP_EVALUATE_TIMEOUT_S`` family default (covers the
       ~3s CDP session setup + lock-wait that any site evaluate
       routinely sees under contention).  This prevents tiny calls like
       the site's open-session tool (1.6 KB JS) from tripping the 8s health
       cooldown and stalling every subsequent send.
    2. Otherwise → the tight ``_CDP_EVALUATE_TIMEOUT_S`` global so
       non-site evaluates (DOM scrape, generic browser-use actions)
       stay snappy.
    """
    if timeout_s is not None and float(timeout_s) > 0.0:
        effective_timeout_s = float(timeout_s)
    elif _live_chat_trace_label(trace_label):
        effective_timeout_s = _LIVE_CHAT_CDP_EVALUATE_TIMEOUT_S
    else:
        effective_timeout_s = _CDP_EVALUATE_TIMEOUT_S
    if lock_free:
        # ws003e: the WS off-DOM inject is a tiny, isolated socket.send (median ~0.5s
        # eval, no DOM walk, no shared-state clobber). Serializing it on the per-tab
        # operation lock made 65/118 WS sends wait 1-18.5s behind DOM scrapes/sends under
        # 1-vs-N load — defeating the point of off-DOM delivery. Skip the lock for it.
        operation_lock = None
    else:
        try:
            # Site bundle's per-tab CDP operation lock, resolved via the
            # live-chat bridge (platform code imports no bundle modules).
            _session_cdp_operation_lock = (
                live_chat_dispatch.runner_bridge().dom.session_cdp_operation_lock
            )
            # Phase 3.5 (2026-05-21): pass target_id so multi-tab
            # CDP operations on DIFFERENT tabs get DIFFERENT locks.
            # Same-target work still serializes (the per-tab lock prevents
            # concurrent eval clobber within a single tab).
            operation_lock = _session_cdp_operation_lock(
                browser_session, target_id=str(target_id or "")
            )
        except Exception:
            operation_lock = None

    timings: dict[str, float] = {}
    started = _time.perf_counter()
    current_phase = "init"
    phase_started = started
    current_loop_id = 0
    handler_loop_id = 0
    session_id = ""
    cdp_client_ref = None
    # Step 7 telemetry: who was holding the operation lock when we arrived
    # (snapshot taken non-blockingly *before* we try to acquire), plus how
    # long they had been holding it.  Both surface in the CDP-EVAL trace and
    # in the lock-wait-timeout WARN log.
    lock_holder_blocking: str = ""
    lock_holder_blocking_held_ms: float = 0.0
    # How long *we* held the lock, measured at release.  0.0 if we never
    # acquired (lock missing, or timed out while waiting).
    lock_acquired_at: float = 0.0
    lock_held_ms: float = 0.0
    # Holder label we register on this acquire.  Prefer the trace_label so
    # contention logs name a real action; fall back to "cdp_eval".
    _holder_label = str(trace_label or "").strip() or "cdp_eval"
    try:
        current_loop_id = id(asyncio.get_running_loop())
    except Exception:
        pass

    def _set_phase(name: str) -> None:
        nonlocal current_phase, phase_started
        current_phase = name
        phase_started = _time.perf_counter()

    def _emit_trace(
        *,
        ok: bool,
        timed_out: bool,
        error: str = "",
    ) -> None:
        total_ms = (_time.perf_counter() - started) * 1000.0
        phase_elapsed_ms = (_time.perf_counter() - phase_started) * 1000.0
        _log_cdp_eval_trace(
            trace_label=trace_label,
            trace_fields=trace_fields,
            ok=ok,
            timed_out=timed_out,
            phase=current_phase,
            phase_elapsed_ms=phase_elapsed_ms,
            total_ms=total_ms,
            timings=timings,
            target_id=target_id,
            focus=focus,
            session_id=session_id,
            expression=expression,
            current_loop_id=current_loop_id,
            handler_loop_id=handler_loop_id,
            pending_at_log=_safe_pending_request_count(cdp_client_ref),
            error=error,
            lock_holder_blocking=lock_holder_blocking,
            lock_holder_blocking_held_ms=lock_holder_blocking_held_ms,
            lock_held_ms=lock_held_ms,
        )

    async def _run_eval() -> Any:
        nonlocal cdp_client_ref, handler_loop_id, session_id
        cdp_session = None
        cdp_client = None

        # Phase 5 (2026-05-21) — per-tab CDP client routing:
        # When target_id matches a pool typing tab, use that tab's
        # DEDICATED CDP WebSocket instead of the shared browser_session
        # CDP transport.  This is the only way to get true concurrent
        # typing — the shared transport serialized all messages through
        # one WebSocket and capped parallelism at ~1-2 sends regardless
        # of pool size.  Verified necessary live 2026-05-20 17:18:
        # 6 tabs all hung at 30s Runtime.evaluate timeouts with shared
        # transport; per-tab transports avoid that.
        if target_id:
            try:
                _ej_tab_pool = live_chat_dispatch.runner_bridge().tab_pool
                _ej_tab_state = _ej_tab_pool.get_pool().get_typing_tab_state(target_id)
            except Exception:
                _ej_tab_state = None
            if (
                _ej_tab_state is not None
                and _ej_tab_state.cdp_client is not None
                and _ej_tab_state.cdp_session_id
            ):
                _set_phase("pool_cdp_session_lookup")
                phase_t0 = _time.perf_counter()
                cdp_client = _ej_tab_state.cdp_client
                session_id = str(_ej_tab_state.cdp_session_id)
                timings["session_ms"] = (_time.perf_counter() - phase_t0) * 1000.0
                cdp_client_ref = cdp_client
                handler_loop_id = _safe_handler_loop_id(cdp_client)
                # ws051: attach the stall heartbeat to the EXACT CDP handler loop.
                try:
                    from utils import stall_diagnostics as _sd051
                    if _sd051.enabled():
                        _sd051.ensure_loop_heartbeat(_safe_handler_loop(cdp_client))
                except Exception:
                    pass
                timings["pool_dedicated_cdp"] = 1.0
                # Skip the rest of the shared-CDP resolution path —
                # fall through to the eval steps below with this client.
                _eval_params = {
                    "expression": expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                }
                # Use the same owner-loop handoff as below.
                async def _ej_send_on_owner_loop(_callable: Any, **kwargs: Any) -> Any:
                    owner_loop = _safe_handler_loop(cdp_client)
                    try:
                        running_loop = asyncio.get_running_loop()
                    except RuntimeError:
                        running_loop = None
                    if owner_loop is not None and running_loop is not owner_loop:
                        timings["owner_loop_handoff"] = 1.0
                        future = asyncio.run_coroutine_threadsafe(
                            _callable(**kwargs),
                            owner_loop,
                        )
                        return await asyncio.wrap_future(future)
                    return await _callable(**kwargs)
                timings["pending_before_enable"] = _safe_pending_request_count(cdp_client)
                if _CDP_RUNTIME_ENABLE_BEFORE_EVALUATE:
                    _set_phase("Runtime.enable")
                    phase_t0 = _time.perf_counter()
                    await _ej_send_on_owner_loop(
                        cdp_client.send.Runtime.enable, session_id=session_id
                    )
                    timings["runtime_enable_ms"] = (_time.perf_counter() - phase_t0) * 1000.0
                else:
                    timings["runtime_enable_ms"] = 0.0
                _set_phase("Runtime.evaluate")
                phase_t0 = _time.perf_counter()
                timings["pending_before_evaluate"] = _safe_pending_request_count(cdp_client)
                result = await _ej_send_on_owner_loop(
                    cdp_client.send.Runtime.evaluate,
                    params=_eval_params,
                    session_id=session_id,
                )
                timings["runtime_evaluate_ms"] = (_time.perf_counter() - phase_t0) * 1000.0
                timings["pending_after_evaluate"] = _safe_pending_request_count(cdp_client)
                return result

        # Legacy / shared-CDP path: still used for the monitor tab and
        # any non-pool target.
        if hasattr(browser_session, "get_or_create_cdp_session"):
            _set_phase("get_or_create_cdp_session")
            phase_t0 = _time.perf_counter()
            if target_id:
                cdp_session = await browser_session.get_or_create_cdp_session(
                    target_id=target_id,
                    focus=focus,
                )
            else:
                cdp_session = await browser_session.get_or_create_cdp_session()
            timings["session_ms"] = (_time.perf_counter() - phase_t0) * 1000.0
            cdp_client = cdp_session.cdp_client if cdp_session else None
        elif hasattr(browser_session, "cdp_client"):
            _set_phase("resolve_cdp_client")
            phase_t0 = _time.perf_counter()
            cdp_client = browser_session.cdp_client
            timings["session_ms"] = (_time.perf_counter() - phase_t0) * 1000.0
        if not cdp_client:
            raise RuntimeError("No CDP client available")

        cdp_client_ref = cdp_client
        handler_loop_id = _safe_handler_loop_id(cdp_client)
        # ws051: attach the stall heartbeat to the EXACT CDP handler loop (once).
        try:
            from utils import stall_diagnostics as _sd051
            if _sd051.enabled():
                _sd051.ensure_loop_heartbeat(_safe_handler_loop(cdp_client))
        except Exception:
            pass
        session_id = str(getattr(cdp_session, "session_id", None) or "") if cdp_session else ""
        eval_params = {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        }

        async def _send_on_owner_loop(_callable: Any, **kwargs: Any) -> Any:
            owner_loop = _safe_handler_loop(cdp_client)
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if owner_loop is not None and running_loop is not owner_loop:
                timings["owner_loop_handoff"] = 1.0
                future = asyncio.run_coroutine_threadsafe(
                    _callable(**kwargs),
                    owner_loop,
                )
                return await asyncio.wrap_future(future)
            return await _callable(**kwargs)

        timings["pending_before_enable"] = _safe_pending_request_count(cdp_client)
        if _CDP_RUNTIME_ENABLE_BEFORE_EVALUATE:
            _set_phase("Runtime.enable")
            phase_t0 = _time.perf_counter()
            if session_id:
                await _send_on_owner_loop(
                    cdp_client.send.Runtime.enable,
                    session_id=session_id,
                )
            else:
                await _send_on_owner_loop(cdp_client.send.Runtime.enable)
            timings["runtime_enable_ms"] = (_time.perf_counter() - phase_t0) * 1000.0
        else:
            timings["runtime_enable_ms"] = 0.0
        _set_phase("Runtime.evaluate")
        phase_t0 = _time.perf_counter()
        timings["pending_before_evaluate"] = _safe_pending_request_count(cdp_client)
        if session_id:
            result = await _send_on_owner_loop(
                cdp_client.send.Runtime.evaluate,
                params=eval_params,
                session_id=session_id,
            )
        else:
            result = await _send_on_owner_loop(
                cdp_client.send.Runtime.evaluate,
                params=eval_params,
            )
        timings["runtime_evaluate_ms"] = (_time.perf_counter() - phase_t0) * 1000.0
        timings["pending_after_evaluate"] = _safe_pending_request_count(cdp_client)
        _set_phase("complete")
        return result

    async def _run_with_optional_operation_lock() -> Any:
        nonlocal lock_holder_blocking, lock_holder_blocking_held_ms
        nonlocal lock_acquired_at, lock_held_ms
        if operation_lock is not None:
            _set_phase("cdp_operation_lock_wait")
            # Snapshot the current holder *before* we block.  If the lock is
            # free this returns ("", 0.0); otherwise it tells us who's making
            # us wait — invaluable when our acquire later times out.
            try:
                blocker, blocker_held_ms = operation_lock.peek()
            except Exception:
                blocker, blocker_held_ms = ("", 0.0)
            lock_holder_blocking = blocker
            lock_holder_blocking_held_ms = blocker_held_ms
            phase_t0 = _time.perf_counter()
            async with operation_lock.held_by(_holder_label):
                timings["lock_wait_ms"] = (_time.perf_counter() - phase_t0) * 1000.0
                lock_acquired_at = _time.perf_counter()
                try:
                    return await _run_eval()
                finally:
                    lock_held_ms = (_time.perf_counter() - lock_acquired_at) * 1000.0
        timings["lock_wait_ms"] = 0.0
        return await _run_eval()

    try:
        result = await asyncio.wait_for(
            _run_with_optional_operation_lock(),
            timeout=effective_timeout_s,
        )
    except asyncio.TimeoutError as exc:
        # Step 7: distinguish lock-wait timeouts from CDP timeouts.  If we
        # timed out while waiting for the per-session operation lock the
        # renderer/CDP transport is healthy — we were starved by another
        # holder on the same BrowserSession.  Marking the live-chat transport unhealthy here
        # would stall *all* subsequent sends for the 8s+ cooldown window,
        # and tripping the recovery-signal counter could eventually
        # invalidate the browser session entirely.  Neither is appropriate
        # when the renderer never had a chance to misbehave.
        timed_out_on_lock_wait = current_phase == "cdp_operation_lock_wait"
        if timed_out_on_lock_wait:
            # No CDP request was sent — nothing to prune, no recovery signal,
            # no unhealthy cooldown.  Emit a distinct contention WARN so this
            # case is easy to grep for and so the blocker shows up in
            # production logs even when the CDP-EVAL trace is filtered.
            logger.warning(
                f"[CDP-EVAL][LOCK-CONTENTION] action={trace_label or 'cdp_eval'} "
                f"blocked_by={lock_holder_blocking or 'unknown'} "
                f"blocker_held_ms={lock_holder_blocking_held_ms:.1f} "
                f"lock_wait_timeout_after={effective_timeout_s:.1f}s — "
                f"renderer NOT marked unhealthy"
            )
        else:
            timings["pending_pruned_on_timeout"] = _prune_cdp_pending_requests(
                cdp_client_ref
            )
            if read_only:
                # A read-only eval (pre-dispatch DOM scrape) timing out is
                # not a reason to freeze every send (unhealthy cooldown) or
                # to invalidate the shared BrowserSession (recovery signal).
                # The caller falls back gracefully; just emit a distinct
                # WARN so these are visible without poisoning the writers.
                logger.warning(
                    f"[CDP-EVAL][READ-ONLY-TIMEOUT] action={trace_label or 'cdp_eval'} "
                    f"phase={current_phase} after={effective_timeout_s:.1f}s — "
                    f"renderer NOT marked unhealthy, session NOT invalidated"
                )
            else:
                # ws011: distinguish RENDERER-SLOW from a CDP TRANSPORT failure.
                # A ``Runtime.evaluate``/``complete`` timeout means the renderer
                # was too slow to finish our JS (busy SPA under 1-vs-N) — the CDP
                # transport and BrowserSession are FINE. Arming the health cooldown
                # there does NOT un-busy the renderer; it just delays the retry into
                # the same jam, and under sustained load the cooldowns stack into a
                # feedback-loop wedge (slow→cooldown→wait→still slow→cooldown — the
                # 2026-06-06 ~2-min stall). So on renderer-slowness we now SKIP the
                # cooldown arm and let the caller fall back. A *setup*-phase timeout
                # (get_or_create_cdp_session / resolve_cdp_client / Runtime.enable)
                # is the signature of a wedged transport, where invalidating +
                # reconnecting actually helps — that path still arms the cooldown and
                # feeds the recovery counter. Reversible: set
                # ECAN_LIVE_CHAT_COOLDOWN_RENDERER_SLOW_SKIP=0 to restore the old
                # "cool down on any site timeout" behaviour.
                _is_renderer_slow = current_phase in ("Runtime.evaluate", "complete")
                _skip_rs_cooldown = (live_chat_env(
                    "ECAN_LIVE_CHAT_COOLDOWN_RENDERER_SLOW_SKIP"
                ) or "1") != "0"
                # ws035: the old wording always said "renderer too slow", which is
                # MISLEADING — when runtime_evaluate_ms==0 the eval NEVER ran: it
                # starved in the cross-loop handoff to the shared CDP handler loop
                # (a busy loop), not a slow renderer. Capture (a browser-process
                # event) keeps flowing in that case, so "renderer slow" actively
                # sent debugging down the wrong path. Surface the real discriminator.
                _ran_ms = float(timings.get("runtime_evaluate_ms", 0.0) or 0.0)
                if _ran_ms == 0.0 and bool(timings.get("owner_loop_handoff")):
                    _stall_kind = "HANDOFF-STARVED"
                    _stall_why = (
                        f"eval NEVER ran — cross-loop handoff to the shared CDP loop "
                        f"didn't get its turn (pending_before="
                        f"{timings.get('pending_before_evaluate')}); NOT the renderer"
                    )
                else:
                    _stall_kind = "RENDERER-BUSY"
                    _stall_why = f"eval ran {_ran_ms:.0f}ms on the renderer then timed out"
                if _is_renderer_slow and _skip_rs_cooldown:
                    logger.warning(
                        f"[CDP-EVAL][EVAL-STALL] kind={_stall_kind} "
                        f"action={trace_label or 'cdp_eval'} phase={current_phase} "
                        f"after={effective_timeout_s:.1f}s — {_stall_why}; session NOT "
                        f"invalidated, NO cooldown armed (not a transport failure)"
                    )
                else:
                    if _live_chat_trace_label(trace_label):
                        mark_live_chat_cdp_unhealthy(
                            f"{trace_label or 'live_chat'}:{current_phase}:timeout"
                        )
                    if _is_renderer_slow:
                        logger.warning(
                            f"[CDP-EVAL][EVAL-STALL] kind={_stall_kind} "
                            f"action={trace_label or 'cdp_eval'} phase={current_phase} "
                            f"after={effective_timeout_s:.1f}s — {_stall_why}; session "
                            f"NOT invalidated ({_LIVE_CHAT_CDP_HEALTH_COOLDOWN_S:.0f}s "
                            f"cooldown applied)"
                        )
                    else:
                        _record_cdp_evaluate_recovery_signal(
                            browser_session, trace_label, current_phase
                        )
        _emit_trace(
            ok=False,
            timed_out=True,
            error=f"timeout after {effective_timeout_s:.1f}s",
        )
        raise TimeoutError(
            f"CDP Runtime.evaluate timed out after {effective_timeout_s:.1f}s "
            f"(phase={current_phase})"
        ) from exc
    except Exception as exc:
        _emit_trace(ok=False, timed_out=False, error=str(exc))
        raise
    if _live_chat_trace_label(trace_label):
        mark_live_chat_cdp_healthy()
    _emit_trace(ok=True, timed_out=False)
    # Fix 12: slow-CDP-eval tracker.  Counts consecutive slow live-chat
    # evals; triggers a longer health cooldown when threshold is hit.
    # The cooldown gives the renderer idle time to release state.
    try:
        _record_live_chat_cdp_eval_timing(
            total_ms=(_time.perf_counter() - started) * 1000.0,
            trace_label=trace_label or "",
        )
    except Exception:
        pass  # Telemetry hook — never fail the eval
    value = result.get("result", {}).get("value", "")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


async def _resolve_live_chat_tab_target_id_bounded(
    browser_session: BrowserSession,
    *,
    timeout_s: float | None = None,
    resolver=None,
    customer_key: str = "",
) -> str:
    """Resolve the live-chat tab target with a hard timeout.

    Direct delivery already performs this lookup once before calling the
    send tool.  The send tool still needs its own bounded lookup because a
    stale Chrome/CDP state can hang here and otherwise keep the site typing
    lock held indefinitely.

    Phase 1 multi-tab plumbing (2026-05-20): ``customer_key`` is threaded
    through to the bundle's tab-target resolver so that once Phase 3 lands
    the typing pool, this lookup automatically routes customer-specific
    requests to their assigned typing tab.  Until then the parameter is
    accepted but has no functional effect (pool is empty).
    """
    timeout = _LIVE_CHAT_TARGET_RESOLVE_TIMEOUT_S if timeout_s is None else timeout_s
    try:
        if resolver is None:
            # Default resolver comes from the live-chat bundle via the bridge.
            resolver = live_chat_dispatch.runner_bridge().resolve_tab_target_id
        # The bundle's default resolver accepts
        # ``customer_key`` kwarg as of Phase 1 multi-tab plumbing.  Custom
        # resolvers passed via the ``resolver`` parameter may not — fall
        # back to the no-kwarg signature on TypeError.
        try:
            coro = resolver(browser_session, customer_key=customer_key)
        except TypeError:
            coro = resolver(browser_session)
        return str(await asyncio.wait_for(coro, timeout=timeout) or "")
    except asyncio.TimeoutError:
        logger.warning(
            f"[LIVE-CHAT] live-chat target id resolve timed out after {timeout:.1f}s"
        )
        return ""
    except Exception as target_err:
        logger.debug(
            f"[LIVE-CHAT] live-chat target id resolve failed: {target_err}"
        )
        return ""


async def _evaluate_live_chat_js(
    browser_session: BrowserSession,
    expression: str,
    *,
    trace_label: str,
    trace_fields: dict[str, Any] | None = None,
    timeout_s: float | None = None,
    read_only: bool = False,
    customer_key: str = "",
    lock_free: bool = False,
) -> Any:
    """``_evaluate_js`` against the resolved live-chat tab session, ``focus=False``.

    The site's chat JS (list / open / scrape / get-thread) operates on the
    SPA's DOM directly and clicks rows itself, so it does **not** need
    browser-use's ``ensure_valid_focus`` round-trip — which consistently
    cost ~3s of ``session_ms`` whenever ``_evaluate_js`` was called without
    a ``target_id`` (see the 2026-05-11 flood trace: every ``action=unknown``
    / open-session line showed ``session_ms`` ≈ 3000ms).  Resolving
    the cached live-chat target once and passing ``focus=False`` drops that to
    near-zero.  Falls back to the focused-tab path only when no live-chat target
    can be resolved (rare; logged via ``fallback_target`` trace field).

    The site's send tool deliberately keeps its own copy of this pattern
    (it has extra send-specific trace fields and a bespoke timeout) — keep
    the two in sync if you change the resolution behaviour here.

    Phase 1 multi-tab plumbing (2026-05-20): ``customer_key`` is forwarded
    to the resolver so that — once Phase 3 lands typing-tab routing —
    customer-keyed evaluations land on that customer's assigned tab.
    Read-only callers (sidebar enumeration, etc.) leave ``customer_key``
    empty so they keep hitting the monitor tab.
    """
    target_id = ""
    try:
        target_id = await _resolve_live_chat_tab_target_id_bounded(
            browser_session, customer_key=customer_key
        )
    except Exception:
        target_id = ""
    if target_id:
        return await _evaluate_js(
            browser_session,
            expression,
            target_id=target_id,
            focus=False,
            trace_label=trace_label,
            trace_fields=trace_fields,
            timeout_s=timeout_s,
            read_only=read_only,
            lock_free=lock_free,
        )
    return await _evaluate_js(
        browser_session,
        expression,
        trace_label=trace_label,
        trace_fields={**(trace_fields or {}), "fallback_target": True},
        timeout_s=timeout_s,
        read_only=read_only,
        lock_free=lock_free,
    )


def _build_dom_region_inspection_expression(max_regions: int, max_text_length: int, include_html_hint: bool) -> str:
    return f"""
        (function() {{
            function normText(v) {{
                return String(v || '').replace(/\\s+/g, ' ').trim();
            }}
            function isVisible(el) {{
                if (!el || !el.getBoundingClientRect) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 8 && rect.height > 8;
            }}
            function cssPath(el) {{
                if (!el || !el.tagName) return '';
                const parts = [];
                let cur = el;
                while (cur && cur.nodeType === 1 && parts.length < 5) {{
                    let part = cur.tagName.toLowerCase();
                    if (cur.id) {{
                        part += '#' + cur.id;
                        parts.unshift(part);
                        break;
                    }}
                    const cls = Array.from(cur.classList || []).slice(0, 2).join('.');
                    if (cls) part += '.' + cls;
                    parts.unshift(part);
                    cur = cur.parentElement;
                }}
                return parts.join(' > ');
            }}
            const candidates = [];
            const all = Array.from(document.querySelectorAll('body *')).filter(isVisible);
            for (const el of all) {{
                const children = Array.from(el.children || []).filter(isVisible);
                if (children.length < 2) continue;
                const rect = el.getBoundingClientRect();
                const text = normText(el.innerText || el.textContent || '').slice(0, {max_text_length});
                if (!text) continue;
                const clickableChildren = children.filter(c => c.onclick || c.matches('a,button,[role="button"],[tabindex]')).length;
                const repeatedClassCount = children.reduce((acc, child) => {{
                    const cls = (child.className || '').toString().trim();
                    if (cls) acc[cls] = (acc[cls] || 0) + 1;
                    return acc;
                }}, {{}});
                const repeatedGroups = Object.values(repeatedClassCount).filter(v => Number(v) > 1).length;
                const timestamps = (text.match(/\\b\\d{{1,2}}[:/]\\d{{1,2}}(?:[:/]\\d{{1,2}})?\\b/g) || []).length;
                const avatars = el.querySelectorAll('img,svg').length;
                let score = 0;
                if (children.length >= 4) score += 2;
                if (clickableChildren >= 2) score += 2;
                if (repeatedGroups > 0) score += 2;
                if (timestamps > 0) score += 1;
                if (avatars > 0) score += 1;
                candidates.push({{
                    path: cssPath(el),
                    tag: el.tagName.toLowerCase(),
                    child_count: children.length,
                    clickable_children: clickableChildren,
                    repeated_groups: repeatedGroups,
                    timestamps,
                    avatars,
                    text_sample: text,
                    bounds: {{ x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }},
                    html_hint: {str(include_html_hint).lower()} ? String((el.outerHTML || '').slice(0, 220)) : '',
                    score
                }});
            }}
            candidates.sort((a, b) => b.score - a.score || a.bounds.y - b.bounds.y);
            return JSON.stringify({{
                url: window.location.href,
                title: document.title,
                regions: candidates.slice(0, {max_regions})
            }});
        }})()
    """


def _pick_chat_adapter_from_regions(summary: Dict[str, Any], prefer_selected_thread: bool = True) -> Dict[str, Any]:
    regions = summary.get("regions") if isinstance(summary, dict) else []
    if not isinstance(regions, list):
        regions = []
    conversation_region = None
    thread_region = None
    for region in regions:
        if not isinstance(region, dict):
            continue
        text_sample = str(region.get("text_sample") or "")
        path = str(region.get("path") or "")
        if conversation_region is None and (
            "conversation" in path.lower()
            or "chat-item" in path.lower()
            or region.get("clickable_children", 0) >= 2
        ):
            conversation_region = region
        if thread_region is None and (
            "message" in text_sample.lower()
            or "workspace-chat" in path.lower()
            or region.get("timestamps", 0) >= 2
        ):
            thread_region = region
    conversation_region = conversation_region or (regions[0] if regions else {})
    thread_region = thread_region or (regions[1] if len(regions) > 1 else conversation_region or {})
    return {
        "adapter_type": "generic_realtime_portal",
        "url": summary.get("url", ""),
        "conversation_region": {
            "root_selector": conversation_region.get("path", ""),
            "confidence": 0.75 if conversation_region else 0.0,
            "evidence": conversation_region,
        },
        "thread_region": {
            "root_selector": thread_region.get("path", ""),
            "confidence": 0.65 if thread_region else 0.0,
            "evidence": thread_region,
        },
        "identity": {
            "key_fields": ["title", "timestamp", "preview"]
        },
        "notes": "Heuristic adapter proposal. Review selectors/paths before production use.",
    }


def _normalize_items_with_adapter(adapter: Dict[str, Any], page_summary: Dict[str, Any]) -> Dict[str, Any]:
    regions = page_summary.get("regions") if isinstance(page_summary, dict) else []
    if not isinstance(regions, list):
        regions = []
    conversations = []
    for idx, region in enumerate(regions):
        if not isinstance(region, dict):
            continue
        title = str(region.get("path") or "").split(" > ")[-1]
        preview = str(region.get("text_sample") or "")
        timestamp = str(region.get("timestamps") or "")
        key = _stable_hash([title, timestamp, preview, str(idx)])
        conversations.append({
            "key": key,
            "title": title,
            "preview": preview,
            "timestamp": timestamp,
            "position": idx,
            "score": region.get("score", 0),
        })
    return {
        "adapter_type": adapter.get("adapter_type", "generic_realtime_portal"),
        "url": page_summary.get("url", ""),
        "conversations": conversations,
        "region_count": len(regions),
    }


def _diff_normalized_states(previous_state: Dict[str, Any], current_state: Dict[str, Any]) -> Dict[str, Any]:
    old_items = previous_state.get("conversations") if isinstance(previous_state, dict) else []
    new_items = current_state.get("conversations") if isinstance(current_state, dict) else []
    if not isinstance(old_items, list):
        old_items = []
    if not isinstance(new_items, list):
        new_items = []
    old_by_key = {str(item.get("key")): item for item in old_items if isinstance(item, dict) and item.get("key")}
    new_by_key = {str(item.get("key")): item for item in new_items if isinstance(item, dict) and item.get("key")}
    old_order = [str(item.get("key")) for item in old_items if isinstance(item, dict) and item.get("key")]
    new_order = [str(item.get("key")) for item in new_items if isinstance(item, dict) and item.get("key")]
    added_keys = [k for k in new_order if k not in old_by_key]
    removed_keys = [k for k in old_order if k not in new_by_key]
    reordered_keys = [k for k in new_order if k in old_by_key and old_order.index(k) != new_order.index(k)]
    changed = []
    for key in new_order:
        if key in old_by_key and key in new_by_key:
            if (
                old_by_key[key].get("preview") != new_by_key[key].get("preview")
                or old_by_key[key].get("timestamp") != new_by_key[key].get("timestamp")
            ):
                changed.append(key)
    return {
        "added_keys": added_keys,
        "removed_keys": removed_keys,
        "reordered_keys": reordered_keys,
        "changed_keys": changed,
        "top_changed": (old_order[:1] != new_order[:1]),
        "event_types": [
            event for event, cond in [
                ("added", bool(added_keys)),
                ("removed", bool(removed_keys)),
                ("reordered", bool(reordered_keys)),
                ("changed", bool(changed)),
                ("top_changed", old_order[:1] != new_order[:1]),
            ] if cond
        ],
    }

@custom_controller.action(
    "Execute Python code in a sandboxed environment. Use 'result' variable to return a value.",
    param_model=RunCodeAction,
)
async def bu_run_code(params: RunCodeAction) -> ActionResult:
    config: Dict[str, Any] = {"code": params.code, "language": "python"}
    if params.args is not None:
        config["args"] = params.args
    if params.timeout is not None:
        config["timeout"] = params.timeout
    if params.allowed_imports is not None:
        config["allowed_imports"] = params.allowed_imports

    login = AppContext.login
    result = run_code(login.main_win, config)

    if result.get("success"):
        parts = [f"Code executed successfully in {result.get('execution_time_ms', 0)}ms"]
        if result.get("stdout"):
            parts.append(f"\nOutput:\n{result['stdout']}")
        if result.get("return_value") is not None:
            parts.append(f"\nReturn value: {result['return_value']}")
        return ActionResult(extracted_content="\n".join(parts))
    else:
        error_msg = f"Code execution failed: {result.get('error', 'Unknown error')}"
        if result.get("stderr"):
            error_msg += f"\nStderr:\n{result['stderr']}"
        return ActionResult(error=error_msg)



@custom_controller.action(
    "Execute a shell script. Auto-detects OS shell (PowerShell/bash/zsh).",
    param_model=RunShellScriptAction,
)
async def bu_run_shell_script(params: RunShellScriptAction) -> ActionResult:
    config: Dict[str, Any] = {"script": params.script}
    if params.shell is not None:
        config["shell"] = params.shell
    if params.timeout is not None:
        config["timeout"] = params.timeout
    if params.working_dir is not None:
        config["working_dir"] = params.working_dir
    if params.env_vars is not None:
        config["env_vars"] = params.env_vars

    login = AppContext.login
    result = run_shell_script(login.main_win, config)

    if result.get("success"):
        parts = [
            f"Script executed successfully on {result.get('os', 'unknown')} "
            f"using {result.get('shell', 'unknown')} in {result.get('execution_time_ms', 0)}ms"
        ]
        if result.get("stdout"):
            stdout = result['stdout'][:2000]
            if len(result['stdout']) > 2000:
                stdout += "\n... (truncated)"
            parts.append(f"\nOutput:\n{stdout}")
        return ActionResult(extracted_content="\n".join(parts))
    else:
        error_msg = f"Script failed (exit code {result.get('return_code', -1)})"
        if result.get("error"):
            error_msg += f": {result['error']}"
        if result.get("stderr"):
            stderr = result['stderr'][:2000]
            if len(result['stderr']) > 2000:
                stderr += "\n... (truncated)"
            error_msg += f"\nStderr:\n{stderr}"
        return ActionResult(error=error_msg)


@custom_controller.action("List all files in a directory recursively, returning file names and sizes.")
async def list_files(directory: str) -> str:
    results = []
    file_paths = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            path = os.path.join(root, f)
            size = os.path.getsize(path)
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'):
                file_type = "image"
            elif ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'):
                file_type = "document"
            else:
                file_type = "text"
            results.append(f"{path} ({size} bytes, {file_type})")
            file_paths.append(path)
    
    # Auto-authorize all discovered files for upload_file action
    if file_paths:
        agent = get_current_agent()
        if agent and hasattr(agent, 'available_file_paths'):
            if agent.available_file_paths is None:
                agent.available_file_paths = []
            # Add new paths that aren't already in the list
            added_count = 0
            for path in file_paths:
                if path not in agent.available_file_paths:
                    agent.available_file_paths.append(path)
                    added_count += 1
            logger.info(f"[list_files] Auto-authorized {added_count} new file paths (total: {len(agent.available_file_paths)})")
            logger.debug(f"[list_files] Available paths: {agent.available_file_paths}")
        else:
            logger.warning(f"[list_files] Cannot auto-authorize files: agent={agent is not None}, has_attr={hasattr(agent, 'available_file_paths') if agent else False}")
    
    return "\n".join(results)

@custom_controller.action('Rename a downloaded file to a new name', param_model=FileRenameAction)
async def rename_file(params: FileRenameAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension] Renaming file {params.old_path} to {params.new_name}")
    if params.old_path in browser_session.downloaded_files:
        dir_path = os.path.dirname(params.old_path)
        new_path = os.path.join(dir_path, params.new_name)
        os.rename(params.old_path, new_path)
        return ActionResult(extracted_content=f"Renamed {params.old_path} to {new_path}")
    return ActionResult(error=f"File {params.old_path} not found in downloaded files")


@custom_controller.action('Print label files to a specified printer. Supports PDF, PNG, JPG files.', param_model=FilesPrintAction)
async def print_labels(params: FilesPrintAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension] Printing {len(params.file_names)} files to printer: {params.printer or 'default'}")
    
    try:
        result = await print_labels_async(
            files=params.file_names,
            printer_name=params.printer if params.printer else None,
            n_copies=params.n_copies
        )
        
        if result.status.value == "success":
            return ActionResult(
                extracted_content=f"Successfully printed {len(result.printed_files)} files to {result.printer_used}"
            )
        elif result.status.value == "partial":
            return ActionResult(
                extracted_content=f"Partial success: {len(result.printed_files)} printed, {len(result.failed_files)} failed. {result.message}"
            )
        else:
            return ActionResult(error=result.message)
    except Exception as e:
        logger.error(f"[Browser Use Extension] Print error: {e}")
        return ActionResult(error=f"Print failed: {str(e)}")


@custom_controller.action('Reformat label PDFs to fit on multi-label sheets with configurable layout and optional backup copies', param_model=LabelsReformatAction)
async def reformat_labels(params: LabelsReformatAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension] Reformatting {len(params.in_files)} label files")
    
    try:
        # Convert LabelInputFile objects to dicts for the utility function
        in_files = [
            {
                "file_name": f.file_name,
                "added_note_text": f.added_note_text,
                "added_note_font": f.added_note_font if f.added_note_font else None,
                "added_note_size": f.added_note_size
            }
            for f in params.in_files
        ]
        
        result = await reformat_labels_async(
            in_files=in_files,
            out_dir=params.out_dir if params.out_dir else None,
            sheet_width=params.sheet_width,
            sheet_height=params.sheet_height,
            label_width=params.label_width,
            label_height=params.label_height,
            label_orientation=params.label_orientation,
            label_rows_per_sheet=params.label_rows_per_sheet,
            label_cols_per_sheet=params.label_cols_per_sheet,
            label_rows_pitch=params.label_rows_pitch if params.label_rows_pitch > 0 else None,
            label_cols_pitch=params.label_cols_pitch if params.label_cols_pitch > 0 else None,
            top_side_margin=params.top_side_margin if params.top_side_margin > 0 else None,
            left_side_margin=params.left_side_margin if params.left_side_margin > 0 else None,
            add_backup=params.add_backup
        )
        
        if result.success:
            msg = f"Reformatted {result.input_count} labels into {result.output_count} output files"
            if params.add_backup:
                msg += " (with backup copies on same sheet)"
            return ActionResult(extracted_content=msg)
        else:
            return ActionResult(error=result.message)
    except Exception as e:
        logger.error(f"[Browser Use Extension] Reformat error: {e}")
        return ActionResult(error=f"Reformat failed: {str(e)}")


@custom_controller.action(
    "Query the local RAG knowledge base for relevant information from ingested documents.",
    param_model=RagQueryAction,
)
async def bu_rag_query(params: RagQueryAction) -> ActionResult:
    """Query the RAG knowledge base using the existing MCP tool.
    
    Defaults optimized for real-time customer support (<12s budget):
    - mode=naive (vector retrieval only, ~1-2s)
    - only_need_context=True (skip LightRAG LLM generation, saves 15-20s)
    - top_k=5, enable_rerank=False
    The calling LLM synthesizes the answer from the returned context chunks.
    """
    import time
    _t0 = time.perf_counter()
    try:
        from agent.ec_skills.rag.local_rag_mcp import rag_query
        
        # Build input dict for MCP tool
        input_data = {
            "query": params.query,
            "mode": params.mode or "naive",
        }
        
        # Add optional parameters
        if params.only_need_context is not None:
            input_data["only_need_context"] = params.only_need_context
        if params.response_type is not None:
            input_data["response_type"] = params.response_type
        if params.top_k is not None:
            input_data["top_k"] = params.top_k
        if params.enable_rerank is not None:
            input_data["enable_rerank"] = params.enable_rerank
        if params.include_references is not None:
            input_data["include_references"] = params.include_references
        # Optional LightRAG workspace (tenant). Empty / None falls back to
        # the server's default workspace (pre-multi-tenant behavior).
        _ws = (getattr(params, "workspace", None) or "").strip()
        if _ws:
            input_data["workspace"] = _ws
        
        # Call MCP tool
        login = AppContext.login
        result_list = await rag_query(login.main_win, {"input": input_data})
        
        _elapsed = time.perf_counter() - _t0
        
        # Extract result from TextContent
        if result_list and len(result_list) > 0:
            text_content = result_list[0]
            result_text = text_content.text
            
            # Check if it's an error
            if result_text.startswith("Error:"):
                logger.warning(f"[bu_rag_query] RAG error in {_elapsed:.2f}s: {result_text[:200]}")
                return ActionResult(error=result_text)
            
            # Truncate very long context to keep LLM prompt manageable
            if len(result_text) > 8000:
                result_text = result_text[:8000] + "\n... (context truncated for speed)"
            
            logger.info(f"[bu_rag_query] RAG query completed in {_elapsed:.2f}s (mode={params.mode}, context_only={params.only_need_context}, workspace={_ws or '(default)'!r}, chars={len(result_text)})")
            return ActionResult(extracted_content=result_text)
        else:
            logger.warning(f"[bu_rag_query] No result in {_elapsed:.2f}s")
            return ActionResult(error="No result returned from RAG query")
            
    except Exception as e:
        _elapsed = time.perf_counter() - _t0
        logger.error(f"[bu_rag_query] RAG query error in {_elapsed:.2f}s: {e}")
        return ActionResult(error=f"RAG query failed: {str(e)}")


@custom_controller.action(
    "Re-ingest a file into the local RAG knowledge base after it has been "
    "edited on disk. Deletes existing copies in the workspace (matched by "
    "basename) and uploads the new version. Use this — NOT bu_ragify — when "
    "a source file's contents have changed; otherwise stale entries from the "
    "previous version remain in the knowledge graph.",
    param_model=RagReplaceDocumentAction,
)
async def bu_rag_replace_document(params: RagReplaceDocumentAction) -> ActionResult:
    """Browser-use action wrapper around the ``rag_replace_document`` MCP tool.

    The MCP tool itself does the list-then-delete-then-ingest dance against
    the local LightRAG server; we just translate the pydantic model into the
    ``input`` dict and surface the result as an ``ActionResult``.
    """
    import time
    _t0 = time.perf_counter()
    try:
        from agent.ec_skills.rag.local_rag_mcp import rag_replace_document

        path = (params.path or "").strip()
        if not path:
            return ActionResult(error="path is required and must be non-empty")

        input_data: Dict[str, Any] = {"path": path}
        ws = (getattr(params, "workspace", None) or "").strip()
        if ws:
            input_data["workspace"] = ws
        if params.match_basename is not None:
            input_data["match_basename"] = bool(params.match_basename)

        login = AppContext.login
        result_list = await rag_replace_document(login.main_win, {"input": input_data})

        _elapsed = time.perf_counter() - _t0

        if not result_list:
            logger.warning(f"[bu_rag_replace_document] No result in {_elapsed:.2f}s")
            return ActionResult(error="No result returned from rag_replace_document")

        text_content = result_list[0]
        result_text = text_content.text or ""

        if result_text.startswith("Error:"):
            logger.warning(
                f"[bu_rag_replace_document] error in {_elapsed:.2f}s: {result_text[:300]}"
            )
            return ActionResult(error=result_text)

        meta = getattr(text_content, "meta", None) or {}
        # The MCP tool's meta carries the underlying client result. When
        # status=success its data dict is what callers usually want.
        data = (meta.get("data") if isinstance(meta, dict) else None) or {}
        deleted = data.get("deleted_count", 0)
        track_id = (data.get("ingest") or {}).get("track_id", "N/A")
        logger.info(
            f"[bu_rag_replace_document] OK in {_elapsed:.2f}s "
            f"(workspace={ws or '(default)'!r}, deleted={deleted}, "
            f"track_id={track_id})"
        )
        return ActionResult(extracted_content=result_text)
    except Exception as e:
        _elapsed = time.perf_counter() - _t0
        logger.error(f"[bu_rag_replace_document] error in {_elapsed:.2f}s: {e}")
        return ActionResult(error=f"rag_replace_document failed: {str(e)}")


def _bu_build_ragify_input(params) -> dict:
    """Translate a RagifyAction / RagifyAsyncAction pydantic model into the
    ``input`` dict expected by the ``ragify`` / ``ragify_async`` MCP tools.

    Only forwards fields that are explicitly set (i.e. non-None). Empty
    string workspace is treated as "use server default" and omitted — this
    keeps logs clean and avoids sending a ``LIGHTRAG-WORKSPACE:`` header
    with an empty value.
    """
    data: dict = {}
    # Content source (file_paths XOR text — enforced by the MCP tool itself)
    if getattr(params, "file_paths", None):
        data["file_paths"] = list(params.file_paths)
    if getattr(params, "text", None):
        data["text"] = params.text
    if getattr(params, "file_source", None) is not None:
        data["file_source"] = params.file_source
    # Workspace (tenant)
    ws = (getattr(params, "workspace", None) or "").strip()
    if ws:
        data["workspace"] = ws
    return data


@custom_controller.action(
    "Ingest documents or text into the local RAG knowledge base and (by default) WAIT for processing to complete. Use this when you need to query the newly ingested data immediately after. For large files or fire-and-forget ingestion, use bu_ragify_async instead.",
    param_model=RagifyAction,
)
async def bu_ragify(params: RagifyAction) -> ActionResult:
    """Blocking ingest wrapper around the ``ragify`` + ``wait_for_rag_completion`` MCP tools.

    Flow:
      1. Call ``ragify`` to upload / insert the content and obtain a ``track_id``.
      2. If ``wait_for_completion`` (default True), call ``wait_for_rag_completion``
         scoped to the SAME workspace to block until PROCESSED/FAILED.
      3. Return a short status summary the LLM can act on.
    """
    import time
    _t0 = time.perf_counter()
    try:
        from agent.ec_skills.rag.local_rag_mcp import ragify, wait_for_rag_completion

        # Basic input validation — the MCP tool enforces this too, but failing
        # fast here produces a cleaner error for the agent.
        if not (params.file_paths or params.text):
            return ActionResult(error="bu_ragify: provide either 'file_paths' or 'text'.")

        input_data = _bu_build_ragify_input(params)
        _ws = input_data.get("workspace") or "(default)"

        login = AppContext.login
        result_list = await ragify(login.main_win, {"input": input_data})

        if not result_list or not getattr(result_list[0], "text", None):
            logger.warning(f"[bu_ragify] No result from ragify in {time.perf_counter() - _t0:.2f}s")
            return ActionResult(error="No result returned from ragify.")

        ragify_text = result_list[0].text
        if ragify_text.startswith("Error:"):
            logger.warning(f"[bu_ragify] ragify error (workspace={_ws!r}): {ragify_text[:200]}")
            return ActionResult(error=ragify_text)

        # Pull track_id out of the ragify result meta when possible, otherwise
        # fall back to parsing the text (ragify's text output includes the id).
        track_id = None
        meta = getattr(result_list[0], "meta", None) or {}
        if isinstance(meta, dict):
            track_id = meta.get("track_id") or meta.get("trackId")
        if not track_id:
            # Heuristic: ragify's text is of the form "...track_id: <id>..."
            import re
            m = re.search(r"track[_-]?id['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]+)", ragify_text)
            if m:
                track_id = m.group(1)

        if not params.wait_for_completion:
            _elapsed = time.perf_counter() - _t0
            logger.info(f"[bu_ragify] Submitted in {_elapsed:.2f}s (workspace={_ws!r}, track_id={track_id!r}, wait=False)")
            return ActionResult(extracted_content=ragify_text)

        if not track_id:
            # Nothing to poll on — return the submission result as-is.
            logger.warning(f"[bu_ragify] ragify returned no track_id (workspace={_ws!r}); returning submission result without waiting.")
            return ActionResult(extracted_content=ragify_text)

        wait_input = {"track_id": track_id}
        if input_data.get("workspace"):
            wait_input["workspace"] = input_data["workspace"]
        if params.timeout_seconds is not None:
            wait_input["timeout_seconds"] = int(params.timeout_seconds)
        if params.poll_interval_seconds is not None:
            wait_input["poll_interval_seconds"] = int(params.poll_interval_seconds)

        wait_result = await wait_for_rag_completion(login.main_win, {"input": wait_input})
        _elapsed = time.perf_counter() - _t0

        if wait_result and getattr(wait_result[0], "text", None):
            wait_text = wait_result[0].text
            if wait_text.startswith("Error:"):
                logger.warning(f"[bu_ragify] wait_for_rag_completion error in {_elapsed:.2f}s (workspace={_ws!r}): {wait_text[:200]}")
                return ActionResult(error=wait_text)
            logger.info(f"[bu_ragify] Ingestion complete in {_elapsed:.2f}s (workspace={_ws!r}, track_id={track_id!r})")
            return ActionResult(extracted_content=wait_text)

        logger.warning(f"[bu_ragify] wait_for_rag_completion returned no result in {_elapsed:.2f}s")
        return ActionResult(error="No result returned from wait_for_rag_completion.")
    except Exception as e:
        _elapsed = time.perf_counter() - _t0
        logger.error(f"[bu_ragify] ragify error in {_elapsed:.2f}s: {e}")
        return ActionResult(error=f"ragify failed: {str(e)}")


@custom_controller.action(
    "Ingest documents or text into the local RAG knowledge base ASYNCHRONOUSLY (fire-and-forget). Returns a track_id immediately; processing continues in the background. Set on_complete=true to receive a notification when done.",
    param_model=RagifyAsyncAction,
)
async def bu_ragify_async(params: RagifyAsyncAction) -> ActionResult:
    """Fire-and-forget ingest wrapper around the ``ragify_async`` MCP tool."""
    import time
    _t0 = time.perf_counter()
    try:
        from agent.ec_skills.rag.local_rag_mcp import ragify_async

        if not (params.file_paths or params.text):
            return ActionResult(error="bu_ragify_async: provide either 'file_paths' or 'text'.")

        input_data = _bu_build_ragify_input(params)
        _ws = input_data.get("workspace") or "(default)"

        # Async-specific fields
        if params.on_complete is not None:
            input_data["on_complete"] = bool(params.on_complete)
        if params.notify_task_id is not None:
            input_data["notify_task_id"] = params.notify_task_id
        if params.notify_chat_id is not None:
            input_data["notify_chat_id"] = params.notify_chat_id
        if params.notification_message is not None:
            input_data["notification_message"] = params.notification_message
        if params.timeout_seconds is not None:
            input_data["timeout_seconds"] = int(params.timeout_seconds)
        if params.poll_interval_seconds is not None:
            input_data["poll_interval_seconds"] = int(params.poll_interval_seconds)

        login = AppContext.login
        result_list = await ragify_async(login.main_win, {"input": input_data})
        _elapsed = time.perf_counter() - _t0

        if not result_list or not getattr(result_list[0], "text", None):
            logger.warning(f"[bu_ragify_async] No result in {_elapsed:.2f}s (workspace={_ws!r})")
            return ActionResult(error="No result returned from ragify_async.")

        text = result_list[0].text
        if text.startswith("Error:"):
            logger.warning(f"[bu_ragify_async] ragify_async error in {_elapsed:.2f}s (workspace={_ws!r}): {text[:200]}")
            return ActionResult(error=text)

        logger.info(f"[bu_ragify_async] Submitted in {_elapsed:.2f}s (workspace={_ws!r}, on_complete={params.on_complete})")
        return ActionResult(extracted_content=text)
    except Exception as e:
        _elapsed = time.perf_counter() - _t0
        logger.error(f"[bu_ragify_async] ragify_async error in {_elapsed:.2f}s: {e}")
        return ActionResult(error=f"ragify_async failed: {str(e)}")


@custom_controller.action(
    'Extract raw DOM/markdown content from the current page. Returns webpage content for cloud-side analysis without requiring local LLM.',
    param_model=ExtractDomAction
)
async def extract_dom(params: ExtractDomAction, browser_session: BrowserSession):
    """Extract raw markdown content from the current page without LLM analysis.
    
    This action is used in passive mode where the cloud agent will analyze the content.
    It extracts the same content that browser-use's extract action would feed to an LLM,
    but returns it raw for the cloud to process.
    
    Enhanced with:
    - Timeout protection (default 30s per attempt)
    - Retry mechanism with fallback strategies
    - Progressive degradation on repeated failures
    """
    import time as time_module
    
    MAX_CHAR_LIMIT = 30000
    query = params.query or ""
    extract_links = params.extract_links
    start_from_char = params.start_from_char or 0
    
    # Timeout configuration
    EXTRACT_TIMEOUT_SECONDS = 30.0
    MAX_RETRIES = 3
    
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        attempt_start = time_module.time()
        logger.info(
            f"[extract_dom] Attempt {attempt + 1}/{MAX_RETRIES}: "
            f"starting extraction (timeout={EXTRACT_TIMEOUT_SECONDS}s)"
        )
        
        try:
            # Try with timeout protection
            from browser_use.dom.markdown_extractor import extract_clean_markdown
            
            content, content_stats = await asyncio.wait_for(
                extract_clean_markdown(
                    browser_session=browser_session, extract_links=extract_links
                ),
                timeout=EXTRACT_TIMEOUT_SECONDS
            )
            
            elapsed = time_module.time() - attempt_start
            logger.info(
                f"[extract_dom] Attempt {attempt + 1} succeeded in {elapsed:.1f}s, "
                f"extracted {len(content):,} chars"
            )
            
            # Success - proceed with processing
            last_error = None
            break
            
        except asyncio.TimeoutError:
            elapsed = time_module.time() - attempt_start
            last_error = f"Timeout after {elapsed:.1f}s"
            logger.warning(
                f"[extract_dom] Attempt {attempt + 1}/{MAX_RETRIES} TIMEOUT "
                f"({EXTRACT_TIMEOUT_SECONDS}s limit). Will {'retry' if attempt < MAX_RETRIES - 1 else 'give up'}."
            )
            
            # On timeout, try to clear DOM cache to get fresh state
            try:
                dom_watchdog = getattr(browser_session, '_dom_watchdog', None)
                if dom_watchdog and hasattr(dom_watchdog, 'clear_cache'):
                    dom_watchdog.clear_cache()
                    logger.info("[extract_dom] Cleared DOM cache after timeout")
            except Exception as cache_err:
                logger.debug(f"[extract_dom] Failed to clear DOM cache: {cache_err}")
                
        except Exception as e:
            elapsed = time_module.time() - attempt_start
            last_error = f"{type(e).__name__}: {e}"
            logger.warning(
                f"[extract_dom] Attempt {attempt + 1}/{MAX_RETRIES} failed "
                f"after {elapsed:.1f}s: {last_error}"
            )
        
        # If this wasn't the last attempt, wait briefly before retry
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(1.0)
    
    # If all retries failed, return error
    if last_error is not None:
        logger.error(
            f"[extract_dom] All {MAX_RETRIES} attempts failed. "
            f"Last error: {last_error}"
        )
        return ActionResult(
            error=f"extract_dom failed after {MAX_RETRIES} attempts: {last_error}. "
                  f"Try again when the page has finished loading or use a simpler query."
        )
    
    final_filtered_length = content_stats.get("final_filtered_chars", len(content))

    if start_from_char > 0:
        if start_from_char >= len(content):
            return ActionResult(
                error=f"start_from_char ({start_from_char}) exceeds content length {final_filtered_length} characters."
            )
        content = content[start_from_char:]
        content_stats["started_from_char"] = start_from_char

    # Smart truncation with context preservation
    truncated = False
    if len(content) > MAX_CHAR_LIMIT:
        truncate_at = MAX_CHAR_LIMIT
        # Look for paragraph break within last 500 chars of limit
        paragraph_break = content.rfind("\n\n", MAX_CHAR_LIMIT - 500, MAX_CHAR_LIMIT)
        if paragraph_break > 0:
            truncate_at = paragraph_break
        else:
            # Look for sentence break within last 200 chars of limit
            sentence_break = content.rfind(".", MAX_CHAR_LIMIT - 200, MAX_CHAR_LIMIT)
            if sentence_break > 0:
                truncate_at = sentence_break + 1
        content = content[:truncate_at]
        truncated = True
        next_start = (start_from_char or 0) + truncate_at
        content_stats["truncated_at_char"] = truncate_at
        content_stats["next_start_char"] = next_start

    # Build stats summary (same format as browser-use)
    original_html_length = content_stats.get("original_html_chars", 0)
    initial_markdown_length = content_stats.get("initial_markdown_chars", 0)
    chars_filtered = content_stats.get("filtered_chars_removed", 0)

    stats_summary = f"Content processed: {original_html_length:,} HTML chars → {initial_markdown_length:,} initial markdown → {final_filtered_length:,} filtered markdown"
    if start_from_char > 0:
        stats_summary += f" (started from char {start_from_char:,})"
    if truncated:
        stats_summary += f" → {len(content):,} final chars (truncated, use start_from_char={content_stats['next_start_char']} to continue)"
    elif chars_filtered > 0:
        stats_summary += f" (filtered {chars_filtered:,} chars of noise)"

    try:
        current_url = await browser_session.get_current_page_url()
    except Exception:
        current_url = "unknown"

    # Return raw content in same format as browser-use's extract action LLM input
    extracted_content = (
        f"<url>\n{current_url}\n</url>\n"
        f"<query>\n{query}\n</query>\n"
        f"<content_stats>\n{stats_summary}\n</content_stats>\n"
        f"<webpage_content>\n{content}\n</webpage_content>"
    )

    logger.info(f"[extract_dom] Extracted {len(content):,} chars from {current_url}")

    return ActionResult(
        extracted_content=extracted_content,
        include_in_memory=True,
        long_term_memory=f"Extracted raw markdown for query: {query}",
    )

@custom_controller.action(
    "Send a chat message to another agent via A2A (Agent-to-Agent) protocol. "
    "Use bu_select_agents first to discover available agents and their IDs.",
    param_model=SendChatAction,
)
async def bu_send_chat(params: SendChatAction) -> ActionResult:
    from agent.mcp.server.chat_utils.chat_tools import send_chat

    runtime_ctx = get_current_runtime_context()
    bound_sender_agent_id = str(runtime_ctx.get("agent_id") or "").strip()
    runtime_skill_name = str(runtime_ctx.get("skill_name") or "").strip()
    explicit_sender_agent_id = str(params.sender_agent_id or "").strip()

    if runtime_skill_name == "rt_chat_bot":
        logger.warning(
            f"[bu_send_chat] Routing disabled for customer-service skill. "
            f"skill={runtime_skill_name}, task_id={runtime_ctx.get('task_id', '')}, "
            f"node_id={runtime_ctx.get('node_id', '')}, recipient_id={params.recipient_agent_id or ''}"
        )
        return ActionResult(
            extracted_content=(
                "Routing tools are disabled for the customer-service skill. "
                "This task already owns the assigned customer session. "
                "Do not send assignment chat messages. Stay on the assigned customer tab, "
                "reply to the customer message in the browser chat, "
                "and call done() when finished."
            )
        )

    if not bound_sender_agent_id:
        return ActionResult(
            error="Current runtime agent_id is unavailable for bu_send_chat. "
                  "This tool requires an active browser/task agent context."
        )

    if explicit_sender_agent_id and explicit_sender_agent_id != bound_sender_agent_id:
        return ActionResult(
            error=(
                f"sender_agent_id mismatch: requested={explicit_sender_agent_id}, "
                f"runtime={bound_sender_agent_id}. bu_send_chat binds sender to the current runtime agent."
            )
        )

    config: Dict[str, Any] = {
        "sender_agent_id": bound_sender_agent_id,
        "message": params.message,
    }
    normalized_recipient_id = str(params.recipient_agent_id or "").strip()
    normalized_recipient_name = str(params.recipient_agent_name or "").strip()
    if not normalized_recipient_id and normalized_recipient_name.startswith("agent_"):
        normalized_recipient_id = normalized_recipient_name
        normalized_recipient_name = ""
        logger.info(
            f"[bu_send_chat] Normalized recipient_agent_name-looking-like-id into recipient_agent_id: "
            f"{normalized_recipient_id}"
        )
    # If recipient_agent_id does NOT look like a real UUID (no "agent_" prefix),
    # the LLM passed a name (or example/template string) as the ID. Resolve it
    # to the real UUID so DEDUP keys are consistent (Fix C). If the name cannot
    # be resolved, reject — sending with a dangling name bypasses per-UUID
    # DEDUP and lets the LLM create duplicate customer replies by rotating
    # through name variants.
    if normalized_recipient_id and not normalized_recipient_id.startswith("agent_"):
        from agent.mcp.server.chat_utils.chat_tools import _get_agent_by_name as _hp_get_agent_by_name
        _resolved = _hp_get_agent_by_name(normalized_recipient_id)
        _resolved_id = ""
        if _resolved is not None:
            _resolved_card = getattr(_resolved, "card", None)
            _resolved_id = getattr(_resolved_card, "id", "") if _resolved_card else ""
        if _resolved_id:
            logger.info(
                f"[bu_send_chat] Resolved recipient name '{normalized_recipient_id}' "
                f"to agent_id '{_resolved_id}' (Fix C)"
            )
            if not normalized_recipient_name:
                normalized_recipient_name = normalized_recipient_id
            normalized_recipient_id = _resolved_id
        else:
            logger.warning(
                f"[bu_send_chat] Rejecting dispatch: recipient_agent_id='{normalized_recipient_id}' "
                f"is not a UUID and no agent with that name was found (Fix C)."
            )
            return ActionResult(
                error=(
                    f"recipient_agent_id '{normalized_recipient_id}' is not a real agent UUID "
                    f"(expected prefix 'agent_'). Call bu_select_agents(filter_task_name=\"客户应答\") "
                    f"first to get real agent UUIDs. Do NOT pass agent names, example strings "
                    f"like 'agent_id_1', or unresolved templates like '{{{{...}}}}' as recipient_agent_id."
                )
            )
    if normalized_recipient_id:
        config["recipient_agent_id"] = normalized_recipient_id
    if normalized_recipient_name:
        config["recipient_agent_name"] = normalized_recipient_name
    if params.chat_id is not None:
        config["chat_id"] = params.chat_id
    if params.message_type is not None:
        config["message_type"] = params.message_type
    if params.async_send is not None:
        config["async_send"] = params.async_send

    # Front-desk service assignment hardening:
    # browser-use sometimes tries to send the assignment payload before it carries a
    # resolved tab_id. That causes the service agent to start from an ambiguous page
    # and drift into front-desk behavior. Before sending, enrich the payload from the
    # live browser session; if the tab still is not open, fail fast so front desk
    # keeps opening/locating tabs instead of dispatching a broken assignment.
    try:
        if runtime_skill_name == "customer_front_desk":
            payload_obj = None
            if isinstance(config.get("message"), str):
                payload_obj = try_parse_json(config.get("message"))
            # Reject batched multi-customer assignments: LLM must send one per call
            if isinstance(payload_obj, list):
                return ActionResult(
                    error=(
                        "Assignment payload contains multiple customers in a single message. "
                        "Send exactly ONE assignment per bu_send_chat call. "
                        "Call bu_send_chat once for each customer with their individual assignment payload."
                    )
                )
            if isinstance(payload_obj, dict):
                _assignments_list = payload_obj.get("assignments") or payload_obj.get("customers")
                if isinstance(_assignments_list, list) and len(_assignments_list) > 1:
                    return ActionResult(
                        error=(
                            "Assignment payload contains multiple customers in a single message. "
                            "Send exactly ONE assignment per bu_send_chat call. "
                            "Call bu_send_chat once for each customer with their individual assignment payload."
                        )
                    )
            if isinstance(payload_obj, dict):
                payload_session_id = str(
                    payload_obj.get("session_id")
                    or payload_obj.get("sessionId")
                    or payload_obj.get("customer_id")
                    or ""
                ).strip()
                payload_chat_url = str(
                    payload_obj.get("chat_url")
                    or payload_obj.get("chatUrl")
                    or ""
                ).strip()
                payload_tab_id = str(
                    payload_obj.get("tab_id")
                    or payload_obj.get("tabId")
                    or ""
                ).strip()

                recipient_for_service = str(config.get("recipient_agent_id") or "").strip() or str(
                    config.get("recipient_agent_name") or ""
                ).strip()
                if payload_session_id and payload_chat_url and recipient_for_service:
                    if not payload_tab_id:
                        current_agent = get_current_agent()
                        browser_session = getattr(current_agent, "browser_session", None) if current_agent else None
                        resolved_tab_id = _find_frontdesk_open_tab_id(browser_session, payload_chat_url) if browser_session else ""
                        if resolved_tab_id:
                            payload_obj["tab_id"] = resolved_tab_id
                            config["message"] = json.dumps(payload_obj, ensure_ascii=False)
                            logger.info(
                                f"[bu_send_chat] Enriched front-desk assignment with resolved tab_id: "
                                f"session_id={payload_session_id} tab_id=...{resolved_tab_id[-4:]}"
                            )
                        else:
                            logger.info(
                                f"[bu_send_chat] Refusing to send assignment without resolved tab_id: "
                                f"session_id={payload_session_id} chat_url={payload_chat_url}"
                            )
                            return ActionResult(
                                error=(
                                    "Assignment payload is missing a resolved tab_id and the chat tab is not open yet. "
                                    "Open or locate the customer's chat tab first, then send the assignment."
                                )
                            )
    except Exception as _assignment_enrich_err:
        logger.warning(f"[bu_send_chat] Failed to normalize front-desk assignment payload: {_assignment_enrich_err}")

    # ── Q&A dispatch payload normalization (Fix A) ────────────────────
    #
    # The front-desk LLM sometimes echoes the result shape of
    # the open-session tool's result shape (session_id/chat_url) into a
    # `bu_send_chat` payload that should instead be a Q&A dispatch
    # ({customer_id, customer_name, latest_message}).  The worker LLM
    # then receives a payload with no `latest_message` and either
    # produces an unrelated reply (compensating from chat history) or
    # — once that malformed payload contaminates conversation history
    # — emits `done(success=False, text="payload 缺少必需字段")` on a
    # subsequent turn even when that turn's payload is correct.
    #
    # Detection rule for a Q&A dispatch shape:
    #   - has customer_id and/or customer_name
    #   - has NO service-assignment fields (session_id, chat_url, tab_id)
    #   - has NO response_text (which would identify a Q&A *reply*)
    #
    # When detected, we require `latest_message` to be present.  If
    # absent, we reject the call with a precise correction message.
    # This is strictly additive: legitimate service assignments and
    # Q&A replies are unaffected because their shapes don't match.
    try:
        _qa_msg_str = config.get("message", "")
        if isinstance(_qa_msg_str, str):
            _qa_obj = try_parse_json(_qa_msg_str)
            if isinstance(_qa_obj, dict):
                _has_session = bool(str(
                    _qa_obj.get("session_id") or _qa_obj.get("sessionId") or ""
                ).strip())
                _has_chat_url = bool(str(
                    _qa_obj.get("chat_url") or _qa_obj.get("chatUrl") or ""
                ).strip())
                _has_tab_id = bool(str(
                    _qa_obj.get("tab_id") or _qa_obj.get("tabId") or ""
                ).strip())
                _has_response = bool(str(_qa_obj.get("response_text") or "").strip())
                _has_latest = bool(str(_qa_obj.get("latest_message") or "").strip())
                _has_customer = bool(str(
                    _qa_obj.get("customer_id") or _qa_obj.get("customer_name") or ""
                ).strip())
                _is_qa_dispatch = (
                    _has_customer
                    and not _has_session
                    and not _has_chat_url
                    and not _has_tab_id
                    and not _has_response
                )
                if _is_qa_dispatch and not _has_latest:
                    _list_tool_name = "list_sessions"
                    try:
                        _list_tool_name = str(
                            getattr(
                                live_chat_dispatch.runner_bridge(),
                                "list_sessions_tool_name",
                                "",
                            )
                            or _list_tool_name
                        )
                    except Exception:
                        pass
                    logger.warning(
                        f"[bu_send_chat] REJECT Q&A dispatch with no latest_message: "
                        f"sender={bound_sender_agent_id} "
                        f"recipient={normalized_recipient_id or normalized_recipient_name} "
                        f"payload_keys={sorted(_qa_obj.keys())}"
                    )
                    return ActionResult(
                        error=(
                            "Q&A dispatch payload is missing the required field "
                            "'latest_message'. The recipient is a Q&A worker — its "
                            "contract requires exactly: "
                            '{"customer_id": "<id>", "customer_name": "<name>", '
                            '"latest_message": "<the customer\'s original message text>"}. '
                            "Do NOT pass session_id, chat_url, or tab_id (those are "
                            "for service-assignment payloads to a different worker "
                            "type). Take 'latest_message' from the `last_message` "
                            f"field of the matching {_list_tool_name} entry for "
                            "this customer."
                        )
                    )
                # Strip non-contract noise fields so the worker's history
                # doesn't accumulate inconsistent shapes across turns.
                if _is_qa_dispatch and _has_latest:
                    _stripped = False
                    for _k in ("session_id", "sessionId", "chat_url", "chatUrl",
                               "tab_id", "tabId"):
                        if _k in _qa_obj:
                            _qa_obj.pop(_k, None)
                            _stripped = True
                    if _stripped:
                        config["message"] = json.dumps(_qa_obj, ensure_ascii=False)
                        logger.info(
                            f"[bu_send_chat] Stripped non-contract fields from Q&A "
                            f"dispatch payload (customer="
                            f"{_qa_obj.get('customer_id') or _qa_obj.get('customer_name')}) "
                            f"to keep worker history consistent."
                        )
    except Exception as _qa_norm_err:
        logger.warning(f"[bu_send_chat] Failed to normalize Q&A dispatch payload: {_qa_norm_err}")

    # Discovery gate and duplicate-recipient detection are now handled
    # in chat_tools.send_chat() — the common path for both bu_send_chat
    # and MCP send_chat.  No need to duplicate here.

    # ── Dedup: skip if same (recipient, customer) was sent recently ──
    try:
        _dedup_recipient = normalized_recipient_id or normalized_recipient_name
        _dedup_customer = ""
        _msg_str = config.get("message", "")
        if isinstance(_msg_str, str):
            _msg_obj = try_parse_json(_msg_str)
            if isinstance(_msg_obj, dict):
                _dedup_customer = str(
                    _msg_obj.get("customer_id") or _msg_obj.get("customer_name") or ""
                ).strip()
                # Normalize: strip message-preview suffix from identity keys
                # like "sc|有紫色款吗？" → "sc"
                if "|" in _dedup_customer:
                    _prefix = _dedup_customer.split("|", 1)[0].strip()
                    if _prefix:
                        _dedup_customer = _prefix
        _dedup_key = f"{_dedup_recipient}|{_dedup_customer}" if _dedup_customer else ""
        if _dedup_key:
            now = _time.time()
            # Prune old entries
            _expired = [k for k, t in _send_chat_dedup_cache.items() if now - t > _SEND_CHAT_DEDUP_WINDOW_S]
            for k in _expired:
                _send_chat_dedup_cache.pop(k, None)
            last_sent = _send_chat_dedup_cache.get(_dedup_key)
            if last_sent is not None and now - last_sent < _SEND_CHAT_DEDUP_WINDOW_S:
                logger.info(
                    f"[bu_send_chat] DEDUP: skipping duplicate dispatch "
                    f"(key={_dedup_key}, last_sent={now - last_sent:.1f}s ago, "
                    f"window={_SEND_CHAT_DEDUP_WINDOW_S}s)"
                )
                return ActionResult(
                    extracted_content=(
                        f"Message already sent to this agent for customer '{_dedup_customer}' "
                        f"{now - last_sent:.0f}s ago. Skipping duplicate dispatch."
                    )
                )
            _send_chat_dedup_cache[_dedup_key] = now
        # Track per-customer (any recipient) for Fix A: front-desk
        # actionable_items filter uses this to skip customers with an
        # in-flight dispatch so the DOM's still-stuck pending_timer doesn't
        # loop the LLM into a re-dispatch.
        if _dedup_customer:
            try:
                _cust_now = _time.time()
                _expired_cust = [
                    k for k, t in _send_chat_customer_last.items()
                    if _cust_now - t > _SEND_CHAT_CUSTOMER_WINDOW_S
                ]
                for k in _expired_cust:
                    _send_chat_customer_last.pop(k, None)
                _send_chat_customer_last[_dedup_customer] = _cust_now
            except Exception:
                pass
    except Exception as _dedup_err:
        logger.debug(f"[bu_send_chat] Dedup check failed (non-fatal): {_dedup_err}")

    login = AppContext.login
    logger.info(
        f"[bu_send_chat] runtime sender={bound_sender_agent_id}, "
        f"recipient_id={config.get('recipient_agent_id', '')}, "
        f"recipient_name={config.get('recipient_agent_name', '')}, "
        f"task_id={runtime_ctx.get('task_id', '')}, skill={runtime_ctx.get('skill_name', '')}, "
        f"node_id={runtime_ctx.get('node_id', '')}"
    )
    result = send_chat(login.main_win, config)

    if result.get("success"):
        recipient = result.get("recipient_name") or result.get("recipient_id", "recipient")
        msg = (
            f"Message sent to {recipient}\n"
            f"Chat ID: {result.get('chat_id')}\n"
            f"Message ID: {result.get('message_id')}"
        )
        return ActionResult(extracted_content=msg)
    else:
        return ActionResult(error=f"Failed to send message: {result.get('error', 'Unknown error')}")


@custom_controller.action(
    "Select agents by filtering on agent name, task name, or task description. "
    "Use this to discover agent IDs for routing, delegation, or any multi-agent coordination task.",
    param_model=SelectAgentsAction,
)
async def bu_select_agents(params: SelectAgentsAction) -> ActionResult:
    from agent.mcp.server.chat_utils.chat_tools import list_chat_agents

    config: Dict[str, Any] = {}
    if params.exclude_self is not None:
        config["exclude_self"] = params.exclude_self
    if params.filter_name is not None:
        config["filter_name"] = params.filter_name
    if params.filter_task_name is not None:
        config["filter_task_name"] = params.filter_task_name
    if params.filter_task_description is not None:
        config["filter_task_description"] = params.filter_task_description

    login = AppContext.login
    result = list_chat_agents(login.main_win, config)

    if result.get("success"):
        agents = result.get("agents", [])
        # Also mark discovery at the chat_tools level (via sender agent ID)
        # so the dispatch gate in send_chat() recognises this caller.
        ctx = get_current_runtime_context()
        sender_id = str(ctx.get("agent_id") or "").strip()
        if sender_id:
            from agent.mcp.server.chat_utils.chat_tools import _mark_discovery
            _mark_discovery(sender_id, agents)
        if agents:
            agent_lines = []
            for a in agents:
                tasks_str = ', '.join(a.get('tasks', [])) or 'none'
                descs = a.get('task_descriptions', [])
                desc_str = ('; '.join(descs)) if descs else ''
                line = f"- {a['name']} (ID: {a['id']}, tasks: {tasks_str}"
                if desc_str:
                    line += f", task_desc: {desc_str}"
                line += ")"
                agent_lines.append(line)
            msg = f"Available agents ({result.get('count', 0)}):\n" + "\n".join(agent_lines)
        else:
            msg = "No agents available for chat."
        return ActionResult(extracted_content=msg)
    else:
        return ActionResult(error=f"Failed to list agents: {result.get('error', 'Unknown error')}")


@custom_controller.action(
    "Reconfigure the active HTTP polling event monitor with new URL patterns, content filters, or HTTP methods. "
    "Use this to change what browser events you're listening for without restarting the browser session.",
    param_model=ReconfigureEventMonitorAction,
)
async def bu_reconfigure_event_monitor(params: ReconfigureEventMonitorAction, browser_session: BrowserSession) -> ActionResult:
    """Reconfigure the active event monitor's settings."""
    try:
        from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability

        capability = get_event_monitor_capability(browser_session, create=False)
        monitor_set = capability.get_active_monitor_set() if capability else None
        if not monitor_set or not monitor_set.monitors:
            return ActionResult(error="No active event monitors found on this browser session. Start monitors first.")
        
        # Find the monitor to reconfigure (by label or first one)
        target_monitor = None
        for monitor in monitor_set.monitors:
            if hasattr(monitor, "config"):
                if params.label and getattr(monitor.config, "label", "") == params.label:
                    target_monitor = monitor
                    break
                elif not params.label and not target_monitor:
                    target_monitor = monitor
        
        if not target_monitor:
            available = [getattr(m.config, "label", "unnamed") for m in monitor_set.monitors if hasattr(m, "config")]
            return ActionResult(error=f"Monitor with label '{params.label}' not found. Available: {available}")
        
        # Get the config to update
        if not hasattr(target_monitor, "config"):
            return ActionResult(error="Monitor does not have a reconfigurable config")
        
        config = target_monitor.config
        changes = []
        
        # Update URL patterns
        if params.url_patterns is not None:
            if params.append:
                existing = getattr(config, "url_patterns", [])
                new_patterns = list(set(existing + params.url_patterns))
                config.url_patterns = new_patterns
                changes.append(f"appended url_patterns: {params.url_patterns}")
            else:
                config.url_patterns = params.url_patterns
                changes.append(f"replaced url_patterns with: {params.url_patterns}")
        
        # Update content filters
        if params.content_filters is not None:
            if params.append:
                existing = getattr(config, "content_filters", [])
                new_filters = list(set(existing + params.content_filters))
                config.content_filters = new_filters
                changes.append(f"appended content_filters: {params.content_filters}")
            else:
                config.content_filters = params.content_filters
                changes.append(f"replaced content_filters with: {params.content_filters}")
        
        # Update methods
        if params.methods is not None:
            config.methods = params.methods
            changes.append(f"updated methods to: {params.methods}")
        
        # Update min body length
        if params.min_body_length is not None:
            config.min_body_length = params.min_body_length
            changes.append(f"updated min_body_length to: {params.min_body_length}")
        
        # Rebuild content filter functions if content filters changed
        if params.content_filters is not None:
            from typing import Callable, Optional, List
            
            def _make_filter(s: str):
                def _filter(body: str) -> Optional[str]:
                    return s if s in body else None
                return _filter
            
            new_filter_fns: List[Callable[[str], Optional[str]]] = []
            for substr in config.content_filters:
                new_filter_fns.append(_make_filter(substr))
            
            # Update the filter functions on the capture instance
            if hasattr(target_monitor, "_config") and hasattr(target_monitor._config, "content_filters"):
                target_monitor._config.content_filters = new_filter_fns
            changes.append(f"rebuilt {len(new_filter_fns)} content filter functions")
        
        logger.info(f"[ExtensionTools] Reconfigured event monitor: {', '.join(changes)}")
        return ActionResult(
            extracted_content=f"Event monitor reconfigured successfully:\n" + "\n".join(f"- {c}" for c in changes)
        )
        
    except Exception as e:
        logger.error(f"[ExtensionTools] Error reconfiguring event monitor: {e}")
        return ActionResult(error=f"Failed to reconfigure event monitor: {str(e)}")


@custom_controller.action(
    "List the active session-scoped browser event monitors and their current capability status.",
    param_model=ListSessionMonitorsAction,
)
async def bu_list_session_monitors(params: ListSessionMonitorsAction, browser_session: BrowserSession) -> ActionResult:
    try:
        from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability

        is_frontdesk, task_id = _is_frontdesk_runtime_context()
        dispatch_notice = _frontdesk_dispatch_notice(browser_session, task_id) if is_frontdesk else ""
        capability = get_event_monitor_capability(browser_session, create=True)
        payload = capability.snapshot()
        if not params.include_configs:
            payload.pop("monitor_configs", None)
        summary_text = _compact_monitor_summary_text(payload, include_configs=params.include_configs)
        if dispatch_notice:
            summary_text = dispatch_notice + "\n" + summary_text
        logger.info(
            f"[ExtensionTools] Listed session monitors: "
            f"configured_count={payload.get('configured_count', 0)}, "
            f"active_count={payload.get('active_count', 0)}, "
            f"status={payload.get('status', 'unknown')}"
        )
        return ActionResult(extracted_content=summary_text)
    except Exception as e:
        logger.error(f"[ExtensionTools] Error listing session monitors: {e}")
        return ActionResult(error=f"Failed to list session monitors: {str(e)}")


@custom_controller.action(
    "Create or replace a session-scoped browser event monitor using the canonical monitor schema.",
    param_model=UpsertSessionMonitorAction,
)
async def bu_upsert_session_monitor(params: UpsertSessionMonitorAction, browser_session: BrowserSession) -> ActionResult:
    try:
        from agent.ec_skills.browser_use_extension.event_monitor import parse_monitor_configs
        from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability

        capability = get_event_monitor_capability(browser_session, create=True)
        raw_existing = [
            _normalize_monitor_raw_for_skill(item.get("raw") or {})
            for item in capability.get_configs()
            if isinstance(item, dict)
        ]

        raw_item = _canonicalize_monitor_raw_for_skill(_build_monitor_raw_from_params(params))
        target_id = str(raw_item.get("id") or raw_item.get("label") or "")
        target_label = str(raw_item.get("label") or "")

        # Guard: never replace a working dom_mutation monitor with http_polling
        new_source = str(raw_item.get("sourceType") or "").lower()
        for item in raw_existing:
            item_label2 = str(item.get("label") or "")
            item_source = str(item.get("sourceType") or "").lower()
            if (item_label2 == target_label and item_source == "dom_mutation"
                    and new_source != "dom_mutation"):
                logger.warning(
                    f"[ExtensionTools] Blocked upsert: cannot replace dom_mutation monitor "
                    f"'{target_label}' with source_type='{new_source}'"
                )
                return _json_result({
                    "success": True,
                    "replaced": False,
                    "monitor_id": target_id,
                    "label": target_label,
                    "message": f"Monitor '{target_label}' already exists as dom_mutation and is managed by the system. No changes made.",
                    "configured_count": len(raw_existing),
                })

        filtered_existing = []
        replaced = False
        removed_duplicates = 0
        for item in raw_existing:
            item_id = str(item.get("id") or item.get("label") or "")
            item_label = str(item.get("label") or "")
            if item_id == target_id or item_label == target_label:
                replaced = True
                removed_duplicates += 1
                continue
            filtered_existing.append(item)
        raw_existing = filtered_existing
        raw_existing.append(raw_item)
        raw_existing = _dedupe_monitor_raws(raw_existing)

        configs = parse_monitor_configs({"eventMonitors": {"content": raw_existing}})
        if params.auto_start:
            await capability.replace_monitors(configs, agent_id="")
        else:
            capability.configure(configs)
        logger.info(
            f"[ExtensionTools] Upserted session monitor: "
            f"id={raw_item['id']}, label={raw_item['label']}, source={raw_item.get('sourceType')}, "
            f"replaced={replaced}, removed_duplicates={removed_duplicates}, "
            f"auto_start={params.auto_start}, configured_count={len(configs)}"
        )

        return _json_result({
            "success": True,
            "replaced": replaced,
            "monitor_id": raw_item["id"],
            "label": raw_item["label"],
            "auto_start": params.auto_start,
            "configured_count": len(configs),
        })
    except Exception as e:
        logger.error(f"[ExtensionTools] Error upserting session monitor: {e}")
        return ActionResult(error=f"Failed to upsert session monitor: {str(e)}")


@custom_controller.action(
    "Remove a configured session browser event monitor by id or label.",
    param_model=RemoveSessionMonitorAction,
)
async def bu_remove_session_monitor(params: RemoveSessionMonitorAction, browser_session: BrowserSession) -> ActionResult:
    try:
        from agent.ec_skills.browser_use_extension.event_monitor import parse_monitor_configs
        from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability

        capability = get_event_monitor_capability(browser_session, create=True)
        raw_existing = []
        removed = []
        for cfg_item in capability.get_configs():
            item = _normalize_monitor_raw_for_skill((cfg_item or {}).get("raw") or {})
            item_id = str(item.get("id") or item.get("label") or "")
            if item_id == params.id_or_label or item.get("label") == params.id_or_label:
                removed.append(item_id)
                continue
            raw_existing.append(item)

        configs = parse_monitor_configs({"eventMonitors": {"content": raw_existing}})
        if params.auto_restart:
            if raw_existing:
                await capability.replace_monitors(configs, agent_id="")
            else:
                await capability.stop()
                capability.configure([])
        else:
            capability.configure(configs)
        logger.info(
            f"[ExtensionTools] Removed session monitor(s): removed={removed}, "
            f"remaining_count={len(configs)}, auto_restart={params.auto_restart}"
        )

        return _json_result({
            "success": True,
            "removed": removed,
            "remaining_count": len(configs),
        })
    except Exception as e:
        logger.error(f"[ExtensionTools] Error removing session monitor: {e}")
        return ActionResult(error=f"Failed to remove session monitor: {str(e)}")


@custom_controller.action(
    "Return the current event-monitor capability snapshot for the active browser session.",
    param_model=GetSessionMonitorSnapshotAction,
)
async def bu_get_session_monitor_snapshot(params: GetSessionMonitorSnapshotAction, browser_session: BrowserSession) -> ActionResult:
    try:
        from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability

        is_frontdesk, task_id = _is_frontdesk_runtime_context()
        capability = get_event_monitor_capability(browser_session, create=True)
        full_payload = capability.snapshot()
        if is_frontdesk:
            instance = _extract_control_monitor_instance(full_payload)
            status = str(instance.get("status") or "").strip()
            current_url = str(instance.get("current_url") or "").strip()
            if status in ("ok", "empty", "no_match") and "/control" in current_url:
                _mark_frontdesk_dispatch_ready(browser_session, full_payload, task_id)
                auto_assign_result = _maybe_frontdesk_auto_assign(full_payload, browser_session, task_id)
            else:
                auto_assign_result = {"attempted": False}
        else:
            auto_assign_result = {"attempted": False}
        payload = dict(full_payload)
        if not params.include_configs:
            payload.pop("monitor_configs", None)
        if not params.include_runtime:
            payload = {
                "configured_count": payload.get("configured_count", 0),
                "monitor_configs": payload.get("monitor_configs", []),
            }
        summary_text = _compact_monitor_summary_text(
            full_payload if params.include_runtime else payload,
            include_configs=params.include_configs,
        )
        if auto_assign_result.get("attempted"):
            assigned_rows = auto_assign_result.get("assigned_rows") or []
            failure_rows = auto_assign_result.get("failure_rows") or []
            tab_rows = auto_assign_result.get("tab_rows") or []
            pending_sessions = auto_assign_result.get("pending_sessions") or []
            auto_lines = [
                "FRONT-DESK AUTO-ASSIGN CHECK:",
                f"- visible_session_count={auto_assign_result.get('visible_count', 0)}",
                f"- open_tab_hits={len(tab_rows)}",
                f"- assigned_now={len(assigned_rows)}",
                f"- assignment_failures={len(failure_rows)}",
            ]
            if auto_assign_result.get("waiting_for_tabs"):
                auto_lines.append(f"- waiting_for_tabs={len(pending_sessions)}")
            if assigned_rows:
                auto_lines.append("- assigned_sessions=" + ", ".join(assigned_rows))
            if pending_sessions:
                auto_lines.append("- pending_sessions=" + ", ".join(str(x) for x in pending_sessions))
            if failure_rows:
                auto_lines.append("- failures=" + " | ".join(str(x) for x in failure_rows))
            summary_text = "\n".join(auto_lines) + "\n\n" + summary_text
        dispatch_notice = _frontdesk_dispatch_notice(browser_session, task_id) if is_frontdesk else ""
        if dispatch_notice:
            summary_text = dispatch_notice + "\n" + summary_text
        logger.info(
            f"[ExtensionTools] Session monitor snapshot: "
            f"configured_count={payload.get('configured_count', 0)}, "
            f"status={payload.get('status', 'n/a')}, include_runtime={params.include_runtime}"
        )
        return ActionResult(extracted_content=summary_text)
    except Exception as e:
        logger.error(f"[ExtensionTools] Error getting session monitor snapshot: {e}")
        return ActionResult(error=f"Failed to get session monitor snapshot: {str(e)}")


@custom_controller.action(
    "Persist configured session monitors back into the current browser-automation node's skill JSON and bundle JSON. "
    "This saves self-discovered monitor configs for later runs without keeping monitors active after done().",
    param_model=PersistSessionMonitorsToSkillAction,
)
async def bu_persist_session_monitors_to_skill(
    params: PersistSessionMonitorsToSkillAction,
    browser_session: BrowserSession,
) -> ActionResult:
    try:
        from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability

        capability = get_event_monitor_capability(browser_session, create=True)
        configured = capability.get_configs()
        raw_monitors = []
        wanted = {str(v).strip() for v in params.monitor_ids_or_labels if str(v).strip()}
        for item in configured:
            if not isinstance(item, dict):
                continue
            raw = _canonicalize_monitor_raw_for_skill(item.get("raw") or {})
            item_id = str(raw.get("id") or raw.get("label") or "")
            label = str(raw.get("label") or "")
            if wanted and item_id not in wanted and label not in wanted:
                continue
            raw_monitors.append(raw)

        if not raw_monitors:
            return ActionResult(error="No configured monitors matched the requested ids/labels.")

        current_agent = get_current_agent()
        skill_name = str(
            getattr(current_agent, "_ecan_skill_name", None)
            or getattr(current_agent, "skill_id", None)
            or getattr(current_agent, "cloud_skill_id", None)
            or ""
        ).strip()
        node_id = str(
            getattr(current_agent, "_ecan_node_id", None)
            or getattr(current_agent, "node_id", None)
            or getattr(current_agent, "cloud_node_id", None)
            or ""
        ).strip()
        if not skill_name or not node_id:
            return ActionResult(error="Current agent is missing skill/node metadata, cannot persist monitor config.")

        core_path, bundle_path = _resolve_skill_file_paths(skill_name)
        logger.info(
            f"[ExtensionTools] Persisting session monitors to skill: "
            f"skill={skill_name}, node_id={node_id}, core_path={core_path}, bundle_path={bundle_path}"
        )
        core_payload = _read_json_file(core_path)
        core_updated = _update_skill_node_monitors(core_payload, node_id, raw_monitors)
        if not core_updated:
            return ActionResult(error=f"Node '{node_id}' not found in {core_path}")
        _write_json_file(core_path, core_payload)

        bundle_updated = False
        if bundle_path and bundle_path.exists():
            bundle_payload = _read_json_file(bundle_path)
            bundle_updated = _update_bundle_node_monitors(bundle_payload, node_id, raw_monitors)
            if bundle_updated:
                _write_json_file(bundle_path, bundle_payload)

        if params.stop_after_persist:
            await capability.stop()
        logger.info(
            f"[ExtensionTools] Persisted session monitors to skill: "
            f"skill={skill_name}, node_id={node_id}, persisted_count={len(raw_monitors)}, "
            f"bundle_updated={bundle_updated}, stopped_after_persist={bool(params.stop_after_persist)}"
        )

        return _json_result({
            "success": True,
            "skill_name": skill_name,
            "node_id": node_id,
            "core_path": str(core_path),
            "bundle_path": str(bundle_path) if bundle_path else "",
            "bundle_updated": bundle_updated,
            "persisted_count": len(raw_monitors),
            "stopped_after_persist": bool(params.stop_after_persist),
        })
    except Exception as e:
        logger.error(f"[ExtensionTools] Error persisting session monitors to skill: {e}")
        return ActionResult(error=f"Failed to persist session monitors to skill: {str(e)}")


@custom_controller.action(
    "Inspect visible DOM regions and summarize repeated/interactive areas for agentic page understanding.",
    param_model=InspectDomRegionsAction,
)
async def bu_inspect_dom_regions(params: InspectDomRegionsAction, browser_session: BrowserSession) -> ActionResult:
    try:
        is_frontdesk, task_id = _is_frontdesk_runtime_context()
        expression = _build_dom_region_inspection_expression(
            max_regions=params.max_regions,
            max_text_length=params.max_text_length,
            include_html_hint=params.include_html_hint,
        )
        summary = await _evaluate_js(browser_session, expression)
        logger.info(
            f"[ExtensionTools] Inspected DOM regions: "
            f"url={summary.get('url', '') if isinstance(summary, dict) else ''}, "
            f"regions={len(summary.get('regions', []) if isinstance(summary, dict) else [])}, "
            f"max_regions={params.max_regions}"
        )
        summary_text = _compact_dom_region_summary_text(
            summary,
            max_regions=params.max_regions,
        )
        dispatch_notice = _frontdesk_dispatch_notice(browser_session, task_id) if is_frontdesk else ""
        if dispatch_notice:
            summary_text = dispatch_notice + "\n" + summary_text
        return ActionResult(extracted_content=summary_text)
    except Exception as e:
        logger.error(f"[ExtensionTools] Error inspecting DOM regions: {e}")
        return ActionResult(error=f"Failed to inspect DOM regions: {str(e)}")


@custom_controller.action(
    "Heuristically discover a generic chat adapter proposal from the current page structure.",
    param_model=DiscoverChatAdapterAction,
)
async def bu_discover_chat_adapter(params: DiscoverChatAdapterAction, browser_session: BrowserSession) -> ActionResult:
    try:
        expression = _build_dom_region_inspection_expression(
            max_regions=params.max_regions,
            max_text_length=160,
            include_html_hint=False,
        )
        summary = await _evaluate_js(browser_session, expression)
        adapter = _pick_chat_adapter_from_regions(summary, prefer_selected_thread=params.prefer_selected_thread)
        logger.info(
            f"[ExtensionTools] Discovered chat adapter: "
            f"url={summary.get('url', '') if isinstance(summary, dict) else ''}, "
            f"conversation_root={((adapter.get('conversation_region') or {}).get('root_selector', ''))}, "
            f"thread_root={((adapter.get('thread_region') or {}).get('root_selector', ''))}"
        )
        return _json_result({
            "page_summary": summary,
            "adapter_proposal": adapter,
        })
    except Exception as e:
        logger.error(f"[ExtensionTools] Error discovering chat adapter: {e}")
        return ActionResult(error=f"Failed to discover chat adapter: {str(e)}")


@custom_controller.action(
    "Normalize the current page into a semantic state using a provided adapter JSON.",
    param_model=NormalizePageStateAction,
)
async def bu_normalize_page_state(params: NormalizePageStateAction, browser_session: BrowserSession) -> ActionResult:
    try:
        adapter = json.loads(params.adapter_json)
        expression = _build_dom_region_inspection_expression(
            max_regions=25,
            max_text_length=200,
            include_html_hint=False,
        )
        summary = await _evaluate_js(browser_session, expression)
        normalized = _normalize_items_with_adapter(adapter, summary)
        logger.info(
            f"[ExtensionTools] Normalized page state: "
            f"adapter_type={normalized.get('adapter_type', '')}, "
            f"url={normalized.get('url', '')}, "
            f"conversations={len(normalized.get('conversations', []) or [])}"
        )
        return _json_result(normalized)
    except Exception as e:
        logger.error(f"[ExtensionTools] Error normalizing page state: {e}")
        return ActionResult(error=f"Failed to normalize page state: {str(e)}")


@custom_controller.action(
    "Diff two normalized page-state JSON blobs and return semantic change events.",
    param_model=DiffNormalizedStateAction,
)
async def bu_diff_normalized_state(params: DiffNormalizedStateAction) -> ActionResult:
    try:
        previous_state = json.loads(params.previous_state_json)
        current_state = json.loads(params.current_state_json)
        diff = _diff_normalized_states(previous_state, current_state)
        logger.info(
            f"[ExtensionTools] Diffed normalized state: "
            f"events={diff.get('event_types', [])}, "
            f"added={len(diff.get('added_keys', []) or [])}, "
            f"removed={len(diff.get('removed_keys', []) or [])}, "
            f"reordered={len(diff.get('reordered_keys', []) or [])}, "
            f"changed={len(diff.get('changed_keys', []) or [])}, "
            f"top_changed={diff.get('top_changed', False)}"
        )
        return _json_result(diff)
    except Exception as e:
        logger.error(f"[ExtensionTools] Error diffing normalized state: {e}")
        return ActionResult(error=f"Failed to diff normalized state: {str(e)}")


@custom_controller.action(
    "Send an SMS to a phone number via AWS End User Messaging SMS. "
    "Phone number must be E.164 (e.g. '+14155550100', country code included). "
    "Use for short notifications, alerts, or 2FA confirmations.",
    param_model=SendSmsAction,
)
async def bu_send_sms(params: SendSmsAction) -> ActionResult:
    from agent.mcp.server.messaging.messaging_tools import send_sms

    mainwin = AppContext.get_main_window()
    if mainwin is None:
        return ActionResult(error="bu_send_sms: AppContext main window unavailable.")

    phone = (params.phone_number or "").strip()
    message = (params.message or "").strip()
    if not phone:
        return ActionResult(error="bu_send_sms: phone_number is required.")
    if not message:
        return ActionResult(error="bu_send_sms: message is required.")
    if not phone.startswith("+"):
        return ActionResult(
            error=(
                f"bu_send_sms: phone_number must be E.164 (start with +country code). "
                f"Got: {phone!r}"
            )
        )

    try:
        result = await send_sms(mainwin, {"input": {"phone_number": phone, "message": message}})
        text = ""
        if isinstance(result, list) and result:
            first = result[0]
            text = getattr(first, "text", str(first))
        else:
            text = str(result)
        if text.lstrip().startswith("❌") or text.lstrip().startswith("Error"):
            return ActionResult(error=text)
        return ActionResult(
            extracted_content=text,
            include_in_memory=True,
            long_term_memory=f"Sent SMS to {phone}",
        )
    except Exception as e:
        logger.error(f"[bu_send_sms] Exception: {e}", exc_info=True)
        return ActionResult(error=f"bu_send_sms failed: {e}")


@custom_controller.action(
    "Send an email via AWS SES. Provide at least one of body_text or body_html. "
    "The sender address is configured cloud-side and not user-supplied. "
    "Use for outbound notifications, reports, or follow-ups.",
    param_model=SendEmailAction,
)
async def bu_send_email(params: SendEmailAction) -> ActionResult:
    from agent.mcp.server.messaging.messaging_tools import send_email

    mainwin = AppContext.get_main_window()
    if mainwin is None:
        return ActionResult(error="bu_send_email: AppContext main window unavailable.")

    to_addr = (params.to or "").strip()
    subject = (params.subject or "").strip()
    body_text = (params.body_text or "").strip() if params.body_text else None
    body_html = (params.body_html or "").strip() if params.body_html else None
    reply_to = (params.reply_to or "").strip() if params.reply_to else None

    if not to_addr or "@" not in to_addr:
        return ActionResult(error=f"bu_send_email: invalid 'to' address: {to_addr!r}")
    if not subject:
        return ActionResult(error="bu_send_email: subject is required.")
    if not body_text and not body_html:
        return ActionResult(
            error="bu_send_email: at least one of body_text or body_html must be provided."
        )

    cfg: Dict[str, Any] = {"to": to_addr, "subject": subject}
    if body_text:
        cfg["body_text"] = body_text
    if body_html:
        cfg["body_html"] = body_html
    if reply_to:
        cfg["reply_to"] = reply_to

    try:
        result = await send_email(mainwin, {"input": cfg})
        text = ""
        if isinstance(result, list) and result:
            first = result[0]
            text = getattr(first, "text", str(first))
        else:
            text = str(result)
        if text.lstrip().startswith("❌") or text.lstrip().startswith("Error"):
            return ActionResult(error=text)
        return ActionResult(
            extracted_content=text,
            include_in_memory=True,
            long_term_memory=f"Sent email to {to_addr}: {subject}",
        )
    except Exception as e:
        logger.error(f"[bu_send_email] Exception: {e}", exc_info=True)
        return ActionResult(error=f"bu_send_email failed: {e}")


# Log registered custom actions at module load time for debugging
try:
    # Access the actions dict from registry.registry.actions (current browser-use API)
    action_registry = custom_controller.registry.registry.actions
    action_names = list(action_registry.keys())
    logger.info(f"[Browser-Use Extension] Registered {len(action_registry)} custom actions: {action_names}")

    # Startup self-check: ensure critical actions are loaded in current process.
    required_actions = ["download_file", "convert_file_format"]
    missing_actions = [a for a in required_actions if a not in action_names]
    if missing_actions:
        logger.error(
            "[Browser-Use Extension] Startup self-check FAILED. "
            f"Missing actions: {missing_actions}. "
            "Please restart main.py to load latest extension actions."
        )
    else:
        logger.info(
            "[Browser-Use Extension] Startup self-check OK. "
            f"Critical actions loaded: {required_actions}"
        )
except AttributeError:
    logger.warning("[Browser-Use Extension] Could not access registry actions - API may have changed")

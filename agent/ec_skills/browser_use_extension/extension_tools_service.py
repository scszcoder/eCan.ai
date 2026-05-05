import hashlib
import asyncio
import json
import os
import shutil
import subprocess
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional, List
from pathlib import Path
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionResult
from browser_use import BrowserSession, Controller
from agent.mcp.server.code_utils.code_tools import run_code, run_shell_script
from agent.ec_skills.browser_use_extension.extension_tools_views import (
    ConvertFileFormatAction,
    DownloadFileAction,
    DiffNormalizedStateAction,
    DiscoverChatAdapterAction,
    ExtractDomAction,
    FeigeGetChatThreadAction,
    FeigeListSessionsAction,
    FeigeOpenSessionAction,
    FeigeSendMessageAction,
    FileRenameAction,
    FilesPrintAction,
    GetSessionMonitorSnapshotAction,
    InspectDomRegionsAction,
    LabelInputFile,
    LabelsReformatAction,
    ListSessionMonitorsAction,
    SelectAgentsAction,
    NormalizePageStateAction,
    PersistSessionMonitorsToSkillAction,
    RagQueryAction,
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
    _FEIGE_TARGET_RESOLVE_TIMEOUT_S = float(
        os.getenv("ECAN_FEIGE_TARGET_RESOLVE_TIMEOUT_S", "2.0")
    )
except Exception:
    _FEIGE_TARGET_RESOLVE_TIMEOUT_S = 2.0
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
    skill_dir = Path("my_skills") / f"{skill_name}_skill" / "diagram_dir"
    core_candidates = [
        skill_dir / f"{skill_name}_skill.json",
        skill_dir / f"{skill_name}.json",
    ]
    bundle_candidates = [
        skill_dir / f"{skill_name}_skill_bundle.json",
        skill_dir / f"{skill_name}_bundle.json",
    ]
    core_path = next((p for p in core_candidates if p.exists()), None)
    if core_path is None and skill_dir.exists():
        core_path = next(iter(skill_dir.glob("*_skill.json")), None)
        if core_path is None:
            core_path = next(iter(skill_dir.glob("*.json")), None)
    if core_path is None:
        raise FileNotFoundError(f"Could not locate skill JSON for skill '{skill_name}' under {skill_dir}")
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


async def _evaluate_js(
    browser_session: BrowserSession,
    expression: str,
    *,
    target_id: str | None = None,
    focus: bool = True,
) -> Any:
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets import (
            session_cdp_operation_lock as _session_cdp_operation_lock,
        )
        operation_lock = _session_cdp_operation_lock(browser_session)
    except Exception:
        operation_lock = None

    async def _run_eval() -> Any:
        cdp_session = None
        cdp_client = None
        if hasattr(browser_session, "get_or_create_cdp_session"):
            if target_id:
                cdp_session = await browser_session.get_or_create_cdp_session(
                    target_id=target_id,
                    focus=focus,
                )
            else:
                cdp_session = await browser_session.get_or_create_cdp_session()
            cdp_client = cdp_session.cdp_client if cdp_session else None
        elif hasattr(browser_session, "cdp_client"):
            cdp_client = browser_session.cdp_client
        if not cdp_client:
            raise RuntimeError("No CDP client available")

        session_id = getattr(cdp_session, "session_id", None) if cdp_session else None
        eval_params = {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        }
        if session_id:
            await cdp_client.send.Runtime.enable(session_id=session_id)
            return await cdp_client.send.Runtime.evaluate(
                params=eval_params,
                session_id=session_id,
            )
        await cdp_client.send.Runtime.enable()
        return await cdp_client.send.Runtime.evaluate(params=eval_params)

    async def _run_with_optional_operation_lock() -> Any:
        if operation_lock is not None:
            async with operation_lock:
                return await _run_eval()
        return await _run_eval()

    try:
        result = await asyncio.wait_for(
            _run_with_optional_operation_lock(),
            timeout=_CDP_EVALUATE_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"CDP Runtime.evaluate timed out after {_CDP_EVALUATE_TIMEOUT_S:.1f}s"
        ) from exc
    value = result.get("result", {}).get("value", "")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


async def _resolve_feige_tab_target_id_bounded(
    browser_session: BrowserSession,
    *,
    timeout_s: float | None = None,
    resolver=None,
) -> str:
    """Resolve the Feige tab target with a hard timeout.

    Direct delivery already performs this lookup once before calling the
    send tool.  The send tool still needs its own bounded lookup because a
    stale Chrome/CDP state can hang here and otherwise keep the Feige typing
    lock held indefinitely.
    """
    timeout = _FEIGE_TARGET_RESOLVE_TIMEOUT_S if timeout_s is None else timeout_s
    try:
        if resolver is None:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets import (
                resolve_feige_tab_target_id,
            )
            resolver = resolve_feige_tab_target_id
        return str(await asyncio.wait_for(resolver(browser_session), timeout=timeout) or "")
    except asyncio.TimeoutError:
        logger.warning(
            f"[Feige] Feige target id resolve timed out after {timeout:.1f}s"
        )
        return ""
    except Exception as target_err:
        logger.debug(
            f"[Feige] Feige target id resolve failed: {target_err}"
        )
        return ""


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
    """
    MAX_CHAR_LIMIT = 30000
    query = params.query or ""
    extract_links = params.extract_links
    start_from_char = params.start_from_char or 0

    try:
        from browser_use.dom.markdown_extractor import extract_clean_markdown
        content, content_stats = await extract_clean_markdown(
            browser_session=browser_session, extract_links=extract_links
        )
    except Exception as e:
        logger.error(f"[extract_dom] Failed to extract markdown: {e}", exc_info=True)
        return ActionResult(error=f"Could not extract clean markdown: {type(e).__name__}: {e}")

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
    # `feige_open_session` (which has session_id/chat_url) into a
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
                            "field of the matching feige_list_sessions entry for "
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


# ─── Feige (飞鸽) platform-specific tools ─────────────────────────────────────
#
# Selectors confirmed from live DOM captures (Feige customer-service web app).
# Session list panel:
#   Scroll root : #chantListScrollArea
#   Items       : [data-qa-id="qa-conversation-chat-item"]
#   Name        : .MP1bk3ccfHC9V2SnPCGD (title attr) or .Jv6FtqUv5VoYARd2pp4y (text)
#   Last msg    : .lF_M7QiFB0ukHWpMfQde span
#   Timestamp   : .CEnLM8MEGksTdgi_8Lqf (absolute) or .FDBMBK87T0SHSZ_4swP6 (relative "45秒")
#   Last msg ID : data-btm attr on bottom-row div (changes per message, used for change detection)
#   Unread badge: .rxAvaVFJHvpEGMc1ejm1  (div; empty = CSS dot badge, number = count badge;
#                 ALWAYS present in DOM — do NOT use :has() to filter by it)
#   Tab buttons : [data-qa-id="qa-active-chat-tab"]  (当前会话)
#                 [data-qa-id="qa-last-chat-tab"]    (最近联系)
#
# Chat thread (confirmed from live DOM):
#   Message wrappers : [data-qa-id="qa-message-warpper"]  ← Feige typo, NOT "wrapper"
#   Bubble element   : .iD7SHBvMhm4OhfCsBGr1
#   Agent bubble     : .messageIsMe   (flex-direction: row-reverse)
#   Customer bubble  : .messageNotMe  (flex-direction: row)
#   Timestamp        : .O4UWWFoQxgMq4AWHMq25
#   Message id       : data-id attr on child div of wrapper
#   System messages  : .BqNO6cexAGBsZgUmEzIE or .e0Bi5IauHWvUG8773oi9
#
# Chat compose area (confirmed from live DOM):
#   Input   : textarea[data-qa-id="qa-send-message-textarea"]
#   Send btn: [data-qa-id="qa-send-message-button"]  (div, not button)
#
# If a selector stops working, run feige_get_chat_thread or feige_list_sessions with
# extract_dom=True to get fresh HTML snippets and update the constants below.
# ─────────────────────────────────────────────────────────────────────────────

_FEIGE_SESSION_ITEM = '[data-qa-id="qa-conversation-chat-item"]'
_FEIGE_SESSION_SCROLL = '#chantListScrollArea'
_FEIGE_NAME_ATTR_PARENT = '.MP1bk3ccfHC9V2SnPCGD'
_FEIGE_NAME_TEXT = '.Jv6FtqUv5VoYARd2pp4y'
_FEIGE_LAST_MSG = '.lF_M7QiFB0ukHWpMfQde span'
_FEIGE_TIMESTAMP = '.CEnLM8MEGksTdgi_8Lqf'
_FEIGE_UNREAD = '.rxAvaVFJHvpEGMc1ejm1'

_FEIGE_LIST_SESSIONS_JS = r"""
(function(includeRead, maxSessions) {
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.recent') || btm.endsWith('.systemConv')) return false;
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  var allItems = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
  var items = allItems.filter(rowIsCurrent);
  var results = [];
  for (var i = 0; i < Math.min(items.length, maxSessions); i++) {
    var el = items[i];
    var nameEl = el.querySelector('.MP1bk3ccfHC9V2SnPCGD');
    var name = (nameEl && (nameEl.getAttribute('title') || nameEl.textContent || '')).trim();
    if (!name) {
      var nameEl2 = el.querySelector('.Jv6FtqUv5VoYARd2pp4y');
      name = nameEl2 ? nameEl2.textContent.trim() : '';
    }
    var lastMsgEl = el.querySelector('.lF_M7QiFB0ukHWpMfQde span');
    var lastMsg = lastMsgEl ? lastMsgEl.textContent.trim() : '';
    var tsEl = el.querySelector('.CEnLM8MEGksTdgi_8Lqf');
    var ts = tsEl ? tsEl.textContent.trim() : '';
    // Detect unread count and tags from .rxAvaVFJHvpEGMc1ejm1
    // This element can contain either a numeric unread badge OR a warning tag (e.g. 服务态度预警)
    var unread = 0;
    var tags = [];
    var unreadEl = el.querySelector('.rxAvaVFJHvpEGMc1ejm1');
    if (unreadEl) {
      var rawText = unreadEl.textContent.trim();
      var parsed = parseInt(rawText, 10);
      if (!isNaN(parsed) && String(parsed) === rawText) {
        unread = parsed;
      } else if (rawText) {
        // Non-numeric text = tag (e.g. 服务态度预警)
        tags.push(rawText);
      }
    }
    if (unread === 0) {
      // Fallback: sup element (dot/number badge)
      var supEl = el.querySelector('sup');
      if (supEl) {
        unread = parseInt(supEl.textContent.trim(), 10) || 1;
      }
    }
    // Collect inline tags (e.g. 重复来访)
    var tagEls = el.querySelectorAll('.obeJrSyU4KwAzGeRfcbk span');
    for (var j = 0; j < tagEls.length; j++) {
      var tagText = tagEls[j].textContent.trim();
      if (tagText && tags.indexOf(tagText) < 0) tags.push(tagText);
    }
    if (!includeRead && unread === 0 && tags.length === 0) continue;
    results.push({ index: i, name: name, last_message: lastMsg, timestamp: ts, unread: unread, tags: tags });
  }
  return JSON.stringify({ sessions: results, total_visible: items.length });
})(INCLUDE_READ, MAX_SESSIONS);
"""


@custom_controller.action(
    "List visible customer sessions in the Feige (飞鸽) customer-service session panel.",
    param_model=FeigeListSessionsAction,
)
async def feige_list_sessions(params: FeigeListSessionsAction, browser_session: BrowserSession) -> ActionResult:
    try:
        js = _FEIGE_LIST_SESSIONS_JS.replace("INCLUDE_READ", "true" if params.include_read else "false")
        js = js.replace("MAX_SESSIONS", str(params.max_sessions))
        data = await _evaluate_js(browser_session, js)
        if isinstance(data, str):
            import json as _json
            data = _json.loads(data)
        sessions = data.get("sessions", []) if isinstance(data, dict) else []
        total = data.get("total_visible", 0) if isinstance(data, dict) else 0
        logger.info(f"[Feige] Listed sessions: visible={total}, returned={len(sessions)}")
        return _json_result({"sessions": sessions, "total_visible": total})
    except Exception as e:
        logger.error(f"[Feige] feige_list_sessions error: {e}")
        return ActionResult(error=f"feige_list_sessions failed: {e}")


_FEIGE_OPEN_SESSION_JS = r"""
(function(customerName, sessionIndex) {
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.recent') || btm.endsWith('.systemConv')) return false;
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  var allItems = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
  var items = allItems.filter(rowIsCurrent);
  var target = null;
  if (customerName) {
    for (var i = 0; i < items.length; i++) {
      var nameEl = items[i].querySelector('.MP1bk3ccfHC9V2SnPCGD');
      var name = (nameEl && (nameEl.getAttribute('title') || nameEl.textContent || '')).trim();
      if (!name) {
        var nameEl2 = items[i].querySelector('.Jv6FtqUv5VoYARd2pp4y');
        name = nameEl2 ? nameEl2.textContent.trim() : '';
      }
      if (name === customerName) { target = items[i]; break; }
    }
  }
  if (!target && sessionIndex >= 0 && sessionIndex < items.length) {
    target = items[sessionIndex];
  }
  if (!target) return JSON.stringify({
    clicked: false,
    error: 'Session not found in current conversations',
    current_visible: items.length,
    total_visible: allItems.length
  });
  target.click();
  var nameEl = target.querySelector('.MP1bk3ccfHC9V2SnPCGD');
  var clickedName = (nameEl && (nameEl.getAttribute('title') || nameEl.textContent || '')).trim();
  return JSON.stringify({ clicked: true, name: clickedName });
})(CUSTOMER_NAME, SESSION_INDEX);
"""


@custom_controller.action(
    "Open a customer chat session in Feige (飞鸽) by clicking on it in the session list.",
    param_model=FeigeOpenSessionAction,
)
async def feige_open_session(params: FeigeOpenSessionAction, browser_session: BrowserSession) -> ActionResult:
    try:
        name_js = json.dumps(params.customer_name, ensure_ascii=False) if params.customer_name else "null"
        idx_js = str(params.session_index) if params.session_index is not None else "-1"
        js = _FEIGE_OPEN_SESSION_JS.replace("CUSTOMER_NAME", name_js).replace("SESSION_INDEX", idx_js)
        data = await _evaluate_js(browser_session, js)
        if isinstance(data, str):
            import json as _json
            data = _json.loads(data)
        if isinstance(data, dict) and data.get("clicked"):
            logger.info(f"[Feige] Opened session: name={data.get('name')}")
            return ActionResult(extracted_content=f"Opened session: {data.get('name', '(unknown)')}")
        err = data.get("error") if isinstance(data, dict) else str(data)
        return ActionResult(error=f"feige_open_session: {err}")
    except Exception as e:
        logger.error(f"[Feige] feige_open_session error: {e}")
        return ActionResult(error=f"feige_open_session failed: {e}")


# NOTE: Chat thread selectors below are best-effort guesses derived from common
# Feige DOM patterns.  If they stop working, extract a fresh chat thread DOM
# snapshot (e.g. via extract_dom on the right-hand pane) and update the JS.
_FEIGE_GET_THREAD_JS = r"""
(function(maxMessages) {
  // Confirmed selectors from live DOM capture (note Feige typo: "warpper" not "wrapper")
  // Each message wrapper: [data-qa-id="qa-message-warpper"] > div[data-id] > div.tC9ap6QtAyeCD0jfuMns
  // Agent message:   inner div with flex-direction:row-reverse  OR  class containing "messageIsMe"
  // Customer message: inner div with flex-direction:row          OR  class containing "messageNotMe"
  // System/event:    div.tC9ap6QtAyeCD0jfuMns containing no leaveMessageWrapper (just text spans)
  //
  // Image bubbles do NOT have ".iD7SHBvMhm4OhfCsBGr1" — the bubble is a
  // bare <img alt="图片"> inside the row container.  We extract images
  // from the row separately (skipping avatar imgs by class+alt) so an
  // image-only message is no longer silently dropped.
  function _collectAttachments(row) {
    if (!row) return [];
    var atts = [];
    var imgs = Array.from(row.querySelectorAll('img'));
    for (var k = 0; k < imgs.length; k++) {
      var im = imgs[k];
      var cls = (im.className || '').toString();
      var alt = (im.getAttribute('alt') || '').trim();
      if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
      if (alt === '头像') continue;
      // Prefer the resolved ``.src`` property over the raw attribute
      // so relative URLs (``/sample0.png``) become absolute, matching
      // what the downstream aiohttp-based eager-fetch requires.  See
      // ``feige_chat/dom_assets.py`` for the same fix on the bubble
      // scraper.
      var src = im.src || im.getAttribute('src') || '';
      if (!src) continue;
      if (src.indexOf('data:image/svg') === 0) continue;
      atts.push({ kind: 'image', url: src, alt: alt });
    }
    return atts;
  }
  var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
  var results = [];
  var start = Math.max(0, wrappers.length - maxMessages);
  for (var i = start; i < wrappers.length; i++) {
    var wrap = wrappers[i];
    // Row container holds avatar + bubble; flex-direction tells us sender.
    var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
    var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1');
    if (!bubble && !row) {
      // System/event message (no bubble, no row) — capture inner text.
      var sysEl = wrap.querySelector('.BqNO6cexAGBsZgUmEzIE, .e0Bi5IauHWvUG8773oi9, .rcHPT4n3TlQD0Nu4sSiv');
      if (sysEl) {
        results.push({ index: i, text: sysEl.textContent.trim(), is_agent: false, is_system: true, timestamp: '', attachments: [] });
      }
      continue;
    }
    var text = bubble ? (bubble.querySelector('pre') || bubble).textContent.trim() : '';
    // Determine sender: prefer the bubble's class, fall back to row direction.
    var isAgent;
    if (bubble) {
      isAgent = bubble.classList.contains('messageIsMe');
    } else {
      isAgent = ((row && row.style.flexDirection) || '').indexOf('reverse') !== -1;
    }
    var attachments = _collectAttachments(row);
    // Drop bubbles with neither text nor attachments (defensive).
    if (!text && attachments.length === 0) continue;
    var tsEl = wrap.querySelector('.O4UWWFoQxgMq4AWHMq25');
    var ts = tsEl ? tsEl.textContent.trim() : '';
    var msgIdEl = wrap.querySelector('[data-id]');
    var msgId = msgIdEl ? msgIdEl.getAttribute('data-id') : '';
    results.push({ index: i, text: text, is_agent: isAgent, is_system: false, timestamp: ts, msg_id: msgId, attachments: attachments });
  }
  return JSON.stringify({ messages: results, total_found: wrappers.length, selector_used: wrappers.length > 0 ? 'matched' : 'none' });
})(MAX_MESSAGES);
"""


@custom_controller.action(
    "Extract visible messages from the currently open Feige (飞鸽) chat thread.",
    param_model=FeigeGetChatThreadAction,
)
async def feige_get_chat_thread(params: FeigeGetChatThreadAction, browser_session: BrowserSession) -> ActionResult:
    try:
        js = _FEIGE_GET_THREAD_JS.replace("MAX_MESSAGES", str(params.max_messages))
        data = await _evaluate_js(browser_session, js)
        if isinstance(data, str):
            import json as _json
            data = _json.loads(data)
        messages = data.get("messages", []) if isinstance(data, dict) else []
        total = data.get("total_found", 0) if isinstance(data, dict) else 0
        selector_used = data.get("selector_used", "unknown") if isinstance(data, dict) else "unknown"
        logger.info(f"[Feige] Got chat thread: total={total}, returned={len(messages)}, selector={selector_used}")
        if selector_used == "none":
            return ActionResult(
                extracted_content="No message elements found. The chat thread selectors may need updating. "
                "Use extract_dom on the right-hand chat pane to get fresh HTML and update _FEIGE_GET_THREAD_JS."
            )
        return _json_result({"messages": messages, "total_found": total})
    except Exception as e:
        logger.error(f"[Feige] feige_get_chat_thread error: {e}")
        return ActionResult(error=f"feige_get_chat_thread failed: {e}")


_FEIGE_SEND_MESSAGE_JS = r"""
(async function(text, expectedCustomer, expectedSourceMsgId, expectedSourceText) {
  function sleep(ms) { return new Promise(function(resolve) { setTimeout(resolve, ms); }); }
  function visible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    var rect = el.getBoundingClientRect();
    var style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    return rect.width > 0 && rect.height > 0 &&
      (!style || (style.display !== 'none' && style.visibility !== 'hidden'));
  }
  function readValue(el) {
    if (!el) return '';
    if ('value' in el) return String(el.value || '');
    return String(el.textContent || '');
  }
  function setValue(el, val) {
    if (!el) return;
    el.focus();
    if (el.tagName === 'TEXTAREA') {
      var taSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
      if (taSetter && taSetter.set) taSetter.set.call(el, val);
      else el.value = val;
    } else if (el.tagName === 'INPUT') {
      var inSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
      if (inSetter && inSetter.set) inSetter.set.call(el, val);
      else el.value = val;
    } else {
      el.textContent = val;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function latestAgentBubbleText() {
    var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
    for (var i = wrappers.length - 1; i >= 0; i--) {
      var wrap = wrappers[i];
      var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1');
      if (!bubble || !bubble.classList.contains('messageIsMe')) continue;
      return (bubble.querySelector('pre') || bubble).textContent.trim();
    }
    return '';
  }
  function latestVisibleBubble() {
    var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
    for (var i = wrappers.length - 1; i >= 0; i--) {
      var wrap = wrappers[i];
      var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1');
      if (!bubble) continue;
      var text = (bubble.querySelector('pre') || bubble).textContent.trim();
      if (bubble.classList.contains('messageIsMe')) {
        if (!text) continue;
        return { found: true, sender: 'agent', text: text };
      }
      if (bubble.classList.contains('messageNotMe')) {
        if (!text) {
          var customerRow = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
          var customerImgs = Array.from(customerRow ? customerRow.querySelectorAll('img') : []);
          for (var ci = 0; ci < customerImgs.length; ci++) {
            var cim = customerImgs[ci];
            var ccls = (cim.className || '').toString();
            var calt = (cim.getAttribute('alt') || '').trim();
            if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(ccls)) continue;
            if (calt === 'å¤´åƒ') continue;
            var csrc = cim.src || cim.getAttribute('src') || '';
            if (csrc && csrc.indexOf('data:image/svg') !== 0) {
              return { found: true, sender: 'customer', text: '' };
            }
          }
          continue;
        }
        return { found: true, sender: 'customer', text: text };
      }
      var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
      var direction = row ? String(row.style.flexDirection || '') : '';
      if (!text && direction.indexOf('reverse') === -1) {
        var imgs = Array.from(row ? row.querySelectorAll('img') : []);
        for (var k = 0; k < imgs.length; k++) {
          var im = imgs[k];
          var cls = (im.className || '').toString();
          var alt = (im.getAttribute('alt') || '').trim();
          if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
          if (alt === 'å¤´åƒ') continue;
          var src = im.src || im.getAttribute('src') || '';
          if (src && src.indexOf('data:image/svg') !== 0) {
            return { found: true, sender: 'customer', text: '' };
          }
        }
      }
      if (!text) continue;
      return {
        found: true,
        sender: direction.indexOf('reverse') !== -1 ? 'agent' : 'customer',
        text: text
      };
    }
    return { found: false, sender: '', text: '' };
  }
  function latestCustomerBubble() {
    var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
    for (var i = wrappers.length - 1; i >= 0; i--) {
      var wrap = wrappers[i];
      var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
      if (!row) continue;
      if ((row.style.flexDirection || '').indexOf('reverse') !== -1) continue;
      var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1');
      var text = '';
      if (bubble) {
        if (bubble.classList.contains('messageIsMe')) continue;
        text = (bubble.querySelector('pre') || bubble).textContent.trim();
      }
      var hasContentImage = false;
      var imgs = Array.from(row.querySelectorAll('img'));
      for (var k = 0; k < imgs.length; k++) {
        var im = imgs[k];
        var cls = (im.className || '').toString();
        var alt = (im.getAttribute('alt') || '').trim();
        if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
        if (alt === '头像') continue;
        var src = im.src || im.getAttribute('src') || '';
        if (src && src.indexOf('data:image/svg') !== 0) {
          hasContentImage = true;
          break;
        }
      }
      if (!text && !hasContentImage) continue;
      var idEl = wrap.querySelector('[data-id]');
      return {
        found: true,
        text: text,
        msg_id: idEl ? (idEl.getAttribute('data-id') || '') : ''
      };
    }
    return { found: false, text: '', msg_id: '' };
  }
  function sameText(a, b) {
    function norm(s) { return String(s || '').replace(/\s+/g, ' ').trim(); }
    return norm(a) === norm(b);
  }
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.recent') || btm.endsWith('.systemConv')) return false;
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  function readRowName(row) {
    var wrap = row && row.querySelector ? row.querySelector('.MP1bk3ccfHC9V2SnPCGD') : null;
    if (wrap) {
      var t = (wrap.getAttribute('title') || wrap.textContent || '').trim();
      if (t) return t;
    }
    var span = row && row.querySelector ? row.querySelector('.Jv6FtqUv5VoYARd2pp4y') : null;
    return span ? (span.textContent || '').trim() : '';
  }
  function readHeaderName() {
    var topbar = document.querySelector('#topbar-left-info');
    if (!topbar) return '';
    var cands = topbar.querySelectorAll('div, span');
    for (var hi = 0; hi < cands.length; hi++) {
      var ht = (cands[hi].textContent || '').trim();
      if (!ht || ht === '添加备注' || ht.length > 60) continue;
      if (cands[hi].children.length === 0) return ht;
    }
    var btm = topbar.querySelector('div[data-btm-id]');
    return btm ? (btm.textContent || '').trim() : '';
  }
  function currentActiveRowName(items) {
    for (var i = 0; i < items.length; i++) {
      var cn = String(items[i].className || '').toLowerCase();
      if (cn.indexOf('active') >= 0 || items[i].classList.contains('wmvLQcpt39Hk9PSISrlN')) {
        return readRowName(items[i]);
      }
    }
    return '';
  }
  function activeMatches(expected, items) {
    if (!expected) return { ok: true, header: '', sidebar: '' };
    var header = readHeaderName();
    var sidebar = currentActiveRowName(items || []);
    var headerConflict = header && header !== expected;
    var sidebarConflict = sidebar && sidebar !== expected;
    return {
      ok: !headerConflict && !sidebarConflict && (header === expected || sidebar === expected),
      header: header,
      sidebar: sidebar
    };
  }
  var items = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
    .filter(rowIsCurrent);
  if (expectedCustomer) {
    var target = null;
    for (var oi = 0; oi < items.length; oi++) {
      if (readRowName(items[oi]) === expectedCustomer) { target = items[oi]; break; }
    }
    if (!target) {
      return JSON.stringify({
        sent: false,
        error: 'Session not found in current conversations',
        expected_customer: expectedCustomer,
        current_visible: items.length,
        seen_names: items.slice(0, 20).map(readRowName)
      });
    }
    var beforeMatch = activeMatches(expectedCustomer, items);
    if (!beforeMatch.ok) {
      target.click();
      await sleep(260);
      items = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
        .filter(rowIsCurrent);
    }
    var afterMatch = activeMatches(expectedCustomer, items);
    if (!afterMatch.ok) {
      return JSON.stringify({
        sent: false,
        error: 'Active customer mismatch after open',
        expected_customer: expectedCustomer,
        header_name: afterMatch.header,
        sidebar_name: afterMatch.sidebar
      });
    }
  }

  var sourceMsgId = String(expectedSourceMsgId || '').trim();
  var sourceText = String(expectedSourceText || '').trim();
  if (sourceMsgId || sourceText) {
    var latest = { found: false, text: '', msg_id: '' };
    var sourceOk = false;
    for (var guardPoll = 0; guardPoll < 10; guardPoll++) {
      latest = latestCustomerBubble();
      if (latest.found) {
        if (sourceMsgId && latest.msg_id && latest.msg_id === sourceMsgId) sourceOk = true;
        if (!sourceOk && sourceText && sameText(latest.text, sourceText)) sourceOk = true;
        if (sourceOk) break;
      }
      if (guardPoll < 9) await sleep(100);
    }
    if (!latest.found) {
      return JSON.stringify({
        sent: false,
        error: 'source_turn_not_found',
        expected_source_msg_id: sourceMsgId,
        expected_source_text: sourceText
      });
    }
    if (!sourceOk) {
      return JSON.stringify({
        sent: false,
        error: 'stale_reply_source_msg_id',
        expected_source_msg_id: sourceMsgId,
        active_source_msg_id: latest.msg_id || '',
        expected_source_text: sourceText,
        active_source_text: (latest.text || '').slice(0, 160)
      });
    }
  }

  var inputSelectors = [
    '[data-qa-id="qa-send-message-textarea"]',
    'textarea[placeholder*="发送"]',
    'textarea',
    '[contenteditable="true"]'
  ];
  var input = null;
  for (var s = 0; s < inputSelectors.length; s++) {
    var candidates = Array.from(document.querySelectorAll(inputSelectors[s]));
    for (var c = 0; c < candidates.length; c++) {
      if (visible(candidates[c])) { input = candidates[c]; break; }
    }
    if (input) break;
  }
  if (!input) return JSON.stringify({ sent: false, error: 'Input box not found' });

  var beforeAgentText = latestAgentBubbleText();
  var latestBeforeInput = latestVisibleBubble();
  if (
    latestBeforeInput.found &&
    latestBeforeInput.sender === 'agent' &&
    sameText(latestBeforeInput.text, text)
  ) {
    return JSON.stringify({
      sent: true,
      method: 'dedup_latest_agent_bubble',
      selector: '',
      verified: 'already_sent_bubble'
    });
  }
  setValue(input, text);
  await sleep(80);
  if (!sameText(readValue(input), text)) {
    return JSON.stringify({
      sent: false,
      error: 'Input did not accept message text',
      input_value_preview: readValue(input).slice(0, 120)
    });
  }

  var sendSelectors = [
    '[data-qa-id="qa-send-message-button"]',
    '[data-qa-id="qa-send-btn"]',
    'button[class*="send"]'
  ];
  var sendBtn = null;
  var selector = '';
  for (var sb = 0; sb < sendSelectors.length; sb++) {
    var btn = document.querySelector(sendSelectors[sb]);
    if (btn && visible(btn)) {
      sendBtn = btn;
      selector = sendSelectors[sb];
      break;
    }
  }

  var method = '';
  if (sendBtn) {
    sendBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    sendBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    sendBtn.click();
    method = 'button_click';
  } else {
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    method = 'enter_key';
  }

  for (var poll = 0; poll < 8; poll++) {
    await sleep(100);
    var currentValue = readValue(input);
    var afterAgentText = latestAgentBubbleText();
    if (!currentValue.trim()) {
      return JSON.stringify({ sent: true, method: method, selector: selector, verified: 'input_cleared' });
    }
    if (sameText(afterAgentText, text) && !sameText(beforeAgentText, text)) {
      return JSON.stringify({ sent: true, method: method, selector: selector, verified: 'outgoing_bubble' });
    }
  }

  return JSON.stringify({
    sent: false,
    error: 'Send did not clear input or create outgoing bubble',
    method: method,
    selector: selector,
    input_value_preview: readValue(input).slice(0, 120)
  });
})(MESSAGE_TEXT, EXPECTED_CUSTOMER, EXPECTED_SOURCE_MSG_ID, EXPECTED_SOURCE_TEXT);
"""


@custom_controller.action(
    "Type and send a message in the currently open Feige (飞鸽) chat thread.",
    param_model=FeigeSendMessageAction,
)
async def feige_send_message(params: FeigeSendMessageAction, browser_session: BrowserSession) -> ActionResult:
    # Process-global typing-lock serialization (added 2026-04-30 21:00).
    # Concurrent feige_send_message calls from different callers (Q&A
    # workers, direct-delivery, HOT-PATH-B) all run JS through Chrome's
    # single-threaded renderer.  When two sends overlap the renderer
    # saturates and unrelated CDP Runtime.evaluate calls (e.g. PreDispatch
    # sidebar-click scrapes) timeout at 6s.  The process-wide typing_lock
    # module already exists for the cross-customer race guard; acquire it
    # here so all callers serialize regardless of whether they remembered
    # to lock at their level.  Re-entrant for same key, so callers that
    # already hold it (HOT-PATH-B / direct-delivery) pass straight through.
    # The finally: block below calls release(_send_lock_key) when this
    # function acquired the lock itself.
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            typing_lock as _send_typing_lock,
        )
    except Exception:
        _send_typing_lock = None
    _send_lock_key = str(getattr(params, "customer_name", "") or "").strip()
    _send_acquired = False
    _send_has_lock = False
    _feige_ledger = None
    if _send_typing_lock is not None and _send_lock_key:
        import asyncio as _send_asyncio
        try:
            _already_holding = _send_typing_lock.holder() == _send_lock_key
        except Exception:
            _already_holding = False
        # Poll up to 10s for the lock; the Feige typing-lock TTL self-heals
        # stale holders after the guarded send timeout window.
        for _send_attempt in range(100):
            if _send_typing_lock.try_acquire(_send_lock_key):
                _send_has_lock = True
                _send_acquired = not _already_holding
                break
            await _send_asyncio.sleep(0.1)
        if not _send_has_lock:
            logger.warning(
                f"[Feige] feige_send_message: typing-lock contention persisted "
                f"10s for {_send_lock_key!r} (current holder={_send_typing_lock.holder()!r}); "
                f"proceeding without lock"
            )
    try:
        expected_customer = str(params.customer_name or "").strip()
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.trace_ledger import (
                log_event as _feige_ledger,
            )
        except Exception:
            _feige_ledger = None
        if _feige_ledger is not None:
            _feige_ledger(
                "feige_send_tool_start",
                customer=expected_customer,
                source_msg_id=str(getattr(params, "source_customer_msg_id", "") or "").strip(),
                latest_preview=str(getattr(params, "source_latest_message", "") or "").strip(),
                response_preview=str(getattr(params, "text", "") or ""),
                response_len=len(str(getattr(params, "text", "") or "")),
            )
        # JSON-encode the text so any quotes/newlines are safe inside the JS string
        text_json = json.dumps(params.text, ensure_ascii=False)
        expected_json = json.dumps(expected_customer, ensure_ascii=False)
        source_msg_id = str(getattr(params, "source_customer_msg_id", "") or "").strip()
        source_text = str(getattr(params, "source_latest_message", "") or "").strip()
        source_msg_id_json = json.dumps(source_msg_id, ensure_ascii=False)
        source_text_json = json.dumps(source_text, ensure_ascii=False)
        js = (
            _FEIGE_SEND_MESSAGE_JS
            .replace("MESSAGE_TEXT", text_json)
            .replace("EXPECTED_CUSTOMER", expected_json)
            .replace("EXPECTED_SOURCE_MSG_ID", source_msg_id_json)
            .replace("EXPECTED_SOURCE_TEXT", source_text_json)
        )
        target_id = await _resolve_feige_tab_target_id_bounded(browser_session)
        if target_id:
            data = await _evaluate_js(
                browser_session,
                js,
                target_id=target_id,
                focus=False,
            )
        else:
            logger.warning(
                "[Feige] feige_send_message: no Feige target id resolved; "
                "falling back to focused tab evaluation"
            )
            data = await _evaluate_js(browser_session, js)
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict) and data.get("sent"):
            method = data.get("method", "unknown")
            verified = data.get("verified", "unknown")
            logger.info(
                f"[Feige] Sent message via {method}/{verified}: {params.text[:60]}"
            )
            if _feige_ledger is not None:
                _feige_ledger(
                    "feige_send_tool_success",
                    customer=expected_customer,
                    source_msg_id=source_msg_id,
                    latest_preview=source_text,
                    response_preview=str(getattr(params, "text", "") or ""),
                    method=str(method),
                    verified=str(verified),
                )
            return ActionResult(
                extracted_content=f"Message sent (method: {method}, verified: {verified})."
            )
        err = data.get("error") if isinstance(data, dict) else str(data)
        if _feige_ledger is not None:
            _feige_ledger(
                "feige_send_tool_failed",
                customer=expected_customer,
                source_msg_id=source_msg_id,
                latest_preview=source_text,
                response_preview=str(getattr(params, "text", "") or ""),
                error=str(err),
                result_preview=str(data),
            )
        return ActionResult(error=f"feige_send_message: {err}")
    except Exception as e:
        logger.error(f"[Feige] feige_send_message error: {e}")
        try:
            if _feige_ledger is not None:
                _feige_ledger(
                    "feige_send_tool_exception",
                    customer=str(getattr(params, "customer_name", "") or ""),
                    source_msg_id=str(getattr(params, "source_customer_msg_id", "") or ""),
                    latest_preview=str(getattr(params, "source_latest_message", "") or ""),
                    response_preview=str(getattr(params, "text", "") or ""),
                    error=str(e),
                )
        except Exception:
            pass
        return ActionResult(error=f"feige_send_message failed: {e}")
    finally:
        if _send_acquired and _send_typing_lock is not None:
            try:
                _send_typing_lock.release(_send_lock_key)
            except Exception:
                pass


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

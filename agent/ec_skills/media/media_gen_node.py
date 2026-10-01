"""``media-gen`` skill node: image / video / speech / music generation via the llm-proxy.

Config (flowgram ``data.inputsValues``, each ``{"type": ..., "content": ...}``):
``mediaType`` (image|video|speech|music), ``modelName``, ``promptSelection`` /
``negativePromptSelection`` (a saved prompt id, or in-line), ``prompt``
(template; for speech the text to speak, for music the style / description),
``negativePrompt``, ``referenceImages`` (template,
newline/comma separated paths or URLs), ``firstFrame`` / ``lastFrame``
(template, video only), ``size``,
``aspectRatio``, ``n``, ``durationSeconds``, ``resolution``, ``generateAudio``,
``voice``, ``audioFormat``, ``speed``, ``lyrics`` (template, music),
``title`` / ``instrumental`` (music), ``timeoutSeconds``, ``outputSubdir``.

Result: ``state["result"]["media"]`` = list of ``{path, url, mime_type, width,
height, duration_seconds}`` (known keys only), plus ``state["result"]["media_job"]``
= ``{id, status}`` for video. On failure ``state["result"]["media_error"]`` =
``{code, message}`` and a WARNING -- the node never raises (a raise would make
node_builder retry paid work).

A prompt may open with a parameter block that overrides the node's fields for
that run; it is stripped before the text goes to the model::

    ---
    时长: 10
    分辨率: 1080p
    比例: 9:16
    ---
    一只橘猫在黄昏的海边奔跑……

Keys are field names or their Chinese labels (see ``_PARAM_KEYS``).
"""

from __future__ import annotations

import base64
import contextvars
import mimetypes
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from agent.ec_skills.media.proxy_media_client import (
    CONTENT_POLICY_HINT,
    MediaProxyError,
    ProxyMediaClient,
    is_url,
    unique_path,
)
from agent.ec_skills.media.media_inputs import split_media_list
from langgraph.errors import GraphInterrupt
from agent.cloud_worker.cloud_logger import send_skill_editor_log
from utils.logger_helper import logger_helper as logger

DEFAULT_TIMEOUTS = {"image": 120.0, "speech": 60.0, "video": 900.0, "music": 600.0}
_AUDIO_EXT = {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
              "audio/wave": "wav", "audio/pcm": "pcm", "audio/l16": "pcm", "audio/opus": "opus",
              "audio/ogg": "opus"}


# Parameter-block keys (lower-cased) -> node field.
_PARAM_KEYS = {
    **{k: "durationSeconds" for k in ("durationseconds", "duration", "时长", "视频时长", "秒数")},
    **{k: "resolution" for k in ("resolution", "分辨率")},
    **{k: "aspectRatio" for k in ("aspectratio", "aspect_ratio", "ratio", "比例", "宽高比", "画幅")},
    **{k: "size" for k in ("size", "尺寸", "图片尺寸")},
    **{k: "n" for k in ("n", "count", "数量", "张数")},
    **{k: "negativePrompt" for k in ("negativeprompt", "negative_prompt", "negative", "反向提示词", "负面提示词")},
    **{k: "voice" for k in ("voice", "音色")},
    **{k: "speed" for k in ("speed", "语速")},
    **{k: "audioFormat" for k in ("audioformat", "audio_format", "format", "格式", "音频格式")},
    **{k: "generateAudio" for k in ("generateaudio", "generate_audio", "生成音频", "配音")},
    **{k: "title" for k in ("title", "标题", "歌名")},
    **{k: "instrumental" for k in ("instrumental", "纯音乐", "无人声")},
    **{k: "modelName" for k in ("modelname", "model", "模型")},
    **{k: "timeoutSeconds" for k in ("timeoutseconds", "timeout", "超时")},
}
_NUMERIC_PARAMS = {"durationSeconds", "n", "speed", "timeoutSeconds"}
_INLINE = ("", "inline", "in-line")

# This run's parameter-block overrides. A contextvar, not closure state: one
# compiled node can run in several tasks at once.
_overrides: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "media_gen_overrides", default={})


def split_param_block(text: str) -> Tuple[Dict[str, Any], str]:
    """``(overrides, body)`` from a prompt opening with a ``---`` block of
    ``key: value`` lines. Anything else -- no block, an unclosed one, a line
    that is not ``key: value`` -- leaves the text untouched. Unknown keys are
    ignored (logged)."""
    lines = (text or "").lstrip("﻿").splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return {}, text
    params: Dict[str, Any] = {}
    for j in range(i + 1, len(lines)):
        line = lines[j].strip()
        if line == "---":
            return params, "\n".join(lines[j + 1:]).strip()
        if not line:
            continue
        m = re.match(r"^([^:：]+)[:：]\s*(.*)$", line)
        if not m:
            return {}, text
        key, value = m.group(1).strip(), m.group(2).strip()
        field = _PARAM_KEYS.get(key.lower())
        if field is None:
            logger.warning(f"[MediaGen] unknown parameter '{key}' in the prompt's parameter block (ignored)")
            continue
        if field in _NUMERIC_PARAMS:
            num = re.match(r"^\d+(\.\d+)?", value)
            value = num.group(0) if num else value
        elif field == "size":
            value = re.sub(r"\s*[x×X]\s*", "*", value)
        params[field] = value
    return {}, text


def _make_client() -> ProxyMediaClient:
    return ProxyMediaClient.from_ecanai()


def generated_medias_root() -> str:
    """The user's ``generated_medias`` directory under the app data dir."""
    from utils.user_path_helper import ensure_user_data_dir
    return ensure_user_data_dir(subdir="generated_medias")


def _output_dir(subdir: str) -> str:
    root = generated_medias_root()
    sub = (subdir or "").strip().strip("/\\")
    if sub and not os.path.isabs(sub) and ".." not in re.split(r"[\\/]", sub):
        root = os.path.join(root, sub)
    os.makedirs(root, exist_ok=True)
    return root


def render_template(text: Any, state: dict) -> str:
    """Substitute ``{{var}}`` from state the same way the LLM node does."""
    text = "" if text is None else str(text)
    variables = re.findall(r"\{\{(\w+)\}\}", text)
    if not variables:
        return text
    from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables
    from agent.ec_skills.build_node import _safe_prompt_value
    mainwin = None
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
    except Exception:
        pass
    values = resolve_prompt_variables(variable_names=variables, state=state, mainwin=mainwin)
    for var, val in values.items():
        text = text.replace(f"{{{{{var}}}}}", _safe_prompt_value(val))
    return text


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_bool(v: Any) -> Optional[bool]:
    if v in (None, ""):
        return None
    return str(v).strip().lower() in ("true", "1", "yes", "on", "是", "对", "开")


def _media_entry(**fields: Any) -> Dict[str, Any]:
    return {k: v for k, v in fields.items() if v not in (None, "")}


def _acct_site_id() -> str:
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        return str(mainwin.getAcctSiteID() or "") if mainwin is not None else ""
    except Exception:
        return ""


def _runtime_value(runtime: Any, key: str) -> str:
    ctx = getattr(runtime, "context", None)
    if isinstance(ctx, dict):
        return str(ctx.get(key) or "")
    return str(getattr(ctx, key, "") or "")


def _async_key(runtime: Any, node_name: str) -> str:
    """(task, thread, node) -- stable across LangGraph's re-run of a resumed node."""
    thread_id = ""
    try:
        from langgraph.config import get_config
        thread_id = str(((get_config() or {}).get("configurable") or {}).get("thread_id") or "")
    except Exception:
        pass
    return ":".join([_runtime_value(runtime, "task_id"), thread_id or _runtime_value(runtime, "run_id"), str(node_name)])


def build_media_gen_node(config_metadata: dict, node_name, skill_name, owner, bp_manager):
    from agent.ec_skill import node_builder
    from agent.ec_skills.media import media_job_watcher
    media_job_watcher.ensure_started()   # settle jobs a previous run left behind

    inputs = (config_metadata or {}).get("inputsValues", {}) or {}
    node_title = str((config_metadata or {}).get("title") or "").strip()

    def _cfg(key: str, default: Any = None) -> Any:
        ov = _overrides.get().get(key)
        if ov not in (None, ""):
            return ov
        v = inputs.get(key)
        if isinstance(v, dict):
            v = v.get("content")
        return default if v in (None, "") else v

    media_type = str(_cfg("mediaType", "image")).strip().lower()

    def _model() -> str:
        return str(_cfg("modelName", "") or "").strip()

    def _timeout() -> float:
        return _to_float(_cfg("timeoutSeconds")) or DEFAULT_TIMEOUTS.get(media_type, 120.0)

    def _prompt_text(selection_key: str, inline_key: str) -> str:
        """The in-line field, or the saved prompt the pulldown selects (resolved
        like the LLM node's, so a subscribed skill finds its author's prompt)."""
        selection = str(_cfg(selection_key, "") or "").strip()
        if selection.lower() in _INLINE:
            return str(_cfg(inline_key, "") or "")
        from agent.ec_skills.build_node import _resolve_prompt_templates
        system_text, user_text, _ = _resolve_prompt_templates(selection, "", "", skill_owner=owner or "")
        text = "\n\n".join(t.strip() for t in (system_text, user_text) if t and t.strip())
        if not text:
            logger.warning(f"[MediaGen] node={node_name} prompt '{selection}' not found or empty; "
                           f"using the in-line {inline_key}")
            return str(_cfg(inline_key, "") or "")
        return text

    def _resolve_refs(client: ProxyMediaClient, raw: Any, state: dict) -> List[str]:
        urls = []
        for ref in split_media_list(render_template(raw, state)):
            urls.append(ref if is_url(ref) else client.upload_file(ref))
        return urls

    def _gen_image(client: ProxyMediaClient, state: dict, prompt: str, out_dir: str) -> List[dict]:
        refs = _resolve_refs(client, _cfg("referenceImages"), state) if _cfg("referenceImages") else []
        data = client.generate_images(
            _model(), prompt, timeout_s=_timeout(),
            n=_to_int(_cfg("n")), size=_cfg("size"), aspect_ratio=_cfg("aspectRatio"),
            negative_prompt=_cfg("negativePrompt"), reference_images=refs or None,
        )
        media = []
        for i, item in enumerate(data):
            mime = item.get("mime_type") or "image/png"
            if item.get("url"):
                path = client.download(item["url"], out_dir)
            elif item.get("b64_json"):
                ext = (mime.split("/")[-1] or "png").replace("jpeg", "jpg")
                path = unique_path(out_dir, f"image_{int(time.time())}_{i}.{ext}")
                with open(path, "wb") as fh:
                    fh.write(base64.b64decode(item["b64_json"]))
            else:
                continue
            media.append(_media_entry(path=path, url=item.get("url"), mime_type=mime,
                                      width=item.get("width"), height=item.get("height")))
        if not media:
            raise MediaProxyError(502, "empty_output", "image generation returned no images")
        return media

    def _gen_speech(client: ProxyMediaClient, prompt: str, out_dir: str) -> List[dict]:
        fmt = str(_cfg("audioFormat", "") or "").strip().lower()   # empty: the model's default format
        audio, mime = client.speech(_model(), prompt, voice=_cfg("voice"), fmt=fmt or None,
                                    speed=_to_float(_cfg("speed")), timeout_s=_timeout())
        mime = (mime or "").lower()
        ext = (_AUDIO_EXT.get(mime) or (mimetypes.guess_extension(mime) or "").lstrip(".")
               or fmt or "bin")
        path = unique_path(out_dir, f"speech_{int(time.time())}.{ext}")
        with open(path, "wb") as fh:
            fh.write(audio)
        return [_media_entry(path=path, mime_type=mime or mimetypes.guess_type(path)[0])]

    # ── video / music: jobs ──────────────────────────────────────────────
    def _submit_job(client: ProxyMediaClient, state: dict, prompt: str, notify: bool = False) -> dict:
        # Async jobs ask the proxy to push the outcome to this machine's
        # onLongLLMTaskComplete subscription (an unknown field is ignored).
        extra = {"notify_acct_site_id": _acct_site_id()} if notify else {}
        if media_type == "music":
            fmt = str(_cfg("audioFormat", "") or "").strip().lower()
            job = client.submit_music(
                _model(), prompt,
                lyrics=render_template(_cfg("lyrics", ""), state).strip() or None,
                title=_cfg("title"), instrumental=_to_bool(_cfg("instrumental")),
                duration_seconds=_to_int(_cfg("durationSeconds")), format=fmt or None, **extra,
            )
        else:
            refs = _resolve_refs(client, _cfg("referenceImages"), state) if _cfg("referenceImages") else []
            first = _resolve_refs(client, _cfg("firstFrame"), state) if _cfg("firstFrame") else []
            last = _resolve_refs(client, _cfg("lastFrame"), state) if _cfg("lastFrame") else []
            job = client.submit_video(
                _model(), prompt,
                negative_prompt=_cfg("negativePrompt"), image_url=first[0] if first else None,
                last_frame_url=last[0] if last else None,
                reference_images=refs or None, duration_seconds=_to_int(_cfg("durationSeconds")),
                resolution=_cfg("resolution"), aspect_ratio=_cfg("aspectRatio"),
                generate_audio=_to_bool(_cfg("generateAudio")), **extra,
            )
        state["result"]["media_job"] = {"id": job.get("id"), "status": job.get("status")}
        msg = f"[MediaGen] node={node_name} {media_type} job {job.get('id')} {job.get('status')}"
        logger.info(msg)
        send_skill_editor_log("log", msg)
        return job

    def _collect_job(client: ProxyMediaClient, state: dict, job: dict, out_dir: str) -> List[dict]:
        """A finished job -> downloaded files. A job may return several takes
        (``outputs``, music) or one (``output``)."""
        status = job.get("status")
        state["result"]["media_job"] = {"id": job.get("id"), "status": status}
        if status != "succeeded":
            err = job.get("error") or {}
            code = str(err.get("code") or status)
            message = str(err.get("message") or f"{media_type} job {status}")
            if code == "content_policy":
                message = f"{CONTENT_POLICY_HINT} ({message})"
            raise MediaProxyError(408 if code == "client_timeout" else 200, code, message)
        outputs = job.get("outputs") or ([job["output"]] if job.get("output") else [])
        default_mime = "video/mp4" if media_type == "video" else None
        media = []
        for out in outputs:
            if not (out or {}).get("url"):
                continue
            path = client.download(out["url"], out_dir)
            media.append(_media_entry(path=path, url=out.get("url"),
                                      mime_type=out.get("mime_type") or default_mime or mimetypes.guess_type(path)[0],
                                      width=out.get("width"), height=out.get("height"),
                                      duration_seconds=out.get("duration_seconds"), title=out.get("title")))
        if not media:
            raise MediaProxyError(502, "empty_output", f"{media_type} job succeeded without an output url")
        return media

    def _gen_job_sync(client: ProxyMediaClient, state: dict, prompt: str, out_dir: str) -> List[dict]:
        """Sync mode: submit and poll inside this node until done or timeout."""
        job = _submit_job(client, state, prompt)
        job_id = job.get("id")
        wait = client.wait_music if media_type == "music" else client.wait_video
        cancel = client.cancel_music if media_type == "music" else client.cancel_video

        def _progress(j: dict) -> None:
            state["result"]["media_job"] = {"id": job_id, "status": j.get("status")}
            logger.info(f"[MediaGen] node={node_name} {media_type} job {job_id} "
                        f"{j.get('status')} progress={j.get('progress')}")

        try:
            job = wait(job_id, timeout_s=_timeout(), on_progress=_progress)
        except MediaProxyError as e:
            if e.code == "client_timeout":
                # Give up: cancel so the proxy releases the pre-authorization.
                try:
                    cancel(job_id)
                except Exception as ce:
                    logger.warning(f"[MediaGen] cancel of timed-out {media_type} {job_id} failed: {ce}")
                state["result"]["media_job"] = {"id": job_id, "status": "timeout"}
            raise
        return _collect_job(client, state, job, out_dir)

    def _gen_job_async(client: ProxyMediaClient, state: dict, prompt: str, out_dir: str, runtime) -> List[dict]:
        """Async mode: submit once, park the task (no thread held) until the job
        watcher records the outcome and wakes it, then collect.

        LangGraph re-runs a resumed node from the top, so the job is keyed by
        (task, thread, node) in the watcher: a re-run finds its job instead of
        submitting again. Each resume replays earlier ``interrupt()`` calls, so
        the loop re-checks the watcher after every one; an unrelated event that
        woke the task just parks it again."""
        from langgraph.types import interrupt
        from agent.ec_skills.media import media_job_watcher as watcher
        key = _async_key(runtime, node_name)
        entry = watcher.lookup(key)
        if entry is None:
            task_id = _runtime_value(runtime, "task_id")
            if not task_id:
                # Not inside a task run (e.g. a direct test call): nothing can wake us.
                return _gen_job_sync(client, state, prompt, out_dir)
            job = _submit_job(client, state, prompt, notify=True)
            watcher.record(key, job_id=job.get("id"), kind=media_type, task_id=task_id, timeout_s=_timeout())
            entry = watcher.lookup(key)
        while not (entry or {}).get("done"):
            state["result"]["media_job"] = {"id": entry.get("job_id"), "status": entry.get("status")}
            msg = f"[MediaGen] node={node_name} parked on {media_type} job {entry.get('job_id')} (async)"
            logger.info(msg)
            send_skill_editor_log("log", msg)
            interrupt({"paused_at": node_name, "i_tag": entry.get("job_id"),
                       "waiting_for": "media_gen", "job_id": entry.get("job_id")})
            entry = watcher.lookup(key)
        watcher.release(key)
        return _collect_job(client, state, entry.get("job") or {}, out_dir)

    def media_gen_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        if not isinstance(state.get("result"), dict):
            state["result"] = {}
        for k in ("media", "media_job", "media_error"):
            state["result"].pop(k, None)

        client = None
        overrides_token = None
        try:
            # The prompt's own parameter block overrides the node's fields for this run.
            overrides, prompt = split_param_block(render_template(_prompt_text("promptSelection", "prompt"), state))
            if "negativePrompt" not in overrides:
                negative = render_template(
                    _prompt_text("negativePromptSelection", "negativePrompt"), state).strip()
                if negative:
                    overrides["negativePrompt"] = negative
            overrides_token = _overrides.set(overrides)
            msg = f"🎬 Executing media-gen node: {node_name} ({media_type}, model={_model()})"
            logger.info(msg)
            send_skill_editor_log("log", msg)
            applied = {k: v for k, v in overrides.items() if k != "negativePrompt"}
            if applied:
                msg = f"[MediaGen] node={node_name} prompt overrides: {applied}"
                logger.info(msg)
                send_skill_editor_log("log", msg)

            if media_type not in DEFAULT_TIMEOUTS:
                raise MediaProxyError(400, "invalid_request", f"unsupported mediaType '{media_type}'")
            if not _model():
                raise MediaProxyError(400, "invalid_request", "modelName is required")
            prompt = prompt.strip()
            if not prompt:
                raise MediaProxyError(400, "invalid_request", "prompt is empty")
            client = _make_client()
            out_dir = _output_dir(str(_cfg("outputSubdir", "") or ""))
            if media_type == "image":
                media = _gen_image(client, state, prompt, out_dir)
            elif media_type in ("video", "music"):
                if str(_cfg("runMode", "sync")).strip().lower() == "async":
                    media = _gen_job_async(client, state, prompt, out_dir, runtime)
                else:
                    media = _gen_job_sync(client, state, prompt, out_dir)
            else:
                media = _gen_speech(client, prompt, out_dir)
            state["result"]["media"] = media
            msg = f"✅ [MediaGen] node={node_name} saved {[m.get('path') for m in media]}"
            logger.info(msg)
            send_skill_editor_log("log", msg)
        except GraphInterrupt:
            raise   # async mode parked the task; the watcher resumes it
        except Exception as e:
            if isinstance(e, MediaProxyError):
                code, message = e.code, e.message
            else:
                code, message = "client_error", f"{type(e).__name__}: {e}"
            state["result"]["media_error"] = {"code": code, "message": message}
            msg = f"[MediaGen] node={node_name} {media_type} generation failed: {code}: {message}"
            logger.warning(msg)
            send_skill_editor_log("warning", msg)
        finally:
            if client is not None:
                client.close()
            if overrides_token is not None:
                _overrides.reset(overrides_token)
        publish_media_output(state, node_name, alias=node_title)
        return state

    return node_builder(media_gen_callable, node_name, skill_name, owner, bp_manager)


def publish_media_output(state: dict, node_name: str, alias: str = "") -> None:
    """Expose this node's output where later nodes look for upstream values:
    ``state["tool_result"][node_name]``. ``state["result"]`` is replaced by the
    next node that writes one, and ``{{var}}`` resolves plain names from the
    latest node output, so a following LLM node's media input can say
    ``{{media_paths}}`` (or ``{{tool_result.<node>.media_paths}}`` in text)."""
    result = state.get("result") or {}
    media = result.get("media") or []
    out: Dict[str, Any] = {
        "media": media,
        "media_paths": "\n".join(m["path"] for m in media if m.get("path")),
        "media_urls": "\n".join(m["url"] for m in media if m.get("url")),
    }
    for key in ("media_job", "media_error"):
        if result.get(key):
            out[key] = result[key]
    tool_result = state.get("tool_result")
    if not isinstance(tool_result, dict):
        tool_result = state["tool_result"] = {}
    tool_result[node_name] = out
    # The node id ("media-gen_Ab3xZ") has a hyphen, which {{tool_result.x.y}}
    # cannot match; the title the user sees ("MediaGen_1") can.
    if alias and alias != node_name and re.fullmatch(r"\w+", alias):
        tool_result[alias] = out

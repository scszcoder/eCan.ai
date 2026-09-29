"""``media-gen`` skill node: image / video / speech generation via the llm-proxy.

Config (flowgram ``data.inputsValues``, each ``{"type": ..., "content": ...}``):
``mediaType`` (image|video|speech), ``modelName``, ``prompt`` (template; for
speech the text to speak), ``negativePrompt``, ``referenceImages`` (template,
newline/comma separated paths or URLs), ``firstFrame`` / ``lastFrame``
(template, video only), ``size``,
``aspectRatio``, ``n``, ``durationSeconds``, ``resolution``, ``generateAudio``,
``voice``, ``audioFormat``, ``speed``, ``timeoutSeconds``, ``outputSubdir``.

Result: ``state["result"]["media"]`` = list of ``{path, url, mime_type, width,
height, duration_seconds}`` (known keys only), plus ``state["result"]["media_job"]``
= ``{id, status}`` for video. On failure ``state["result"]["media_error"]`` =
``{code, message}`` and a WARNING -- the node never raises (a raise would make
node_builder retry paid work).
"""

from __future__ import annotations

import base64
import mimetypes
import os
import re
import time
from typing import Any, Dict, List, Optional

from agent.ec_skills.media.proxy_media_client import (
    CONTENT_POLICY_HINT,
    MediaProxyError,
    ProxyMediaClient,
    is_url,
    unique_path,
)
from agent.ec_skills.media.media_inputs import split_media_list
from agent.cloud_worker.cloud_logger import send_skill_editor_log
from utils.logger_helper import logger_helper as logger

DEFAULT_TIMEOUTS = {"image": 120.0, "speech": 60.0, "video": 900.0}
_AUDIO_EXT = {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
              "audio/wave": "wav", "audio/pcm": "pcm", "audio/l16": "pcm", "audio/opus": "opus",
              "audio/ogg": "opus"}


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
    return str(v).strip().lower() in ("true", "1", "yes", "on")


def _media_entry(**fields: Any) -> Dict[str, Any]:
    return {k: v for k, v in fields.items() if v not in (None, "")}


def build_media_gen_node(config_metadata: dict, node_name, skill_name, owner, bp_manager):
    from agent.ec_skill import node_builder

    inputs = (config_metadata or {}).get("inputsValues", {}) or {}

    def _cfg(key: str, default: Any = None) -> Any:
        v = inputs.get(key)
        if isinstance(v, dict):
            v = v.get("content")
        return default if v in (None, "") else v

    media_type = str(_cfg("mediaType", "image")).strip().lower()
    model_name = str(_cfg("modelName", "") or "").strip()
    timeout_s = _to_float(_cfg("timeoutSeconds")) or DEFAULT_TIMEOUTS.get(media_type, 120.0)

    def _resolve_refs(client: ProxyMediaClient, raw: Any, state: dict) -> List[str]:
        urls = []
        for ref in split_media_list(render_template(raw, state)):
            urls.append(ref if is_url(ref) else client.upload_file(ref))
        return urls

    def _gen_image(client: ProxyMediaClient, state: dict, prompt: str, out_dir: str) -> List[dict]:
        refs = _resolve_refs(client, _cfg("referenceImages"), state) if _cfg("referenceImages") else []
        data = client.generate_images(
            model_name, prompt, timeout_s=timeout_s,
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
        audio, mime = client.speech(model_name, prompt, voice=_cfg("voice"), fmt=fmt or None,
                                    speed=_to_float(_cfg("speed")), timeout_s=timeout_s)
        mime = (mime or "").lower()
        ext = (_AUDIO_EXT.get(mime) or (mimetypes.guess_extension(mime) or "").lstrip(".")
               or fmt or "bin")
        path = unique_path(out_dir, f"speech_{int(time.time())}.{ext}")
        with open(path, "wb") as fh:
            fh.write(audio)
        return [_media_entry(path=path, mime_type=mime or mimetypes.guess_type(path)[0])]

    def _gen_video(client: ProxyMediaClient, state: dict, prompt: str, out_dir: str) -> List[dict]:
        refs = _resolve_refs(client, _cfg("referenceImages"), state) if _cfg("referenceImages") else []
        first = _resolve_refs(client, _cfg("firstFrame"), state) if _cfg("firstFrame") else []
        last = _resolve_refs(client, _cfg("lastFrame"), state) if _cfg("lastFrame") else []
        job = client.submit_video(
            model_name, prompt,
            negative_prompt=_cfg("negativePrompt"), image_url=first[0] if first else None,
            last_frame_url=last[0] if last else None,
            reference_images=refs or None, duration_seconds=_to_int(_cfg("durationSeconds")),
            resolution=_cfg("resolution"), aspect_ratio=_cfg("aspectRatio"),
            generate_audio=_to_bool(_cfg("generateAudio")),
        )
        job_id = job.get("id")
        state["result"]["media_job"] = {"id": job_id, "status": job.get("status")}
        msg = f"[MediaGen] node={node_name} video job {job_id} {job.get('status')}"
        logger.info(msg)
        send_skill_editor_log("log", msg)

        def _progress(j: dict) -> None:
            state["result"]["media_job"] = {"id": job_id, "status": j.get("status")}
            logger.info(f"[MediaGen] node={node_name} video job {job_id} "
                        f"{j.get('status')} progress={j.get('progress')}")

        try:
            job = client.wait_video(job_id, timeout_s=timeout_s, on_progress=_progress)
        except MediaProxyError as e:
            if e.code == "client_timeout":
                # Give up: cancel so the proxy releases the pre-authorization.
                try:
                    client.cancel_video(job_id)
                except Exception as ce:
                    logger.warning(f"[MediaGen] cancel of timed-out video {job_id} failed: {ce}")
                state["result"]["media_job"] = {"id": job_id, "status": "timeout"}
            raise
        status = job.get("status")
        state["result"]["media_job"] = {"id": job_id, "status": status}
        if status != "succeeded":
            err = job.get("error") or {}
            code = str(err.get("code") or status)
            message = str(err.get("message") or f"video job {status}")
            if code == "content_policy":
                message = f"{CONTENT_POLICY_HINT} ({message})"
            raise MediaProxyError(200, code, message)
        out = job.get("output") or {}
        if not out.get("url"):
            raise MediaProxyError(502, "empty_output", "video job succeeded without an output url")
        path = client.download(out["url"], out_dir)
        return [_media_entry(path=path, url=out.get("url"), mime_type=out.get("mime_type") or "video/mp4",
                             width=out.get("width"), height=out.get("height"),
                             duration_seconds=out.get("duration_seconds"))]

    def media_gen_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        msg = f"🎬 Executing media-gen node: {node_name} ({media_type}, model={model_name})"
        logger.info(msg)
        send_skill_editor_log("log", msg)
        if not isinstance(state.get("result"), dict):
            state["result"] = {}
        for k in ("media", "media_job", "media_error"):
            state["result"].pop(k, None)

        client = None
        try:
            if media_type not in DEFAULT_TIMEOUTS:
                raise MediaProxyError(400, "invalid_request", f"unsupported mediaType '{media_type}'")
            if not model_name:
                raise MediaProxyError(400, "invalid_request", "modelName is required")
            prompt = render_template(_cfg("prompt", ""), state).strip()
            if not prompt:
                raise MediaProxyError(400, "invalid_request", "prompt is empty")
            client = _make_client()
            out_dir = _output_dir(str(_cfg("outputSubdir", "") or ""))
            if media_type == "image":
                media = _gen_image(client, state, prompt, out_dir)
            elif media_type == "video":
                media = _gen_video(client, state, prompt, out_dir)
            else:
                media = _gen_speech(client, prompt, out_dir)
            state["result"]["media"] = media
            msg = f"✅ [MediaGen] node={node_name} saved {[m.get('path') for m in media]}"
            logger.info(msg)
            send_skill_editor_log("log", msg)
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
        return state

    return node_builder(media_gen_callable, node_name, skill_name, owner, bp_manager)

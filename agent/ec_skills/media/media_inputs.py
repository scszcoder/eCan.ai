"""Video / audio (and extra image) inputs for LLM-node chat messages.

Turns media references into OpenAI-style content parts per the llm-proxy
contract: image -> ``image_url``; video -> uploaded via ``/files`` ->
``video_url``; audio <=10 MB -> ``input_audio`` (base64), larger -> uploaded ->
``audio_url``.

When the chat model can't take the media, it falls back locally: a video is
sampled with ffmpeg (~1 fps, <=16 JPEG frames, sent as images if the model has
vision) and its audio track transcribed via the proxy; audio is transcribed.
Every failure degrades to a short text note -- this never raises.
"""

from __future__ import annotations

import base64
import glob
import os
import re
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import unquote, urlparse

import httpx

from agent.ec_skills.media.proxy_media_client import ProxyMediaClient, guess_mime, is_url
from utils.logger_helper import logger_helper as logger

DEFAULT_TRANSCRIBE_MODEL = "paraformer-v2"
INLINE_AUDIO_MAX_BYTES = 10 * 1024 * 1024
INLINE_AUDIO_FORMATS = ("mp3", "wav", "m4a")
MAX_FRAMES = 16


def _make_client() -> ProxyMediaClient:
    return ProxyMediaClient.from_ecanai()


def find_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def _run(cmd: List[str]):
    from utils.subprocess_helper import run_no_window
    return run_no_window(cmd, capture_output=True, timeout=300)


def split_media_list(text: Any) -> List[str]:
    """Newline- or comma-separated paths / URLs -> list (blanks dropped). A list
    rendered into a template field (``["a.png", "b.png"]`` or Python's
    ``['a.png']``) counts as that list."""
    if isinstance(text, (list, tuple)):
        return [str(x).strip() for x in text if str(x).strip()]
    raw = str(text or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        import ast
        try:
            items = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            items = None
        if isinstance(items, (list, tuple)):
            return [str(x).strip() for x in items if str(x).strip()]
    return [p.strip() for p in re.split(r"[\r\n,]+", raw) if p.strip()]


def _ref_name(source: str) -> str:
    return os.path.basename(unquote(urlparse(source).path)) if is_url(source) else os.path.basename(source)


def classify_media(source: str, mime_type: str = "") -> Optional[str]:
    """``image`` / ``video`` / ``audio`` from a mime type or file extension."""
    mime = (mime_type or guess_mime(_ref_name(source), "")).lower()
    for kind in ("image", "video", "audio"):
        if mime.startswith(kind + "/"):
            return kind
    return None


def _probe_duration(ffmpeg: str, src: str) -> float:
    try:
        proc = _run([ffmpeg, "-hide_banner", "-i", src])
        err = proc.stderr.decode("utf-8", "ignore") if isinstance(proc.stderr, bytes) else str(proc.stderr or "")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def sample_frames(ffmpeg: str, src: str, out_dir: str) -> List[str]:
    """~1 fps JPEG frames, spread over the whole clip, at most ``MAX_FRAMES``."""
    duration = _probe_duration(ffmpeg, src)
    fps = min(1.0, MAX_FRAMES / duration) if duration > 0 else 1.0
    _run([ffmpeg, "-v", "error", "-y", "-i", src,
          "-vf", f"fps={fps:.4f},scale='min(1280,iw)':-2",
          "-frames:v", str(MAX_FRAMES), "-q:v", "4",
          os.path.join(out_dir, "frame_%03d.jpg")])
    return sorted(glob.glob(os.path.join(out_dir, "frame_*.jpg")))[:MAX_FRAMES]


def extract_audio(ffmpeg: str, src: str, out_dir: str) -> Optional[str]:
    """Mono 16 kHz mp3 of the audio track, or None (e.g. a silent clip)."""
    out = os.path.join(out_dir, "audio_track.mp3")
    proc = _run([ffmpeg, "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", out])
    if getattr(proc, "returncode", 1) == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    return None


def _fetch(url: str, out_dir: str) -> str:
    resp = httpx.get(url, timeout=httpx.Timeout(600.0, connect=15.0), follow_redirects=True)
    resp.raise_for_status()
    path = os.path.join(out_dir, _ref_name(url) or "media.bin")
    with open(path, "wb") as fh:
        fh.write(resp.content)
    return path


def _image_data_uri(path: str) -> str:
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{guess_mime(path, 'image/jpeg')};base64,{data}"


def _text(t: str) -> Dict[str, Any]:
    return {"type": "text", "text": t}


def build_media_parts(
    refs: List[Dict[str, Any]],
    *,
    supports_vision: bool = True,
    supports_video: bool = False,
    supports_audio: bool = False,
    transcribe_model: str = DEFAULT_TRANSCRIBE_MODEL,
) -> List[Dict[str, Any]]:
    """Content parts for ``refs`` (``{"kind", "source", "name"?, "data"?}``;
    ``source`` is a local path or URL, ``data`` raw bytes to materialise)."""
    parts: List[Dict[str, Any]] = []
    client_box: Dict[str, ProxyMediaClient] = {}

    def client() -> ProxyMediaClient:
        if "c" not in client_box:
            client_box["c"] = _make_client()
        return client_box["c"]

    def transcript(src: str, label: str) -> Optional[Dict[str, Any]]:
        text = (client().transcribe(src, transcribe_model) or {}).get("text") or ""
        return _text(f"Transcript of {label}:\n{text.strip()}") if text.strip() else None

    with tempfile.TemporaryDirectory(prefix="ecan_media_") as tmp:
        for i, ref in enumerate(refs):
            kind = ref.get("kind")
            src = str(ref.get("source") or "")
            name = ref.get("name") or _ref_name(src) or f"{kind}_{i}"
            try:
                if ref.get("data") is not None:
                    src = os.path.join(tmp, f"{i}_{os.path.basename(name)}")
                    with open(src, "wb") as fh:
                        fh.write(ref["data"])
                if kind == "image":
                    if supports_vision:
                        url = src if is_url(src) else _image_data_uri(src)
                        parts.append({"type": "image_url", "image_url": {"url": url, "detail": "auto"}})
                elif kind == "video":
                    if supports_video:
                        url = src if is_url(src) else client().upload_file(src)
                        parts.append({"type": "video_url", "video_url": {"url": url}})
                    else:
                        parts.extend(_video_fallback(src, name, tmp, i, supports_vision, transcript))
                elif kind == "audio":
                    if supports_audio:
                        parts.append(_audio_part(src, client))
                    else:
                        t = transcript(src, f"audio {name}")
                        parts.append(t or _text(f"[Audio file: {name} - no speech recognised]"))
            except Exception as e:
                logger.warning(f"[multimodal] {kind} input {name} could not be processed: "
                               f"{type(e).__name__}: {e}")
                parts.append(_text(f"[{str(kind).capitalize()} file: {name} - could not be processed]"))
        if client_box:
            client_box["c"].close()
    return parts


def _audio_part(src: str, client: Callable[[], ProxyMediaClient]) -> Dict[str, Any]:
    if is_url(src):
        return {"type": "audio_url", "audio_url": {"url": src}}
    fmt = os.path.splitext(src)[1].lstrip(".").lower()
    if fmt in INLINE_AUDIO_FORMATS and os.path.getsize(src) <= INLINE_AUDIO_MAX_BYTES:
        with open(src, "rb") as fh:
            data = base64.b64encode(fh.read()).decode("ascii")
        return {"type": "input_audio", "input_audio": {"data": data, "format": fmt}}
    return {"type": "audio_url", "audio_url": {"url": client().upload_file(src)}}


def _video_fallback(src: str, name: str, tmp: str, idx: int, supports_vision: bool,
                    transcript: Callable[[str, str], Optional[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        logger.warning(f"[multimodal] ffmpeg not available; video {name} sent as a text note only")
        return [_text(f"[Video file: {name} - cannot be viewed by this model and ffmpeg is unavailable]")]
    work = os.path.join(tmp, f"v{idx}")
    os.makedirs(work, exist_ok=True)
    if is_url(src):
        src = _fetch(src, work)
    parts: List[Dict[str, Any]] = []
    frames = sample_frames(ffmpeg, src, work) if supports_vision else []
    if frames:
        parts.append(_text(f"[Video {name}: {len(frames)} frames sampled in order]"))
        parts.extend({"type": "image_url", "image_url": {"url": _image_data_uri(f), "detail": "auto"}}
                     for f in frames)
    audio = extract_audio(ffmpeg, src, work)
    t = transcript(audio, f"video {name}") if audio else None
    if t:
        parts.append(t)
    if not parts:
        parts.append(_text(f"[Video file: {name} - no frames or speech could be extracted]"))
    return parts

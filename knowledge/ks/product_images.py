"""Product images in the knowledge base: a stored copy of each, and a one-line
description of what it shows, so "do you have this / something similar?" can
be answered from a buyer's photo.

Sources (all end up the same): an image link or a local file path in the
catalog's 图片 column, a picture embedded in the Excel row, or the store's own
product images. Each is copied into the knowledge base's own folder once
(links expire, files move) and described once by the vision model through the
llm-proxy; the description is indexed with the product (chunking.py).

A product's ``images`` list holds dicts:
    {"src": "<link / path / 'embedded'>", "file": "<stored file name>", "sha": "...",
     "desc": "<what it shows>", "error": "<why it could not be stored>"}
Plain strings from older imports are read as {"src": <string>}.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

MAX_BYTES = 15 * 1024 * 1024
MAX_IMAGES_PER_PRODUCT = 6
DESCRIBE_PER_PRODUCT = 3          # the first images (main pictures) are what a buyer's photo resembles
VISION_MODEL = os.environ.get("ECAN_PRODUCT_IMAGE_MODEL", "qwen3-vl-plus")
_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif", "bmp"}
_lock = threading.Lock()

_PROMPT = ("这是一张电商商品图片。用一句中文描述它的外观，供顾客发来照片时按图找同款或相似款："
           "品类、颜色、图案或材质外观、款式、明显特征（如领型、袖长、图案位置、logo 文字）。"
           "只写图里看得到的，不写价格，不猜品牌（除非图上有字），不超过60字。只输出这一句。")


def images_dir() -> str:
    try:
        from utils.user_path_helper import get_user_data_dir
        d = str(get_user_data_dir(subdir=os.path.join("knowledge_service", "product_images")))
    except Exception:
        d = os.path.join(os.path.expanduser("~"), ".ecan", "product_images")
    os.makedirs(d, exist_ok=True)
    return d


def file_path(entry: Dict[str, Any]) -> str:
    return os.path.join(images_dir(), entry["file"]) if entry.get("file") else ""


def normalize(images: Iterable[Any]) -> List[Dict[str, Any]]:
    out = []
    for it in images or []:
        if isinstance(it, dict) and (it.get("src") or it.get("file")):
            out.append(dict(it))
        elif isinstance(it, str) and it.strip():
            out.append({"src": it.strip()})
    return out


def _ext_of(data: bytes, hint: str = "") -> str:
    head = data[:12]
    if head.startswith(b"\x89PNG"):
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:3] == b"GIF":
        return "gif"
    if head[:2] == b"BM":
        return "bmp"
    h = (hint or "").lower().lstrip(".")
    return h if h in _IMAGE_EXT else ""


def _fetch(src: str, base_dir: str = "") -> Tuple[Optional[bytes], str]:
    """(bytes, error) for an image link or a local path."""
    s = src.strip().strip('"')
    try:
        if s.lower().startswith(("http://", "https://")):
            if s.startswith("http://"):
                s = "https://" + s[len("http://"):] if "alicdn" in s or "pddpic" in s else s
            req = urllib.request.Request(s, headers={"User-Agent": "Mozilla/5.0 eCan-catalog"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read(MAX_BYTES + 1)
        else:
            p = os.path.expandvars(os.path.expanduser(s))
            if not os.path.isabs(p) and base_dir:
                p = os.path.join(base_dir, p)
            if not os.path.isfile(p):
                return None, "file not found"
            if os.path.getsize(p) > MAX_BYTES:
                return None, "file too large"
            with open(p, "rb") as f:
                data = f.read()
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:80]}"
    if len(data) > MAX_BYTES:
        return None, "image too large"
    return data, ""


def store_bytes(data: bytes, ext_hint: str = "") -> Tuple[str, str]:
    """Save *data* once under its hash. Returns (sha, file name) or ('', '') if not an image."""
    ext = _ext_of(data, ext_hint)
    if not ext:
        return "", ""
    sha = hashlib.sha256(data).hexdigest()[:24]
    name = f"{sha}.{ext}"
    path = os.path.join(images_dir(), name)
    if not os.path.exists(path):
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return sha, name


def prepare(images: Iterable[Any], base_dir: str = "",
            embedded: Iterable[Tuple[bytes, str]] = ()) -> List[Dict[str, Any]]:
    """Every image of one product stored locally (already stored ones are kept)."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for data, ext in embedded or []:
        sha, name = store_bytes(data, ext)
        if sha and sha not in seen:
            seen.add(sha)
            out.append({"src": "embedded", "file": name, "sha": sha})
    for e in normalize(images):
        if e.get("file") and os.path.exists(file_path(e)):
            if e.get("sha") not in seen:
                seen.add(e.get("sha"))
                out.append(e)
            continue
        data, err = _fetch(str(e.get("src") or ""), base_dir)
        if data is None:
            out.append({"src": e.get("src"), "error": err})
            continue
        sha, name = store_bytes(data, os.path.splitext(str(e.get("src") or ""))[1])
        if not sha:
            out.append({"src": e.get("src"), "error": "not an image"})
        elif sha not in seen:
            seen.add(sha)
            out.append({**{k: v for k, v in e.items() if k not in ("error",)}, "file": name, "sha": sha})
    return out[:MAX_IMAGES_PER_PRODUCT]


# ---- descriptions ---------------------------------------------------------------
def _cache_path() -> str:
    return os.path.join(images_dir(), "descriptions.json")


def _load_cache() -> Dict[str, str]:
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_cache(cache: Dict[str, str]) -> None:
    try:
        with open(_cache_path() + ".part", "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(_cache_path() + ".part", _cache_path())
    except Exception as exc:
        logger.warning(f"[product-images] description cache not saved: {exc}")


def _jpeg_for_model(path) -> bytes:
    """A smaller JPEG for the model (long side <= 1024): cheaper, and under the route's limit.
    *path* is a file path or the image bytes."""
    try:
        from PIL import Image
        src = io.BytesIO(path) if isinstance(path, (bytes, bytearray)) else path
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((1024, 1024))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
            return buf.getvalue()
    except Exception:
        if isinstance(path, (bytes, bytearray)):
            return bytes(path)
        with open(path, "rb") as f:
            return f.read()


def _ask_vision(path) -> str:
    import base64
    from langchain_core.messages import HumanMessage
    from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
    from utils.log_scope import scope
    b64 = base64.b64encode(_jpeg_for_model(path)).decode("ascii")
    llm = create_ecanai_chat_llm(VISION_MODEL, temperature=0.0, media=True)
    with scope(modality="multimodal"):
        reply = llm.invoke([HumanMessage(content=[
            {"type": "text", "text": _PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}])]).content
    text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
    return " ".join(text.split())[:120]


def describe(entries: List[Dict[str, Any]], limit: int = DESCRIBE_PER_PRODUCT, ask=None) -> int:
    """Describe the first *limit* stored images that have no description yet.
    Same picture = same description (cached by hash across products). Returns
    how many were newly described. Never raises: a product without
    descriptions is still imported."""
    ask = ask or _ask_vision
    with _lock:
        cache = _load_cache()
    done = 0
    for e in [x for x in entries if x.get("file")][:limit]:
        if e.get("desc"):
            continue
        sha = e.get("sha") or ""
        if sha in cache:
            e["desc"] = cache[sha]
            continue
        try:
            desc = ask(file_path(e))
        except Exception as exc:
            logger.warning(f"[product-images] could not describe {e.get('file')}: {type(exc).__name__}: {exc}")
            break                  # the model is unreachable: stop, the next import retries
        if desc:
            e["desc"] = desc
            cache[sha] = desc
            done += 1
    if done:
        with _lock:
            merged = _load_cache()
            merged.update(cache)
            _save_cache(merged)
    return done


def describe_bytes(data: bytes, ask=None) -> str:
    """A buyer's picture described the same way as the product pictures, so the
    two can be matched (rag_query). Cached by hash; "" when it can't be done."""
    ask = ask or _ask_vision
    sha = hashlib.sha256(data).hexdigest()[:24]
    with _lock:
        cache = _load_cache()
    if sha in cache:
        return cache[sha]
    try:
        desc = ask(data)
    except Exception as exc:
        logger.warning(f"[product-images] could not describe the buyer's picture: {type(exc).__name__}: {exc}")
        return ""
    if desc:
        with _lock:
            merged = _load_cache()
            merged[sha] = desc
            _save_cache(merged)
    return desc


def looks_text(images: Iterable[Any]) -> str:
    """The product's appearance, for the index: '外观：...；...'."""
    descs = [e.get("desc") for e in normalize(images) if e.get("desc")]
    return ("外观：" + "；".join(descs)) if descs else ""

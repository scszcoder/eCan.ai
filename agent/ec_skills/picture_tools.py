"""图片小工具: everyday picture chores on the merchant's own pictures.

Input: pictures in <folder>/输入/ (loose, or one folder per product). Output:
<folder>/结果/<商品>/<工具>_<原名>.png and a summary. Tools:

  white_bg  白底图    background replaced by pure white (image model with the picture as
                      reference), padded to a square of at least 800 px
  cutout    透明图    white_bg, then the white background made transparent (PNG)
  unmark    去水印    watermarks / stray text / logos that are not part of the product removed
                      (image model) -- only for the merchant's OWN pictures
  stamp     促销角标  a promo badge drawn on the picture, locally (task vars stamp_text
                      e.g. "限时直降", stamp_corner tl|tr|bl|br, stamp_color #E02E24)
  resize    改尺寸    1:1 (800x800) and 3:4 (750x1000) versions, padded with the picture's own
                      edge colour, never cropped (locally)

white_bg / cutout / unmark are paid model calls; stamp and resize are free. The model can
change small details of a product: the summary asks the person to check before use.
Nothing is uploaded to a store.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

PICS = (".jpg", ".jpeg", ".png", ".webp")
NAMES = {"white_bg": "白底图", "cutout": "透明图", "unmark": "去水印", "stamp": "促销角标", "resize": "改尺寸"}
MODEL_TOOLS = {"white_bg", "cutout", "unmark"}
_KEEP = "严格保持商品本身的外形、颜色、图案、文字、材质和细节完全不变，不要添加任何东西，构图和商品位置不变。"
PROMPTS = {"white_bg": "把这张商品图的背景换成纯白色（#FFFFFF），去掉阴影以外的所有背景物体。" + _KEEP,
           "unmark": "去掉这张图上的水印、角标、网址和不属于商品本身的文字或标志，被遮住的地方按周围自然补全。" + _KEEP}
PROMPTS["cutout"] = PROMPTS["white_bg"]
SIZES = {"1比1": (800, 800), "3比4": (750, 1000)}
FONTS = (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
         "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")


def pictures(folder: str) -> List[Tuple[str, str]]:
    """[(group, path)]: loose pictures in 输入/ are group "", a product folder is its name."""
    root = os.path.join(folder, "输入")
    out: List[Tuple[str, str]] = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        p = os.path.join(root, name)
        if os.path.isdir(p):
            out += [(name, os.path.join(p, f)) for f in sorted(os.listdir(p)) if f.lower().endswith(PICS)]
        elif name.lower().endswith(PICS):
            out.append(("", p))
    return out


def _edge_colour(im) -> Tuple[int, int, int]:
    w, h = im.size
    px = [im.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    return tuple(sorted(c[i] for c in px)[1] for i in range(3))


def fit(path: str, size: Tuple[int, int], out: str) -> str:
    """Scale *path* to fit inside *size* and pad with its edge colour."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        k = min(size[0] / im.width, size[1] / im.height)
        im2 = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        canvas = Image.new("RGB", size, _edge_colour(im))
        canvas.paste(im2, ((size[0] - im2.width) // 2, (size[1] - im2.height) // 2))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        canvas.save(out)
    return out


def transparent(path: str, out: str, tolerance: int = 18) -> str:
    """White background connected to the border -> transparent; white inside the product stays."""
    from PIL import Image, ImageDraw
    with Image.open(path) as im:
        rgb = im.convert("RGB")
    mask = rgb.copy()
    w, h = mask.size
    marker = (255, 0, 255)
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)):
        if min(mask.getpixel((x, y))) >= 255 - tolerance:
            ImageDraw.floodfill(mask, (x, y), marker, thresh=tolerance)
    rgba = rgb.convert("RGBA")
    src, m = rgba.load(), mask.load()
    for y in range(h):
        for x in range(w):
            if m[x, y] == marker:
                src[x, y] = (255, 255, 255, 0)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    rgba.save(out)
    return out


def _font(px: int):
    from PIL import ImageFont
    for f in FONTS:
        if os.path.isfile(f):
            return ImageFont.truetype(f, px)
    return ImageFont.load_default()


def stamp(path: str, out: str, text: str, corner: str = "tl", colour: str = "#E02E24") -> str:
    """A rounded badge with *text* in a corner, about 1/4 of the picture wide."""
    from PIL import Image, ImageDraw
    with Image.open(path) as im:
        im = im.convert("RGB")
    w, h = im.size
    font = _font(max(16, w // 14))
    d = ImageDraw.Draw(im)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    pad = max(8, w // 60)
    bw, bh = r - l + pad * 2, b - t + pad * 2
    m = max(8, w // 40)
    x = m if corner in ("tl", "bl") else w - bw - m
    y = m if corner in ("tl", "tr") else h - bh - m
    d.rounded_rectangle((x, y, x + bw, y + bh), radius=bh // 3, fill=colour)
    d.text((x + pad - l, y + pad - t), text, font=font, fill="white")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    return out


def _out(folder: str, group: str, tool: str, src: str, tag: str = "") -> str:
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(folder, "结果", group or "图片", f"{NAMES[tool]}{tag}_{base}.png")


def run(tool: str, folder: str, opts: Optional[Dict[str, Any]] = None, client=None) -> Dict[str, Any]:
    """Apply *tool* to every picture under <folder>/输入/. {summary, files, errors}."""
    opts = opts or {}
    if tool not in NAMES:
        raise ValueError(f"unknown tool {tool!r}; one of {', '.join(NAMES)}")
    name = NAMES[tool]
    items = pictures(folder)
    only = str(opts.get("product") or "").strip()
    if only:
        items = [(g, p) for g, p in items if g == only or os.path.basename(p) == only]
    items = items[: int(opts.get("max_pictures") or 20)]
    if not items:
        return {"summary": f"{name}：{os.path.join(folder, '输入')} 里没有图片（jpg/png/webp，可以按商品分文件夹）。",
                "files": [], "errors": []}
    files, errors, model = [], [], ""
    if tool in MODEL_TOOLS:
        from agent.ec_skills.art_studio import pick_model, square
        from agent.ec_skills.media.proxy_media_client import ProxyMediaClient
        client = client or ProxyMediaClient.from_ecanai()
        caps = client.get_model_capabilities()
        model = pick_model(caps, str(opts.get("model") or ""))
        spare = [m for m in caps if m != model and "images" in (caps[m].get("endpoints") or []) and caps[m].get("reference_images")]
    for group, src in items:
        try:
            if tool == "resize":
                files += [fit(src, size, _out(folder, group, tool, src, f"_{tag}")) for tag, size in SIZES.items()]
            elif tool == "stamp":
                text = str(opts.get("stamp_text") or "限时优惠").strip()[:8]
                files.append(stamp(src, _out(folder, group, tool, src), text, str(opts.get("stamp_corner") or "tl"),
                                   str(opts.get("stamp_color") or "#E02E24")))
            else:
                ref = client.upload_file(src)
                while True:
                    try:
                        data = client.generate_images(model, PROMPTS[tool], timeout_s=180.0, reference_images=[ref])
                        break
                    except Exception as exc:   # a model the proxy lists but its vendor no longer serves (KEN 11-05)
                        if not spare or "upstream" not in str(exc):
                            raise
                        logger.warning(f"[picture-tools] {model} failed ({str(exc)[:80]}); trying {spare[0]}")
                        model = spare.pop(0)
                url = (data[:1] or [{}])[0].get("url")
                if not url:
                    raise RuntimeError("模型没有返回图片")
                out = _out(folder, group, tool, src)
                got = client.download(url, os.path.dirname(out), os.path.basename(out))
                got = square(got)
                files.append(transparent(got, got) if tool == "cutout" else got)
        except Exception as exc:
            errors.append(f"{os.path.basename(src)}：{type(exc).__name__}: {str(exc)[:100]}")
    logger.info(f"[picture-tools] {tool} model={model or '-'} pictures={len(items)} files={len(files)} errors={len(errors)}")
    text = f"{name}：{len(items)} 张图，做好 {len(files)} 张，在 {os.path.join(folder, '结果')}。"
    if tool in MODEL_TOOLS:
        text += f"（模型 {model}）\n用之前请检查商品细节有没有被改动。"
    if tool == "unmark":
        text += "只处理自己有版权的图片。"
    if errors:
        text += "\n没做成：" + "；".join(errors[:3])
    return {"summary": text, "files": files, "errors": errors, "model": model}

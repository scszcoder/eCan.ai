"""美工 chores: product pictures from the merchant's own photos, on the llm-proxy image models.

Input: <folder>/输入/<商品>/ holds a product's photos (jpg/png/webp; the clearest first) and
optionally 说明.txt (selling points, style, anything the pictures must say). Output:
<folder>/结果/<商品>/<kind>_<n>.png, square (1:1, at least 800 px, as all three platforms
want for 主图), plus a summary. Kinds:

  main      主图生成    4 candidate main pictures (white or simple scene, product centred)
  set       主图套图    5 pictures: 白底正面, 卖点, 细节, 使用场景, 规格/尺码说明
  campaign  氛围图      the product in a campaign setting (task var campaign, e.g. 双11)

The model is chosen from the proxy's live list: an image model that takes reference
pictures (so the real product is kept, not invented). Each picture is a paid call; the
skill only runs when the merchant runs it. Generated text in pictures can be wrong --
the summary asks the person to check before uploading. Nothing is uploaded to a store.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

PICS = (".jpg", ".jpeg", ".png", ".webp")
MIN_SIDE = 800
NAMES = {"main": "主图生成", "set": "主图套图", "campaign": "氛围图"}
PREFERRED = ("seedream", "wan2.5-i2i")   # by name prefix, when several fit

_BASE = ("电商商品图。严格保持参考图里商品本身的外形、颜色、图案、材质和细节，不要改变商品，不要添加别的商品。"
         "正方形 1:1 构图，商品居中、完整、清晰，光线干净，高级质感。{notes}")
PROMPTS = {
    "main": [("主图", _BASE + "纯白或浅色简洁背景，突出商品主体，适合做平台主图首图，不要文字和水印。")] * 4,
    "set": [("白底正面", _BASE + "纯白背景，商品正面完整展示，不要文字。"),
            ("卖点", _BASE + "画面一侧用简短的中文大字写出 2-3 个卖点（只用说明里给出的卖点，没有就不写字）。"),
            ("细节", _BASE + "近景特写商品的面料/做工/关键细节，不要文字。"),
            ("场景", _BASE + "商品放在真实的使用场景里（符合商品用途），自然生活感，不要文字。"),
            ("规格", _BASE + "干净背景，旁边留出清晰的规格/尺码说明区域，文字只用说明里给出的信息，没有就不写字。")],
    "campaign": [("氛围", _BASE + "{campaign}大促氛围背景（色彩热烈、节日装饰），商品仍是画面主体，可加一行“{campaign}”字样。")] * 2,
}


def pick_model(caps: Dict[str, Dict[str, Any]], wanted: str = "") -> str:
    """An image model that accepts reference pictures (*wanted* if it does)."""
    ok = [m for m, c in caps.items() if "images" in (c.get("endpoints") or []) and c.get("reference_images")]
    if wanted:
        if wanted in ok:
            return wanted
        raise ValueError(f"模型 {wanted} 不能用参考图生成图片；可用：{', '.join(ok) or '无'}")
    for pref in PREFERRED:
        for m in ok:
            if m.startswith(pref):
                return m
    if not ok:
        raise RuntimeError("服务端现在没有能用参考图生成图片的模型")
    return sorted(ok)[0]


def products(folder: str) -> List[Dict[str, Any]]:
    """[{name, pictures, notes}] for each product folder under <folder>/输入/."""
    root = os.path.join(folder, "输入")
    out = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        pics = sorted(os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(PICS))
        notes = ""
        for fn in ("说明.txt", "notes.txt"):
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as fh:
                    notes = fh.read().strip()[:500]
                break
            except OSError:
                continue
        if pics:
            out.append({"name": name, "pictures": pics, "notes": notes})
    return out


def square(path: str, min_side: int = MIN_SIDE) -> str:
    """Pad to a square on the picture's own corner colour (never crops the product), at least *min_side*."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        side = max(w, h, min_side)
        if (w, h) == (side, side):
            return path
        canvas = Image.new("RGB", (side, side), im.getpixel((0, 0)))
        if max(w, h) < min_side:
            k = min_side / max(w, h)
            im = im.resize((round(w * k), round(h * k)), Image.LANCZOS)
            w, h = im.size
        canvas.paste(im, ((side - w) // 2, (side - h) // 2))
        out = os.path.splitext(path)[0] + ".png"
        canvas.save(out)
    if out != path:
        os.remove(path)
    return out


def run(kind: str, folder: str, opts: Optional[Dict[str, Any]] = None, client=None) -> Dict[str, Any]:
    """Make *kind* pictures for every product in <folder>/输入/. Returns {summary, files, errors}."""
    from agent.ec_skills.media.proxy_media_client import ProxyMediaClient
    opts = opts or {}
    if kind not in PROMPTS:
        raise ValueError(f"unknown kind {kind!r}; one of {', '.join(PROMPTS)}")
    items = products(folder)
    only = str(opts.get("product") or "").strip()
    if only:
        items = [p for p in items if p["name"] == only]
    name = NAMES[kind]
    if not items:
        return {"summary": f"{name}：{os.path.join(folder, '输入')} 下面没有商品文件夹（每个商品一个文件夹，放实拍图，"
                           f"可加 说明.txt 写卖点）。", "files": [], "errors": []}
    client = client or ProxyMediaClient.from_ecanai()
    model = pick_model(client.get_model_capabilities(), str(opts.get("model") or ""))
    max_refs = int((client.get_model_capabilities().get(model) or {}).get("max_reference_images") or 1)
    campaign = str(opts.get("campaign") or "双11")
    files, errors = [], []
    for p in items[: int(opts.get("max_products") or 5)]:
        refs = [client.upload_file(x) for x in p["pictures"][:min(max_refs, 3)]]
        out_dir = os.path.join(folder, "结果", p["name"])
        notes = f"商品说明：{p['notes']}" if p["notes"] else ""
        for i, (label, tmpl) in enumerate(PROMPTS[kind], 1):
            prompt = tmpl.format(notes=notes, campaign=campaign)
            try:
                data = client.generate_images(model, prompt, timeout_s=180.0, reference_images=refs)
                for item in data[:1]:
                    path = client.download(item["url"], out_dir, f"{name}_{label}_{i}.png") if item.get("url") else ""
                    if path:
                        files.append(square(path))
            except Exception as exc:
                errors.append(f"{p['name']} {label}：{type(exc).__name__}: {str(exc)[:120]}")
    logger.info(f"[art-studio] {kind} model={model} products={len(items)} files={len(files)} errors={len(errors)}")
    text = (f"{name}：{len(items)} 个商品，生成 {len(files)} 张图（模型 {model}），在 {os.path.join(folder, '结果')}。"
            "\n上传前请人工检查：商品细节有没有走样、图上的字对不对。")
    if errors:
        text += "\n没生成成功：" + "；".join(errors[:3])
    return {"summary": text, "files": files, "errors": errors, "model": model}

#!/usr/bin/env python3
"""Regenerate eCan.cn.icns from dock_512x512.png with full macOS icon sizes.

Run from project root:
    python3 scripts/build/regen_eCan_cn_icns.py

The script:
  1. Resizes dock_512x512.png into all required macOS icon sizes.
  2. Uses `iconutil` (macOS native) to assemble them into a proper .icns.
  3. Overwrites:
       - eCan.cn.icns                                  (root)
       - apps/cn/branding/icon.icns                    (CN branding copy)
  4. Verifies the new .icns contains 16/32/64/128/256/512/1024 sizes.

Requirements: macOS, Python with Pillow (`pip install Pillow`).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image
from PIL.IcnsImagePlugin import IcnsImageFile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PNG = PROJECT_ROOT / "resource/images/logos/dock_512x512.png"
OUT_MAIN = PROJECT_ROOT / "eCan.cn.icns"
OUT_BRANDING = PROJECT_ROOT / "apps/cn/branding/icon.icns"

# (pixel size, iconset file name) — covers Finder, Launchpad, Dock, App Switcher
SIZES = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]


def main() -> int:
    if not SRC_PNG.exists():
        print(f"[ERROR] Source PNG not found: {SRC_PNG}", file=sys.stderr)
        return 1

    src = Image.open(SRC_PNG).convert("RGBA")
    print(f"Source: {SRC_PNG}  size={src.size}  mode={src.mode}")

    iconset_dir = Path("/tmp/eCan.iconset")
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True)

    resized_cache: dict[int, Image.Image] = {}
    for size, name in SIZES:
        if size not in resized_cache:
            resized_cache[size] = src.resize((size, size), Image.LANCZOS)
        resized_cache[size].save(iconset_dir / name, "PNG")
        print(f"  wrote {name}  {size}x{size}")

    print(f"\nAssembling .icns via iconutil...")
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(OUT_MAIN)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] iconutil failed: {result.stderr}", file=sys.stderr)
        return 1

    shutil.copy(OUT_MAIN, OUT_BRANDING)
    print(f"\nWrote: {OUT_MAIN}")
    print(f"Wrote: {OUT_BRANDING}")

    # Verify
    icns = IcnsImageFile(str(OUT_MAIN))
    sizes_present = sorted({s for s, _, _ in icns.info.get("sizes", [])})
    print(f"\nFinal .icns sizes present: {sizes_present}")
    print(f"Final .icns file size: {OUT_MAIN.stat().st_size} bytes")

    required = {16, 32, 64, 128, 256, 512, 1024}
    missing = required - set(sizes_present)
    if missing:
        print(f"[WARN] Missing sizes: {missing}", file=sys.stderr)
        return 1

    print("\n[OK] eCan.cn.icns now contains all required macOS icon sizes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Parameters (column headers) of ST's MCU product selector tables (code only, no LLM).

Each ST product line has a product selector grid whose JSON
(``/bin/st/selectors/cxst/en.cxst-ps-grid.html/<SC id>.json``) holds its columns and
one row per product. Repeated names are told apart by ST's qualifier, condition and
group ("Supply Voltage (min)", "A/D Converters 12-bit: Number of Channels"). The grids
carry no filter definitions, so ranges and value lists are derived from the rows.

Writes ``<root>/parameters/parameters.json`` and ``parameters.md`` in the same shape as
the Microchip ones (``param_columns``), mirrored to the NAS. st.com refuses plain HTTP
clients and Playwright-launched browsers, so the JSON is read from a normally started
Chrome driven over CDP.

    python -m agent.ec_skills.chip_docs.st_param_columns C:/chip_docs/ST
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.ec_skills.chip_docs.param_columns import EMPTY, family_of, render_md

SITE = "https://www.st.com"
GRID_API = "/bin/st/selectors/cxst/en.cxst-ps-grid.html/{}.json"
LINE = "Microcontrollers & microprocessors"
# every MCU product line, not MPUs (same list as raw/collect_parts.js)
GRIDS = {"SC2154": "stm32-high-performance-mcus", "SC2155": "stm32-mainstream-mcus",
         "SC2157": "stm32-ultra-low-power-mcus", "SC2156": "stm32-wireless-mcus",
         "SC1244": "stm8-8-bit-mcus", "SC963": "spc5-32-bit-automotive-mcus",
         "SC2574": "stellar-32-bit-automotive-mcus", "SC2754": "stm8a-automotive-mcus"}
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
NUMERIC = ("integer", "float")
LISTED = ("multi", "boolean")
SERIES = re.compile(r"(STM32[A-Z]+\d|STM8[A-Z]+|SPC5\d|SR\d[A-Z])")
DERIVED = "series (from part number)"


def column_label(c: dict) -> str:
    name = c["name"].strip()
    if c.get("aggregation"):
        name = f"{c['aggregation'].strip()}: {name}"
    extra = [c[k].strip() for k in ("conditional",) if c.get(k)]
    if c.get("qualifier") in ("min", "max"):
        extra.append(c["qualifier"])
    return f"{name} ({', '.join(extra)})" if extra else name


def series_of(part: str) -> str:
    """STM32F103C8 -> STM32F1, STM8S003K3 -> STM8S, SPC582B60E1 -> SPC58, SR6P7C8 -> SR6P."""
    m = SERIES.match(part.strip().upper())
    return m.group(1) if m else family_of(part)


def _values(v) -> list[str]:
    return [] if v in EMPTY else [x.strip() for x in str(v).split("||") if x.strip()]


def describe_grid(sc: str, grid: dict) -> dict:
    cols = grid.get("columns") or []
    labels = [column_label(c) for c in cols]
    rows = [{labels[i]: cell_map.get(c["id"]) for i, c in enumerate(cols)}
            for cell_map in ({x["columnId"]: x["value"] for x in r.get("cells") or []} for r in grid.get("rows") or [])]
    params = []
    for c, label in zip(cols, labels):
        vals = [x for r in rows for x in _values(r.get(label))]
        p = {"name": label, "filled": sum(bool(_values(r.get(label))) for r in rows)}
        nums = []
        for x in vals:
            try:
                nums.append(float(x))
            except ValueError:
                pass
        if c.get("type") in NUMERIC and nums:
            p["filter"] = {"kind": "range", "min": min(nums), "max": max(nums)}
        # a text column is a filter only if its values repeat (not part numbers or descriptions)
        elif c.get("type") in LISTED or (c.get("type") == "string" and 1 < len(set(vals)) <= min(50, p["filled"] / 2)):
            p["filter"] = {"kind": "values", "values": sorted(set(vals))}
        if c.get("units"):
            p["units"] = c["units"]
        params.append(p)
    families = {}
    for r in rows:
        families.setdefault(series_of(str(r.get("Part Number") or "")), []).append(r)
    by_family = {fam: {"products": len(rs), "empty": [l for l in labels if all(not _values(r.get(l)) for r in rs)]}
                 for fam, rs in sorted(families.items())}
    name = re.sub(r"\s+", " ", grid.get("levelTitle") or sc).strip()
    return {"id": sc, "name": name, "path": [LINE, name],
            "url": f"{SITE}/en/microcontrollers-microprocessors/{GRIDS.get(sc, sc)}/products.html",
            "products": len(rows), "family_key": DERIVED, "parameters": params, "families": by_family}


async def fetch(profile: Path, port: int = 9334) -> dict[str, dict]:
    from playwright.async_api import async_playwright

    chrome = subprocess.Popen([CHROME, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                               "--no-first-run", "--no-default-browser-check", "about:blank"])
    try:
        time.sleep(4)
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            page = browser.contexts[0].pages[0]
            await page.goto(f"{SITE}/en/microcontrollers-microprocessors.html", timeout=90000,
                            wait_until="domcontentloaded")
            get = "async u => { const r = await fetch(u); if (!r.ok) throw new Error(r.status + ' ' + u); return r.json(); }"
            grids = {}
            for sc in GRIDS:
                grids[sc] = await page.evaluate(f"({get})", GRID_API.format(sc))
                print(f"{sc} {grids[sc].get('levelTitle')}: {len(grids[sc].get('rows') or [])} products, "
                      f"{len(grids[sc].get('columns') or [])} columns", flush=True)
            return grids
    finally:
        chrome.terminate()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="vendor folder, e.g. C:/chip_docs/ST")
    ap.add_argument("--profile", type=Path, help="Chrome profile dir (default <root>/raw/_params_browser_profile)")
    ap.add_argument("--no-nas", action="store_true", help="keep the local copy only")
    a = ap.parse_args()
    # the NAS upload roots (ECAN_NAS_UPLOAD_ROOTS) live in run.env, which only main.py loads
    from dotenv import load_dotenv
    from utils.run_env import run_env_path
    load_dotenv(run_env_path(), override=False)
    grids = asyncio.run(fetch(a.profile or a.root / "raw" / "_params_browser_profile"))
    charts = [describe_grid(sc, g) for sc, g in grids.items()]
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = a.root / "parameters"
    out.mkdir(parents=True, exist_ok=True)
    (out / "parameters.json").write_text(json.dumps({"fetched_at": fetched_at, "charts": charts},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "parameters.md").write_text(render_md(charts, fetched_at).replace(
        "# Microchip MCU parametric search parameters", "# ST MCU product selector parameters"), encoding="utf-8")
    print(f"{len(charts)} tables -> {out}", flush=True)
    if not a.no_nas:
        from agent.ec_skills.nas import ugreen_nas
        for name in ("parameters.json", "parameters.md"):
            ugreen_nas.nas_upload(str(out / name), f"{a.root.name}/parameters/{name}")
        print(f"mirrored to the NAS: {a.root.name}/parameters/", flush=True)


if __name__ == "__main__":
    main()

"""Parameters (column headers) of Microchip's parametric search tables (code only, no LLM).

Each product line's table is a "chart" on microchip.com. The site's own JSON API gives
the chart tree (product line > category > chart) and, per chart, its columns, filter
ranges and rows. Columns are per chart; within a chart, families leave different
columns empty, so each family's own parameter set is derived from the rows.

Writes ``<root>/parameters/parameters.json`` (everything) and ``parameters.md``
(readable summary). The API answers only inside a real Chrome session (Microchip's
CDN refuses plain HTTP clients), so requests run from a loaded parametric page.

    python -m agent.ec_skills.chip_docs.param_columns C:/chip_docs/Microchip
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SITE = "https://www.microchip.com"
TREE_API = "/chartAPIPreviewExternal/api/Chart/GetAllParametricDropdownView"
CHART_API = "/ChartAPIPreviewExternal/api/Chart/GetChartParametricSearchViewById?chartId="
PRODUCT_LINE = "Microcontrollers And Processors"
# the crawl's scope: every 8-, 16- and 32-bit MCU family and the dsPIC DSCs, not MPUs
CATEGORIES = ("8-Bit Microcontrollers", "16-Bit Microcontrollers", "32-Bit Microcontrollers",
              "Digital Signal Controllers")
EMPTY = (None, "", "-", "N/A", "n/a")
FAMILY_COLUMNS = ("Part Family", "Part Prefix", "Family")
DERIVED = "part number"


def family_of(part: str) -> str:
    """A family from the part number, for charts with no family column: the prefix, then
    the series letters after the size digits (PIC18F47Q43 -> PIC18F…Q, AVR128DA48 -> AVR…DA)."""
    part = part.strip().upper()  # the site writes both dsPIC33EP… and DSPIC33EP…
    m = re.match(r"([A-Z]+\d{0,2}[A-Z]+)\d+([A-Z]+)?", part)
    if not m:
        return part
    return m.group(1) + (f"…{m.group(2)}" if m.group(2) else "")


def charts_in_scope(tree: list[dict]) -> list[dict]:
    """Every chart under PRODUCT_LINE > CATEGORIES: {id, name, path}."""
    out = []

    def walk(nodes: list[dict], path: tuple[str, ...]) -> None:
        for n in nodes:
            p = path + (n["name"].strip(),)
            branch = n.get("branchId") or ""
            if branch.startswith("chartno_"):
                out.append({"id": int(branch[len("chartno_"):]), "name": p[-1], "path": list(p)})
            walk(n.get("subCategories") or [], p)

    for line in tree:
        if line["name"].strip() != PRODUCT_LINE:
            continue
        for cat in line.get("subCategories") or []:
            if cat["name"].strip() in CATEGORIES:
                walk([cat], (PRODUCT_LINE,))
    return out


def describe_chart(chart: dict, view: dict) -> dict:
    """A chart's parameters: each column with its filter, how many products fill it,
    and per family (a FAMILY_COLUMNS column, else from the part number) the columns it leaves empty."""
    rows = [r.get("demographics") or {} for r in view.get("chartData") or []]
    columns = list(view.get("allColumns") or [])
    filters = {}
    for f in view.get("columnFilters") or []:
        name, kind = f["column"][0], f["column"][1]
        filters[name] = ({"kind": "range", "min": f.get("minVal"), "max": f.get("maxVal")} if kind == 1
                         else {"kind": "values", "values": f.get("values") or []})
    params = [{"name": c, "filled": sum(r.get(c) not in EMPTY for r in rows), **({"filter": filters[c]}
              if c in filters else {})} for c in columns]
    # a family column counts only if it splits the chart (some hold one value, e.g. "8-bit MCU")
    key = next((c for c in FAMILY_COLUMNS if c in columns
                and len({str(r.get(c)).strip() for r in rows if r.get(c) not in EMPTY}) > 1), DERIVED)
    families = {}
    for r in rows:  # a row with no value in the family column falls back to its part number
        fam = str(r.get(key) or "").strip() if key != DERIVED else ""
        families.setdefault(fam or family_of(str(r.get("Product") or "")), []).append(r)
    by_family = {fam: {"products": len(rs),
                       "empty": [c for c in columns if all(r.get(c) in EMPTY for r in rs)]}
                 for fam, rs in sorted(families.items())}
    return {**chart, "url": f"{SITE}/en-us/parametric-search.html/{chart['id']}",
            "products": len(rows), "family_key": key, "parameters": params, "families": by_family}


def render_md(charts: list[dict], fetched_at: str) -> str:
    out = ["# Microchip MCU parametric search parameters", "",
           f"Fetched {fetched_at} from {len(charts)} parametric tables. "
           "`filled` = products with a value; per family, the parameters it leaves empty.", ""]
    for c in charts:
        out += [f"## {' > '.join(c['path'][1:])} (chart {c['id']})", "",
                f"{c['url']} · {c['products']} products · {len(c['parameters'])} parameters", "",
                "| parameter | filter | filled |", "|---|---|---|"]
        for p in c["parameters"]:
            f = p.get("filter")
            ftxt = (f"{f['min']} – {f['max']}" if f and f["kind"] == "range"
                    else f"{len(f['values'])} values" if f else "")
            out.append(f"| {p['name']} | {ftxt} | {p['filled']}/{c['products']} |")
        if c["families"]:
            out += ["", f"By {c['family_key']}:", ""]
            out += [f"- **{fam}** ({v['products']}): empty: {', '.join(v['empty']) or 'none'}"
                    for fam, v in c["families"].items()]
        out.append("")
    return "\n".join(out)


async def fetch(profile: Path) -> tuple[list[dict], dict[int, dict]]:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(profile), channel="chrome", headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(f"{SITE}/en-us/parametric-search.html/980", timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_selector('#product-table-container tr:has(td[name="Product"])', timeout=90000)
        get = "async u => { const r = await fetch(u); if (!r.ok) throw new Error(r.status + ' ' + u); return r.json(); }"
        tree = await page.evaluate(f"({get})", TREE_API)
        views = {}
        for chart in charts_in_scope(tree):
            views[chart["id"]] = await page.evaluate(f"({get})", CHART_API + str(chart["id"]))
            print(f"chart {chart['id']} {chart['name']}: {len(views[chart['id']].get('allColumns') or [])} columns",
                  flush=True)
        await ctx.close()
    return tree, views


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="vendor folder, e.g. C:/chip_docs/Microchip")
    ap.add_argument("--profile", type=Path, help="Chrome profile dir (default <root>/raw/_params_browser_profile)")
    a = ap.parse_args()
    tree, views = asyncio.run(fetch(a.profile or a.root / "raw" / "_params_browser_profile"))
    charts = [describe_chart(c, views[c["id"]]) for c in charts_in_scope(tree)]
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = a.root / "parameters"
    out.mkdir(parents=True, exist_ok=True)
    (out / "parameters.json").write_text(json.dumps({"fetched_at": fetched_at, "charts": charts},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "parameters.md").write_text(render_md(charts, fetched_at), encoding="utf-8")
    print(f"{len(charts)} charts -> {out}", flush=True)


if __name__ == "__main__":
    main()

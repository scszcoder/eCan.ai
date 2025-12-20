import asyncio
import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.mcp.server.scrapers.scrape_util import write_csv, clean_text, compute_header_order

START_URL = "https://www.digikey.com/en/products/filter/programmable-logic-ics/696"  # <-- put your results URL here
OUT_CSV = Path("digikey_results_dynamic.csv")
MAX_PAGES = 1  # set >1 to paginate
HEADLESS = True


# -------------------------------
# Helpers
# -------------------------------
async def dk_click_consent_banners(page: Page):
    # Try a few common consent / cookie banners Digi-Key shows
    selectors = [
        'button:has-text("Accept")',
        'button:has-text("I Accept")',
        'button:has-text("AGREE")',
        'button[aria-label="Close"]',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0:
                await el.first.click(timeout=1500)
        except PlaywrightTimeoutError:
            pass
        except Exception:
            pass


def dk_preferred_key(raw_key: str) -> str:
    """Map Digi-Key's data-atag to a nicer header when we recognize it, else keep raw."""
    mapping = {
        "tr-product": "Product",
        "tr-qtyAvailable": "Qty Available",
        "tr-unitPrice": "Unit Price",
        "tr-tariff": "Tariff",
        "tr-series": "Series",
        "tr-packaging": "Packaging",
        "tr-productstatus": "Product Status",
    }
    return mapping.get(raw_key, raw_key)


async def dk_extract_links_from_cell(td) -> Dict[str, str]:
    """Grab commonly useful links if present in a cell."""
    out = {}

    # MPN + Product URL
    mpn_a = td.locator('[data-testid="data-table-product-number"]').first
    if await mpn_a.count() > 0:
        out["MPN"] = clean_text(await mpn_a.inner_text())
        href = await mpn_a.get_attribute("href")
        if href:
            out["Product URL"] = href if href.startswith("http") else f"https://www.digikey.com{href}"

    # Manufacturer link
    mfr_a = td.locator('[data-testid="data-table-mfr-link"]').first
    if await mfr_a.count() > 0:
        out["Manufacturer"] = clean_text(await mfr_a.inner_text())
        href = await mfr_a.get_attribute("href")
        if href:
            out["Manufacturer URL"] = href if href.startswith("http") else f"https://www.digikey.com{href}"

    # Datasheet link (PDF icon)
    ds_a = td.locator('a:has(svg[data-testid="icon-alt-pdf"])').first
    if await ds_a.count() > 0:
        href = await ds_a.get_attribute("href")
        if href:
            out["Datasheet URL"] = href

    # Product image
    img = td.locator('img[data-testid="data-table-product-image"]').first
    if await img.count() > 0:
        src = await img.get_attribute("src")
        if src:
            # Digi-Key often uses protocol-relative //...
            out["Image URL"] = src if src.startswith("http") else f"https:{src}"

    return out


async def dk_parse_rows_on_page(page: Page) -> Tuple[List[Dict[str, str]], List[str]]:
    """Parse all rows on current results page. Returns (rows, encountered_keys_order)."""
    rows_out: List[Dict[str, str]] = []
    encountered_keys: List[str] = []  # keep first-seen order for dynamic columns

    # Wait for any product rows to exist
    await page.wait_for_selector('tr[class*="muwdap-tr"], tbody tr', timeout=15000)

    # Use the more specific class if present; fall back to generic rows
    row_locator = page.locator('tr[class*="muwdap-tr"]')
    if await row_locator.count() == 0:
        row_locator = page.locator("tbody tr")

    n_rows = await row_locator.count()
    for i in range(n_rows):
        tr = row_locator.nth(i)
        tds = tr.locator("td")
        n_tds = await tds.count()
        row_dict: Dict[str, str] = {}

        for j in range(n_tds):
            td = tds.nth(j)

            # Header key: prefer Digi-Key's data-atag on a child container
            data_atag = None
            try:
                atag_node = td.locator("[data-atag]").first
                if await atag_node.count() > 0:
                    data_atag = await atag_node.get_attribute("data-atag")
            except Exception:
                pass

            key = dk_preferred_key(data_atag) if data_atag else f"col{j}"
            # Remember first-seen order of dynamic keys
            if key not in encountered_keys:
                encountered_keys.append(key)

            # Cell text (flattening whitespace)
            try:
                text_val = clean_text(await td.inner_text())
            except Exception:
                text_val = ""

            # Store text for this dynamic column
            if text_val:
                row_dict[key] = text_val

            # Opportunistically add helpful link fields if found
            try:
                link_bits = await dk_extract_links_from_cell(td)
                for lk, lv in link_bits.items():
                    # prefer first found (usually lives in the "Product" column TD)
                    row_dict.setdefault(lk, lv)
            except Exception:
                pass

        # Only keep non-empty rows
        if any(v for v in row_dict.values()):
            rows_out.append(row_dict)

    return rows_out, encountered_keys


async def dk_click_next_if_present(page: Page) -> bool:
    """Try to paginate. Returns True if we navigated to next page."""
    candidates = [
        'button[aria-label="Next"]',
        'a[aria-label="Next"]',
        'button:has-text("Next")',
        'a:has-text("Next")',
    ]
    for sel in candidates:
        btn = page.locator(sel)
        if await btn.count() > 0 and await btn.first.is_enabled():
            await btn.first.click()
            # wait for rows to reload
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.5)
            return True
    return False


def dk_compute_header_order(all_rows: List[Dict[str, str]], dynamic_order: List[str]) -> List[str]:
    """Special fields first, then dynamic columns, then any leftovers."""
    special = ["MPN", "Product URL", "Manufacturer", "Manufacturer URL", "Datasheet URL", "Image URL"]
    return compute_header_order(special, all_rows, dynamic_order)


# -------------------------------
# Main
# -------------------------------
async def playwright_dk_extract_search_results_table(page):
    try:
        await page.goto(START_URL, wait_until="domcontentloaded")
        await dk_click_consent_banners(page)
        await page.wait_for_load_state("networkidle")

        all_rows: List[Dict[str, str]] = []
        dynamic_key_order: List[str] = []

        for page_idx in range(MAX_PAGES):
            # Some categories lazy-load; small scroll jiggle wakes the grid
            await page.mouse.wheel(0, 1200)
            await asyncio.sleep(0.4)
            await page.mouse.wheel(0, -800)
            await asyncio.sleep(0.2)

            rows, dyn_keys = await dk_parse_rows_on_page(page)
            all_rows.extend(rows)
            # merge first-seen order of dynamic headers
            for k in dyn_keys:
                if k not in dynamic_key_order:
                    dynamic_key_order.append(k)

            if page_idx + 1 >= MAX_PAGES:
                break
            moved = await dk_click_next_if_present(page)
            if not moved:
                break

        if not all_rows:
            print("No rows found. Is the URL a product results page?")
        else:
            header_order = dk_compute_header_order(all_rows, dynamic_key_order)
            write_csv(all_rows, header_order, OUT_CSV)
            print(f"Wrote {len(all_rows)} rows to {OUT_CSV.resolve()} with {len(header_order)} columns.")

    except Exception as e:
        err_trace = get_traceback(e, "ErrorPlaywrightExtractSearchResultsTable")
        logger.debug(err_trace)
        # await ctx.close()
        # await browser.close()

#
# if __name__ == "__main__":
#     asyncio.run(main())

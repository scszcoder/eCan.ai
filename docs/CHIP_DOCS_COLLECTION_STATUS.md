# Chip documentation collection: status and how to resume

State as of 2026-10-26. The collection is paused, with nothing running. This page records what is on the NAS, what is still missing, and how to pick the work up again.

## Where things live

- **NAS**
  - Host 192.168.0.4, share `personal_folder`, base `chips/` (see `agent/ec_skills/nas/ugreen_nas.py`).
  - Every vendor folder uses the same **shared store** layout:
    - `<Vendor>/files/<doc type>/<'doc type - title'.ext>` holds each document once.
    - `<Vendor>/docs/<category>/<part>/index.json` lists one part's documents as entries `{type, title, url, lang, file | restricted | error}`. The `file` value is `files/<doc type>/<name>`.
    - `<Vendor>/html/...` holds HTML editions (Microchip, ST).
    - `<Vendor>/parameters/` holds parametric tables (Microchip, ST).
- **Local root `C:/chip_docs/`, which is not in git**
  - `<Vendor>/raw/` holds each vendor's notes and inputs:
    - `NOTES.md`: site research, quirks and post-crawl backfills. Read it first.
    - `parts.json`: the unit list, `{parts: [{part, category, url, ...}]}`.
    - `collect_parts.js` and `collect_docs.js`: the collector scripts the crawler runs in the browser.
  - `<Vendor>/status.md` records each part's crawl state and is the coordinator's source of truth. Back it up before editing it.
  - `_queues/cnmcu.txt` is the Chinese MCU vendor queue. The `END` line closes it; to add vendors, append them above `END` and remove the line.
  - `_queues/cnmcu_gaps.md` records, per CN vendor, the gaps, backfills and vendors that need a human.
  - `_queues/summary_cn.json` holds the per-vendor counts from 2026-10-26, taken before the Beken SDK docs were added.
  - `browser_profiles/` holds the crawler and CDP Chrome profiles.
- **Crawler code**
  - `agent/ec_skills/chip_docs/crawl_executor.py` contains the coordinator and the vendor queue.
  - `agent/ec_skills/browser_use_extension/extension_tools_service.py` contains `download_docs_to_nas` and the shared-store helpers.
  - Skills live under `my_skills/chip_docs_*` and are gitignored, local only. Keep the Microchip and ST skills, prompts and scripts, and only add to them.
- **Maintenance scripts:** `scripts/chip_docs/` (see the last section).

## What has been collected

### Global vendors

| Vendor | Units done / planned | Index entries | Unique files | Not fetched |
|---|---|---|---|---|
| Microchip | 2331 + 8 covered / 2339 | 78,527 | 2,805 | 49 restricted, 17 not saved |
| ST | 1903 / 1903 | 118,402 | 1,251 (+68 HTML editions) | 0 |
| NXP | 603 / 604 | about 14,700 | 3,983 | 1,948 restricted (account), 1 error |
| Infineon | 2989 / 3036 | 109,516 | 1,331 | 47 parts login-only (automotive PSOC 4 M) |
| TI | 1525 / 1526 | 44,511 | 4,380 | DM8107 has no docs |
| Silicon Labs | 1382 / 1392 | 94,814 | 1,208 | 302 restricted; EFR32BG2D/FG2D unreleased |
| ADI | 249 / 253 | n/a | 966 | MAX32658 is a 404; 3 MAXQ parts are NDA-only |

### Chinese MCU vendors: all 33 in the queue are done

The table is ordered by queue position. "Files" counts index entries that point at a stored file; "unique" counts distinct files in the shared store.

| Vendor | Parts | With files | Files | Unique | Restricted | Errors |
|---|---|---|---|---|---|---|
| WCH | 68 | 65 | 268 | 151 | 1 | 0 |
| GigaDevice | 65 | 65 | 4593 | 398 | 0 | 0 |
| Nuvoton | 87 | 86 | 959 | 676 | 0 | 0 |
| Espressif | 21 | 18 | 298 | 198 | 0 | 0 |
| Telink | 19 | 19 | 110 | 101 | 0 | 0 |
| Sinowealth | 181 | 152 | 376 | 363 | 0 | 0 |
| MindMotion | 94 | 81 | 375 | 298 | 0 | 6 |
| Artery | 31 | 31 | 2981 | 1436 | 0 | 10 |
| Puya | 28 | 28 | 198 | 158 | 0 | 0 |
| Beken | 11 | 11 | 86 | 85 | 0 | 1 |
| Holtek | 429 | 429 | 3117 | 1074 | 0 | 0 |
| CMS | 123 | 75 | 124 | 111 | 262 | 0 |
| Fortior | 55 | 55 | 105 | 64 | 0 | 0 |
| Nationstech | 55 | 48 | 698 | 388 | 145 | 5 |
| Sonix | 68 | 68 | 714 | 641 | 107 | 0 |
| Elan | 7 | 7 | 209 | 207 | 0 | 0 |
| XHSC | 60 | 59 | 1320 | 430 | 0 | 2 |
| BYDMicro | 14 | 13 | 141 | 123 | 0 | 1 |
| Megawin | 68 | 66 | 177 | 117 | 0 | 0 |
| SOC | 16 | 16 | 199 | 158 | 0 | 1 |
| Belling | 3 | 3 | 3 | 3 | 0 | 0 |
| Padauk | 59 | 59 | 982 | 160 | 0 | 0 |
| Hycontek | 12 | 8 | 186 | 160 | 0 | 0 |
| HSXP | 44 | 38 | 275 | 217 | 0 | 0 |
| Spintrol | 25 | 25 | 81 | 79 | 0 | 0 |
| Essemi | 18 | 18 | 368 | 189 | 0 | 0 |
| ChinaCore | 4 | 2 | 16 | 16 | 0 | 0 |
| XTX | 5 | 2 | 2 | 2 | 0 | 0 |
| Unicmicro | 16 | 16 | 130 | 130 | 0 | 0 |
| Panchip | 19 | 19 | 40 | 39 | 0 | 0 |
| APTChip | 44 | 43 | 316 | 154 | 0 | 0 |
| STC | 16 | 16 | 52 | 47 | 6 | 0 |
| FMSH | 35 | 25 | 90 | 87 | 151 | 0 |
| **Total** | **1800** | **1666** | **19,589** | **about 8,460** | **672** | **26** |

Notes on individual vendors:
- **Beken**
  - Its website product pages carry no files.
  - The bulk of its documentation is the Armino SDK documentation on docs.bekencorp.com: 61 doc sets (kit × chip × language), each saved as an offline HTML zip in `Beken/files/SDK Documentation/` (about 525 MB).
  - Script: `scripts/chip_docs/beken_sdkdocs.py`. Set list: `C:/chip_docs/Beken/raw/sdk_sets.json`.
- **Holtek**
  - 54 series were added from its selection tool.
  - 258 application notes were fetched through its public API (`holtek_an.py`).
- **Elan** was crawled on a retry; the earlier bot check was gone.
- **The 26 errors are permanent** vendor-side failures, mostly 404s plus two 403s at XHSC. One of them is Beken's M39N module data sheet, which is a 404.
- **Restricted** means the document is listed in the index but needs a login. These were not fetched, by policy.

## Open items: where to pick up

1. **Restricted documents behind vendor accounts:** NXP (1,948 entries), Infineon (47 parts), Silicon Labs (302), Microchip (49), CMS (262), Nationstech (145), Sonix (107), FMSH (151) and STC (6).
   - Each needs the user to create or log in to an account first. The crawler must never log in or solve captchas on its own.
   - Agreed order: NXP, then Infineon.
2. **CN vendors that need a human.** These were researched but not queued; details are in `_queues/cnmcu_gaps.md` and each vendor's `raw/NOTES.md`.
   - Generalplus: 331 parts and tested scripts are ready, but every download has an image captcha.
   - Silan: 25 MCUs and 66 docs are indexed, but every download needs an e-mail verification code.
   - Nyquest: login plus captcha.
   - HiTrend: captcha on every download.
   - AutoChips: Feishu portal for authorised companies only.
   - Chipsea: a WAF blocks non-China IP addresses, and the English site has a captcha.
   - Not applicable: Blestech publishes no documents, and ChipRight makes no MCUs.
3. **Beken downloads site:** dl.bekencorp.com (BK3633 files, security flaw-reporting procedures, a stability-analysis guide) and support/armino.bekencorp.com sit behind a "confirm you are human" check (HTTP 468). Only the user can fetch these by hand.
4. **Microchip HTML editions:** 401 editions on onlinedocs.microchip.com were waiting on that site's maintenance window, and `Microchip/html` is still empty locally. Run `python -m agent.ec_skills.chip_docs.html_docs crawl C:/chip_docs/Microchip`, after checking that the site is up by reading the page text: it answers HTTP 200 even during maintenance.
5. **Adding more CN vendors:**
   - Research the vendor into `C:/chip_docs/<Vendor>/raw/` (NOTES.md, parts.json, collect_*.js), following the existing vendors.
   - Append the vendor to `_queues/cnmcu.txt` above `END`, then remove `END`.
   - Clear `completed_once_at` on the CNMCU coordinator task in the DB, and start the app.
6. **Before calling any vendor done**, check:
   - `verify_nas.py` passes.
   - Every unit in `parts.json` appears in `status.md`. Units added after planning are never crawled.
   - The vendor's selection or parametric tool, and any separate docs or SDK site, are covered.
   - Every "details" link has been followed one level down.

## Maintenance scripts (`scripts/chip_docs/`)

Run them from the repo root with `PYTHONPATH=.` and `.venv/Scripts/python.exe`. Any script that uploads needs `ECAN_NAS_UPLOAD_ROOTS=C:/chip_docs`.

| Script | Purpose |
|---|---|
| `summary.py <out.json> <Vendor>...` | Per-vendor counts from the NAS indexes (the tables above) |
| `verify_nas.py <Vendor>` | Every done part has an index, and every indexed file exists in the store |
| `errs.py <Vendor> <out.json>` | Failed index entries, grouped by URL |
| `retry_errors.py <Vendor>` | Re-fetches failed entries and patches the indexes (also fixes double-encoded URLs) |
| `add_docs.py <Vendor> <sweep.json> [--dry]` | Adds docs the crawl missed, from `{part: [ {type,title,url,lang[,restricted]} ]}` |
| `holtek_an.py` | Holtek application notes through the public download API |
| `beken_sdkdocs.py <sets.json>` | Mirrors the Beken Armino SDK doc sets to the NAS as offline zips |
| `run_collector.js <collector.js> <page url> [args] [out]` | Tests a collector script under Node and jsdom |
| `cdp_eval.py <collector.js> <start url>` | Tests a collector script in a real local Chrome over CDP |

"""Amazon Seller Central "Add Products via Upload" actions on the shared controller.

``amazon_download_template`` / ``amazon_upload_flatfile`` /
``amazon_fetch_report`` -- the fixed page dances of listing by flat file, so a
browser node never has to rediscover them: shadow-DOM kat-* components that
ignore JS clicks, a decoy upload button, controls below the fold, a store
checkbox that region-stamps the template. The spreadsheet work between them is
the ``amazon_template_*`` / ``amazon_parse_feedback`` MCP tools.

Ported from vibe-seller's bh_download_template.py / bh_upload_flatfile.py /
bh_fetch_report.py (Apache-2.0, see agent/ec_skills/listing/amazon_flatfile/
NOTICE). Page steps and waits are theirs; the harness calls are page_driver.
Each action returns its result as JSON; a failure's ``reason`` says which step
missed -- look at the page before retrying.
"""
# No ``from __future__ import annotations`` here: browser-use matches the
# injected ``browser_session: BrowserSession`` parameter by its real type.
import asyncio
import json
import os
import time

from pydantic import BaseModel, Field

from browser_use import BrowserSession
from browser_use.agent.views import ActionResult

from utils.logger_helper import logger_helper as logger
from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller

from .page_driver import WALK, FileChooser, Page, downloads_dir, newest

_HOST_HELP = "Seller Central host of the target marketplace, e.g. sellercentral.amazon.com"


class AmazonDownloadTemplateAction(BaseModel):
    host: str = Field(..., description=_HOST_HELP)
    product_type: str = Field(..., description="Product-type keyword to search in the template generator, e.g. 'socks'")
    store_label: str = Field(..., description="The store checkbox to tick, exactly as shown, e.g. 'Amazon.com' or 'Amazon.ae'")
    downloads_dir: str = Field("", description="Where this browser saves downloads (default: the browser's downloads path)")


class AmazonUploadFlatfileAction(BaseModel):
    host: str = Field(..., description=_HOST_HELP)
    file_path: str = Field(..., description="Absolute path of the tab-delimited .txt from amazon_template_fill (never the Excel file)")
    load_wait_s: int = Field(15, description="Seconds to let the upload page load")
    introspect_wait_s: int = Field(12, description="Seconds to let Amazon detect the file type after staging")


class AmazonFetchReportAction(BaseModel):
    host: str = Field(..., description=_HOST_HELP)
    batch_id: str = Field(..., description="The upload's batch id (reference_id) from amazon_upload_flatfile")
    downloads_dir: str = Field("", description="Where this browser saves downloads (default: the browser's downloads path)")


def _done(out: dict) -> ActionResult:
    text = json.dumps(out, ensure_ascii=False)
    if out.get("ok"):
        return ActionResult(extracted_content=text, include_in_memory=True)
    return ActionResult(error=text)


def _js_str(s: str) -> str:
    """A Python string as a JS string literal."""
    return json.dumps(str(s), ensure_ascii=False)


async def _click_text(page: Page, pattern: str) -> bool:
    """Trusted-click the first element whose text matches *pattern*."""
    b = await page.js_json(
        WALK + 'for(const e of w(document)){'
        'const t=(e.innerText||(e.getAttribute&&e.getAttribute("label"))||"").trim();'
        f'if(/{pattern}/i.test(t) && t.length<60){{'
        'const r=e.getBoundingClientRect();'
        'if(r.width) return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)});}}'
        'return null;'
    )
    if not isinstance(b, dict):
        return False
    await page.click(b['x'], b['y'])
    return True


async def _store_states(page: Page) -> list:
    """Every Amazon.* store checkbox: label, ticked (property OR attribute), coords."""
    res = await page.js_json(
        WALK + 'const res=[];'
        'for(const e of w(document)){'
        'if((e.tagName||"").toLowerCase()!=="kat-checkbox") continue;'
        'const lbl=(e.getAttribute("label")||e.textContent||"").trim();'
        'if(!/^Amazon\\./i.test(lbl)) continue;'
        'const on=(e.checked===true)||(e.hasAttribute("checked")&&e.getAttribute("checked")!=="false");'
        'const r=e.getBoundingClientRect();'
        'res.push({label:lbl,on:on,x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)});}'
        'return JSON.stringify(res);'
    )
    return res if isinstance(res, list) else []


async def _target_unticked(page: Page, store: str):
    states = await _store_states(page)
    tgt = next((s for s in states if s['label'].lower() == store.lower()), None)
    return states, tgt, (tgt if tgt is not None and not tgt['on'] else None)


@custom_controller.action(
    "Amazon Seller Central: generate and download the category flat-file template for ONE "
    "marketplace (Add Products via Upload > Download Product Spreadsheet). Ticks and VERIFIES "
    "the target store checkbox, because the template is region-stamped by it. Returns the "
    "downloaded template path.",
    param_model=AmazonDownloadTemplateAction)
async def amazon_download_template(params: AmazonDownloadTemplateAction,
                                   browser_session: BrowserSession) -> ActionResult:
    out = {'ok': False, 'template': None, 'picked': None, 'stores': None}
    dl = downloads_dir(browser_session, params.downloads_dir)
    if not dl:
        return _done({**out, 'reason': 'no downloads directory: pass downloads_dir'})
    store = params.store_label.strip()
    page = None
    try:
        t0 = time.time()
        page = await Page.open(browser_session, f'https://{params.host}/product-search/bulk/generate')
        await asyncio.sleep(13)
        # The UI language follows the session: every text match carries Chinese too.
        dps = '^(download product spreadsheet|下载商品电子表格)$'
        entered = await _click_text(page, dps)
        if not entered:
            # Some layouts gate the generator behind the Download Blank Template entry.
            await _click_text(page, '^(download blank template|下载空白模板)$')
            await asyncio.sleep(5)
            entered = await _click_text(page, dps)
        if not entered:
            return _done({**out, 'reason': 'Download Product Spreadsheet button not found '
                                           '(tried EN+ZH and the Download Blank Template entry)'})
        await asyncio.sleep(7)

        # The kat predictive input only takes TRUSTED keystrokes.
        sb = await page.js_json(
            WALK + 'for(const e of w(document)){'
            'const tag=(e.tagName||"").toLowerCase();'
            'const ph=(e.placeholder||(e.getAttribute&&e.getAttribute("placeholder"))||"");'
            'if(tag==="input" && /product keyword|商品关键|关键词/i.test(ph)){'
            'const r=e.getBoundingClientRect();'
            'return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)});}}'
            'return null;'
        )
        if not isinstance(sb, dict):
            return _done({**out, 'reason': 'product-type search input not found'})
        await page.click(sb['x'], sb['y'])
        await asyncio.sleep(1)
        await page.send('Input.insertText', text=params.product_type)
        for t in ('keyDown', 'keyUp'):
            await page.send('Input.dispatchKeyEvent', type=t, key='Enter', code='Enter',
                            windowsVirtualKeyCode=13)
        await asyncio.sleep(6)

        # The topmost result's Select button; its label is the text just before it.
        sel = await page.js_json(
            WALK + 'let best=null, label=null, prev=null;'
            'for(const e of w(document)){'
            'const t=(e.innerText||(e.getAttribute&&e.getAttribute("label"))||"").trim();'
            'if(/^(select|选择)$/i.test(t)){const r=e.getBoundingClientRect();'
            'if(r.width && (!best||r.y<best.y)){'
            'best={x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}; label=prev;}}'
            'if(t && t.length<40 && !/^(select|选择)$/i.test(t)) prev=t;}'
            'return best?JSON.stringify({box:best,label:label}):null;'
        )
        if not isinstance(sel, dict):
            return _done({**out, 'reason': f'no product-type result for {params.product_type!r}'})
        out['picked'] = sel.get('label')
        await page.click(sel['box']['x'], sel['box']['y'])
        await asyncio.sleep(4)

        # The store boxes and Generate sit low in the modal: tall viewport first.
        await page.tall_viewport(1600)
        await asyncio.sleep(1)
        # Tick only the TARGET leaf (never region parents: unticking one clears its
        # children; extra ticked leaves are fine, fill routes by marketplace). JS
        # click first; kat-checkbox often ignores it, so read back + trusted retry.
        await page.js(
            WALK + 'for(const e of w(document)){'
            'if((e.tagName||"").toLowerCase()!=="kat-checkbox") continue;'
            'const lbl=(e.getAttribute("label")||e.textContent||"").trim();'
            f'if(lbl.toLowerCase()!=={_js_str(store.lower())}) continue;'
            'const on=(e.checked===true)||(e.hasAttribute("checked")&&e.getAttribute("checked")!=="false");'
            'if(!on) e.click();}'
            'return "stores set";'
        )
        await asyncio.sleep(2)
        states, tgt, needs_click = await _target_unticked(page, store)
        for _ in range(2):
            if not needs_click:
                break
            await page.click(needs_click['x'], needs_click['y'])
            await asyncio.sleep(1.5)
            states, tgt, needs_click = await _target_unticked(page, store)
        out['stores'] = {s['label']: bool(s['on']) for s in states}
        if not states:
            return _done({**out, 'reason': 'no Amazon.* store checkboxes in the generator modal '
                                           '-- the page layout changed'})
        if tgt is None:
            return _done({**out, 'reason': f'store {store!r} is not among the Amazon.* checkboxes '
                                           '(see stores): wrong store_label, or the account has no such '
                                           'storefront. Not generated: it would be stamped for another region.'})
        if needs_click:
            return _done({**out, 'reason': f'store {store!r} is still NOT ticked after JS + trusted-click '
                                           'retries (see stores). Not generated: it would be stamped for '
                                           'the wrong region.'})
        if not await _click_text(page, '^(generate spreadsheet|生成电子表格)$'):
            return _done({**out, 'reason': 'Generate Spreadsheet button not found'})

        template = None
        for _ in range(25):
            await asyncio.sleep(1)
            template = newest(dl, ('.xlsm',), t0)
            if template:
                break
        out['template'] = template
        out['ok'] = bool(template)
        if not template:
            out['reason'] = f'Generate clicked but no new .xlsm landed in {dl}'
        return _done(out)
    except Exception as exc:
        logger.warning(f"[amazon_listing] download_template: {exc}")
        return _done({**out, 'reason': f'{type(exc).__name__}: {exc}'})
    finally:
        if page is not None:
            await page.reset_viewport()


@custom_controller.action(
    "Amazon Seller Central: stage and submit a filled flat file (the .txt from "
    "amazon_template_fill) on Add Products via Upload for ONE marketplace. Returns the "
    "upload's batch_id for amazon_fetch_report.",
    param_model=AmazonUploadFlatfileAction)
async def amazon_upload_flatfile(params: AmazonUploadFlatfileAction,
                                 browser_session: BrowserSession) -> ActionResult:
    f = os.path.abspath(os.path.expanduser(params.file_path))
    out = {'ok': False, 'staged': False, 'detected': False, 'region_error': False,
           'batch_id': None, 'host': params.host, 'file': f}
    if not os.path.isfile(f):
        return _done({**out, 'reason': f'file not found: {f}'})
    if f.lower().endswith(('.xlsm', '.xlsx', '.xls')):
        return _done({**out, 'reason': 'upload the tab-delimited .txt (upload_file from '
                                       'amazon_template_fill), not the Excel file'})
    page = None
    try:
        page = await Page.open(browser_session, f'https://{params.host}/product-search/bulk')
        await asyncio.sleep(params.load_wait_s)
        # A short viewport leaves the file button and Submit below the fold.
        await page.tall_viewport(3000)
        await asyncio.sleep(1)
        async with FileChooser(page) as chooser:
            box = await page.js(
                "var u=document.querySelector('kat-file-upload');"
                'if(!u||!u.shadowRoot) return null;'
                'u.scrollIntoView({block:"center"});'
                "var b=u.shadowRoot.querySelector('#select-file')||u.shadowRoot.querySelector('button');"
                'if(!b) return null;'
                'var r=b.getBoundingClientRect();'
                'return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)};'
            )
            if not isinstance(box, dict):
                return _done({**out, 'reason': 'upload widget (kat-file-upload) not found on the page'})
            # The visible input is a decoy: the trusted click opens the (suppressed)
            # chooser and Chrome names the REAL input.
            await page.click(box['x'], box['y'])
            node = await chooser.wait(6.0)
            if not node:
                return _done({**out, 'reason': 'file chooser never opened (the click missed?)'})
            await page.send('DOM.setFileInputFiles', backendNodeId=node, files=[f])
        await asyncio.sleep(params.introspect_wait_s)
        state = await page.js(
            'var t=document.body.innerText;'
            'return {detected:/automatically detected/i.test(t),'
            'region:/different region|MARKETPLACES_DIFFERENT/i.test(t),'
            'notup:/file not uploaded/i.test(t)};'
        ) or {}
        out['staged'] = not state.get('notup')
        out['detected'] = bool(state.get('detected'))
        out['region_error'] = bool(state.get('region'))
        if out['region_error']:
            return _done({**out, 'reason': 'template region-stamp mismatch: download the template again '
                                           'with THIS marketplace ticked (amazon_download_template)'})
        if not out['detected']:
            return _done({**out, 'reason': 'file staged but its type was not detected -- read the '
                                           'upload widget error on the page',
                          'page_text': await page.body_text()})
        ref = None
        for _ in range(2):  # some flows need a second Submit click
            sb = await page.js(
                "var els=[...document.querySelectorAll('kat-button,button')];"
                'var b=els.find(function(e){return /submit products/i'
                ".test(e.innerText||e.getAttribute('label')||'');});"
                'if(!b) return null;'
                'b.scrollIntoView({block:"center"});'
                'var r=b.getBoundingClientRect();'
                'return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)};'
            )
            if isinstance(sb, dict):
                await page.click(sb['x'], sb['y'])
                await asyncio.sleep(8)
            ref = await page.js('return (location.href.match(/reference_id=(\\d+)/)||[])[1]||null')
            if ref:
                break
        out['batch_id'] = ref
        out['ok'] = bool(ref)
        if not ref:
            out['reason'] = 'Submit clicked but no reference_id in the URL'
        return _done(out)
    except Exception as exc:
        logger.warning(f"[amazon_listing] upload_flatfile: {exc}")
        return _done({**out, 'reason': f'{type(exc).__name__}: {exc}'})
    finally:
        if page is not None:
            await page.reset_viewport()


@custom_controller.action(
    "Amazon Seller Central: find ONE upload batch on Check Upload Status and download its "
    "Processing Summary report. Returns the batch's status row and the report path for "
    "amazon_parse_feedback. No report yet means it is still processing -- wait and retry.",
    param_model=AmazonFetchReportAction)
async def amazon_fetch_report(params: AmazonFetchReportAction,
                              browser_session: BrowserSession) -> ActionResult:
    batch = params.batch_id.strip()
    out = {'ok': False, 'batch_id': batch, 'row': None, 'report': None}
    dl = downloads_dir(browser_session, params.downloads_dir)
    if not dl:
        return _done({**out, 'reason': 'no downloads directory: pass downloads_dir'})
    try:
        page = await Page.open(browser_session, f'https://{params.host}/listing/status')
        await asyncio.sleep(15)
        row = await page.js(
            WALK + 'let seq=[];'
            'for(const e of w(document)){if(e.children.length===0){'
            'const t=(e.textContent||"").trim(); if(t) seq.push(t);}}'
            f'let i=seq.findIndex(s=>s.includes({_js_str(batch)}));'
            'return i>=0? seq.slice(Math.max(0,i-2), i+4).join(" | ") : null;'
        )
        out['row'] = row
        if not row:
            return _done({**out, 'reason': 'batch id not found on the upload status page'})
        t0 = time.time()
        # From the batch id cell, climb to its row, then find that row's download button.
        btn = await page.js_json(
            WALK + 'let anchor=null;'
            'for(const e of w(document)){const t=(e.textContent||"").trim();'
            f'if(t==={_js_str(batch)}){{anchor=e;break;}}}}'
            'if(!anchor) return "no anchor";'
            'let row=anchor;'
            'for(let i=0;i<14&&row;i++){const tg=row.tagName||"";'
            'if(/ROW|TR/.test(tg))break;'
            'row=row.parentElement||(row.getRootNode&&row.getRootNode().host);}'
            'const scope=row||document;'
            'for(const b of w(scope)){'
            'const bt=(b.innerText||(b.getAttribute&&b.getAttribute("label"))||"").trim();'
            'if(/download processing summary/i.test(bt)){'
            'const r=b.getBoundingClientRect();'
            'if(r.width) return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)});}}'
            'return "no dl button";'
        )
        if not isinstance(btn, dict):
            return _done({**out, 'reason': f'no Download Processing Summary for this batch yet '
                                           f'(still processing?) -- row: {row}'})
        await page.click(btn['x'], btn['y'])  # the kat-button ignores a JS .click()
        report = None
        for _ in range(20):
            await asyncio.sleep(1)
            report = newest(dl, ('.xlsm',), t0)
            if report:
                break
        out['report'] = report
        out['ok'] = bool(report)
        if not report:
            out['reason'] = f'download clicked but no new .xlsm appeared in {dl}'
        return _done(out)
    except Exception as exc:
        logger.warning(f"[amazon_listing] fetch_report: {exc}")
        return _done({**out, 'reason': f'{type(exc).__name__}: {exc}'})

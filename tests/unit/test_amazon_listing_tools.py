"""Amazon listing: the MCP tools over the flat-file engine, and the Seller Central
browser actions driven against a fake CDP session."""

import asyncio
import json
import os
from types import SimpleNamespace

import pytest

pytest.importorskip('openpyxl')

from agent.mcp.server.integrations import amazon_listing_tools as tools
from agent.ec_skills.browser_use_extension.hooks.external.amazon_listing import site_tools
from tests.unit.test_amazon_flatfile_engine import _make_mkt_template, _make_template


def _call(fn, **inp):
    res = asyncio.run(fn(None, {'input': inp}))
    return json.loads(res[0].text)


@pytest.fixture
def template(tmp_path):
    p = tmp_path / 'template.xlsx'
    _make_template(str(p))
    return str(p)


# --- MCP tools ---------------------------------------------------------------

def test_inspect_reports_required_fields_and_caps_value_lists(template):
    out = _call(tools.amazon_template_inspect, template_path=template, max_values=1)
    assert out['ok'] and out['required']
    lists = [v for v in out['required'].values() if v]
    assert lists and all(len(v) <= 2 for v in lists), 'one value + the "... more" marker'
    assert any(str(v[-1]).startswith('... (') for v in lists)


def test_fill_writes_the_txt_to_upload(template, tmp_path):
    spec = {'product_type': 'socks', 'brand': 'ACME',
            'rows': [{'sku': 'W-1', 'operation': 'create', 'fields': {'item_name': 'ACME Thing'}}]}
    out = _call(tools.amazon_template_fill, template_path=template, spec=json.dumps(spec),
                out_path=str(tmp_path / 'out.xlsx'))
    assert out['ok'] and out['rows'] == 1
    assert out['upload_file'].endswith('.txt') and os.path.isfile(out['upload_file'])


def test_fill_turns_the_engines_hard_stop_into_an_error(tmp_path):
    p = tmp_path / 'mkt.xlsx'
    _make_mkt_template(str(p))
    spec = {'marketplace': 'EG', 'product_type': 'socks',
            'rows': [{'sku': 'K', 'parentage': 'Child', 'fields': {'item_name': 'x'}}]}
    out = _call(tools.amazon_template_fill, template_path=str(p), spec=spec)
    assert out['ok'] is False and 'region-stamped' in out['error']


def test_missing_files_and_empty_specs_are_errors_not_exceptions(template):
    assert _call(tools.amazon_template_inspect, template_path='nope.xlsm')['ok'] is False
    assert 'rows' in _call(tools.amazon_template_fill, template_path=template, spec={})['error']


def test_parse_feedback_gives_errors_and_a_verdict(tmp_path):
    report = tmp_path / 'report.txt'
    report.write_text('original-record-number\tsku\terror-type\terror-code\terror-message\n'
                      '4\tW-1\tError\t8541\tMissing required field external_product_id\n',
                      encoding='utf-8')
    out = _call(tools.amazon_parse_feedback, report_path=str(report), batch_id='42')
    assert out['ok'] and out['done'] is False and out['errors'] == 1
    assert out['verdict']['batch_id'] == '42'
    assert 'fix exactly the fields' in out['next']


def test_the_tools_are_registered_desktop_only():
    from agent.mcp.server.server import tool_function_mapping
    schemas = []
    tools.add_amazon_listing_tool_schemas(schemas)
    for s in schemas:
        assert s.name in tool_function_mapping
        assert s.meta == {'run_in_cloud': False}


# --- browser actions (fake CDP) ---------------------------------------------

class _Registry:
    def __init__(self):
        self._handlers = {}

    def register(self, method, fn):
        self._handlers[method] = fn

    def unregister(self, method):
        self._handlers.pop(method, None)


class FakeBrowser:
    """A browser whose page answers Runtime.evaluate through ``answer(expression)``
    and runs ``on_click(x, y)`` for every trusted click."""

    def __init__(self, downloads, answer, on_click=None):
        self.calls, self.urls = [], []
        self.answer, self.on_click = answer, on_click or (lambda x, y: None)
        self.registry = _Registry()
        client = SimpleNamespace(send=_Send(self), _event_registry=self.registry)
        self.cdp = SimpleNamespace(cdp_client=client, session_id='S1', target_id='T1')
        self.session = SimpleNamespace(navigate_to=self._navigate, get_or_create_cdp_session=self._cdp,
                                       browser_profile=SimpleNamespace(downloads_path=str(downloads)))

    async def _navigate(self, url, new_tab=False):
        self.urls.append(url)

    async def _cdp(self, target_id=None, focus=True):
        return self.cdp

    async def dispatch(self, method, params):
        self.calls.append((method, params or {}))
        if method == 'Runtime.evaluate':
            return {'result': {'value': self.answer(params['expression'])}}
        if method == 'Input.dispatchMouseEvent' and params['type'] == 'mousePressed':
            self.on_click(params['x'], params['y'])
        return {}

    def sent(self, method):
        return [p for m, p in self.calls if m == method]


class _Send:
    def __init__(self, browser):
        self._b = browser

    def __getattr__(self, domain):
        b = self._b

        class _Domain:
            def __getattr__(self, name):
                async def call(params=None, session_id=None):
                    return await b.dispatch(f'{domain}.{name}', params)
                return call
        return _Domain()


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    real = asyncio.sleep

    async def fast(*_a, **_k):
        await real(0)
    monkeypatch.setattr(asyncio, 'sleep', fast)


def _download(path):
    """A file landing in the downloads dir (dated ahead: Windows mtimes can trail time.time())."""
    path.write_text('x')
    t = path.stat().st_mtime + 5
    os.utime(path, (t, t))


def _run_action(fn, browser, **params):
    model = {site_tools.amazon_upload_flatfile: site_tools.AmazonUploadFlatfileAction,
             site_tools.amazon_download_template: site_tools.AmazonDownloadTemplateAction,
             site_tools.amazon_fetch_report: site_tools.AmazonFetchReportAction}[fn]
    res = asyncio.run(fn(params=model(**params), browser_session=browser.session))
    return json.loads(res.extracted_content or res.error), res


def _upload_page(detected=True, region=False, ref='1234567'):
    state = {'submitted': False}

    def answer(expr):
        if "querySelector('kat-file-upload')" in expr:
            return {'x': 100, 'y': 200}
        if 'automatically detected' in expr:
            return {'detected': detected, 'region': region, 'notup': False}
        if 'submit products' in expr:
            return {'x': 300, 'y': 900}
        if 'reference_id' in expr:
            return ref if state['submitted'] else None
        return None
    return answer, state


def test_upload_stages_the_file_through_the_real_input_and_returns_the_batch(tmp_path):
    f = tmp_path / 'listing.txt'
    f.write_text('x')
    answer, state = _upload_page()
    b = FakeBrowser(tmp_path, answer)

    def on_click(x, y):
        if (x, y) == (100, 200):  # the decoy button -> Chrome names the real input
            b.registry._handlers['Page.fileChooserOpened']({'backendNodeId': 77}, 'S1')
        if (x, y) == (300, 900):
            state['submitted'] = True
    b.on_click = on_click
    prev = lambda p, s: None
    b.registry.register('Page.fileChooserOpened', prev)

    out, res = _run_action(site_tools.amazon_upload_flatfile, b, host='sellercentral.amazon.com',
                           file_path=str(f))
    assert out['ok'] and out['batch_id'] == '1234567' and res.error is None
    assert b.urls == ['https://sellercentral.amazon.com/product-search/bulk']
    assert b.sent('DOM.setFileInputFiles') == [{'backendNodeId': 77, 'files': [str(f)]}]
    assert [p['enabled'] for p in b.sent('Page.setInterceptFileChooserDialog')] == [True, False]
    assert b.registry._handlers['Page.fileChooserOpened'] is prev, 'the page\'s own handler is restored'


def test_upload_refuses_the_excel_file(tmp_path):
    f = tmp_path / 'listing.xlsm'
    f.write_text('x')
    b = FakeBrowser(tmp_path, lambda e: None)
    out, res = _run_action(site_tools.amazon_upload_flatfile, b, host='h', file_path=str(f))
    assert out['ok'] is False and '.txt' in out['reason'] and not b.calls


def test_upload_reports_a_region_stamp_mismatch_without_submitting(tmp_path):
    f = tmp_path / 'listing.txt'
    f.write_text('x')
    answer, _ = _upload_page(region=True)
    b = FakeBrowser(tmp_path, answer)
    b.on_click = lambda x, y: b.registry._handlers['Page.fileChooserOpened']({'backendNodeId': 5}, 'S1')
    out, _ = _run_action(site_tools.amazon_upload_flatfile, b, host='h', file_path=str(f))
    assert out['region_error'] and not out['ok'] and 'amazon_download_template' in out['reason']
    assert 'Page.fileChooserOpened' not in b.registry._handlers


def test_download_template_verifies_the_store_tick_with_a_trusted_retry(tmp_path):
    ticked = {'Amazon.com': False, 'Amazon.ca': True}

    def answer(expr):
        if 'download product spreadsheet' in expr:
            return json.dumps({'x': 10, 'y': 10})
        if 'product keyword' in expr:
            return json.dumps({'x': 20, 'y': 20})
        if '^(select|选择)$' in expr and 'best' in expr:
            return json.dumps({'box': {'x': 30, 'y': 30}, 'label': 'Socks'})
        if 'res.push' in expr:
            return json.dumps([{'label': k, 'on': v, 'x': 40 if k == 'Amazon.com' else 41, 'y': 40}
                               for k, v in ticked.items()])
        if 'stores set' in expr:
            return 'stores set'  # the JS click is ignored, as kat-checkbox often does
        if 'generate spreadsheet' in expr:
            return json.dumps({'x': 50, 'y': 50})
        return None

    def on_click(x, y):
        if (x, y) == (40, 40):
            ticked['Amazon.com'] = True
        if (x, y) == (50, 50):
            _download(tmp_path / 'SOCKS.xlsm')

    b = FakeBrowser(tmp_path, answer, on_click)
    out, _ = _run_action(site_tools.amazon_download_template, b, host='sellercentral.amazon.com',
                         product_type='socks', store_label='amazon.com')
    assert out['ok'] and out['template'].endswith('SOCKS.xlsm')
    assert out['picked'] == 'Socks' and out['stores'] == {'Amazon.com': True, 'Amazon.ca': True}
    assert b.sent('Input.insertText') == [{'text': 'socks'}]
    assert b.sent('Emulation.clearDeviceMetricsOverride'), 'viewport restored'


def test_download_template_refuses_to_generate_for_a_store_it_cannot_tick(tmp_path):
    def answer(expr):
        if 'res.push' in expr:
            return json.dumps([{'label': 'Amazon.com', 'on': False, 'x': 40, 'y': 40}])
        if 'generate spreadsheet' in expr:
            raise AssertionError('must not generate')
        if 'best' in expr:
            return json.dumps({'box': {'x': 30, 'y': 30}, 'label': 'Socks'})
        return json.dumps({'x': 1, 'y': 1})

    b = FakeBrowser(tmp_path, answer)
    out, res = _run_action(site_tools.amazon_download_template, b, host='h',
                           product_type='socks', store_label='Amazon.com')
    assert not out['ok'] and 'NOT ticked' in out['reason'] and res.error


def test_fetch_report_downloads_the_batchs_processing_summary(tmp_path):
    def answer(expr):
        if 'seq.push' in expr:
            return 'Done | 1234567 | 1 error'
        if 'download processing summary' in expr:
            return json.dumps({'x': 60, 'y': 60})
        return None

    b = FakeBrowser(tmp_path, answer,
                    lambda x, y: _download(tmp_path / 'report.xlsm'))
    out, _ = _run_action(site_tools.amazon_fetch_report, b, host='h', batch_id='1234567')
    assert out['ok'] and out['report'].endswith('report.xlsm') and '1234567' in out['row']


def test_fetch_report_says_still_processing_when_no_download_yet(tmp_path):
    def answer(expr):
        if 'seq.push' in expr:
            return 'In progress | 1234567'
        return 'no dl button'

    out, _ = _run_action(site_tools.amazon_fetch_report, FakeBrowser(tmp_path, answer),
                         host='h', batch_id='1234567')
    assert not out['ok'] and 'still processing' in out['reason']

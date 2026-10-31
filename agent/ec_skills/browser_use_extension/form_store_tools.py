"""Browser actions for a page's own form data: find it, read it, write it, undo it.

Seller back offices keep what a form holds in a form store, not in the inputs on
screen (virtual tables draw a few rows, editors open sub-forms). Explorers were
told the technique in words and had to hand-write DOM-walking code each step;
they found the data but fumbled the code (KEN 2026-10-30: 3 size-chart
explorations, no recipe). These actions are that code, tested once:

- ``probe_page_data(text)``: the form stores behind the element showing *text*
  and the keys their data has.
- ``read_form_field(key)``: a field's whole value (``a/b`` paths), safely.
- ``write_form_field(key, value_json)``: set it, read it back, keep the old value.
- ``revert_form_field(key)``: put the old value back.

Works on React pages whose form fields carry ``root``/``setValue``/``address``
(zform/formily-style) and on antd-style forms (``getFieldValue``/``setFieldsValue``).
Nothing here is specific to a site.
"""

import json

from browser_use import BrowserSession
from browser_use.agent.views import ActionResult
from typing import Any

from pydantic import BaseModel, Field

from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller

from agent.ec_skills.experience.page_data import HELPERS as _HELPERS


def _probe_js(text: str) -> str:
    return "(async()=>{" + _HELPERS + """
const T = %s;
const el = [...document.querySelectorAll('input,textarea,button,label,span,td,th,div,a')]
  .find(e => e.children.length < 4 && ((e.innerText || '') + (e.placeholder || '')).includes(T));
const near = el ? stores(el) : [];
const found = (near.length ? near : stores(null)).map(s => s.kind === 'path'
  ? { kind: 'path-addressed fields', depth: s.depth, keys: Object.keys(valOf(s.root) || {}).slice(0, 120) }
  : { kind: 'named fields', depth: s.depth, keys: Object.keys(namesOf(s.form)).slice(0, 120) });
return safe({ near: el ? el.tagName + (near.length ? '' : ' (no store on its chain: searched the whole form)') : 'no element with that text: searched the whole form', stores: found }, 8000);
})()""" % json.dumps(text)


def _read_js(key: str) -> str:
    return "(async()=>{" + _HELPERS + """
const loc = locate(%s);
return loc ? safe({ key: %s, value: loc.get() }, 8000) : 'no field ' + %s + ' (probe_page_data lists the keys)';
})()""" % (json.dumps(key), json.dumps(key), json.dumps(key))


def _write_js(key: str, value) -> str:
    return "(async()=>{" + _HELPERS + """
const key = %s, want = %s;
const loc = locate(key);
if (!loc) return 'no field ' + key + ' (probe_page_data lists the keys)';
if (!(key in window.__ecanFieldBackup)) window.__ecanFieldBackup[key] = JSON.parse(safe(loc.get(), 1e7));
await loc.set(want);
await new Promise(r => setTimeout(r, 600));
const got = loc.get();
return safe({ key, same_as_written: safe(got, 1e7) === safe(want, 1e7), now: got }, 6000);
})()""" % (json.dumps(key), json.dumps(value, ensure_ascii=False))


def _revert_js(key: str) -> str:
    return "(async()=>{" + _HELPERS + """
const key = %s;
if (!(key in window.__ecanFieldBackup)) return 'nothing written to ' + key + ' yet';
const loc = locate(key);
if (!loc) return 'no field ' + key;
await loc.set(window.__ecanFieldBackup[key]);
delete window.__ecanFieldBackup[key];
return 'reverted ' + key;
})()""" % json.dumps(key)


async def _run(browser_session: BrowserSession, js: str) -> str:
    cdp = await browser_session.get_or_create_cdp_session(focus=False)
    r = await cdp.cdp_client.send.Runtime.evaluate(
        params={"expression": js, "returnByValue": True, "awaitPromise": True}, session_id=cdp.session_id)
    if r.get("exceptionDetails"):
        return "page error: " + str((r["exceptionDetails"].get("exception") or {}).get("description") or r["exceptionDetails"])[:500]
    return str((r.get("result") or {}).get("value"))


class ProbePageDataAction(BaseModel):
    text: str = Field(description="Text shown next to the part of the page (a label, a column title, a value)")


class FormFieldAction(BaseModel):
    key: str = Field(description="A key from probe_page_data; a/b for a field inside another")


class WriteFormFieldAction(BaseModel):
    key: str = Field(description="A key from probe_page_data; a/b for a field inside another")
    # A JSON value, not a JSON string: writing JSON inside a string, Opus mixed escaped
    # and plain quotes and all 5 of its writes were rejected (KEN 2026-10-30).
    value: Any = Field(description="The field's whole new value (an object, list, string or number), "
                                   "same shape as read_form_field returned -- not a JSON string")


def _as_value(value: Any) -> Any:
    """A value given as JSON text is parsed, repairing quotes escaped once too often."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    for attempt in (text, text.replace('\\"', '"'), text.replace('\\\\', '\\')):
        try:
            return json.loads(attempt)
        except Exception:
            continue
    raise ValueError("value is neither JSON nor plain text")


@custom_controller.action(
    "Find the page's own form data behind the element showing this text: lists the form stores and the "
    "keys of their data. Use it before reading or writing form data; read only.",
    param_model=ProbePageDataAction,
)
async def probe_page_data(params: ProbePageDataAction, browser_session: BrowserSession) -> ActionResult:
    return ActionResult(extracted_content=await _run(browser_session, _probe_js(params.text)))


@custom_controller.action(
    "Read one field of the page's form data (whole value, as JSON). Read only.",
    param_model=FormFieldAction,
)
async def read_form_field(params: FormFieldAction, browser_session: BrowserSession) -> ActionResult:
    return ActionResult(extracted_content=await _run(browser_session, _read_js(params.key)))


@custom_controller.action(
    "Write one field of the page's form data with its whole new value (same shape as read_form_field), "
    "then read it back; the old value is kept for revert_form_field. Does not save or submit the page.",
    param_model=WriteFormFieldAction,
)
async def write_form_field(params: WriteFormFieldAction, browser_session: BrowserSession) -> ActionResult:
    try:
        value = _as_value(params.value)
    except Exception as exc:
        return ActionResult(error=f"write_form_field: {exc}; pass the value itself (an object or list), not a string")
    return ActionResult(extracted_content=await _run(browser_session, _write_js(params.key, value)))


@custom_controller.action(
    "Put back the value a field had before write_form_field changed it.",
    param_model=FormFieldAction,
)
async def revert_form_field(params: FormFieldAction, browser_session: BrowserSession) -> ActionResult:
    return ActionResult(extracted_content=await _run(browser_session, _revert_js(params.key)))

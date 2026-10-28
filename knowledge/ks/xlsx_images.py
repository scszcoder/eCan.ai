"""Pictures embedded in a merchant's product .xlsx, per row.

Merchants paste product photos straight into their sheets; ``openpyxl`` (read-only)
only returns cell values, so those photos were silently lost on import. This
reads the workbook's zip parts directly (stdlib only) and returns, for one sheet,
``{row number: [(image bytes, ext), ...]}`` in left-to-right column order. Row
numbers match ``catalog_import`` (header row = 1, first data row = 2).

Three ways a picture can sit in a sheet:

1. WPS / Kingsoft 嵌入单元格: the cell holds ``=DISPIMG("ID_…",1)``;
   ``xl/cellimages.xml`` names the picture and points at its media file.
2. Excel 365 "Place in Cell": the cell carries ``vm="N"`` (value metadata) ->
   ``xl/metadata.xml`` -> ``xl/richData/rdrichvalue.xml`` -> ``richValueRel.xml``
   -> media file.
3. Floating pictures: the sheet's drawing anchors each picture at a cell; the
   picture goes to the anchor's top row.

Never raises on a malformed file: what was found is returned and a warning logged.
"""
from __future__ import annotations

import posixpath
import re
import zipfile
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from utils.logger_helper import logger_helper as logger

MAX_IMAGE_BYTES = 15 * 1024 * 1024
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff"}

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_DISPIMG = re.compile(r"DISPIMG\(\s*\"([^\"]+)\"", re.I)
_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _rattr(el: ET.Element, name: str) -> str:
    """An r:-namespaced attribute (r:id, r:embed), whatever the prefix."""
    return el.get(f"{{{_R_NS}}}{name}") or ""


def _resolve(base_part: str, target: str) -> str:
    """Zip path of a relationship target, relative to *base_part*'s folder."""
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_part), target))


def _rels_path(part: str) -> str:
    d, f = posixpath.split(part)
    return posixpath.join(d, "_rels", f + ".rels")


def _read_rels(z: zipfile.ZipFile, part: str) -> Dict[str, Tuple[str, str]]:
    """{rId: (resolved target, type)} for *part*; {} when it has none."""
    path = _rels_path(part)
    if path not in z.namelist():
        return {}
    out = {}
    for el in ET.fromstring(z.read(path)).iter():
        if _local(el.tag) == "Relationship" and el.get("Id") and el.get("Target"):
            if el.get("TargetMode") == "External":
                continue
            out[el.get("Id")] = (_resolve(part, el.get("Target")), el.get("Type", ""))
    return out


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def _sheet_part(z: zipfile.ZipFile, sheet_name: Optional[str]) -> Optional[str]:
    wb_part = "xl/workbook.xml"
    rels = _read_rels(z, wb_part)
    sheets = []
    for el in ET.fromstring(z.read(wb_part)).iter():
        if _local(el.tag) == "sheet":
            target = rels.get(_rattr(el, "id"), ("", ""))[0]
            if target:
                sheets.append((el.get("name", ""), target))
    if not sheets:
        return None
    if sheet_name is None:
        from knowledge.ks.catalog_import import PRODUCT_SHEET
        sheet_name = PRODUCT_SHEET if any(n == PRODUCT_SHEET for n, _ in sheets) else sheets[0][0]
    return next((t for n, t in sheets if n == sheet_name), None)


def _media(z: zipfile.ZipFile, path: str) -> Optional[Tuple[bytes, str]]:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext not in IMAGE_EXTS:
        return None
    try:
        if z.getinfo(path).file_size > MAX_IMAGE_BYTES:
            return None
        return z.read(path), ("jpg" if ext == "jpeg" else ext)
    except KeyError:
        return None


def _scan_cells(z: zipfile.ZipFile, sheet: str):
    """[(row, col, 'dispimg', image id) | (row, col, 'vm', vm index)] from the sheet XML."""
    found = []
    with z.open(sheet) as fh:
        cell = None
        for event, el in ET.iterparse(fh, events=("start", "end")):
            name = _local(el.tag)
            if event == "start" and name == "c":
                cell = el
                continue
            if event != "end":
                continue
            if name == "f" and cell is not None and el.text and "DISPIMG" in el.text.upper():
                m = _DISPIMG.search(el.text)
                ref = _CELL_REF.match(cell.get("r", ""))
                if m and ref:
                    found.append((int(ref.group(2)), _col_index(ref.group(1)), "dispimg", m.group(1)))
            elif name == "c":
                vm = el.get("vm")
                ref = _CELL_REF.match(el.get("r", ""))
                if vm and ref and vm.isdigit():
                    found.append((int(ref.group(2)), _col_index(ref.group(1)), "vm", int(vm)))
                cell = None
                el.clear()
    return found


def _wps_images(z: zipfile.ZipFile) -> Dict[str, str]:
    """WPS cellimages.xml: {picture name (ID_…): media path}."""
    part = "xl/cellimages.xml"
    if part not in z.namelist():
        return {}
    rels = _read_rels(z, part)
    out = {}
    for pic in ET.fromstring(z.read(part)).iter():
        if _local(pic.tag) != "pic":
            continue
        name = embed = ""
        for el in pic.iter():
            t = _local(el.tag)
            if t == "cNvPr" and not name:
                name = el.get("name", "")
            elif t == "blip" and not embed:
                embed = _rattr(el, "embed")
        if name and embed in rels:
            out[name] = rels[embed][0]
    return out


def _rich_value_images(z: zipfile.ZipFile) -> Dict[int, str]:
    """Excel picture-in-cell: {vm index (1-based): media path}."""
    names = set(z.namelist())
    if "xl/metadata.xml" not in names or "xl/richData/rdrichvalue.xml" not in names:
        return {}
    meta = ET.fromstring(z.read("xl/metadata.xml"))
    # metadataTypes (1-based) -> name; futureMetadata name -> [rich value index per bk]
    types = [el.get("name", "") for el in meta.iter() if _local(el.tag) == "metadataType"]
    future: Dict[str, List[Optional[int]]] = {}
    value_bks: List[Tuple[int, int]] = []
    for el in meta:
        t = _local(el.tag)
        if t == "futureMetadata":
            idxs = []
            for bk in el:
                if _local(bk.tag) != "bk":
                    continue
                rvb = next((x for x in bk.iter() if _local(x.tag) == "rvb"), None)
                idxs.append(int(rvb.get("i")) if rvb is not None and (rvb.get("i") or "").isdigit() else None)
            future[el.get("name", "")] = idxs
        elif t == "valueMetadata":
            for bk in el:
                rc = next((x for x in bk.iter() if _local(x.tag) == "rc"), None)
                if rc is not None and (rc.get("t") or "").isdigit() and (rc.get("v") or "").isdigit():
                    value_bks.append((int(rc.get("t")), int(rc.get("v"))))
                else:
                    value_bks.append((0, -1))
    # rich value structures: position of the image-relationship key in each structure
    rel_pos: List[int] = []
    if "xl/richData/rdrichvaluestructure.xml" in names:
        for s in ET.fromstring(z.read("xl/richData/rdrichvaluestructure.xml")):
            if _local(s.tag) != "s":
                continue
            keys = [k.get("n", "") for k in s if _local(k.tag) == "k"]
            rel_pos.append(next((i for i, k in enumerate(keys) if k == "_rvRel:LocalImageIdentifier"), 0))
    rich_rel_idx: List[Optional[int]] = []
    for rv in ET.fromstring(z.read("xl/richData/rdrichvalue.xml")):
        if _local(rv.tag) != "rv":
            continue
        vals = [v.text for v in rv if _local(v.tag) == "v"]
        s = int(rv.get("s", "0")) if (rv.get("s") or "0").isdigit() else 0
        pos = rel_pos[s] if s < len(rel_pos) else 0
        txt = vals[pos] if pos < len(vals) else None
        rich_rel_idx.append(int(txt) if txt and txt.strip().isdigit() else None)
    rel_part = "xl/richData/richValueRel.xml"
    rel_ids: List[str] = []
    if rel_part in names:
        rel_ids = [_rattr(el, "id") for el in ET.fromstring(z.read(rel_part)) if _local(el.tag) == "rel"]
    rels = _read_rels(z, rel_part) if rel_part in names else {}
    out: Dict[int, str] = {}
    for vm, (t, v) in enumerate(value_bks, start=1):
        tname = types[t - 1] if 0 < t <= len(types) else ""
        rv_list = future.get(tname) or future.get("XLRICHVALUE") or []
        if not (0 <= v < len(rv_list)) or rv_list[v] is None:
            continue
        rv_i = rv_list[v]
        if not (0 <= rv_i < len(rich_rel_idx)) or rich_rel_idx[rv_i] is None:
            continue
        rel_i = rich_rel_idx[rv_i]
        if 0 <= rel_i < len(rel_ids) and rel_ids[rel_i] in rels:
            out[vm] = rels[rel_ids[rel_i]][0]
    return out


def _drawing_images(z: zipfile.ZipFile, sheet: str):
    """Floating pictures: [(row, col, media path)] from the sheet's drawings."""
    found = []
    for target, typ in _read_rels(z, sheet).values():
        if not typ.endswith("/drawing") or target not in z.namelist():
            continue
        rels = _read_rels(z, target)
        for anchor in ET.fromstring(z.read(target)):
            if _local(anchor.tag) not in ("twoCellAnchor", "oneCellAnchor"):
                continue
            frm = next((x for x in anchor if _local(x.tag) == "from"), None)
            if frm is None:
                continue
            row = col = None
            for x in frm:
                if _local(x.tag) == "row" and (x.text or "").strip().isdigit():
                    row = int(x.text.strip())
                elif _local(x.tag) == "col" and (x.text or "").strip().isdigit():
                    col = int(x.text.strip())
            blip = next((x for x in anchor.iter() if _local(x.tag) == "blip"), None)
            embed = _rattr(blip, "embed") if blip is not None else ""
            if row is not None and embed in rels:
                found.append((row + 1, (col or 0) + 1, rels[embed][0]))
    return found


def extract_row_images(path: str, sheet_name: Optional[str] = None) -> Dict[int, List[Tuple[bytes, str]]]:
    """{row number: [(image bytes, ext), ...]} for one sheet, left to right."""
    placed: List[Tuple[int, int, str]] = []
    try:
        with zipfile.ZipFile(path) as z:
            sheet = _sheet_part(z, sheet_name)
            if not sheet or sheet not in z.namelist():
                return {}
            for step in ("cells", "drawings"):
                try:
                    if step == "cells":
                        cells = _scan_cells(z, sheet)
                        wps = _wps_images(z) if any(k == "dispimg" for _, _, k, _ in cells) else {}
                        rich = _rich_value_images(z) if any(k == "vm" for _, _, k, _ in cells) else {}
                        for row, col, kind, key in cells:
                            media = wps.get(key) if kind == "dispimg" else rich.get(key)
                            if media:
                                placed.append((row, col, media))
                    else:
                        placed.extend(_drawing_images(z, sheet))
                except Exception as exc:          # one malformed part must not lose the rest
                    logger.warning(f"[xlsx_images] {step} of {path}: {type(exc).__name__}: {exc}")
            out: Dict[int, List[Tuple[bytes, str]]] = {}
            for row, col, media in sorted(placed, key=lambda p: (p[0], p[1])):
                img = _media(z, media)
                if img:
                    out.setdefault(row, []).append(img)
            return out
    except Exception as exc:
        logger.warning(f"[xlsx_images] could not read pictures from {path}: {type(exc).__name__}: {exc}")
        return {}

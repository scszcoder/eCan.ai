"""Pictures pasted into a product .xlsx are found per row (WPS 嵌入单元格,
Excel "Place in Cell", floating pictures)."""
import io
import zipfile

import pytest

from knowledge.ks import catalog_import
from knowledge.ks.xlsx_images import extract_row_images


def _png(color=(255, 0, 0)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, "PNG")
    return buf.getvalue()


RED, GREEN, BLUE = _png((255, 0, 0)), _png((0, 255, 0)), _png((0, 0, 255))

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL_SHEET = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
_REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"


def _rels(rels):
    body = "".join(f'<Relationship Id="{i}" Type="{t}" Target="{tg}"/>' for i, t, tg in rels)
    return ('<?xml version="1.0" encoding="UTF-8"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + body + "</Relationships>")


def _workbook(path, sheet_xml, extra_parts, sheet_name="商品"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml",
                   f'<?xml version="1.0"?><workbook xmlns="{_NS_MAIN}" xmlns:r="{_NS_R}"><sheets>'
                   f'<sheet name="说明" sheetId="1" r:id="rId9"/><sheet name="{sheet_name}" sheetId="2" r:id="rId1"/>'
                   '</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   _rels([("rId1", _REL_SHEET, "worksheets/sheet2.xml"), ("rId9", _REL_SHEET, "worksheets/sheet1.xml")]))
        z.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0"?><worksheet xmlns="{_NS_MAIN}"><sheetData/></worksheet>')
        z.writestr("xl/worksheets/sheet2.xml", sheet_xml)
        for name, data in extra_parts.items():
            z.writestr(name, data)


def _sheet(cells):
    rows = {}
    for ref, inner, attrs in cells:
        rows.setdefault(int("".join(c for c in ref if c.isdigit())), []).append(f'<c r="{ref}"{attrs}>{inner}</c>')
    body = "".join(f'<row r="{r}">{"".join(cs)}</row>' for r, cs in sorted(rows.items()))
    return f'<?xml version="1.0"?><worksheet xmlns="{_NS_MAIN}"><sheetData>{body}</sheetData></worksheet>'


def test_wps_dispimg_pictures_map_to_their_rows_left_to_right(tmp_path):
    p = tmp_path / "wps.xlsx"
    sheet = _sheet([("A1", '<is><t>标题</t></is>', ' t="inlineStr"'),
                    ("C2", '<f>_xlfn.DISPIMG("ID_B",1)</f><v>=DISPIMG("ID_B",1)</v>', ' t="str"'),
                    ("B2", '<f>DISPIMG("ID_A",1)</f>', ' t="str"'),
                    ("B4", '<f>DISPIMG("ID_C",1)</f>', ' t="str"')])
    pic = lambda name, rid: (f'<etc:cellImage><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="{name}"/></xdr:nvPicPr>'
                             f'<xdr:blipFill><a:blip r:embed="{rid}"/></xdr:blipFill></xdr:pic></etc:cellImage>')
    cellimages = ('<?xml version="1.0"?><etc:cellImages xmlns:etc="http://www.wps.cn/officeDocument/2017/etCustomData" '
                  'xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                  'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                  f'xmlns:r="{_NS_R}">' + pic("ID_A", "rId1") + pic("ID_B", "rId2") + pic("ID_C", "rId3") + "</etc:cellImages>")
    _workbook(p, sheet, {
        "xl/cellimages.xml": cellimages,
        "xl/_rels/cellimages.xml.rels": _rels([("rId1", _REL_IMAGE, "media/image1.png"),
                                               ("rId2", _REL_IMAGE, "media/image2.jpeg"),
                                               ("rId3", _REL_IMAGE, "media/image3.png")]),
        "xl/media/image1.png": RED, "xl/media/image2.jpeg": GREEN, "xl/media/image3.png": BLUE})
    out = extract_row_images(str(p))
    assert sorted(out) == [2, 4]
    assert [b for b, _ in out[2]] == [RED, GREEN] and [e for _, e in out[2]] == ["png", "jpg"]
    assert out[4] == [(BLUE, "png")]


def test_excel_place_in_cell_pictures_map_to_their_rows(tmp_path):
    p = tmp_path / "rich.xlsx"
    sheet = _sheet([("D3", "<v>#VALUE!</v>", ' t="e" vm="2"'), ("C3", "<v>#VALUE!</v>", ' t="e" vm="1"')])
    metadata = ('<?xml version="1.0"?><metadata xmlns="' + _NS_MAIN + '" '
                'xmlns:xlrd="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata">'
                '<metadataTypes count="1"><metadataType name="XLRICHVALUE"/></metadataTypes>'
                '<futureMetadata name="XLRICHVALUE" count="2">'
                '<bk><extLst><ext><xlrd:rvb i="0"/></ext></extLst></bk>'
                '<bk><extLst><ext><xlrd:rvb i="1"/></ext></extLst></bk></futureMetadata>'
                '<valueMetadata count="2"><bk><rc t="1" v="0"/></bk><bk><rc t="1" v="1"/></bk></valueMetadata></metadata>')
    rdrv = ('<?xml version="1.0"?><rvData xmlns="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata">'
            '<rv s="0"><v>0</v><v>5</v></rv><rv s="0"><v>1</v><v>5</v></rv></rvData>')
    struct = ('<?xml version="1.0"?><rvStructures xmlns="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata">'
              '<s t="_localImage"><k n="_rvRel:LocalImageIdentifier" t="i"/><k n="CalcOrigin" t="i"/></s></rvStructures>')
    rvrel = ('<?xml version="1.0"?><richValueRels xmlns="http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel" '
             f'xmlns:r="{_NS_R}"><rel r:id="rId1"/><rel r:id="rId2"/></richValueRels>')
    _workbook(p, sheet, {
        "xl/metadata.xml": metadata, "xl/richData/rdrichvalue.xml": rdrv,
        "xl/richData/rdrichvaluestructure.xml": struct, "xl/richData/richValueRel.xml": rvrel,
        "xl/richData/_rels/richValueRel.xml.rels": _rels([("rId1", _REL_IMAGE, "../media/image1.png"),
                                                           ("rId2", _REL_IMAGE, "../media/image2.png")]),
        "xl/media/image1.png": RED, "xl/media/image2.png": GREEN})
    assert extract_row_images(str(p)) == {3: [(RED, "png"), (GREEN, "png")]}


def test_floating_pictures_go_to_the_anchor_row(tmp_path):
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    wb = Workbook()
    ws = wb.active
    ws.title = "商品"
    ws.append(["编码", "标题", "图片"])
    ws.append(["A1", "红色T恤", ""])
    ws.append(["A2", "绿色T恤", ""])
    for anchor, data in (("C3", GREEN), ("C2", RED), ("D2", BLUE)):
        img = XLImage(io.BytesIO(data))
        img.anchor = anchor
        ws.add_image(img)
    p = tmp_path / "float.xlsx"
    wb.save(p)
    out = extract_row_images(str(p))
    assert sorted(out) == [2, 3]
    assert len(out[2]) == 2 and len(out[3]) == 1
    # column order kept: C2 before D2 (openpyxl re-encodes the pixels, so compare via Pillow)
    from PIL import Image
    color = lambda b: Image.open(io.BytesIO(b)).convert("RGB").getpixel((0, 0))
    assert [color(b) for b, _ in out[2]] == [(255, 0, 0), (0, 0, 255)]
    assert color(out[3][0][0]) == (0, 255, 0)


def test_rows_match_catalog_import_numbering(tmp_path):
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    wb = Workbook()
    ws = wb.active
    ws.title = "商品"
    ws.append(["编码", "标题"])
    ws.append(["A1", "红色T恤"])
    img = XLImage(io.BytesIO(RED))
    img.anchor = "C2"
    ws.add_image(img)
    p = tmp_path / "num.xlsx"
    wb.save(p)
    _, rows = catalog_import.read_table(str(p))
    assert rows[0][catalog_import.ROW_KEY] == 2
    assert list(catalog_import.embedded_images_for(str(p))) == [2]
    assert catalog_import.embedded_images_for(str(tmp_path / "x.csv")) == {}


@pytest.mark.parametrize("parts", [
    {"xl/cellimages.xml": "<not xml", "xl/media/image1.png": RED},     # broken WPS part
    {"xl/_rels/cellimages.xml.rels": _rels([("rId1", _REL_IMAGE, "media/missing.png")])},  # missing media
])
def test_malformed_parts_give_empty_not_an_error(tmp_path, parts):
    p = tmp_path / "bad.xlsx"
    _workbook(p, _sheet([("B2", '<f>DISPIMG("ID_A",1)</f>', ' t="str"')]), parts)
    assert extract_row_images(str(p)) == {}


def test_not_a_zip_gives_empty(tmp_path):
    p = tmp_path / "junk.xlsx"
    p.write_bytes(b"not a workbook")
    assert extract_row_images(str(p)) == {}

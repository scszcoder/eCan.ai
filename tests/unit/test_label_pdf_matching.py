"""Each label PDF is filed under the order printed on it, never paired by download order."""
import os

import pytest

from agent.ec_skills.label_utils.match_pdfs import label_order, match_label_pdfs

LABELS = [{"order_id": "#2002", "tracking_number": "9400 1000 0000 0000 0000 0011 11", "recipient": "Ann Example"},
          {"order_id": "#2001", "tracking_number": "94001000000000000000002222", "recipient": "Bob Sample"}]


def _pdf(path, text, mtime):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(str(path))
    os.utime(path, (mtime, mtime))
    return str(path)


def test_labels_downloaded_in_the_other_order_go_to_their_own_orders(tmp_path):
    # #2002 was bought first but its PDF was saved second (the packing notes got swapped once)
    a = _pdf(tmp_path / "a.pdf", "BOB SAMPLE\n9400 1000 0000 0000 0000 0022 22\nOrder #2001", 1000)
    b = _pdf(tmp_path / "b.pdf", "ANN EXAMPLE\n9400 1000 0000 0000 0000 0011 11\nOrder #2002", 1001)
    found, rest = match_label_pdfs(str(tmp_path), 0, LABELS)
    assert found == {"#2001": a, "#2002": b} and rest == []


def test_a_label_without_an_order_number_matches_by_tracking_or_name():
    assert label_order("USPS TRACKING #\n9400 1000 0000 0000 0000 0011 11", LABELS) == "#2002"
    assert label_order("SHIP TO:\nBOB SAMPLE\n1 MAIN ST", LABELS) == "#2001"
    assert label_order("Order #20011", LABELS) == ""


def test_a_pdf_that_names_no_order_is_left_for_a_person(tmp_path):
    p = _pdf(tmp_path / "c.pdf", "USPS GROUND ADVANTAGE\nRDC 01", 1000)
    assert match_label_pdfs(str(tmp_path), 0, LABELS) == ({}, [p])

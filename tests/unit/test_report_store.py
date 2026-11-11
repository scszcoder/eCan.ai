r"""Run reports land in C:\reports\<category>\<store>\<date>\ and go to the account's
S3 report area through a presigned PUT; an upload that cannot happen yet is
"pending" and never fails the run (2026-10-26, Amazon after-sales reports)."""
import json
from pathlib import Path

import pytest

from agent.ec_skills.reports import report_store as rs


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "reports_root", lambda: tmp_path)
    return tmp_path


def test_files_land_in_the_dated_store_folder(root):
    folder = rs.save_report("amazon", "sc_amazon_0", {"report.md": "# hi", "report.json": {"a": 1}}, "2026-10-26")
    assert folder == root / "amazon" / "sc_amazon_0" / "2026-10-26"
    assert (folder / "report.md").read_text(encoding="utf-8") == "# hi"
    assert json.loads((folder / "report.json").read_text(encoding="utf-8")) == {"a": 1}


@pytest.mark.parametrize("raw, safe", [("../evil", "_evil"), ("a/b\c", "a_b_c"), ("  ", "unnamed"), ("..", "unnamed")])
def test_names_cannot_escape_the_folder(raw, safe):
    assert rs.safe_part(raw) == safe


def test_no_upload_address_is_pending_and_keeps_the_local_copy(root, monkeypatch):
    monkeypatch.setattr(rs, "_request_upload_url", lambda *a: {"error": "FieldUndefined: requestReportUploadUrl"})
    out = rs.save_and_upload("amazon", "s1", {"report.md": "x"}, "2026-10-26")
    assert out["upload"]["status"] == "pending" and "FieldUndefined" in out["upload"]["reason"]
    assert (Path(out["folder"]) / "report.md").exists()
    assert json.loads((Path(out["folder"]) / "upload_status.json").read_text(encoding="utf-8"))["status"] == "pending"


def test_every_file_is_put_to_its_presigned_url(root, monkeypatch):
    import agent.cloud_api.cloud_api as ca
    puts = []
    monkeypatch.setattr(rs, "_request_upload_url",
                        lambda c, s, d, f: {"uploadUrl": f"https://s3/{f}", "s3Key": f"u/{c}/{s}/{d}/{f}"})
    monkeypatch.setattr(ca, "upload_file_to_presigned_url",
                        lambda p, url, content_type=None: puts.append((Path(p).name, url, content_type)) or {"success": True})
    out = rs.save_and_upload("amazon", "s1", {"report.md": "x", "report.json": {}}, "2026-10-26")
    assert out["upload"]["status"] == "uploaded"
    assert sorted(puts) == [("report.json", "https://s3/report.json", "application/json"),
                            ("report.md", "https://s3/report.md", "text/markdown")]

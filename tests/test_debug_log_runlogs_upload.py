"""Request Log Analysis must package the WHOLE runlogs folder, not just eCan.log.

2026-09-07 customer report: the upload contained only eCan.log. Root: the
whole-folder helper `_add_runlogs_dir` existed but `perform_log_analysis_upload`
still did a single `zf.write(log_path, "runlogs/eCan.log")` — the helper was
never wired in. Support needs eCan.wscap.log (and lightrag/memory/runs) too.
"""

import zipfile
from pathlib import Path

import gui.ipc.w2p_handlers.debug_log_handler as dlh


def _make_runlogs(tmp_path: Path) -> Path:
    d = tmp_path / "runlogs"
    (d / "runs").mkdir(parents=True)
    (d / "eCan.log").write_text("main log", encoding="utf-8")
    (d / "eCan.wscap.log").write_text("ws capture", encoding="utf-8")
    (d / "lightrag.log").write_text("rag", encoding="utf-8")
    (d / "runs" / "run1.log").write_text("run", encoding="utf-8")
    (d / "log_20260101-000000.zip").write_text("old upload", encoding="utf-8")  # must be skipped
    return d


def test_add_runlogs_dir_packages_whole_folder(tmp_path):
    runlogs = _make_runlogs(tmp_path)
    zip_path = tmp_path / "out.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        res = dlh._add_runlogs_dir(zf, runlogs, exclude=zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    # every real file present, nested path preserved.
    assert "runlogs/eCan.log" in names
    assert "runlogs/eCan.wscap.log" in names
    assert "runlogs/lightrag.log" in names
    assert "runlogs/runs/run1.log" in names
    # previous upload zip excluded, and it's noted in the manifest.
    assert "runlogs/log_20260101-000000.zip" not in names
    assert "runlogs/_manifest.txt" in names
    assert res["added"] == 4


def test_add_runlogs_dir_respects_size_cap(tmp_path, monkeypatch):
    runlogs = _make_runlogs(tmp_path)
    (runlogs / "huge.bin").write_bytes(b"x" * 5000)
    monkeypatch.setattr(dlh, "MAX_RUNLOG_FILE_BYTES", 1000)  # 5000-byte file too big
    zip_path = tmp_path / "out.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        dlh._add_runlogs_dir(zf, runlogs, exclude=zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        manifest = zf.read("runlogs/_manifest.txt").decode("utf-8")
    assert "runlogs/huge.bin" not in names
    assert "huge.bin" in manifest and "too large" in manifest
    assert "runlogs/eCan.log" in names  # small files still included


def test_upload_wires_add_runlogs_dir_not_single_file():
    """Guard: the packager must call _add_runlogs_dir, not the old single
    eCan.log write, so this regression can't silently return."""
    src = Path("gui/ipc/w2p_handlers/debug_log_handler.py").read_text(encoding="utf-8")
    build = src.split("# 3. Build zip", 1)[1]
    assert "_add_runlogs_dir(zf, runlogs_dir" in build


def test_save_issue_report_writes_current_issues_and_copies_attachments(tmp_path):
    runlogs = tmp_path / "runlogs"
    runlogs.mkdir()
    shot = tmp_path / "screenshot.png"
    shot.write_bytes(b"PNGDATA")
    rec = tmp_path / "screen.mp4"
    rec.write_bytes(b"VIDEO")
    res = dlh.save_issue_report(runlogs, "包邮吗 was answered wrong", [str(shot), str(rec)])
    # description -> current_issues.md
    report = runlogs / "current_issues.md"
    assert report.is_file()
    assert "包邮吗 was answered wrong" in report.read_text(encoding="utf-8")
    assert res["report"] == str(report)
    # attachments -> issue_attachments/
    assert (runlogs / "issue_attachments" / "screenshot.png").is_file()
    assert (runlogs / "issue_attachments" / "screen.mp4").is_file()
    assert len(res["copied"]) == 2


def test_save_issue_report_deduplicates_names(tmp_path):
    runlogs = tmp_path / "runlogs"; runlogs.mkdir()
    a = tmp_path / "a" / "shot.png"; a.parent.mkdir(); a.write_bytes(b"1")
    b = tmp_path / "b" / "shot.png"; b.parent.mkdir(); b.write_bytes(b"2")
    dlh.save_issue_report(runlogs, "desc", [str(a), str(b)])
    files = sorted(p.name for p in (runlogs / "issue_attachments").glob("*"))
    assert files == ["shot.png", "shot_1.png"]  # no clobber


def test_issue_report_files_ride_the_runlogs_zip(tmp_path):
    """End-to-end: current_issues.md + attachments land in the packaged zip."""
    runlogs = tmp_path / "runlogs"; runlogs.mkdir()
    (runlogs / "eCan.log").write_text("log", encoding="utf-8")
    shot = tmp_path / "shot.png"; shot.write_bytes(b"PNG")
    dlh.save_issue_report(runlogs, "problem text", [str(shot)])
    zip_path = tmp_path / "out.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        dlh._add_runlogs_dir(zf, runlogs, exclude=zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "runlogs/current_issues.md" in names
    assert "runlogs/issue_attachments/shot.png" in names


def test_support_cli_requires_description():
    from click.testing import CliRunner
    from cli.support.commands import support
    r = CliRunner().invoke(support, ["upload", "--yes"])
    assert r.exit_code == 1
    assert "description is required" in r.output.lower()

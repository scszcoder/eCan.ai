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

"""download_docs_to_nas: a part's whole document list in one action.

2026-10-12: the chip crawler spent ~4 model steps per part on download_file /
save_file_to_nas pairs, each step resending the full product page.
"""
import asyncio
import json

from agent.ec_skills.browser_use_extension import extension_tools_service as svc
from agent.ec_skills.browser_use_extension.extension_tools_views import DownloadDocsToNasAction
from agent.ec_skills.nas import ugreen_nas


def _run(tmp_path, monkeypatch, docs, fail_url=None, nas_dir="Microchip/docs/PIC10/PIC10F200", on_nas=()):
    fetched, uploaded = [], []
    monkeypatch.setattr(ugreen_nas, "nas_list", on_nas if callable(on_nas) else lambda reldir: list(on_nas))

    def fake_fetch(url, path):
        if url == fail_url:
            raise OSError("HTTP Error 404")
        fetched.append(url)
        open(path, "wb").write(b"%PDF-")
        return 5

    monkeypatch.setattr(svc, "_fetch_to", fake_fetch)
    monkeypatch.setattr(ugreen_nas, "nas_upload", lambda local, remote: uploaded.append(remote) or {})
    docs_file = tmp_path / "docs.json"
    docs_file.write_text(json.dumps(docs), encoding="utf-8")
    params = DownloadDocsToNasAction(docs_file=str(docs_file), local_dir=str(tmp_path / "part"), nas_dir=nas_dir)
    return asyncio.run(svc.download_docs_to_nas(params=params)), fetched, uploaded


DOCS = [
    {"type": "Data Sheets", "title": "PIC10F200/202 Data Sheet", "url": "https://ww1.example.com/ds/DS40001239.pdf"},
    {"type": "Errata", "title": "Silicon Errata", "url": "https://ww1.example.com/er/DS80000.pdf"},
    {"type": "Errata", "title": "Silicon Errata", "url": "https://ww1.example.com/er/DS80000.pdf"},  # duplicate row
]


def test_downloads_and_uploads_each_doc_once(tmp_path, monkeypatch):
    out, fetched, uploaded = _run(tmp_path, monkeypatch, DOCS)
    assert out.error is None and "2 saved, 0 failed" in out.extracted_content
    assert len(fetched) == 2
    assert sorted(uploaded) == ["Microchip/docs/PIC10/PIC10F200/Data Sheets - PIC10F200 202 Data Sheet.pdf",
                        "Microchip/docs/PIC10/PIC10F200/Errata - Silicon Errata.pdf"]


def test_one_bad_link_does_not_stop_the_rest(tmp_path, monkeypatch):
    out, fetched, _ = _run(tmp_path, monkeypatch, {"docs": DOCS}, fail_url=DOCS[0]["url"])
    assert out.error is None
    assert "1 saved, 1 failed" in out.extracted_content and "404" in out.extracted_content


def test_existing_file_is_not_downloaded_again(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, DOCS)
    _, fetched, uploaded = _run(tmp_path, monkeypatch, DOCS)
    assert fetched == [] and len(uploaded) == 2


def test_files_already_on_nas_with_same_size_are_not_uploaded_again(tmp_path, monkeypatch):
    on_nas = [{"name": "data sheets - PIC10F200 202 Data Sheet.pdf", "is_dir": False, "size": 5},  # same size
              {"name": "Errata - Silicon Errata.pdf", "is_dir": False, "size": 3}]  # partial upload
    out, _, uploaded = _run(tmp_path, monkeypatch, DOCS, on_nas=on_nas)
    assert "2 saved, 0 failed" in out.extracted_content
    assert uploaded == ["Microchip/docs/PIC10/PIC10F200/Errata - Silicon Errata.pdf"]


def test_nas_listing_failure_uploads_everything(tmp_path, monkeypatch):
    def broken(reldir):
        raise RuntimeError("NAS list failed")
    out, _, uploaded = _run(tmp_path, monkeypatch, DOCS, on_nas=broken)
    assert "2 saved, 0 failed" in out.extracted_content and len(uploaded) == 2


def test_junk_titles_fall_back_to_url_names_and_never_collide(tmp_path, monkeypatch):
    # 2026-10-12: the page script returned "[object Object]" for every title and
    # a part's two errata were saved over each other
    docs = [{"type": "Errata", "title": "[object Object]", "url": "https://x/er/PIC16-Si-Errata-DS80001.pdf"},
            {"type": "Errata", "title": "[object Object]", "url": "https://x/er/PIC16-Si-Errata-DS80002.pdf"},
            {"type": "Errata", "title": "Same", "url": "https://x/a.pdf"},
            {"type": "Errata", "title": "Same", "url": "https://x/b.pdf"}]
    out, _, uploaded = _run(tmp_path, monkeypatch, docs, nas_dir="d")
    assert "4 saved" in out.extracted_content
    assert sorted(uploaded) == sorted(["d/Errata - PIC16-Si-Errata-DS80001.pdf", "d/Errata - PIC16-Si-Errata-DS80002.pdf",
                                       "d/Errata - Same.pdf", "d/Errata - Same (2).pdf"])


def test_downloads_run_in_parallel_but_capped(tmp_path, monkeypatch):
    # 2026-10-12: parts with ~22 documents took minutes one file at a time
    import threading, time
    live, peak, lock = [0], [0], threading.Lock()

    def slow_fetch(url, path):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.1)
        with lock:
            live[0] -= 1
        open(path, "wb").write(b"%PDF-")

    monkeypatch.setattr(svc, "_fetch_to", slow_fetch)
    monkeypatch.setattr(ugreen_nas, "nas_upload", lambda local, remote: {})
    monkeypatch.setattr(ugreen_nas, "nas_list", lambda reldir: [])
    docs = [{"type": "Errata", "title": f"E{i}", "url": f"https://x/e{i}.pdf"} for i in range(10)]
    docs_file = tmp_path / "docs.json"
    docs_file.write_text(json.dumps(docs), encoding="utf-8")
    params = DownloadDocsToNasAction(docs_file=str(docs_file), local_dir=str(tmp_path / "p"), nas_dir="d")
    out = asyncio.run(svc.download_docs_to_nas(params=params))
    assert "10 saved" in out.extracted_content
    assert 1 < peak[0] <= svc._DOWNLOAD_PARALLEL


def test_all_failed_is_an_error(tmp_path, monkeypatch):
    out, _, _ = _run(tmp_path, monkeypatch, DOCS[:1], fail_url=DOCS[0]["url"])
    assert out.error and "0 saved, 1 failed" in out.error

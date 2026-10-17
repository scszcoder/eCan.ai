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


def test_login_only_secure_documents_are_skipped_not_failed(tmp_path, monkeypatch):
    # 2026-10-13: the 403 on a myMicrochip secure document failed the whole dsPIC33A part
    secure = {"type": "Data Sheets", "title": "dsPIC33A Cryptographic Accelerator Module Data Sheet",
              "url": "https://www.microchip.com/myMicrochip/#/secure-document-download/63274/0"}
    out, fetched, _ = _run(tmp_path, monkeypatch, DOCS + [secure])
    assert out.error is None and "2 saved, 0 failed" in out.extracted_content
    assert secure["url"] not in fetched
    assert "Skipped (login-only secure documents" in out.extracted_content


def test_html_editions_are_saved_once_and_mirrored(tmp_path, monkeypatch):
    # 2026-10-16: ST lists an HTML edition next to some PDFs; editions are shared by many
    # parts, so each is saved once under html_dir/<doc id>/ and mirrored to nas_html_dir
    from agent.ec_skills.chip_docs import static_html

    calls = []

    def fake_save(url, out_root):
        calls.append(url)
        dest = out_root / static_html.doc_id(url)
        if (dest / static_html.DONE).exists():
            return dest, []
        (dest / "asset").mkdir(parents=True)
        for rel in ("index.html", "asset/f.webp"):
            (dest / rel).write_bytes(b"x")
        (dest / static_html.DONE).write_text(json.dumps({"files": ["index.html", "asset/f.webp"]}))
        return dest, ["index.html", "asset/f.webp"]

    monkeypatch.setattr(static_html, "save_edition", fake_save)
    docs = [dict(DOCS[0], html_url="https://www.st.com/resource/en/application_note/an4879-usb.html"), DOCS[1]]
    html_dir = tmp_path / "html"

    def run():
        uploaded = []
        monkeypatch.setattr(svc, "_fetch_to", lambda url, path: open(path, "wb").write(b"%PDF-"))
        monkeypatch.setattr(ugreen_nas, "nas_upload", lambda local, remote: uploaded.append(remote) or {})
        monkeypatch.setattr(ugreen_nas, "nas_list", lambda reldir: [])
        docs_file = tmp_path / "docs.json"
        docs_file.write_text(json.dumps(docs), encoding="utf-8")
        params = DownloadDocsToNasAction(docs_file=str(docs_file), local_dir=str(tmp_path / "part"), nas_dir="ST/docs/x",
                                         html_dir=str(html_dir), nas_html_dir="ST/html")
        return asyncio.run(svc.download_docs_to_nas(params=params)), uploaded

    out, uploaded = run()
    assert "2 saved, 0 failed" in out.extracted_content and "HTML editions: 1 saved" in out.extracted_content
    assert sorted(u for u in uploaded if u.startswith("ST/html")) == ["ST/html/an4879/asset/f.webp",
                                                                      "ST/html/an4879/index.html"]
    out, uploaded = run()  # the next part sharing the edition
    assert "HTML editions: 0 saved, 1 already saved" in out.extracted_content
    assert not any(u.startswith("ST/html") for u in uploaded)


def test_html_edition_whose_nas_upload_failed_is_uploaded_by_the_next_part(tmp_path, monkeypatch):
    # 2026-10-16 21:40: a NAS hiccup left 17 editions saved locally (.complete) but not on the
    # NAS, and every later part counted them "already saved", so they were never mirrored
    from agent.ec_skills.chip_docs import static_html

    def fake_save(url, out_root):
        dest = out_root / static_html.doc_id(url)
        if (dest / static_html.DONE).exists():
            return dest, []
        dest.mkdir(parents=True)
        (dest / "index.html").write_bytes(b"x")
        (dest / static_html.DONE).write_text(json.dumps({"files": ["index.html"]}))
        return dest, ["index.html"]

    monkeypatch.setattr(static_html, "save_edition", fake_save)
    monkeypatch.setattr(svc, "_fetch_to", lambda url, path: open(path, "wb").write(b"%PDF-"))
    monkeypatch.setattr(ugreen_nas, "nas_list", lambda reldir: [])
    docs_file = tmp_path / "docs.json"
    docs_file.write_text(json.dumps([dict(DOCS[0], html_url="https://www.st.com/x/an1-a.html")]), encoding="utf-8")
    params = DownloadDocsToNasAction(docs_file=str(docs_file), local_dir=str(tmp_path / "p"), nas_dir="d",
                                     html_dir=str(tmp_path / "h"), nas_html_dir="ST/html")

    def broken(local, remote):
        if remote.startswith("ST/html"):
            raise RuntimeError("STATUS_NETWORK_NAME_DELETED")
    monkeypatch.setattr(ugreen_nas, "nas_upload", broken)
    out = asyncio.run(svc.download_docs_to_nas(params=params))
    assert "HTML editions: 0 saved, 0 already saved, 1 failed" in out.extracted_content

    uploaded = []
    monkeypatch.setattr(ugreen_nas, "nas_upload", lambda local, remote: uploaded.append(remote))
    out = asyncio.run(svc.download_docs_to_nas(params=params))
    assert "HTML editions: 1 saved" in out.extracted_content and "ST/html/an1/index.html" in uploaded
    out = asyncio.run(svc.download_docs_to_nas(params=params))
    assert "HTML editions: 0 saved, 1 already saved" in out.extracted_content


def test_html_editions_are_ignored_without_html_dir(tmp_path, monkeypatch):
    from agent.ec_skills.chip_docs import static_html
    monkeypatch.setattr(static_html, "save_edition", lambda *a: (_ for _ in ()).throw(AssertionError("called")))
    out, _, _ = _run(tmp_path, monkeypatch, [dict(DOCS[0], html_url="https://www.st.com/x/an1-a.html")])
    assert "1 saved" in out.extracted_content and "HTML" not in out.extracted_content


def test_failed_html_edition_does_not_fail_the_part(tmp_path, monkeypatch):
    from agent.ec_skills.chip_docs import static_html

    def broken(url, out_root):
        raise OSError("HTTP Error 503")
    monkeypatch.setattr(static_html, "save_edition", broken)
    monkeypatch.setattr(svc, "_fetch_to", lambda url, path: open(path, "wb").write(b"%PDF-"))
    monkeypatch.setattr(ugreen_nas, "nas_upload", lambda local, remote: {})
    monkeypatch.setattr(ugreen_nas, "nas_list", lambda reldir: [])
    docs_file = tmp_path / "docs.json"
    docs_file.write_text(json.dumps([dict(DOCS[0], html_url="https://www.st.com/x/an1-a.html")]), encoding="utf-8")
    params = DownloadDocsToNasAction(docs_file=str(docs_file), local_dir=str(tmp_path / "p"), html_dir=str(tmp_path / "h"))
    out = asyncio.run(svc.download_docs_to_nas(params=params))
    assert out.error is None and "1 saved" in out.extracted_content
    assert "HTML editions: 0 saved, 0 already saved, 1 failed" in out.extracted_content and "503" in out.extracted_content


# ── shared store ─────────────────────────────────────────────────────────────
# 2026-10-16: ST attaches the same ~60 documents to whole product lines; per-part copies
# came to 10 GB for 75 parts holding 106 distinct documents (~230 GB for the 1903 parts).
# Each document now goes once to the NAS; the local file is only a buffer.


def _shared(tmp_path, monkeypatch, docs, part="STM32F103C8", nas=None, fail_url=None):
    fetched = []
    nas = {} if nas is None else nas  # remote path -> bytes

    def fake_fetch(url, path):
        if url == fail_url:
            raise OSError("HTTP Error 404")
        fetched.append(url)
        open(path, "wb").write(b"%PDF-")

    def fake_list(reldir):
        return [{"name": r.rsplit("/", 1)[1], "is_dir": False, "size": len(b)} for r, b in nas.items()
                if r.rsplit("/", 1)[0] == reldir]

    def fake_upload(local, remote):
        nas[remote] = open(local, "rb").read()
        return {}

    monkeypatch.setattr(svc, "_fetch_to", fake_fetch)
    monkeypatch.setattr(ugreen_nas, "nas_upload", fake_upload)
    monkeypatch.setattr(ugreen_nas, "nas_list", fake_list)
    monkeypatch.setattr(svc, "_shared_on_nas", {})
    docs_file = tmp_path / f"{part}.json"
    docs_file.write_text(json.dumps(docs), encoding="utf-8")
    params = DownloadDocsToNasAction(docs_file=str(docs_file), local_dir=str(tmp_path / "docs" / part),
                                     nas_dir=f"ST/docs/{part}", shared_dir=str(tmp_path / "files"),
                                     nas_shared_dir="ST/files")
    return asyncio.run(svc.download_docs_to_nas(params=params)), fetched, nas


ST_DOCS = [{"type": "Product Specifications", "title": "DS5319 STM32F103x8", "url": "https://st/ds/stm32f103c8.pdf"},
           {"type": "Application Notes", "title": "AN4879 USB guidelines", "url": "https://st/an/an4879.pdf",
            "html_url": "https://st/an/an4879.html"}]
AN = "ST/files/Application Notes/Application Notes - AN4879 USB guidelines.pdf"
DS = "ST/files/Product Specifications/Product Specifications - DS5319 STM32F103x8.pdf"


def test_shared_store_puts_each_document_once_on_the_nas_and_indexes_the_part(tmp_path, monkeypatch):
    out, fetched, nas = _shared(tmp_path, monkeypatch, ST_DOCS)
    assert out.error is None and "2 saved, 0 failed" in out.extracted_content
    assert sorted(nas) == ["ST/docs/STM32F103C8/index.json", AN, DS]
    assert not [p for p in tmp_path.rglob("*") if p.is_file() and p.suffix in (".pdf", ".part")]  # local copies gone
    index = json.loads(nas["ST/docs/STM32F103C8/index.json"])
    assert [d["file"] for d in index] == [DS[len("ST/"):], AN[len("ST/"):]]
    assert index[1]["html_url"] == "https://st/an/an4879.html"


def test_shared_store_next_part_fetches_only_new_documents(tmp_path, monkeypatch):
    nas = {}
    _shared(tmp_path, monkeypatch, ST_DOCS, nas=nas)
    before = dict(nas)
    sibling = ST_DOCS[1:] + [{"type": "Errata Sheets", "title": "ES096", "url": "https://st/es/es096.pdf"}]
    out, fetched, nas = _shared(tmp_path, monkeypatch, sibling, part="STM32F103RB", nas=nas)
    assert "2 saved, 0 failed" in out.extracted_content
    assert fetched == ["https://st/es/es096.pdf"]
    assert sorted(set(nas) - set(before)) == ["ST/docs/STM32F103RB/index.json",
                                             "ST/files/Errata Sheets/Errata Sheets - ES096.pdf"]


def test_shared_store_failed_document_is_listed_in_the_index(tmp_path, monkeypatch):
    out, _, nas = _shared(tmp_path, monkeypatch, ST_DOCS, fail_url=ST_DOCS[0]["url"])
    assert "1 saved, 1 failed" in out.extracted_content
    index = json.loads(nas["ST/docs/STM32F103C8/index.json"])
    assert "404" in index[0]["error"] and "file" not in index[0] and index[1]["file"]


def test_shared_store_concurrent_parts_fetch_a_document_once(tmp_path, monkeypatch):
    # three crawlers on sibling parts ask for the same application note at the same time
    import threading, time
    count, lock, nas = [0], threading.Lock(), {}

    def slow_fetch(url, path):
        with lock:
            count[0] += 1
        time.sleep(0.2)
        open(path, "wb").write(b"%PDF-")

    def upload(local, remote):
        nas[remote] = open(local, "rb").read()
    monkeypatch.setattr(svc, "_fetch_to", slow_fetch)
    monkeypatch.setattr(ugreen_nas, "nas_upload", upload)
    monkeypatch.setattr(ugreen_nas, "nas_list", lambda reldir: [])
    monkeypatch.setattr(svc, "_shared_on_nas", {})

    def run(part):
        f = tmp_path / f"{part}.json"
        f.write_text(json.dumps(ST_DOCS[1:]), encoding="utf-8")
        p = DownloadDocsToNasAction(docs_file=str(f), local_dir=str(tmp_path / part), nas_dir=f"ST/docs/{part}",
                                    shared_dir=str(tmp_path / "files"), nas_shared_dir="ST/files")
        asyncio.run(svc.download_docs_to_nas(params=p))
    threads = [threading.Thread(target=run, args=(f"P{i}",)) for i in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert count[0] == 1 and AN in nas

"""千牛 server-GPU OCR with local fallback (2026-10-10)."""
import agent.mcp.server.qianniu.remote_ocr as ro


def test_blocks_become_rapidocr_lines():
    lines = ro.to_rapidocr_lines({"blocks": [
        {"text": "有现货吗", "confidence": 0.98, "bbox": [10, 20, 110, 40]},
        {"text": "", "bbox": [0, 0, 1, 1]}, {"text": "x", "bbox": [1, 2]}]})
    assert lines == [([[10.0, 20.0], [110.0, 20.0], [110.0, 40.0], [10.0, 40.0]], "有现货吗", 0.98)]


def _reset():
    ro._failed_reads[0] = 0
    ro._local_until[0] = 0.0
    ro._inline_refused[0] = False


def test_backs_off_to_local_after_repeated_failed_reads(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setenv("ECAN_QIANNIU_REMOTE_OCR", "1")
    monkeypatch.setattr("utils.app_env.is_cn", lambda: True)
    img = tmp_path / "s.png"; __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 20), "white").save(img)
    calls = []
    def boom(_b, url=None):
        calls.append(1); raise ro.RemoteOcrError("upstream 502")
    monkeypatch.setattr(ro, "_call", boom)
    for _ in range(ro._FAILED_READS_TO_BACK_OFF):
        assert ro.remote_ocr_enabled()
        try:
            ro.ocr_png(str(img))
        except ro.RemoteOcrError:
            pass
    assert len(calls) == ro._FAILED_READS_TO_BACK_OFF * ro._TRIES_PER_READ
    assert not ro.remote_ocr_enabled()          # local for the back-off window
    _reset()


def test_not_enabled_backs_off_immediately(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setattr("utils.app_env.is_cn", lambda: True)
    img = tmp_path / "s.png"; __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 20), "white").save(img)
    monkeypatch.setattr(ro, "_call", lambda b, url=None: (_ for _ in ()).throw(ro.RemoteOcrError("OCR is not enabled on this server")))
    try:
        ro.ocr_png(str(img))
    except ro.RemoteOcrError:
        pass
    assert not ro.remote_ocr_enabled()
    _reset()


def test_intl_uses_local(monkeypatch):
    _reset()
    monkeypatch.setattr("utils.app_env.is_cn", lambda: False)
    assert not ro.remote_ocr_enabled()


def test_small_images_are_sent_inline_as_jpeg_at_same_size(tmp_path):
    from PIL import Image
    import io
    _reset()
    p = tmp_path / "shot.png"
    Image.new("RGB", (1500, 900), "white").save(p)
    data, _ = ro._jpeg_bytes(str(p))
    assert data[:2] == b"\xff\xd8" and len(data) <= ro._MAX_SEND_BYTES
    assert Image.open(io.BytesIO(data)).size == (1500, 900)   # bbox coords stay valid


def test_backend_without_ocr_schema_backs_off_immediately(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setattr("utils.app_env.is_cn", lambda: True)
    img = tmp_path / "s.png"; __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 20), "white").save(img)
    calls = []
    def missing(_b, url=None):
        calls.append(1)
        raise ro.RemoteOcrError('Unknown type "OcrInput"; Cannot query field "ocrImage" on type "Mutation".')
    monkeypatch.setattr(ro, "_call", missing)
    try:
        ro.ocr_png(str(img))
    except ro.RemoteOcrError:
        pass
    assert len(calls) == 1 and not ro.remote_ocr_enabled()
    _reset()


def _ok(provider="aihub"):
    return {"blocks": [{"text": "在吗", "confidence": 0.9, "bbox": [1, 2, 3, 4]}], "provider": provider, "model": "pp"}


def test_oversize_image_goes_by_cos_url(monkeypatch, tmp_path):
    """Too big to inline under the gateway's 100 KB body cap -> COS upload + ocrImage(url)."""
    _reset()
    img = tmp_path / "s.png"; __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 20), "white").save(img)
    monkeypatch.setattr(ro, "_MAX_SEND_BYTES", 10)                 # nothing fits inline
    uploads, calls = [], []
    monkeypatch.setattr(ro, "_upload_for_url", lambda path, jpg: uploads.append(path) or "https://cos/x.png")
    monkeypatch.setattr(ro, "_call", lambda b, url=None: calls.append((b, url)) or _ok())
    lines, engine = ro.ocr_png(str(img))
    assert uploads == [str(img)] and calls == [(None, "https://cos/x.png")]
    assert lines[0][1] == "在吗" and engine.startswith("remote/url:")


def test_gateway_413_switches_to_cos_url(monkeypatch, tmp_path):
    _reset()
    img = tmp_path / "s.png"; __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 20), "white").save(img)
    calls = []
    def call(b, url=None):
        calls.append(url)
        if url is None:
            raise ro._BodyTooLarge("HTTP 413")
        return _ok()
    monkeypatch.setattr(ro, "_call", call)
    monkeypatch.setattr(ro, "_upload_for_url", lambda path, jpg: "https://cos/y.png")
    lines, engine = ro.ocr_png(str(img))
    assert calls == [None, "https://cos/y.png"] and engine.startswith("remote/url:")
    assert ro._failed_reads[0] == 0


def test_upload_uses_original_when_under_url_cap(monkeypatch, tmp_path):
    img = tmp_path / "s.png"; img.write_bytes(b"png")
    seen = []
    class FakeClient:
        def upload_file(self, path):
            seen.append(path); return "https://cos/z"
        def close(self):
            pass
    import agent.ec_skills.media.proxy_media_client as pmc
    monkeypatch.setattr(pmc.ProxyMediaClient, "from_ecanai", classmethod(lambda cls: FakeClient()))
    assert ro._upload_for_url(str(img), b"jpg") == "https://cos/z" and seen == [str(img)]
    monkeypatch.setattr(ro, "_MAX_URL_BYTES", 2)                   # original too big -> temp JPEG
    assert ro._upload_for_url(str(img), b"j") == "https://cos/z" and seen[-1].endswith(".jpg")
    assert not __import__("os").path.exists(seen[-1])               # temp removed


def test_real_screens_go_by_url_not_squeezed_inline(tmp_path):
    """The gateway caps JSON bodies at 100 KB (server team, 2026-10-12): a busy
    screen is over 60 KB as a full-quality JPEG and goes by URL, never inline at
    a blurrier quality."""
    import os
    from PIL import Image
    _reset()
    p = tmp_path / "busy.png"
    Image.frombytes("RGB", (900, 600), os.urandom(900 * 600 * 3)).save(p)
    inline, fallback = ro._jpeg_bytes(str(p))
    assert inline is None and len(fallback) <= ro._MAX_URL_BYTES


def test_after_one_413_every_read_goes_by_url(monkeypatch, tmp_path):
    _reset()
    img = tmp_path / "s.png"; __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 20), "white").save(img)
    calls = []
    def call(b, url=None):
        calls.append(url)
        if url is None:
            raise ro._BodyTooLarge("HTTP 413")
        return _ok()
    monkeypatch.setattr(ro, "_call", call)
    monkeypatch.setattr(ro, "_upload_for_url", lambda path, jpg: "https://cos/y.png")
    ro.ocr_png(str(img))
    ro.ocr_png(str(img))
    assert calls == [None, "https://cos/y.png", "https://cos/y.png"]   # only the first read tried inline
    _reset()

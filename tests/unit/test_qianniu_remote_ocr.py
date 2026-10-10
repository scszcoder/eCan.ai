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


def test_backs_off_to_local_after_repeated_failed_reads(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setenv("ECAN_QIANNIU_REMOTE_OCR", "1")
    monkeypatch.setattr("utils.app_env.is_cn", lambda: True)
    img = tmp_path / "s.png"; __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 20), "white").save(img)
    calls = []
    def boom(_b):
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
    monkeypatch.setattr(ro, "_call", lambda b: (_ for _ in ()).throw(ro.RemoteOcrError("OCR is not enabled on this server")))
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


def test_screens_are_sent_as_small_jpeg_at_same_size(tmp_path):
    from PIL import Image
    import io
    p = tmp_path / "shot.png"
    Image.new("RGB", (1500, 900), "white").save(p)
    data = ro._jpeg_bytes(str(p))
    assert data[:2] == b"\xff\xd8" and len(data) <= ro._MAX_SEND_BYTES
    assert Image.open(io.BytesIO(data)).size == (1500, 900)   # bbox coords stay valid


def test_backend_without_ocr_schema_backs_off_immediately(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setattr("utils.app_env.is_cn", lambda: True)
    img = tmp_path / "s.png"; __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 20), "white").save(img)
    calls = []
    def missing(_b):
        calls.append(1)
        raise ro.RemoteOcrError('Unknown type "OcrInput"; Cannot query field "ocrImage" on type "Mutation".')
    monkeypatch.setattr(ro, "_call", missing)
    try:
        ro.ocr_png(str(img))
    except ro.RemoteOcrError:
        pass
    assert len(calls) == 1 and not ro.remote_ocr_enabled()
    _reset()

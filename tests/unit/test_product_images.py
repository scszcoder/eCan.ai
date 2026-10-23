"""Product images (2026-10-23): every source (link, local path, embedded picture)
is stored once in the knowledge base's own folder and described once; the
description is indexed so a buyer's photo can find the same / similar product."""
import io
import struct
import zlib

import pytest

from knowledge.ks import chunking, product_images as pi


def _png(color=(200, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * 2 for _ in range(2))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def store(tmp_path, monkeypatch):
    d = tmp_path / "imgs"
    d.mkdir()
    monkeypatch.setattr(pi, "images_dir", lambda: str(d))
    return d


def test_every_source_is_stored_once(store, tmp_path, monkeypatch):
    local = tmp_path / "ABC-001.png"
    local.write_bytes(_png((1, 2, 3)))
    red = _png()

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(pi.urllib.request, "urlopen", lambda req, timeout=0: Resp(red))
    out = pi.prepare(["https://img.example.com/a.jpg", "ABC-001.png", "D:\\nope\\gone.jpg"],
                     base_dir=str(tmp_path), embedded=[(red, "png")])
    files = [e for e in out if e.get("file")]
    assert len(files) == 2                                   # the link and the embedded picture are the same image
    assert out[0]["src"] == "embedded" and any(e["src"] == "ABC-001.png" for e in files)
    assert any(e.get("error") == "file not found" for e in out)
    assert len(list(store.glob("*.png"))) == 2
    again = pi.prepare(out)                                  # already stored: kept, nothing fetched again
    assert [e.get("file") for e in again if e.get("file")] == [e["file"] for e in files]


def test_non_images_are_refused(store, tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    assert pi.prepare([str(f)])[0]["error"] == "not an image"


def test_descriptions_are_made_once_and_indexed(store, tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(_png())
    entries = pi.prepare([str(p)])
    calls = []
    n = pi.describe(entries, ask=lambda path: calls.append(path) or "红色纯棉圆领短袖T恤，胸前白色字母logo")
    assert n == 1 and entries[0]["desc"].startswith("红色")
    other = pi.prepare([str(p)])                             # another product with the same picture
    assert pi.describe(other, ask=lambda path: calls.append(path) or "x") == 0
    assert other[0]["desc"] == entries[0]["desc"] and len(calls) == 1
    chunks = chunking.product_chunks({"title": "T恤", "images": entries})
    assert any(c["doc_type"] == "appearance" and "外观：红色纯棉" in c["text"] for c in chunks)


def test_an_unreachable_model_does_not_stop_the_import(store, tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(_png())
    entries = pi.prepare([str(p)])

    def down(path):
        raise RuntimeError("ecanai provider not configured")
    assert pi.describe(entries, ask=down) == 0 and "desc" not in entries[0]


def test_old_string_images_still_work():
    assert pi.normalize(["https://x/1.jpg", "", {"src": "a"}]) == [{"src": "https://x/1.jpg"}, {"src": "a"}]
    assert chunking.product_chunks({"title": "t", "images": ["https://x/1.jpg"]})[-1]["doc_type"] != "appearance"

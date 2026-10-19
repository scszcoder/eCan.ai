"""get_file_content serves the chat's own temp dir and, so the desktop result
panel can show media an agent generated, the app's generated_medias dir --
nothing else."""
from types import SimpleNamespace

import pytest

from gui.ipc.w2p_handlers import chat_handler as ch
from agent.ec_skills.media import media_gen_node


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    temp, media, other = tmp_path / "temp", tmp_path / "medias", tmp_path / "other"
    for d in (temp, media, other):
        d.mkdir()
    monkeypatch.setattr(ch, "get_handler_context",
                        lambda req, params: SimpleNamespace(get_temp_dir=lambda: str(temp)))
    monkeypatch.setattr(media_gen_node, "generated_medias_root", lambda: str(media))
    return temp, media, other


def _get(path):
    req = {"id": "r1", "type": "request", "method": "get_file_content", "params": {"filePath": str(path)}}
    return ch.handle_get_file_content(req, req["params"])


def test_generated_media_is_served(dirs):
    _, media, _ = dirs
    (media / "img.png").write_bytes(b"PNG")
    resp = _get(media / "img.png")
    assert resp["status"] == "success"
    assert resp["result"]["dataUrl"].startswith("data:image/png;base64,")


def test_temp_dir_still_served(dirs):
    temp, _, _ = dirs
    (temp / "a.txt").write_text("x")
    assert _get(temp / "a.txt")["status"] == "success"


def test_other_folders_and_lookalike_prefixes_are_refused(dirs):
    _, media, other = dirs
    (other / "secret.txt").write_text("x")
    lookalike = media.parent / (media.name + "_evil")
    lookalike.mkdir()
    (lookalike / "x.png").write_bytes(b"PNG")
    assert _get(other / "secret.txt")["status"] == "error"
    assert _get(lookalike / "x.png")["status"] == "error"

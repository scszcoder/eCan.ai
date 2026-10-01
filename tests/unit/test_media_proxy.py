"""Media through the eCan llm-proxy: the client, the ``media-gen`` node and
LLM-node video/audio inputs, against a fake proxy implementing the contract
(GET /models, POST /files + PUT, /audio/transcriptions, /images/generations,
/audio/speech, /videos POST/GET/DELETE)."""

import json
import os
import re
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent.ec_skills.media import media_gen_node, media_inputs, proxy_media_client
from agent.ec_skills.media.proxy_media_client import MediaProxyError, ProxyMediaClient
from utils.log_scope import scope

PNG = b"\x89PNG\r\n\x1a\nfakepng"
MP4 = b"\x00\x00\x00\x18ftypmp42fakevideo"


class FakeProxy:
    def __init__(self):
        self.seen = []          # (method, path, headers, body)
        self.store = {"img1.png": (PNG, "image/png"), "out.mp4": (MP4, "video/mp4"),
                      "take1.mp3": (b"ID3take1", "audio/mpeg"), "take2.mp3": (b"ID3take2", "audio/mpeg"),
                      "long.wav": (b"RIFFlongwav", "audio/wav")}
        self.jobs = {}
        self.flaky = 0
        self.busy = 0
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _body(self):
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def _send(self, status, obj=None, raw=None, ctype="application/json", headers=None):
                data = raw if raw is not None else json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Request-Id", "req-1")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def _err(self, status, code, msg):
                self._send(status, {"error": {"message": msg, "type": code, "code": code}})

            def _record(self, body):
                fake.seen.append((self.command, self.path, dict(self.headers.items()), body))

            def do_GET(self):
                self._record(b"")
                p = self.path
                if p == "/v1/models":
                    return self._send(200, {"data": [
                        {"id": "qwen3-vl-plus", "object": "model",
                         "capabilities": {"input": ["text", "image", "video"], "endpoints": ["chat"]}},
                        {"id": "qwen3-omni-flash", "object": "model",
                         "capabilities": {"input": ["text", "image", "video", "audio"], "endpoints": ["chat"]}},
                        {"id": "deepseek-v3", "object": "model"},
                        {"id": "cosyvoice-v2", "object": "model",
                         "capabilities": {"endpoints": ["speech"], "voices": ["longxiaochun_v2"],
                                          "formats": ["mp3", "wav"]}}]})
                if p.startswith("/cos/"):
                    data, ctype = fake.store[p[5:]]
                    return self._send(200, raw=data, ctype=ctype)
                m = re.match(r"/v1/music/(\w+)$", p)
                if m:
                    job = fake.jobs.get(m.group(1))
                    if not job:
                        return self._err(404, "not_found", "no job")
                    job["polls"] += 1
                    if job["mode"] == "slow" or job["polls"] < 2:
                        return self._send(200, {"id": job["id"], "status": "running", "progress": 30})
                    if job["mode"] == "fail":
                        return self._send(200, {"id": job["id"], "status": "failed",
                                                "error": {"code": "content_policy", "message": "blocked"}})
                    base = f"http://127.0.0.1:{fake.port}/cos/"
                    return self._send(200, {"id": job["id"], "status": "succeeded", "outputs": [
                        {"url": base + "take1.mp3", "mime_type": "audio/mpeg", "duration_seconds": 30, "title": "A"},
                        {"url": base + "take2.mp3", "mime_type": "audio/mpeg", "duration_seconds": 31}]})
                m = re.match(r"/v1/videos/(\w+)$", p)
                if m:
                    job = fake.jobs.get(m.group(1))
                    if not job:
                        return self._err(404, "not_found", "no job")
                    job["polls"] += 1
                    if job["mode"] == "slow" or job["polls"] < 2:
                        return self._send(200, {"id": job["id"], "status": "running", "progress": 40})
                    if job["mode"] == "fail":
                        return self._send(200, {"id": job["id"], "status": "failed",
                                                "error": {"code": "content_policy", "message": "blocked"}})
                    return self._send(200, {"id": job["id"], "status": "succeeded", "progress": 100,
                                            "output": {"url": f"http://127.0.0.1:{fake.port}/cos/out.mp4",
                                                       "mime_type": "video/mp4", "duration_seconds": 5,
                                                       "width": 1280, "height": 720}})
                self._err(404, "not_found", p)

            def do_PUT(self):
                body = self._body()
                self._record(body)
                name = self.path.rsplit("/", 1)[-1]
                fake.store[name] = (body, self.headers.get("Content-Type") or "")
                self._send(200, {})

            def do_DELETE(self):
                self._record(b"")
                vid = self.path.rsplit("/", 1)[-1]
                if vid in fake.jobs:
                    fake.jobs[vid]["mode"] = "cancelled"
                self._send(200, {"id": vid, "status": "cancelled"})

            def do_POST(self):
                body = self._body()
                self._record(body)
                p = self.path
                if p == "/v1/files":
                    req = json.loads(body)
                    fid = f"file{len(fake.store)}_{req['filename']}"
                    return self._send(200, {
                        "file_id": fid,
                        "upload_url": f"http://127.0.0.1:{fake.port}/upload/{fid}",
                        "upload_headers": {"Content-Type": req["mime_type"]},
                        "url": f"http://127.0.0.1:{fake.port}/cos/{fid}"})
                if p == "/v1/audio/transcriptions":
                    return self._send(200, {"text": "hello from the clip", "language": "zh", "duration": 3.2,
                                            "segments": []}, headers={"X-Ecan-Billed-Units": "audio_seconds=4"})
                if p == "/v1/images/generations":
                    req = json.loads(body)
                    if req["prompt"] == "broke":
                        return self._err(402, "insufficient_balance", "top up first")
                    if req["prompt"] == "flaky" and fake.flaky == 0:
                        fake.flaky += 1
                        return self._err(503, "upstream_error", "vendor down")
                    if req["prompt"] == "unavail" and fake.flaky == 0:
                        fake.flaky += 1
                        return self._err(503, "provider_unavailable", "provider cooling down")
                    if req["prompt"] == "busy" and fake.busy < 2:
                        fake.busy += 1
                        return self._err(409, "idempotency_in_progress", "still running")
                    if req["prompt"] == "unpriced":
                        return self._err(503, "model_not_priced", "no price for this model")
                    if req["prompt"] == "nsfw":
                        return self._err(400, "content_policy", "inappropriate content")
                    return self._send(200, {"created": 1, "data": [
                        {"url": f"http://127.0.0.1:{fake.port}/cos/img1.png", "mime_type": "image/png",
                         "width": 1024, "height": 1024}], "usage": {"images": 1}},
                        headers={"X-Ecan-Billed-Units": "images=1"})
                if p == "/v1/audio/speech":
                    if json.loads(body)["input"] == "long":
                        return self._send(200, {"object": "audio.speech", "mime_type": "audio/wav",
                                                "url": f"http://127.0.0.1:{fake.port}/cos/long.wav",
                                                "bytes": 11, "expires_at": "2026-09-29T00:00:00Z"})
                    return self._send(200, raw=b"ID3fakeaudio", ctype="audio/mpeg",
                                      headers={"X-Ecan-Billed-Units": "characters=5"})
                if p == "/v1/music":
                    req = json.loads(body)
                    mid = f"mus{len(fake.jobs) + 1}"
                    mode = {"fail": "fail", "slow": "slow"}.get(req["prompt"], "ok")
                    fake.jobs[mid] = {"id": mid, "mode": mode, "polls": 0, "req": req}
                    return self._send(202, {"id": mid, "object": "music", "status": "queued",
                                            "model": req["model"]})
                if p == "/v1/videos":
                    req = json.loads(body)
                    vid = f"vid{len(fake.jobs) + 1}"
                    mode = {"fail": "fail", "slow": "slow"}.get(req["prompt"], "ok")
                    fake.jobs[vid] = {"id": vid, "mode": mode, "polls": 0, "req": req}
                    return self._send(202, {"id": vid, "object": "video", "status": "queued",
                                            "model": req["model"]})
                self._err(404, "not_found", p)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def calls(self, method, path):
        return [s for s in self.seen if s[0] == method and s[1] == path]


@pytest.fixture
def proxy():
    fp = FakeProxy()
    yield fp
    fp.srv.shutdown()


def _client(fp):
    c = ProxyMediaClient(f"http://127.0.0.1:{fp.port}/v1", "tok",
                         extra_headers={"X-User-Id": "u1", "X-Provider": "ecanai"})
    c._sleep = lambda s: None
    c.poll_initial_s = 0.01
    c.poll_max_s = 0.01
    return c


# ── client ──────────────────────────────────────────────────────────────

def test_list_models_returns_capabilities(proxy):
    models = _client(proxy).list_models()
    assert models[0]["capabilities"]["input"] == ["text", "image", "video"]


def test_paid_call_carries_idempotency_and_attribution(proxy):
    with scope(skill_id="SK_MEDIA", source="agent_run"):
        data = _client(proxy).generate_images("seedream-4.0", "a cat", size="1024x1024", n=None)
    assert data[0]["width"] == 1024
    _, _, headers, body = proxy.calls("POST", "/v1/images/generations")[0]
    assert headers.get("Idempotency-Key")
    assert headers.get("X-Ecan-Skill-Id") == "SK_MEDIA"
    assert headers.get("Authorization") == "Bearer tok"
    assert headers.get("X-User-Id") == "u1" and headers.get("X-Provider") == "ecanai"
    sent = json.loads(body)
    assert sent["size"] == "1024x1024" and "n" not in sent and sent["response_format"] == "url"


def test_retry_reuses_the_same_idempotency_key(proxy):
    _client(proxy).generate_images("seedream-4.0", "flaky")
    keys = [h.get("Idempotency-Key") for _, _, h, _ in proxy.calls("POST", "/v1/images/generations")]
    assert len(keys) == 2 and keys[0] == keys[1]


def test_402_maps_to_media_proxy_error(proxy):
    with pytest.raises(MediaProxyError) as ei:
        _client(proxy).generate_images("seedream-4.0", "broke")
    assert ei.value.status == 402 and ei.value.code == "insufficient_balance"
    assert ei.value.message == "top up first"


def test_upload_file_puts_bytes_to_presigned_url(proxy, tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(MP4)
    url = _client(proxy).upload_file(str(f))
    assert url.startswith(f"http://127.0.0.1:{proxy.port}/cos/")
    req = json.loads(proxy.calls("POST", "/v1/files")[0][3])
    assert req == {"filename": "clip.mp4", "mime_type": "video/mp4", "size": len(MP4), "purpose": "model_input"}
    put = [s for s in proxy.seen if s[0] == "PUT"][0]
    assert put[3] == MP4 and "Authorization" not in put[2]   # never leak the bearer to storage


def test_transcribe_local_file_is_multipart_verbose_json(proxy, tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"ID3audio")
    with scope(skill_id="SK_ASR"):
        out = _client(proxy).transcribe(str(f), "paraformer-v2", language="zh")
    assert out["text"] == "hello from the clip"
    _, _, headers, body = proxy.calls("POST", "/v1/audio/transcriptions")[0]
    assert headers["Content-Type"].startswith("multipart/form-data")
    assert b"verbose_json" in body and b"paraformer-v2" in body
    assert headers.get("Idempotency-Key") and headers.get("X-Ecan-Skill-Id") == "SK_ASR"


def test_transcribe_url_is_json(proxy):
    _client(proxy).transcribe("https://cos.example/a.mp3", "paraformer-v2")
    body = json.loads(proxy.calls("POST", "/v1/audio/transcriptions")[0][3])
    assert body == {"url": "https://cos.example/a.mp3", "model": "paraformer-v2", "response_format": "verbose_json"}


def test_speech_returns_bytes(proxy):
    audio, mime = _client(proxy).speech("cosyvoice-v2", "hello", voice="longxiaochun")
    assert audio == b"ID3fakeaudio" and mime == "audio/mpeg"
    _, _, headers, body = proxy.calls("POST", "/v1/audio/speech")[0]
    assert headers.get("Idempotency-Key")
    assert "response_format" not in json.loads(body)   # the model's default format


def test_speech_json_url_response_is_downloaded(proxy):
    audio, mime = _client(proxy).speech("cosyvoice-v2", "long", fmt="wav")
    assert audio == b"RIFFlongwav" and mime == "audio/wav"
    assert json.loads(proxy.calls("POST", "/v1/audio/speech")[0][3])["response_format"] == "wav"
    get = proxy.calls("GET", "/cos/long.wav")[0]
    assert "Authorization" not in get[2]


def test_transcribe_over_4mb_goes_by_url(proxy, tmp_path):
    small = tmp_path / "small.mp3"
    small.write_bytes(b"x" * (4 * 1024 * 1024))
    big = tmp_path / "big.mp3"
    big.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    c = _client(proxy)
    c.transcribe(str(small), "paraformer-v2")
    c.transcribe(str(big), "paraformer-v2")
    first, second = proxy.calls("POST", "/v1/audio/transcriptions")
    assert first[2]["Content-Type"].startswith("multipart/form-data")
    assert json.loads(second[3])["url"].startswith(f"http://127.0.0.1:{proxy.port}/cos/")
    assert len(proxy.calls("POST", "/v1/files")) == 1


def test_409_idempotency_in_progress_retries_with_same_key(proxy):
    data = _client(proxy).generate_images("wan2.2-t2i-plus", "busy")
    assert data[0]["width"] == 1024
    keys = [h.get("Idempotency-Key") for _, _, h, _ in proxy.calls("POST", "/v1/images/generations")]
    assert len(keys) == 3 and len(set(keys)) == 1


def test_409_wait_is_bounded(proxy):
    c = _client(proxy)
    c.idempotency_max_waits = 1
    with pytest.raises(MediaProxyError) as ei:
        c.generate_images("wan2.2-t2i-plus", "busy")
    assert ei.value.status == 409 and ei.value.code == "idempotency_in_progress"


def test_503_model_not_priced_is_not_retried(proxy):
    with pytest.raises(MediaProxyError) as ei:
        _client(proxy).generate_images("wan2.2-t2i-plus", "unpriced")
    assert ei.value.status == 503 and ei.value.code == "model_not_priced"
    assert len(proxy.calls("POST", "/v1/images/generations")) == 1


def test_503_provider_unavailable_is_retried(proxy):
    assert _client(proxy).generate_images("wan2.2-t2i-plus", "unavail")[0]["width"] == 1024
    assert len(proxy.calls("POST", "/v1/images/generations")) == 2


def test_content_policy_is_surfaced_not_retried(proxy):
    with pytest.raises(MediaProxyError) as ei:
        _client(proxy).generate_images("wan2.2-t2i-plus", "nsfw")
    assert ei.value.code == "content_policy"
    assert "moderation" in ei.value.message and "inappropriate content" in ei.value.message
    assert len(proxy.calls("POST", "/v1/images/generations")) == 1


def test_model_capabilities_are_cached(proxy, monkeypatch):
    monkeypatch.setattr(proxy_media_client, "_CAPS_CACHE", {})
    c = _client(proxy)
    caps = c.get_model_capabilities()
    assert caps["cosyvoice-v2"]["voices"] == ["longxiaochun_v2"] and caps["deepseek-v3"] == {}
    c.get_model_capabilities()
    assert len(proxy.calls("GET", "/v1/models")) == 1


def test_video_wait_success(proxy):
    c = _client(proxy)
    job = c.submit_video("seedance-1.0-pro", "a dog", duration_seconds=5)
    assert job["status"] == "queued"
    seen = []
    final = c.wait_video(job["id"], timeout_s=10, on_progress=lambda j: seen.append(j["status"]))
    assert final["status"] == "succeeded" and seen == ["running", "succeeded"]


def test_video_wait_failed_returns_failed_job(proxy):
    c = _client(proxy)
    job = c.submit_video("seedance-1.0-pro", "fail")
    final = c.wait_video(job["id"], timeout_s=10)
    assert final["status"] == "failed" and final["error"]["code"] == "content_policy"


def test_video_wait_timeout(proxy):
    c = _client(proxy)
    job = c.submit_video("seedance-1.0-pro", "slow")
    with pytest.raises(MediaProxyError) as ei:
        c.wait_video(job["id"], timeout_s=0.05)
    assert ei.value.code == "client_timeout"
    assert c.cancel_video(job["id"])["status"] == "cancelled"


def test_download_into_generated_medias(proxy, tmp_path):
    dest = tmp_path / "generated_medias"
    c = _client(proxy)
    p1 = c.download(f"http://127.0.0.1:{proxy.port}/cos/img1.png", str(dest))
    p2 = c.download(f"http://127.0.0.1:{proxy.port}/cos/img1.png", str(dest))
    assert open(p1, "rb").read() == PNG and p1 != p2 and os.path.dirname(p1) == str(dest)


# ── media-gen node ──────────────────────────────────────────────────────

def _node(proxy, tmp_path, monkeypatch, **cfg):
    monkeypatch.setattr(media_gen_node, "_make_client", lambda: _client(proxy))
    monkeypatch.setattr(media_gen_node, "generated_medias_root", lambda: str(tmp_path / "generated_medias"))
    inputs = {k: {"type": "constant", "content": v} for k, v in cfg.items()}
    fn = media_gen_node.build_media_gen_node({"inputsValues": inputs}, "gen1", "sk", "owner", None)
    state = {"messages": [], "attributes": {}, "result": {}, "prompt_refs": {"subject": "a red cat"}}
    return fn(state, runtime=types.SimpleNamespace(context={}), store=None)


def test_node_image(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="image", modelName="seedream-4.0",
                       prompt="draw {{subject}}", aspectRatio="1:1", n=1, timeoutSeconds="",
                       outputSubdir="shots")
    media = out["result"]["media"]
    assert len(media) == 1 and media[0]["width"] == 1024 and media[0]["mime_type"] == "image/png"
    assert media[0]["path"].startswith(str(tmp_path / "generated_medias" / "shots"))
    assert open(media[0]["path"], "rb").read() == PNG
    sent = json.loads(proxy.calls("POST", "/v1/images/generations")[0][3])
    assert sent["prompt"] == "draw a red cat" and sent["aspect_ratio"] == "1:1" and sent["n"] == 1


def test_node_image_error(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="image", modelName="seedream-4.0", prompt="broke")
    assert out["result"]["media_error"] == {"code": "insufficient_balance", "message": "top up first"}
    assert "media" not in out["result"]


def test_node_video(proxy, tmp_path, monkeypatch):
    first = tmp_path / "first.png"
    first.write_bytes(PNG)
    out = _node(proxy, tmp_path, monkeypatch, mediaType="video", modelName="seedance-1.0-pro",
                       prompt="a dog", firstFrame=str(first), durationSeconds=5, resolution="720p",
                       generateAudio=False, aspectRatio="16:9")
    assert out["result"]["media_job"]["status"] == "succeeded"
    m = out["result"]["media"][0]
    assert m["duration_seconds"] == 5 and m["mime_type"] == "video/mp4" and open(m["path"], "rb").read() == MP4
    req = list(proxy.jobs.values())[0]["req"]
    assert req["image_url"].startswith(f"http://127.0.0.1:{proxy.port}/cos/")
    assert req["generate_audio"] is False and req["duration_seconds"] == 5
    assert "last_frame_url" not in req


def test_node_video_last_frame_and_empty_values_omitted(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="video", modelName="seedance-2.0-fast",
                prompt="a dog", firstFrame="https://cos.example/a.png", lastFrame="https://cos.example/b.png",
                resolution="", aspectRatio="", generateAudio="")
    assert out["result"]["media_job"]["status"] == "succeeded"
    req = list(proxy.jobs.values())[0]["req"]
    assert req["image_url"] == "https://cos.example/a.png" and req["last_frame_url"] == "https://cos.example/b.png"
    assert not {"resolution", "aspect_ratio", "generate_audio"} & set(req)


def test_node_video_failed(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="video", modelName="seedance-1.0-pro", prompt="fail")
    assert out["result"]["media_error"]["code"] == "content_policy"
    assert out["result"]["media_job"]["status"] == "failed"


def test_node_speech(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="speech", modelName="cosyvoice-v2",
                       prompt="你好", voice="longxiaochun", audioFormat="mp3", speed=1)
    m = out["result"]["media"][0]
    assert m["mime_type"] == "audio/mpeg" and m["path"].endswith(".mp3")
    assert open(m["path"], "rb").read() == b"ID3fakeaudio"


def test_node_speech_default_format_from_json_url(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="speech", modelName="qwen3-tts-flash",
                prompt="long", audioFormat="")
    m = out["result"]["media"][0]
    assert m["mime_type"] == "audio/wav" and m["path"].endswith(".wav")
    assert open(m["path"], "rb").read() == b"RIFFlongwav"
    assert "response_format" not in json.loads(proxy.calls("POST", "/v1/audio/speech")[0][3])


def test_node_content_policy_error(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="image", modelName="wan2.2-t2i-plus", prompt="nsfw")
    err = out["result"]["media_error"]
    assert err["code"] == "content_policy" and "moderation" in err["message"]


# ── LLM-node media inputs (prep_multi_modal_content) ────────────────────

def _prep(proxy, monkeypatch, state, media, caps, vision=True):
    from agent.ec_skills.llm_utils.llm_utils import prep_multi_modal_content
    monkeypatch.setattr(media_inputs, "_make_client", lambda: _client(proxy))
    llm = types.SimpleNamespace(supports_vision=vision)
    return prep_multi_modal_content(state, llm=llm, base_text="describe it", media_inputs=media, media_caps=caps)


def test_capable_model_gets_video_url_and_input_audio(proxy, tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_bytes(MP4)
    a = tmp_path / "voice.mp3"
    a.write_bytes(b"ID3voice")
    state = {"input": json.dumps({"latest_message_attachments": [
        {"kind": "audio", "url": "https://cos.example/long.m4a"}]})}
    out = _prep(proxy, monkeypatch, state, f"{v}\n{a}", {"video": True, "audio": True})
    assert out[0] == {"type": "text", "text": "describe it"}
    types_ = [p["type"] for p in out[1:]]
    assert types_ == ["video_url", "input_audio", "audio_url"]
    assert out[1]["video_url"]["url"].startswith(f"http://127.0.0.1:{proxy.port}/cos/")
    assert out[2]["input_audio"]["format"] == "mp3"
    assert out[3]["audio_url"]["url"] == "https://cos.example/long.m4a"


def _fake_ffmpeg(monkeypatch):
    monkeypatch.setattr(media_inputs, "find_ffmpeg", lambda: "ffmpeg")

    def run(cmd):
        out = cmd[-1]
        if "frame_%03d.jpg" in out:
            for i in range(1, 4):
                with open(out.replace("%03d", f"{i:03d}"), "wb") as fh:
                    fh.write(b"\xff\xd8jpeg")
        elif out.endswith(".mp3"):
            with open(out, "wb") as fh:
                fh.write(b"ID3track")
        return types.SimpleNamespace(returncode=0, stderr=b"  Duration: 00:00:08.00, start: 0")
    monkeypatch.setattr(media_inputs, "_run", run)


def test_incapable_model_falls_back_to_frames_and_transcripts(proxy, tmp_path, monkeypatch):
    _fake_ffmpeg(monkeypatch)
    v = tmp_path / "clip.mp4"
    v.write_bytes(MP4)
    state = {"input": "hi", "attachments": [
        {"filename": "note.wav", "mime_type": "audio/wav", "file_data": b"RIFFwav"}]}
    with scope(skill_id="SK_FALLBACK"):
        out = _prep(proxy, monkeypatch, state, str(v), {"video": False, "audio": False})
    imgs = [p for p in out if p["type"] == "image_url"]
    texts = [p["text"] for p in out if p["type"] == "text"]
    assert len(imgs) == 3 and imgs[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert any(t.startswith("Transcript of video clip.mp4") for t in texts)
    assert any(t.startswith("Transcript of audio note.wav") for t in texts)
    assert not [p for p in out if p["type"] in ("video_url", "input_audio", "audio_url")]
    asr = proxy.calls("POST", "/v1/audio/transcriptions")
    assert len(asr) == 2 and all(h.get("X-Ecan-Skill-Id") == "SK_FALLBACK" for _, _, h, _ in asr)
    assert b"paraformer-v2" in asr[0][3]


def test_no_ffmpeg_degrades_to_text_note(proxy, tmp_path, monkeypatch):
    monkeypatch.setattr(media_inputs, "find_ffmpeg", lambda: None)
    v = tmp_path / "clip.mp4"
    v.write_bytes(MP4)
    out = _prep(proxy, monkeypatch, {"input": "hi"}, str(v), {"video": False, "audio": False})
    assert "ffmpeg is unavailable" in out[-1]["text"]


def test_non_vision_model_still_gets_audio_transcript(proxy, tmp_path, monkeypatch):
    a = tmp_path / "voice.mp3"
    a.write_bytes(b"ID3voice")
    out = _prep(proxy, monkeypatch, {"input": "hi"}, str(a), {"audio": False}, vision=False)
    assert out[-1]["text"].startswith("Transcript of audio voice.mp3")


# ── capabilities from GET /models ───────────────────────────────────────

def test_ecanai_media_input_caps_from_models(proxy, monkeypatch):
    monkeypatch.setattr(proxy_media_client, "_CAPS_CACHE", {})
    monkeypatch.setattr(ProxyMediaClient, "from_ecanai", classmethod(lambda cls: _client(proxy)))
    assert proxy_media_client.ecanai_media_input_caps("qwen3-vl-plus") == {"video": True, "audio": False}
    assert proxy_media_client.ecanai_media_input_caps("qwen3-omni-flash") == {"video": True, "audio": True}
    assert proxy_media_client.ecanai_media_input_caps("deepseek-v3") == {"video": False, "audio": False}
    assert proxy_media_client.ecanai_media_input_caps("unlisted-model") is None


def test_ecanai_media_input_caps_unreachable_falls_back(monkeypatch):
    monkeypatch.setattr(proxy_media_client, "_CAPS_CACHE", {})

    def boom(cls):
        raise RuntimeError("ecanai provider not configured")
    monkeypatch.setattr(ProxyMediaClient, "from_ecanai", classmethod(boom))
    assert proxy_media_client.ecanai_media_input_caps("qwen3-vl-plus") is None


# ── IPC: media.list_models ─────────────────────────────────────────────

def _list_models_ipc():
    from gui.ipc.types import create_request
    from gui.ipc.w2p_handlers.media_handler import handle_list_media_models
    return handle_list_media_models(create_request("media.list_models", {}), {})


def test_list_models_ipc(proxy, monkeypatch):
    monkeypatch.setattr(proxy_media_client, "_CAPS_CACHE", {})
    monkeypatch.setattr(ProxyMediaClient, "from_ecanai", classmethod(lambda cls: _client(proxy)))
    resp = _list_models_ipc()
    assert resp["status"] == "success"
    models = {m["id"]: m["capabilities"] for m in resp["result"]["models"]}
    assert models["cosyvoice-v2"]["formats"] == ["mp3", "wav"] and models["deepseek-v3"] == {}


def test_list_models_ipc_failure_is_empty_list(monkeypatch):
    monkeypatch.setattr(proxy_media_client, "_CAPS_CACHE", {})

    def boom(cls):
        raise RuntimeError("ecanai provider not configured")
    monkeypatch.setattr(ProxyMediaClient, "from_ecanai", classmethod(boom))
    resp = _list_models_ipc()
    assert resp["status"] == "success" and resp["result"] == {"models": []}


def test_media_caps_callable_is_only_asked_with_media(proxy, tmp_path, monkeypatch):
    asked = []

    def caps():
        asked.append(1)
        return {"video": True, "audio": False}
    _prep(proxy, monkeypatch, {"input": "hi"}, "", caps)
    assert asked == []
    v = tmp_path / "clip.mp4"
    v.write_bytes(MP4)
    out = _prep(proxy, monkeypatch, {"input": "hi"}, str(v), caps)
    assert asked == [1] and out[-1]["type"] == "video_url"


# ── prompt pulldowns + parameter-block overrides ─────────────────────────────

def test_param_block_parses_chinese_keys_and_units():
    ov, body = media_gen_node.split_param_block(
        "\n---\n时长: 10秒\n分辨率：1080p\n比例: 9:16\n尺寸: 1024 x 768\n未知: x\n---\n一只橘猫\n在海边")
    assert ov == {"durationSeconds": "10", "resolution": "1080p", "aspectRatio": "9:16", "size": "1024*768"}
    assert body == "一只橘猫\n在海边"


def test_text_without_a_real_block_is_untouched():
    for text in ("一只猫\n---\n脚注", "---\n时长: 10\n没有结尾", "---\n这是一段正文，不是参数\n---\n猫"):
        assert media_gen_node.split_param_block(text) == ({}, text)


def test_node_prompt_block_overrides_fields(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="video", modelName="seedance-1.0-pro",
                prompt="---\n时长: 10\n分辨率: 1080p\n比例: 9:16\n反向提示词: 模糊\n---\na dog on {{subject}}",
                durationSeconds=5, resolution="720p", aspectRatio="16:9", negativePrompt="text")
    assert out["result"]["media_job"]["status"] == "succeeded"
    req = list(proxy.jobs.values())[0]["req"]
    assert req["duration_seconds"] == 10 and req["resolution"] == "1080p" and req["aspect_ratio"] == "9:16"
    assert req["negative_prompt"] == "模糊" and req["prompt"] == "a dog on a red cat"
    assert media_gen_node._overrides.get() == {}


def test_node_saved_prompts_from_both_pulldowns(proxy, tmp_path, monkeypatch):
    from agent.ec_skills import build_node
    seen = []

    def fake_resolve(selection, inline_system, inline_user, *, skill_owner=""):
        seen.append((selection, skill_owner))
        return {"pr-1": ("---\n数量: 2\n---\n画一只{{subject}}", "", {}),
                "pr-2": ("低质量, 水印", "", {})}[selection]
    monkeypatch.setattr(build_node, "_resolve_prompt_templates", fake_resolve)
    _node(proxy, tmp_path, monkeypatch, mediaType="image", modelName="seedream-4.0",
          promptSelection="pr-1", prompt="ignored in-line text",
          negativePromptSelection="pr-2", negativePrompt="ignored", n=1)
    sent = json.loads(proxy.calls("POST", "/v1/images/generations")[0][3])
    assert sent["prompt"] == "画一只a red cat" and sent["n"] == 2 and sent["negative_prompt"] == "低质量, 水印"
    assert seen == [("pr-1", "owner"), ("pr-2", "owner")]


def test_node_in_line_selection_uses_the_text_box(proxy, tmp_path, monkeypatch):
    _node(proxy, tmp_path, monkeypatch, mediaType="image", modelName="seedream-4.0",
          promptSelection="in-line", prompt="draw {{subject}}", negativePromptSelection="in-line")
    sent = json.loads(proxy.calls("POST", "/v1/images/generations")[0][3])
    assert sent["prompt"] == "draw a red cat" and "negative_prompt" not in sent


# ── music ───────────────────────────────────────────────────────────────────

def test_node_music_submits_polls_and_downloads_every_take(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="music", modelName="suno-v5.5",
                prompt="upbeat city pop", lyrics="[Verse]\n{{subject}} on the roof", title="Roof",
                instrumental=False, durationSeconds=30, audioFormat="mp3", negativePrompt="ignored")
    assert out["result"]["media_job"]["status"] == "succeeded"
    media = out["result"]["media"]
    assert [open(m["path"], "rb").read() for m in media] == [b"ID3take1", b"ID3take2"]
    assert media[0]["title"] == "A" and media[0]["duration_seconds"] == 30
    req = list(proxy.jobs.values())[0]["req"]
    assert req == {"model": "suno-v5.5", "prompt": "upbeat city pop", "lyrics": "[Verse]\na red cat on the roof",
                   "title": "Roof", "instrumental": False, "duration_seconds": 30, "format": "mp3"}


def test_node_music_prompt_block_overrides(proxy, tmp_path, monkeypatch):
    _node(proxy, tmp_path, monkeypatch, mediaType="music", modelName="suno-v5.5",
          prompt="---\n纯音乐: 是\n歌名: 海边\n时长: 60秒\n---\nlo-fi piano", instrumental=False, title="x")
    req = list(proxy.jobs.values())[0]["req"]
    assert req["prompt"] == "lo-fi piano" and req["title"] == "海边" and req["duration_seconds"] == 60
    assert req["instrumental"] is True


def test_node_music_failed(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="music", modelName="suno-v5.5", prompt="fail")
    assert out["result"]["media_error"]["code"] == "content_policy"
    assert out["result"]["media_job"]["status"] == "failed"


def test_node_music_timeout_cancels(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="music", modelName="suno-v5.5", prompt="slow",
                timeoutSeconds=0.01)
    assert out["result"]["media_error"]["code"] == "client_timeout"
    assert out["result"]["media_job"]["status"] == "timeout"
    assert proxy.calls("DELETE", "/v1/music/mus1")


# ── hand-off to later nodes ─────────────────────────────────────────────────

def test_node_output_reaches_the_next_nodes_media_input(proxy, tmp_path, monkeypatch):
    from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables
    out = _node(proxy, tmp_path, monkeypatch, mediaType="image", modelName="seedream-4.0", prompt="a cat")
    published = out["tool_result"]["gen1"]
    path = out["result"]["media"][0]["path"]
    assert published["media_paths"] == path and published["media"] == out["result"]["media"]
    out["result"] = {"llm": "the next node replaced result"}   # media stays reachable via tool_result
    got = resolve_prompt_variables(variable_names=["media_paths"], state=out, mainwin=None)
    assert got["media_paths"] == path


def test_node_error_is_published_too(proxy, tmp_path, monkeypatch):
    out = _node(proxy, tmp_path, monkeypatch, mediaType="image", modelName="seedream-4.0", prompt="broke")
    assert out["tool_result"]["gen1"]["media_error"]["code"] == "insufficient_balance"
    assert out["tool_result"]["gen1"]["media_paths"] == ""


def test_mcp_input_can_name_the_media_node_by_title(proxy, tmp_path, monkeypatch):
    from agent.ec_skills.build_node import _resolve_mustache_template
    monkeypatch.setattr(media_gen_node, "_make_client", lambda: _client(proxy))
    monkeypatch.setattr(media_gen_node, "generated_medias_root", lambda: str(tmp_path / "generated_medias"))
    inputs = {k: {"type": "constant", "content": v}
              for k, v in {"mediaType": "image", "modelName": "seedream-4.0", "prompt": "a cat"}.items()}
    fn = media_gen_node.build_media_gen_node({"title": "MediaGen_1", "inputsValues": inputs},
                                             "media-gen_Ab3xZ", "sk", "owner", None)
    out = fn({"messages": [], "attributes": {}, "result": {}}, runtime=types.SimpleNamespace(context={}), store=None)
    path = out["result"]["media"][0]["path"]
    assert out["tool_result"]["media-gen_Ab3xZ"] is out["tool_result"]["MediaGen_1"]
    rendered = _resolve_mustache_template('{"input": {"files": "{{tool_result.MediaGen_1.media_paths}}"}}', out)
    assert path.replace("\\", "/") in rendered.replace("\\\\", "/").replace("\\", "/")

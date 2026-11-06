import base64
import hashlib
import hmac
import json
import urllib.parse

from agent.ec_skills import report_push as rp

DING = "https://oapi.dingtalk.com/robot/send?access_token=T0KEN"
WECOM = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=K3Y"
FEISHU = "https://open.feishu.cn/open-apis/bot/v2/hook/H00K"


def test_each_robot_gets_its_own_message_format():
    url, body = rp.build(DING, "店铺日巡检", "a\nb")
    assert url == DING and body["msgtype"] == "markdown" and body["markdown"]["text"] == "#### 店铺日巡检\n\na\n\nb"
    url, body = rp.build(WECOM, "店铺日巡检", "a")
    assert body == {"msgtype": "markdown", "markdown": {"content": "**店铺日巡检**\na"}}
    url, body = rp.build(FEISHU, "店铺日巡检", "a")
    assert body == {"msg_type": "text", "content": {"text": "店铺日巡检\na"}}


def test_signed_robots_get_the_documented_signature():
    url, _ = rp.build(DING, "t", "x", secret="SECabc", now_ms=1700000000000)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    want = base64.b64encode(hmac.new(b"SECabc", b"1700000000000\nSECabc", hashlib.sha256).digest()).decode()
    assert q["timestamp"] == ["1700000000000"] and q["sign"] == [want]
    _, body = rp.build(FEISHU, "t", "x", secret="s", now_ms=1700000000000)
    assert body["timestamp"] == "1700000000"
    assert body["sign"] == base64.b64encode(hmac.new(b"1700000000\ns", b"", hashlib.sha256).digest()).decode()


def test_long_text_is_cut_and_other_addresses_are_refused():
    _, body = rp.build(WECOM, "t", "字" * 5000)
    assert len(body["markdown"]["content"]) < 3600
    try:
        rp.build("https://example.com/hook", "t", "x")
        assert False
    except ValueError:
        pass


def test_config_from_task_vars_or_push_json_and_nothing_sent_without_one(tmp_path, monkeypatch):
    assert rp.push("t", "x", str(tmp_path)) == ""
    (tmp_path / "push.json").write_text(json.dumps({"webhook": WECOM}), encoding="utf-8")
    assert rp.config(str(tmp_path)) == (WECOM, "")
    assert rp.config(str(tmp_path), {"push_webhook": DING, "push_secret": "S"}) == (DING, "S")
    sent = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"errcode": 0}'

    def fake_open(req, timeout):
        sent["url"], sent["body"] = req.full_url, json.loads(req.data)
        return Reply()
    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_open)
    assert rp.push("日巡检", "ok", str(tmp_path)) == "sent" and sent["url"] == WECOM


def test_a_refusal_is_reported_without_the_webhook(tmp_path, monkeypatch):
    def boom(req, timeout):
        raise OSError(DING)
    monkeypatch.setattr(rp.urllib.request, "urlopen", boom)
    out = rp.push("t", "x", str(tmp_path), {"push_webhook": DING})
    assert out.startswith("群推送失败") and "T0KEN" not in out

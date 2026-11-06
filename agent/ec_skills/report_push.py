"""Send a chore's result to the merchant's own group (钉钉 / 企业微信 / 飞书 custom robot).

The merchant creates a custom robot in their group and gives eCan its webhook, either
as task variables (push_webhook, push_secret) or in <report folder>/push.json
({"webhook": "...", "secret": "..."}). The webhook carries the robot's token: it is
never logged or returned. No webhook -> nothing is sent.

Formats (each platform's documented custom-robot API):
  钉钉   oapi.dingtalk.com/robot/send?access_token=…  markdown; "加签" secret -> timestamp & sign
  企业微信 qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…  markdown
  飞书   open.feishu.cn/open-apis/bot/v2/hook/…  text; "签名校验" secret -> timestamp & sign
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from utils.logger_helper import logger_helper as logger

MAX_CHARS = 3500   # all three cap a message at a few thousand characters


def kind_of(url: str) -> str:
    host = urllib.parse.urlparse(str(url or "")).hostname or ""
    if host.endswith("dingtalk.com"):
        return "dingtalk"
    if host.endswith("qyapi.weixin.qq.com"):
        return "wecom"
    if host.endswith(("feishu.cn", "larksuite.com")):
        return "feishu"
    return ""


def build(url: str, title: str, text: str, secret: str = "", now_ms: Optional[int] = None) -> Tuple[str, Dict[str, Any]]:
    """(url to POST, JSON body) for *url*'s platform."""
    kind = kind_of(url)
    text = text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n…（完整内容见结果表）"
    now_ms = now_ms or int(time.time() * 1000)
    if kind == "dingtalk":
        if secret:
            sign = base64.b64encode(hmac.new(secret.encode(), f"{now_ms}\n{secret}".encode(), hashlib.sha256).digest())
            url += ("&" if "?" in url else "?") + f"timestamp={now_ms}&sign={urllib.parse.quote_plus(sign.decode())}"
        md = f"#### {title}\n\n" + text.replace("\n", "\n\n")
        return url, {"msgtype": "markdown", "markdown": {"title": title, "text": md}}
    if kind == "wecom":
        return url, {"msgtype": "markdown", "markdown": {"content": f"**{title}**\n{text}"}}
    if kind == "feishu":
        body: Dict[str, Any] = {"msg_type": "text", "content": {"text": f"{title}\n{text}"}}
        if secret:
            ts = now_ms // 1000
            body["timestamp"] = str(ts)
            body["sign"] = base64.b64encode(hmac.new(f"{ts}\n{secret}".encode(), b"", hashlib.sha256).digest()).decode()
        return url, body
    raise ValueError("webhook must be a 钉钉 / 企业微信 / 飞书 group robot address")


def config(folder: str, task_vars: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """(webhook, secret): task variables first, else <folder>/push.json."""
    tv = task_vars or {}
    if tv.get("push_webhook"):
        return str(tv["push_webhook"]).strip(), str(tv.get("push_secret") or "").strip()
    try:
        with open(os.path.join(folder, "push.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        return str(cfg.get("webhook") or "").strip(), str(cfg.get("secret") or "").strip()
    except (OSError, ValueError):
        return "", ""


def push(title: str, text: str, folder: str, task_vars: Optional[Dict[str, Any]] = None) -> str:
    """Send to the configured group. Returns "" (not configured), "sent", or a short error.
    Never raises; never logs the webhook."""
    url, secret = config(folder, task_vars)
    if not url:
        return ""
    kind = kind_of(url) or "unknown"
    try:
        post_url, body = build(url, title, text, secret)
        req = urllib.request.Request(post_url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            reply = json.loads(r.read().decode("utf-8", "replace") or "{}")
        code = reply.get("errcode", reply.get("code", reply.get("StatusCode", 0)))
        if code not in (0, None):
            msg = str(reply.get("errmsg") or reply.get("msg") or code)[:80]
            logger.warning(f"[report-push] {kind}: refused: {msg}")
            return f"群推送失败：{msg}"
        logger.info(f"[report-push] {kind}: sent {len(text)} chars")
        return "sent"
    except Exception as exc:
        logger.warning(f"[report-push] {kind}: {type(exc).__name__}")
        return f"群推送失败：{type(exc).__name__}"

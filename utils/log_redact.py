"""Mask secrets in log text.

Applied by the log formatter to every line written (utils/logger_helper.py)
and by the bug-report packager to log files that were written before it
existed. Log files leave the PC (bug reports, support zips), so a secret in a
log is a leaked secret.

What a 2026-10-22 scan of a dev PC's logs found in clear text: the login
password (GraphQL variables), LLM API keys ("llm config: ... api_key=..."),
our login JWTs inside WebSocket URLs, login tokens in the login response, an
API key in a cloud response, 抖店's own session cookies / csrf tokens / msToken
(WS capture, request headers), signed COS / S3 links with temporary
credentials, and environment variables with keys.

Masks the VALUE and keeps the name, so a line still shows what was there:
``'password': '***'``, ``api_key=***``, ``Bearer ***``, ``eyJ***`` (a JWT),
``...&q-signature=***``. Lines with no secret-looking marker are returned as
they are (cheap substring check first).
"""
from __future__ import annotations

import re

MASK = "***"

# Cheap pre-check: a line without any of these cannot match the patterns below.
_MARKERS = ("eyJ", "assword", "asswd", "pwd", "ecret", "oken", "pi_key", "pikey", "piKey", "PI_KEY",
            "PIKEY", "ccess_key", "ccessKey", "uthorization", "Bearer", "bearer", "sk-", "AKID",
            "ignature", "ecurity-", "ecurity_", "ookie", "csrf", "Csrf", "CSRF", "redential",
            "msToken", "PRIVATE KEY", "sign=", "Bogus", "bogus", "verifyFp", "ession_id", "essionid",
            "?key=", "&key=")

# Key names whose value is a secret. Matched at the END of the key name, so
# "NEO4J_PASSWORD" / "x-tt-passport-csrf-token" / "EMBEDDING_BINDING_API_KEY"
# count while "tokens", "max_tokens", "token_source", "input_tokens" do not.
_SECRET_NAME = (r"(?<![\w.-])[\w.-]*?(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?key(?:[_-]?id)?"
                r"|secret[_-]?key|private[_-]?key|token|authorization|cookie|credentials?"
                r"|session[_-]?id|sessionid|sid_tt|sessionid_ss)")

# "name": "value"  /  'name': 'value'  /  name="value"
_KV_QUOTED = re.compile(
    r"""(?P<k>(?P<q>["']?)(?P<name>""" + _SECRET_NAME + r""")(?P=q))(?P<sep>\s*[:=]\s*)(?P<vq>["'])(?P<v>.*?)(?P=vq)""",
    re.IGNORECASE)
# name=value  /  name: value   (unquoted)
_KV_BARE = re.compile(
    r"""(?P<k>(?P<name>""" + _SECRET_NAME + r"""))(?P<sep>=|:\s+)(?P<v>[^\s,;&'"{}\[\]()|<>]{4,})""",
    re.IGNORECASE)
# secret query parameters in URLs
_URL_PARAM = re.compile(
    r"""(?P<k>[?&](?:q-signature|q-ak|x-cos-security-token|x-amz-signature|x-amz-security-token"""
    r"""|x-amz-credential|access_token|refresh_token|id_token|token|msToken|a_bogus|x-bogus|verifyFp"""
    r"""|fp|sign|signature|pigeon_sign|key|apikey|api_key|auth|ticket|sessionid)=)(?P<v>[^&\s"'<>#\\]+)""",
    re.IGNORECASE)
# Each pattern starts only where its token can start (never inside a run of
# token characters), so a scan stays linear on long base64 / JSON lines.
_JWT = re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")
_BEARER = re.compile(r"(?P<k>\b[Bb]earer\s+)(?P<v>[A-Za-z0-9._~+/=-]{8,})")
_SK = re.compile(r"(?<![A-Za-z0-9_-])sk-(?!x{6})(?:proj-|ant-)?[A-Za-z0-9_-]{12,}")
_AKID = re.compile(r"(?<![A-Za-z0-9])AKID[A-Za-z0-9]{12,}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S)

# Values that are not secrets (placeholders, already masked, empty-ish).
_HARMLESS = re.compile(r"^(?:\*+|none|null|true|false|undefined|n/a|-+|<[^>]*>|\[redacted\]|"
                       r"sk-x{6,}.*|x{6,}|\.\.\.|0)$", re.IGNORECASE)


def _masked(value: str) -> bool:
    v = value.strip()
    return len(v) < 4 or bool(_HARMLESS.match(v)) or v.startswith(MASK)


def _kv_quoted(m: "re.Match") -> str:
    if _masked(m.group("v")):
        return m.group(0)
    return f"{m.group('k')}{m.group('sep')}{m.group('vq')}{MASK}{m.group('vq')}"


def _kv_bare(m: "re.Match") -> str:
    if _masked(m.group("v")):
        return m.group(0)
    return f"{m.group('k')}{m.group('sep')}{MASK}"


def _url_param(m: "re.Match") -> str:
    return m.group("k") + MASK


def scrub(text: str) -> str:
    """*text* with secret values masked. Never raises."""
    if not text or not isinstance(text, str):
        return text
    if not any(mk in text for mk in _MARKERS):
        return text
    try:
        text = _PEM.sub("-----PRIVATE KEY " + MASK + "-----", text)
        text = _JWT.sub("eyJ" + MASK, text)
        text = _BEARER.sub(lambda m: m.group("k") + MASK, text)
        text = _SK.sub("sk-" + MASK, text)
        text = _AKID.sub("AKID" + MASK, text)
        text = _URL_PARAM.sub(_url_param, text)
        text = _KV_QUOTED.sub(_kv_quoted, text)
        text = _KV_BARE.sub(_kv_bare, text)
    except Exception:
        pass
    return text

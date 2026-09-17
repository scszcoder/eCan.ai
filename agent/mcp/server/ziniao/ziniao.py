"""紫鸟 / Ziniao SuperBrowser local-API client.

Mirrors ``agent/mcp/server/ads_power/ads_power.py``: start a store's browser
and hand back the CDP debugging port so browser-use can attach.

Protocol notes (these are the bits that differ from AdsPower and that cost
time if you assume otherwise):

* The local API is served by the **running SuperBrowser client** on the
  machine, not by a cloud endpoint. The port is shown in the client and
  differs per install, so it is a Settings field, not a constant.
* Auth is **company + username + password**, passed as a JSON *string* inside
  the ``userInfo`` field — not a bearer token and not an API key. A ziniao
  account is the credential; there is no separate key to issue.
* A store is addressed by ``browserOauth`` (the store id), which is what the
  node's/Settings' ``profile_id`` carries.
* Both an HTTP mode and a raw-socket mode exist. HTTP is used here because it
  is far easier to time out and log; ziniao's own docs require a timeout of
  120s or more, because starting a store environment is slow.
* ``startBrowser`` answers with ``debuggingPort`` and ``launcherPage``.
  ``statusCode == 0`` means success; anything else puts a reason in ``err``.

Reference: https://open.ziniao.com (开放平台 / OpenAPI docs).
"""

import json
import socket
import uuid

import requests

from utils.logger_helper import logger_helper as logger

# Starting a store environment is genuinely slow — the client may boot a
# profile, sync cookies and wait on the proxy before answering.
START_TIMEOUT_S = 180


def _endpoint(api_url, api_port):
    """Normalize the configured local-API endpoint to 'scheme://host:port'."""
    base = str(api_url or "").strip().rstrip("/") or "http://127.0.0.1"
    if not base.startswith(("http://", "https://")):
        base = f"http://{base}"
    head, _, tail = base.rpartition(":")
    if head.startswith(("http://", "https://")) and tail.isdigit():
        return base
    port = int(api_port or 0)
    if not port:
        raise ValueError(
            "Ziniao local API port is not set (Settings > Browser Automation > "
            "Providers). The SuperBrowser client shows the port it listens on."
        )
    return f"{base}:{port}"


def _user_info(company, username, password):
    """ziniao wants the credentials as a JSON STRING inside the request."""
    return json.dumps(
        {"company": str(company or ""), "username": str(username or ""), "password": str(password or "")},
        ensure_ascii=False,
    )


def _post_http(url, payload):
    response = requests.post(url, json=payload, timeout=START_TIMEOUT_S)
    response.raise_for_status()
    return response.json()


def _post_socket(host, port, payload):
    """Raw-socket fallback: the client also speaks line-delimited JSON."""
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.create_connection((host, port), timeout=START_TIMEOUT_S) as sock:
        sock.sendall(data)
        chunks = []
        sock.settimeout(START_TIMEOUT_S)
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if chunk.endswith(b"\n") or b"}" in chunk:
                break
    return json.loads(b"".join(chunks).decode("utf-8", errors="replace"))


def call_ziniao(action, *, api_url, api_port, company, username, password, extra=None, use_socket=False):
    """One request against the local API. Returns the parsed response dict.

    Raises on transport failure or a non-zero ``statusCode`` so callers get a
    message worth showing rather than a silent None.
    """
    payload = {
        "action": action,
        "userInfo": _user_info(company, username, password),
        "requestId": uuid.uuid4().hex,
    }
    payload.update(extra or {})

    endpoint = _endpoint(api_url, api_port)
    logger.info(f"[Ziniao] {action} -> {endpoint} (socket={use_socket})")

    if use_socket:
        host = endpoint.split("://", 1)[1].rsplit(":", 1)[0]
        port = int(endpoint.rsplit(":", 1)[1])
        result = _post_socket(host, port, payload)
    else:
        result = _post_http(endpoint, payload)

    if not isinstance(result, dict):
        raise RuntimeError(f"Ziniao {action}: unexpected response {result!r}")

    status = result.get("statusCode")
    if status not in (0, "0", None):
        raise RuntimeError(f"Ziniao {action} failed (statusCode={status}): {result.get('err') or result}")
    return result


def startZiniaoBrowser(
    *,
    api_url,
    api_port,
    company,
    username,
    password,
    browser_oauth,
    headless=False,
    use_socket=False,
):
    """Start a store's browser. Returns (debugging_port, launcher_page, raw).

    ``browser_oauth`` is the store id (店铺 id) — Settings calls it profile_id
    so it lines up with the AdsPower field next to it.
    """
    if not str(browser_oauth or "").strip():
        raise ValueError(
            "Ziniao store id (browserOauth) is required — set it on the node or in "
            "Settings > Browser Automation > Providers."
        )

    result = call_ziniao(
        "startBrowser",
        api_url=api_url,
        api_port=api_port,
        company=company,
        username=username,
        password=password,
        use_socket=use_socket,
        extra={
            "browserOauth": str(browser_oauth).strip(),
            "isHeadless": bool(headless),
        },
    )

    debugging_port = result.get("debuggingPort") or result.get("debugging_port")
    launcher_page = result.get("launcherPage") or result.get("launcher_page") or ""
    if not debugging_port:
        raise RuntimeError(f"Ziniao startBrowser returned no debuggingPort: {result}")

    logger.info(f"[Ziniao] store {browser_oauth} started on debugging port {debugging_port}")
    return int(debugging_port), launcher_page, result


def stopZiniaoBrowser(*, api_url, api_port, company, username, password, browser_oauth, use_socket=False):
    """Close a store's browser. Best-effort — never raises into a teardown path."""
    try:
        return call_ziniao(
            "stopBrowser",
            api_url=api_url,
            api_port=api_port,
            company=company,
            username=username,
            password=password,
            use_socket=use_socket,
            extra={"browserOauth": str(browser_oauth or "").strip()},
        )
    except Exception as exc:
        logger.warning(f"[Ziniao] stopBrowser failed (ignored): {exc}")
        return None


def listZiniaoBrowsers(*, api_url, api_port, company, username, password, use_socket=False):
    """The account's stores — used to confirm credentials and find a store id."""
    return call_ziniao(
        "getBrowserList",
        api_url=api_url,
        api_port=api_port,
        company=company,
        username=username,
        password=password,
        use_socket=use_socket,
    )

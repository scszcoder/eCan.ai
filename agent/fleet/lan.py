"""The LAN route: the receiver listens for one upload, the source connects out.

The receiver listens -- not the source -- so for Fetch logs the firewall prompt
(if any) appears on the machine the operator is sitting at, and an unattended
platoon never accepts inbound connections.

The listener serves exactly one path, ``PUT /fleet/<transfer_id>``, behind a
one-time token that only machines of the account can read from the cloud
record. What arrives is sealed (``agent.fleet.seal``), so the token keeps out
junk, not eavesdroppers.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Optional

from utils.logger_helper import logger_helper as logger

TOKEN_HEADER = "X-Ecan-Transfer-Token"
MAX_BYTES = 4 * 1024 * 1024 * 1024
CONNECT_TIMEOUT_S = 2.0


def _lan_address(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.version == 4 and not ip.is_loopback and (ip.is_private or ip.is_link_local)


def private_addrs() -> List[str]:
    """This machine's private IPv4 addresses, the ones a LAN peer could reach."""
    out: List[str] = []
    try:
        import psutil
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family == socket.AF_INET and _lan_address(a.address) and a.address not in out:
                    out.append(a.address)
    except Exception as exc:
        logger.debug(f"[fleet-lan] interface list unavailable: {exc}")
    return out


class Receiver:
    """A one-upload HTTP listener on all interfaces, on a free port."""

    def __init__(self, transfer_id: str, dest_path: str, token: str):
        self.transfer_id = transfer_id
        self.dest_path = dest_path
        self.token = token
        self.received = threading.Event()
        self._server: Optional[ThreadingHTTPServer] = None

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else 0

    def start(self) -> int:
        recv = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):   # no access log: the path names the transfer
                pass

            def do_PUT(self):
                if self.path != f"/fleet/{recv.transfer_id}":
                    return self._reply(404)
                if not hmac.compare_digest(self.headers.get(TOKEN_HEADER, ""), recv.token):
                    return self._reply(403)
                if recv.received.is_set():
                    return self._reply(409)
                try:
                    length = int(self.headers.get("Content-Length") or -1)
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_BYTES:
                    return self._reply(411 if length < 0 else 413)
                part = recv.dest_path + ".part"
                try:
                    left = length
                    with open(part, "wb") as f:
                        while left:
                            chunk = self.rfile.read(min(left, 1024 * 1024))
                            if not chunk:
                                raise IOError("sender went away")
                            f.write(chunk)
                            left -= len(chunk)
                    os.replace(part, recv.dest_path)
                except Exception as exc:
                    logger.warning(f"[fleet-lan] receive failed: {exc}")
                    try:
                        os.remove(part)
                    except OSError:
                        pass
                    return self._reply(500)
                recv.received.set()
                self._reply(200)

            def _reply(self, code):
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self._server = ThreadingHTTPServer(("0.0.0.0", 0), _Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name=f"fleet-recv-{self.transfer_id[:8]}",
                         daemon=True).start()
        logger.info(f"[fleet-lan] listening on port {self.port} for transfer {self.transfer_id[:8]}")
        return self.port

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None


def send(addrs: List[str], port: int, token: str, transfer_id: str, path: str,
         timeout: float = 600.0) -> str:
    """PUT *path* to the first reachable private address; that address, or "".

    Public addresses are never tried: reaching a receiver across the internet
    is the cloud route's job, and a LAN listener has no business being exposed.
    """
    import requests
    if not port or not token:
        return ""
    for addr in addrs or []:
        if not _lan_address(str(addr)):
            continue
        try:
            socket.create_connection((addr, int(port)), timeout=CONNECT_TIMEOUT_S).close()
        except OSError:
            continue
        try:
            with open(path, "rb") as f:
                resp = requests.put(f"http://{addr}:{int(port)}/fleet/{transfer_id}", data=f,
                                    headers={TOKEN_HEADER: token,
                                             "Content-Type": "application/octet-stream"},
                                    timeout=timeout)
            if resp.status_code == 200:
                return str(addr)
            logger.warning(f"[fleet-lan] {addr} refused the upload (HTTP {resp.status_code})")
        except Exception as exc:
            logger.warning(f"[fleet-lan] upload to {addr} failed: {exc}")
    return ""

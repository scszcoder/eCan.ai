"""A local, no-auth SOCKS5 front for an authenticated upstream SOCKS5 proxy.

Why this exists: Chromium cannot authenticate to a SOCKS5 proxy. There is no
command-line form for it, and the extension `onAuthRequired` hook that rescues
authenticated HTTP proxies never fires for SOCKS — Chrome simply fails the
connection. Anti-detect browsers work around it with a patched binary; we run a
relay instead.

    Chromium --proxy-server=socks5://127.0.0.1:<local>
        -> this relay (no auth)
            -> upstream socks5://user:pass@host:port

Discovered 2026-09-17 migrating an AdsPower profile: the browser reached
nothing at all, while the same proxy answered fine from curl with credentials.
The credentials live in the profile's `user_proxy_config`, not in the browser's
command line.

DNS is resolved at the exit node (``rdns=True``), i.e. socks5h semantics —
resolving locally would leak the visited hostnames to the local resolver and
can also route to a geographically wrong IP.
"""

import socket
import struct
import threading
from typing import Callable, Optional, Tuple

from utils.logger_helper import logger_helper as logger

_SOCKS_VERSION = 5
_CMD_CONNECT = 1
_ATYP_IPV4, _ATYP_DOMAIN, _ATYP_IPV6 = 1, 3, 4
_REPLY_OK, _REPLY_GENERAL_FAIL, _REPLY_CMD_UNSUPPORTED = 0, 1, 7


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly *n* bytes or raise. Short reads are the norm on sockets."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed mid-message")
        buf += chunk
    return buf


def _pump(src: socket.socket, dst: socket.socket) -> None:
    """Copy bytes one way until either side closes."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _handle(client: socket.socket, upstream: Tuple[str, int, str, str]) -> None:
    host, port, user, password = upstream
    try:
        # --- greeting: accept only "no authentication required" ---
        ver, nmethods = struct.unpack("!BB", _recv_exact(client, 2))
        _recv_exact(client, nmethods)  # method list, ignored
        if ver != _SOCKS_VERSION:
            client.close()
            return
        client.sendall(struct.pack("!BB", _SOCKS_VERSION, 0))

        # --- request ---
        ver, cmd, _rsv, atyp = struct.unpack("!BBBB", _recv_exact(client, 4))
        if atyp == _ATYP_IPV4:
            dest = socket.inet_ntoa(_recv_exact(client, 4))
        elif atyp == _ATYP_DOMAIN:
            dest = _recv_exact(client, _recv_exact(client, 1)[0]).decode("idna")
        elif atyp == _ATYP_IPV6:
            dest = socket.inet_ntop(socket.AF_INET6, _recv_exact(client, 16))
        else:
            client.sendall(struct.pack("!BBBBIH", _SOCKS_VERSION,
                                       _REPLY_GENERAL_FAIL, 0, _ATYP_IPV4, 0, 0))
            client.close()
            return
        dport = struct.unpack("!H", _recv_exact(client, 2))[0]

        if cmd != _CMD_CONNECT:
            client.sendall(struct.pack("!BBBBIH", _SOCKS_VERSION,
                                       _REPLY_CMD_UNSUPPORTED, 0, _ATYP_IPV4, 0, 0))
            client.close()
            return

        # --- dial upstream WITH credentials ---
        import socks  # PySocks

        remote = socks.socksocket()
        remote.set_proxy(socks.SOCKS5, host, port, rdns=True,
                         username=user, password=password)
        remote.settimeout(30)
        try:
            remote.connect((dest, dport))
        except Exception as exc:
            logger.warning(f"[socks-relay] upstream CONNECT {dest}:{dport} failed: {exc}")
            client.sendall(struct.pack("!BBBBIH", _SOCKS_VERSION,
                                       _REPLY_GENERAL_FAIL, 0, _ATYP_IPV4, 0, 0))
            client.close()
            return
        remote.settimeout(None)

        # Report success. The bound address is informational for a CONNECT and
        # every client ignores it, so 0.0.0.0:0 is fine and avoids a lookup.
        client.sendall(struct.pack("!BBBBIH", _SOCKS_VERSION,
                                   _REPLY_OK, 0, _ATYP_IPV4, 0, 0))

        threading.Thread(target=_pump, args=(client, remote), daemon=True).start()
        _pump(remote, client)
    except Exception as exc:
        logger.debug(f"[socks-relay] connection ended: {type(exc).__name__}: {exc}")
    finally:
        try:
            client.close()
        except OSError:
            pass


def start_relay(
    upstream_host: str,
    upstream_port: int,
    username: str = "",
    password: str = "",
    listen_host: str = "127.0.0.1",
    listen_port: int = 0,
) -> Tuple[int, Callable[[], None]]:
    """Start the relay and return ``(port, stop)``.

    ``listen_port=0`` picks a free port, which is what you usually want — the
    relay is per-browser and a fixed port collides when two profiles run.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((listen_host, listen_port))
    srv.listen(128)
    bound_port = srv.getsockname()[1]
    stop_flag = threading.Event()

    def _serve() -> None:
        while not stop_flag.is_set():
            try:
                client, _addr = srv.accept()
            except OSError:
                break
            threading.Thread(
                target=_handle,
                args=(client, (upstream_host, upstream_port, username, password)),
                daemon=True,
            ).start()

    threading.Thread(target=_serve, daemon=True, name="socks-relay").start()
    logger.info(
        f"[socks-relay] listening on {listen_host}:{bound_port} -> "
        f"{upstream_host}:{upstream_port} (auth={'yes' if username else 'no'})"
    )

    def _stop() -> None:
        stop_flag.set()
        try:
            srv.close()
        except OSError:
            pass

    return bound_port, _stop

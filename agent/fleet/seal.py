"""End-to-end encryption for fleet transfers: only the receiver can open a bundle.

The receiver makes an X25519 key pair per transfer and publishes the public
half. The sender derives a key from its own ephemeral pair (X25519 + HKDF bound
to the transfer id) and writes the file as AES-256-GCM chunks. The cloud, which
relays the public key and may store the ciphertext, can read neither.

Format::

    b"ECF1" | sender ephemeral public key (32) | chunk*
    chunk  = length (4, big-endian) | ciphertext (length)

Chunk ``n`` uses nonce ``0000 || n (8, big-endian)``; its associated data marks
whether it is the last chunk, so a truncated file fails to open instead of
yielding a shorter plaintext.
"""

from __future__ import annotations

import base64
import os
import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"ECF1"
CHUNK = 1024 * 1024
_MAX_CIPHERTEXT = CHUNK + 16


class SealError(ValueError):
    """The bundle is not ours, was tampered with, or was cut short."""


def new_keypair() -> "tuple[bytes, str]":
    """``(private_bytes, public_b64)`` for one transfer."""
    priv = X25519PrivateKey.generate()
    raw_priv = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())
    return raw_priv, _b64(_pub_raw(priv.public_key()))


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _pub_raw(pub: X25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _key(shared: bytes, eph_pub: bytes, receiver_pub: bytes, transfer_id: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=eph_pub + receiver_pub,
                info=b"ecan-fleet-v1|" + transfer_id.encode("utf-8")).derive(shared)


def _aad(transfer_id: str, final: bool) -> bytes:
    return transfer_id.encode("utf-8") + (b"|F" if final else b"|M")


def _nonce(n: int) -> bytes:
    return b"\x00\x00\x00\x00" + struct.pack(">Q", n)


def seal_file(src: str, dst: str, receiver_pub_b64: str, transfer_id: str) -> None:
    """Encrypt *src* into *dst* for the holder of *receiver_pub_b64*."""
    try:
        receiver_pub = base64.b64decode(receiver_pub_b64)
        receiver = X25519PublicKey.from_public_bytes(receiver_pub)
    except Exception as exc:
        raise SealError(f"receiver key is not an X25519 public key: {exc}") from exc
    eph = X25519PrivateKey.generate()
    eph_pub = _pub_raw(eph.public_key())
    aes = AESGCM(_key(eph.exchange(receiver), eph_pub, receiver_pub, transfer_id))
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(MAGIC + eph_pub)
        n = 0
        block = fin.read(CHUNK)
        while True:
            nxt = fin.read(CHUNK)
            final = not nxt
            ct = aes.encrypt(_nonce(n), block, _aad(transfer_id, final))
            fout.write(struct.pack(">I", len(ct)) + ct)
            if final:
                break
            block, n = nxt, n + 1


def open_file(src: str, dst: str, receiver_priv: bytes, transfer_id: str) -> None:
    """Decrypt *src* into *dst*. Raises :class:`SealError`; *dst* is removed on failure."""
    try:
        _open(src, dst, receiver_priv, transfer_id)
    except Exception:
        try:
            os.remove(dst)
        except OSError:
            pass
        raise


def _open(src: str, dst: str, receiver_priv: bytes, transfer_id: str) -> None:
    priv = X25519PrivateKey.from_private_bytes(receiver_priv)
    receiver_pub = _pub_raw(priv.public_key())
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        head = fin.read(len(MAGIC) + 32)
        if len(head) != len(MAGIC) + 32 or not head.startswith(MAGIC):
            raise SealError("not a fleet bundle")
        eph_pub = head[len(MAGIC):]
        try:
            shared = priv.exchange(X25519PublicKey.from_public_bytes(eph_pub))
        except Exception as exc:
            raise SealError(f"bad sender key: {exc}") from exc
        aes = AESGCM(_key(shared, eph_pub, receiver_pub, transfer_id))
        n, finished = 0, False
        while True:
            raw_len = fin.read(4)
            if not raw_len:
                break
            if finished:
                raise SealError("data after the final chunk")
            if len(raw_len) != 4:
                raise SealError("cut short")
            (length,) = struct.unpack(">I", raw_len)
            if length > _MAX_CIPHERTEXT:
                raise SealError("chunk too large")
            ct = fin.read(length)
            if len(ct) != length:
                raise SealError("cut short")
            for final in (False, True):
                try:
                    fout.write(aes.decrypt(_nonce(n), ct, _aad(transfer_id, final)))
                    finished = final
                    break
                except Exception:
                    continue
            else:
                raise SealError("tampered, or sealed for another receiver")
            n += 1
        if not finished:
            raise SealError("cut short")

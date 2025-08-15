#!/usr/bin/env python3
"""
Verify a file against a Sparkle 2 edSignature (Ed25519, base64) using a public key PEM.

Usage:
  python scripts/verify_ed25519_signature.py --file <path> --signature <base64-or-file> --public-key <pubkey.pem>

Notes:
- Signature is the base64 value found in appcast enclosure@"sparkle:edSignature".
- Public key must be an Ed25519 public key in PEM (SubjectPublicKeyInfo) format.
- Exit code 0 on success; non-zero on failure. Prints a concise result line.

Extras:
- Use --print-sparkle-key to print SUPublicEDKey (base64 raw 32-byte key) for Sparkle 2 Info.plist derived from the PEM.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature


def load_public_key(pem_path: Path) -> ed25519.Ed25519PublicKey:
    data = pem_path.read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, ed25519.Ed25519PublicKey):
        raise TypeError("Public key is not Ed25519")
    return key


def read_signature(sig_arg: str) -> bytes:
    p = Path(sig_arg)
    if p.exists() and p.is_file():
        raw = p.read_text(encoding="utf-8").strip()
    else:
        raw = sig_arg.strip()
    # Expect base64; try decode first
    try:
        return base64.b64decode(raw)
    except Exception:
        # fallback: maybe hex
        try:
            return bytes.fromhex(raw)
        except Exception:
            raise ValueError("Signature must be base64 (preferred) or hex")


def print_sparkle_key(pub: ed25519.Ed25519PublicKey) -> None:
    # Sparkle 2 expects base64 of the raw 32-byte public key for SUPublicEDKey
    raw = pub.public_bytes(encoding=serialization.Encoding.Raw,
                           format=serialization.PublicFormat.RawPublicKey)
    print(base64.b64encode(raw).decode("ascii"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify Ed25519 signature (Sparkle 2)")
    ap.add_argument("--file", required=True, help="Path to file to verify")
    ap.add_argument("--signature", required=True, help="Base64 signature or path to a signature file")
    ap.add_argument("--public-key", required=True, help="Path to Ed25519 public key PEM")
    ap.add_argument("--print-sparkle-key", action="store_true", help="Print SUPublicEDKey string derived from PEM and exit")
    args = ap.parse_args()

    pub = load_public_key(Path(args.public_key))

    if args.print_sparkle_key:
        print_sparkle_key(pub)
        return 0

    sig = read_signature(args.signature)
    data = Path(args.file).read_bytes()

    try:
        pub.verify(sig, data)
        print("OK: signature verified (Ed25519)")
        return 0
    except InvalidSignature:
        print("FAIL: invalid signature")
        return 2
    except Exception as e:
        print(f"ERROR: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())


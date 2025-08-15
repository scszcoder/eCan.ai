#!/usr/bin/env python3
"""
Set Sparkle 2 SUPublicEDKey into a macOS app's Info.plist.

This tool derives the SUPublicEDKey (base64 of 32-byte raw Ed25519 public key)
from either:
  - ED25519_PRIVATE_KEY environment variable (PEM or base64-encoded PEM), or
  - a provided public/private PEM file via --public-key/--private-key

Usage:
  python scripts/infoplist_set_su_public_key.py --info-plist "dist/YourApp.app/Contents/Info.plist"
  python scripts/infoplist_set_su_public_key.py --info-plist Info.plist --public-key ed25519-public.pem
  python scripts/infoplist_set_su_public_key.py --info-plist Info.plist --private-key ed25519-private.pem

Exit code 0 on success; non-zero on failure.
Requires: cryptography
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import plistlib
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def load_pem_or_b64(value: str) -> bytes:
    data = value.strip().encode('utf-8')
    if b"BEGIN" in data:
        return data
    try:
        return base64.b64decode(data)
    except Exception:
        return data


def derive_public_raw_from_sources(public_key_path: Optional[Path], private_key_path: Optional[Path]) -> bytes:
    # Priority: explicit public, then explicit private, then env private, then env public
    if public_key_path:
        pub_pem = public_key_path.read_bytes()
        pub = serialization.load_pem_public_key(pub_pem)
        if not isinstance(pub, ed25519.Ed25519PublicKey):
            raise TypeError("Provided public key is not Ed25519")
        return pub.public_bytes(encoding=serialization.Encoding.Raw,
                                format=serialization.PublicFormat.RawPublicKey)

    if private_key_path:
        priv_pem = private_key_path.read_bytes()
        priv = serialization.load_pem_private_key(priv_pem, password=None)
        if not isinstance(priv, ed25519.Ed25519PrivateKey):
            raise TypeError("Provided private key is not Ed25519")
        pub = priv.public_key()
        return pub.public_bytes(encoding=serialization.Encoding.Raw,
                                format=serialization.PublicFormat.RawPublicKey)

    env_priv = os.environ.get('ED25519_PRIVATE_KEY')
    if env_priv:
        pem_bytes = load_pem_or_b64(env_priv)
        priv = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(priv, ed25519.Ed25519PrivateKey):
            raise TypeError("ED25519_PRIVATE_KEY is not Ed25519")
        pub = priv.public_key()
        return pub.public_bytes(encoding=serialization.Encoding.Raw,
                                format=serialization.PublicFormat.RawPublicKey)

    env_pub = os.environ.get('ED25519_PUBLIC_KEY')
    if env_pub:
        pem_bytes = load_pem_or_b64(env_pub)
        try:
            pub = serialization.load_pem_public_key(pem_bytes)
            if not isinstance(pub, ed25519.Ed25519PublicKey):
                raise TypeError("ED25519_PUBLIC_KEY is not Ed25519")
            return pub.public_bytes(encoding=serialization.Encoding.Raw,
                                    format=serialization.PublicFormat.RawPublicKey)
        except Exception:
            # Maybe provided as base64 raw key
            try:
                raw = base64.b64decode(env_pub)
                if len(raw) != 32:
                    raise ValueError("ED25519_PUBLIC_KEY base64 not 32 bytes raw")
                return raw
            except Exception as e:
                raise ValueError(f"Failed to parse ED25519_PUBLIC_KEY: {e}")

    raise RuntimeError("No key provided. Set ED25519_PRIVATE_KEY/ED25519_PUBLIC_KEY or pass --public-key/--private-key")


def set_su_public_ed_key(info_plist: Path, sparkle_key_b64: str) -> None:
    with open(info_plist, 'rb') as f:
        data = plistlib.load(f)
    data['SUPublicEDKey'] = sparkle_key_b64
    with open(info_plist, 'wb') as f:
        plistlib.dump(data, f)


def main() -> int:
    ap = argparse.ArgumentParser(description='Set SUPublicEDKey in Info.plist')
    ap.add_argument('--info-plist', required=True, help='Path to Info.plist')
    ap.add_argument('--public-key', help='Path to Ed25519 public key PEM')
    ap.add_argument('--private-key', help='Path to Ed25519 private key PEM')
    args = ap.parse_args()

    info_plist = Path(args.info_plist)
    if not info_plist.exists():
        print(f"Info.plist not found: {info_plist}")
        return 2

    pub_raw = derive_public_raw_from_sources(Path(args.public_key) if args.public_key else None,
                                             Path(args.private_key) if args.private_key else None)
    sparkle_key_b64 = base64.b64encode(pub_raw).decode('ascii')
    set_su_public_ed_key(info_plist, sparkle_key_b64)
    print(f"Set SUPublicEDKey in {info_plist}")
    return 0


if __name__ == '__main__':
    sys.exit(main())


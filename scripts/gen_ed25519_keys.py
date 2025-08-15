#!/usr/bin/env python3
"""
Generate an Ed25519 key pair for Sparkle 2 appcast signatures.
- Outputs: ed25519-private.pem (PKCS#8), ed25519-public.pem (SPKI)
- Prints a base64-encoded private key suitable for GitHub Secrets (ED25519_PRIVATE_KEY)
- Performs a self-test: signs and verifies a sample message

Usage:
  python scripts/gen_ed25519_keys.py

Requires:
  pip install cryptography
"""
from __future__ import annotations

import base64
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

def main() -> None:
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()

    pem_priv = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_pub = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    out_dir = Path('.')
    (out_dir / 'ed25519-private.pem').write_bytes(pem_priv)
    (out_dir / 'ed25519-public.pem').write_bytes(pem_pub)
    print('Wrote ed25519-private.pem and ed25519-public.pem')

    b64_priv = base64.b64encode(pem_priv).decode('ascii')
    print('\n=== Base64 private key (for GitHub Secret: ED25519_PRIVATE_KEY) ===')
    print(b64_priv)

    # Self-test
    sample = b'ECBot-Appcast-Signature-Test'
    sig = priv.sign(sample)
    try:
        pub.verify(sig, sample)
        print('\nSignature self-test: OK')
    except Exception as e:
        print('\nSignature self-test: FAILED ->', e)

if __name__ == '__main__':
    main()


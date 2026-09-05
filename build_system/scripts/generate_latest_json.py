#!/usr/bin/env python3
"""Generate and upload the public OTA latest.json pointer.

This is a thin CLI around :meth:`AppcastGenerator.generate_latest_json` so
S3 and COS share the same package discovery, version filtering, and payload
format.
"""

import argparse
import sys

from generate_appcast import AppcastGenerator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and upload latest.json from the OTA backend"
    )
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "development", "test", "staging", "production", "simulation"],
    )
    parser.add_argument(
        "--channel",
        choices=["dev", "beta", "stable", "lts", "simulation"],
        default="stable",
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--user-prefix", default="")
    parser.add_argument("--app", choices=["intl", "cn"], default="intl")
    args = parser.parse_args()

    generator = AppcastGenerator(
        environment=args.env,
        channel=args.channel,
        specific_version=args.version,
        user_prefix=args.user_prefix,
        app_id=args.app,
    )
    return 0 if generator.generate_latest_json() else 1


if __name__ == "__main__":
    sys.exit(main())

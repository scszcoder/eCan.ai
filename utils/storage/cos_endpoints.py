"""
Tencent COS accelerate endpoint helper — build uploads only.

Why this module exists
-----------------------
``build_system/scripts/upload_to_cos.py`` uploads large build
artifacts (Windows installers, macOS .pkg, Linux .AppImage) to the
``ecan-releases-1251680599`` COS bucket. The default
``cos.<region>.myqcloud.com`` endpoint was observed to cap at
~0.35 MB/s from a GHA runner, blowing past the 30-minute step
timeout on a 600 MB Windows installer.

Tencent offers a global accelerated endpoint
(``<bucket>-<appid>.cos.accelerate.myqcloud.com``) that routes over
their private backbone. We use it ONLY for build uploads — runtime
traffic (avatar upload, skill download, appcast fetches) keeps the
default regional endpoint because:

* it costs extra (accelerate traffic is billed at a different rate),
* the default endpoint is already inside mainland China where most
  CN end users live, so it isn't slow for them,
* expanding the accelerate usage to every storage call would risk
  hitting rate limits on the accelerated CDN.

Where this is wired in
----------------------
* ``build_system/scripts/upload_to_cos.py`` -- CI/CD upload of build
  artifacts.
* ``scripts/dev/measure_cos_throughput.py`` -- diagnostic probe that
  needs to reflect production upload performance.

Everywhere else (runtime SDK client, appcast XML, OTA endpoints,
GUI storage URLs) keeps the default regional endpoint.

SDK endpoint vs public URL
--------------------------
The cos-python-sdk-v5 SDK's ``CosConfig(Endpoint=...)`` is NOT the
same as the public HTTPS URL the GUI/browser sees. The SDK builds
the per-request hostname as ``f"{bucket}.{endpoint}"``, so passing
the public form here would produce a double-bucket hostname at
request time and break TLS cert verification. We pass only the BASE
host (``cos.accelerate.myqcloud.com``); the SDK adds the bucket
prefix itself.

Env vars
--------
* ``ECAN_COS_ACCELERATE=0`` -- Disable acceleration, fall back to
  the regional endpoint derived from ``Region=...``. Useful when
  debugging CORS / bucket policy issues.
* ``ECAN_COS_USE_INTERNAL_ACCEL=1`` -- Use the internal acceleration
  domain (``cos-internal.accelerate.tencentcos.cn``); only reachable
  from inside Tencent's network (CVM / SCF / TCB). Default OFF; do
  not enable from GHA.
"""

from __future__ import annotations

import os


# Base hosts for the SDK (no bucket prefix; SDK adds it).
# Internal acceleration is unreachable from the public internet;
# it only resolves from CVM / SCF / TCB.
_PUBLIC_ACCEL_BASE = "cos.accelerate.myqcloud.com"
_INTERNAL_ACCEL_BASE = "cos-internal.accelerate.tencentcos.cn"


def _want_acceleration() -> bool:
    """True unless the operator has explicitly disabled acceleration."""
    flag = os.environ.get("ECAN_COS_ACCELERATE", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _want_internal_acceleration() -> bool:
    """True iff internal acceleration was explicitly requested.

    Internal acceleration is unsafe from public internet callers (DNS
    only resolves inside Tencent). Must only be enabled when running
    on Tencent's side (SCF, CVM, TCB).
    """
    flag = os.environ.get("ECAN_COS_USE_INTERNAL_ACCEL", "0").strip().lower()
    return flag in ("1", "true", "yes", "on")


def accelerated_endpoint() -> str:
    """Return the COS SDK ``Endpoint`` base host for build uploads.

    Returns ``""`` when acceleration is disabled, signalling the SDK
    to derive the endpoint from ``Region=...`` alone.

    The SDK constructs the per-request hostname as
    ``f"{bucket}.{endpoint}"`` (``qcloud_cos/cos_comm.py``), so this
    is the BASE host only -- do not include the bucket prefix here.
    """
    if not _want_acceleration():
        return ""
    if _want_internal_acceleration():
        return _INTERNAL_ACCEL_BASE
    return _PUBLIC_ACCEL_BASE
"""
Resolves which :class:`CloudProvider` to use for a given account region.

This is the single place that maps ``home_region`` -> provider. Almost every
caller goes through an L1 transport router that calls ``get_cloud_provider()``
with no argument, so the **process-wide active region** (set at login from the
account's ``home_region``) is the single lever that switches the whole app's
backend. Default is ``global`` (AWS), so behavior is unchanged until login sets
a CN region.

Providers are cached as singletons per region family (they are stateless
transport wrappers, so one instance each is enough).
"""

from agent.cloud_api.provider import CloudProvider
from agent.cloud_api.aws_provider import AWSCloudProvider
from agent.cloud_api.tencent_provider import TencentCloudProvider

# region value -> provider class. Anything not listed (incl. None / "global")
# falls through to AWS, the current default.
_CN_REGIONS = {"cn", "china"}

_instances: dict = {}

# Process-wide active region. None == global/AWS (the default). Set once per
# session by the auth layer when the logged-in account's home_region is known
# (Layer 2 increment 2). A single reference assignment under the GIL — no lock.
_active_home_region: str | None = None


def set_active_home_region(home_region: str | None) -> None:
    """Set the session's active region (called by auth on login/restore).

    ``home_region`` is the account's permanent region; ``None`` / unknown clears
    back to the global default. Subsequent no-argument ``get_cloud_provider()``
    calls route to the matching backend.
    """
    global _active_home_region
    _active_home_region = home_region


def get_active_home_region() -> str | None:
    """Return the session's active region (``None`` == global/AWS)."""
    return _active_home_region


def get_cloud_provider(home_region: str | None = None) -> CloudProvider:
    """Return the cloud provider for ``home_region`` (default: the active region).

    Args:
        home_region: The account's permanent region (``"cn"`` for China,
            anything else / ``None`` for the global AWS backend). When ``None``
            (the usual case — L1 routers pass nothing), falls back to the
            process-wide active region set by the auth layer.
    """
    if home_region is None:
        home_region = _active_home_region

    is_cn = isinstance(home_region, str) and home_region.strip().lower() in _CN_REGIONS
    key = "cn" if is_cn else "global"

    inst = _instances.get(key)
    if inst is None:
        inst = TencentCloudProvider() if is_cn else AWSCloudProvider()
        _instances[key] = inst
    return inst

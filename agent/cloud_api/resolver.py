"""
Resolves which :class:`CloudProvider` to use for a given account region.

This is the single place that maps ``home_region`` -> provider. Until Layer 2
(region plumbing) lands, nothing passes a region, so everyone resolves to AWS —
preserving today's behavior exactly.

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


def get_cloud_provider(home_region: str | None = None) -> CloudProvider:
    """Return the cloud provider for ``home_region`` (default: AWS).

    Args:
        home_region: The account's permanent region (``"cn"`` for China,
            anything else / ``None`` for the global AWS backend). Layer 2 will
            populate this from the account; for now callers pass nothing.
    """
    is_cn = isinstance(home_region, str) and home_region.strip().lower() in _CN_REGIONS
    key = "cn" if is_cn else "global"

    inst = _instances.get(key)
    if inst is None:
        inst = TencentCloudProvider() if is_cn else AWSCloudProvider()
        _instances[key] = inst
    return inst

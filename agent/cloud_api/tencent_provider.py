"""
Tencent (China-region) implementation of :class:`CloudProvider`.

Stub for now — the CN backend (Cloud Native Gateway + SCF/TKE Serverless, COS,
CIAM-token auth) is Layer 4 of the China-region plan. This class exists so the
resolver has a target to return for ``home_region == "cn"`` and so the transport
contract is visible. Each method raises until the CN backend is built.
"""

from agent.cloud_api.provider import CloudProvider

_NOT_BUILT = (
    "TencentCloudProvider is not implemented yet (China-region Layer 4). "
    "CN backend transport (Cloud Native Gateway/SCF + COS + CIAM) is pending."
)


class TencentCloudProvider(CloudProvider):
    """Routes backend calls to the Tencent Cloud CN backend (not yet built)."""

    def send_request(self, query_string, session, token, endpoint=None,
                     timeout=180, variables=None) -> dict:
        raise NotImplementedError(_NOT_BUILT)

    async def send_request_async(self, query_string, token, endpoint,
                                 retries=3) -> dict:
        raise NotImplementedError(_NOT_BUILT)

    def get_endpoint(self) -> str:
        raise NotImplementedError(_NOT_BUILT)

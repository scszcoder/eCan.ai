"""
AWS implementation of :class:`CloudProvider`.

This is a pure delegation layer over the existing AppSync transport in
``cloud_api.py`` — it adds NO behavior. The real request bodies still live in
``cloud_api._appsync_http_request_aws`` / ``_appsync_http_request8_aws`` and
``get_appsync_endpoint``; this class just exposes them through the provider
interface so the resolver can swap in a CN provider later.

Imports of ``cloud_api`` are deferred to call time to avoid an import cycle
(``cloud_api`` lazily imports the resolver, which imports this module).
"""

from agent.cloud_api.provider import CloudProvider


class AWSCloudProvider(CloudProvider):
    """Routes backend calls to AWS AppSync (today's behavior, unchanged)."""

    def send_request(self, query_string, session, token, endpoint=None,
                     timeout=180, variables=None) -> dict:
        from agent.cloud_api import cloud_api
        return cloud_api._appsync_http_request_aws(
            query_string, session, token,
            endpoint=endpoint, timeout=timeout, variables=variables,
        )

    async def send_request_async(self, query_string, token, endpoint,
                                 retries=3) -> dict:
        from agent.cloud_api import cloud_api
        return await cloud_api._appsync_http_request8_aws(
            query_string, token, endpoint, retries=retries,
        )

    def get_endpoint(self) -> str:
        from agent.cloud_api import cloud_api
        return cloud_api.get_appsync_endpoint()

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

    # --- presigned S3 transfer (delegates to the unchanged _aws bodies) ---

    def upload_via_presigned(self, src_file, presigned_resp) -> None:
        from agent.cloud_api import cloud_api
        return cloud_api._send_file_with_presigned_url_aws(src_file, presigned_resp)

    async def upload_via_presigned_async(self, session, src_file, presigned_resp):
        from agent.cloud_api import cloud_api
        return await cloud_api._send_file_with_presigned_url8_aws(
            session, src_file, presigned_resp,
        )

    def download_via_presigned(self, dest_file, url) -> None:
        from agent.cloud_api import cloud_api
        return cloud_api._get_file_with_presigned_url_aws(dest_file, url)

    def upload_file_to_presigned_url(self, file_path, presigned_url,
                                     content_type=None) -> dict:
        from agent.cloud_api import cloud_api
        return cloud_api._upload_file_to_presigned_url_aws(
            file_path, presigned_url, content_type,
        )

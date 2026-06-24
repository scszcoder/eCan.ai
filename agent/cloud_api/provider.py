"""
Cloud-provider abstraction (Layer 1 keystone for China-region support).

The app's backend surface (~150 functions in ``cloud_api.py``) is, structurally,
a set of GraphQL strings funneled through a single HTTP chokepoint plus a small
number of realtime/file primitives.  This module defines the seam at that
transport chokepoint: every cloud call ultimately goes through a ``CloudProvider``,
so a second backend (Tencent) can be slotted in without touching the ~150
operation functions or their call sites.

Design note (locked 2026-06-23): the seam sits at the *transport* level
(``send_request`` / ``send_request_async`` / ``get_endpoint``), NOT at the
semantic-operation level.  ``AWSCloudProvider`` wraps today's AppSync code with
zero behavior change; ``TencentCloudProvider`` will translate as needed inside
its own implementation.

Realtime subscriptions and presigned file I/O are separate transport chokepoints;
they will be added to this interface in a later Layer 1 increment.
"""

from abc import ABC, abstractmethod


class CloudProvider(ABC):
    """Abstract backend transport.

    Implementations own the wire protocol (GraphQL-over-HTTP for AWS AppSync;
    whatever the CN backend exposes for Tencent).  The ~150 operation functions
    in ``cloud_api.py`` remain provider-agnostic: they build a request and hand
    it to the active provider.
    """

    @abstractmethod
    def send_request(self, query_string, session, token, endpoint=None,
                     timeout=180, variables=None) -> dict:
        """Send a synchronous backend request and return the parsed response dict.

        Mirrors the legacy ``appsync_http_request`` signature so existing callers
        are unchanged.

        Args:
            query_string: The request payload (a GraphQL string for AWS).
            session: A ``requests.Session`` provided by the caller.
            token: The caller's auth token (Cognito JWT for AWS).
            endpoint: Optional explicit endpoint; falls back to ``get_endpoint()``.
            timeout: Request timeout in seconds.
            variables: Optional GraphQL variables dict.

        Returns:
            Parsed response dict. On transport failure, a dict shaped like a
            GraphQL error response (``{"errors": [...]}``) rather than raising.
        """
        raise NotImplementedError

    @abstractmethod
    async def send_request_async(self, query_string, token, endpoint,
                                 retries=3) -> dict:
        """Async counterpart of :meth:`send_request`.

        Mirrors the legacy ``appsync_http_request8`` signature (no caller-supplied
        session; the implementation manages its own).
        """
        raise NotImplementedError

    @abstractmethod
    def get_endpoint(self) -> str:
        """Return the backend endpoint URL for this provider."""
        raise NotImplementedError

    # --- presigned object-storage transfer (S3 for AWS, COS for Tencent) ---
    # The presigned-URL *request* is a GraphQL op and already flows through
    # send_request above; these are the raw byte transfers to/from object
    # storage, which is where S3 and COS diverge.

    @abstractmethod
    def upload_via_presigned(self, src_file, presigned_resp) -> None:
        """Upload a local file using a presigned grant from the acquisition step.

        ``presigned_resp`` is provider-shaped: for AWS S3 it is a presigned-POST
        policy (``{"url": ..., "fields": {...}}``); the CN/COS provider will use
        its own grant shape. Mirrors ``send_file_with_presigned_url``.
        """
        raise NotImplementedError

    @abstractmethod
    async def upload_via_presigned_async(self, session, src_file, presigned_resp):
        """Async counterpart of :meth:`upload_via_presigned`.

        Mirrors ``send_file_with_presigned_url8`` (the ``session`` arg is part of
        the legacy signature; the AWS impl manages its own).
        """
        raise NotImplementedError

    @abstractmethod
    def download_via_presigned(self, dest_file, url) -> None:
        """Download from a presigned URL to ``dest_file``.

        Mirrors ``get_file_with_presigned_url``.
        """
        raise NotImplementedError

    @abstractmethod
    def upload_file_to_presigned_url(self, file_path, presigned_url,
                                     content_type=None) -> dict:
        """Upload a local file to a presigned PUT URL (avatar path).

        Mirrors ``upload_file_to_presigned_url``; returns a result dict.
        """
        raise NotImplementedError

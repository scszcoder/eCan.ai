"""
A2A Client Wrapper - Compatibility layer for a2a-sdk client.

This module provides a synchronous-friendly wrapper around the a2a-sdk client,
maintaining backward compatibility with the existing EC_Agent client usage patterns.

The wrapper supports:
- set_recipient(url) - Set target agent URL
- sync_send_task(payload) - Synchronous message send (blocking)
- send_task(payload) - Async message send
"""

from __future__ import annotations
import asyncio
import traceback
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx

try:
    from a2a.types import AgentCard, Message
except ImportError:
    # Fallback if a2a-sdk not installed yet
    AgentCard = None
    Message = None

from utils.logger_helper import logger_helper as logger


class A2AClientWrapper:
    """
    Wrapper around a2a-sdk client providing backward-compatible interface.
    
    This class bridges the gap between the old A2A client API (with set_recipient,
    sync_send_task) and the new a2a-sdk async-first API.
    
    Usage:
        client = A2AClientWrapper(url="http://localhost:5000/a2a/")
        client.set_recipient(url="http://192.168.1.100:5001/a2a/")
        response = client.sync_send_task(payload_dict)
    """
    
    def __init__(self, url: str = "http://localhost:5000/a2a/"):
        """
        Initialize the A2A client wrapper.
        
        Args:
            url: Default A2A endpoint URL
        """
        self._url = url
        self._recipient_url: Optional[str] = None
        self._httpx_client: Optional[httpx.Client] = None
        self._async_httpx_client: Optional[httpx.AsyncClient] = None
        
    @property
    def url(self) -> str:
        """Get the current target URL (recipient or default)."""
        return self._recipient_url or self._url
    
    def set_recipient(self, url: str = None, card: AgentCard = None):
        """
        Set the recipient agent for subsequent messages.
        
        Args:
            url: Direct URL to the recipient's A2A endpoint
            card: AgentCard to extract URL from (alternative to url)
        """
        if url:
            self._recipient_url = url
        elif card:
            self._recipient_url = card.url
        else:
            raise ValueError("Either url or card must be provided")
        logger.debug(f"[A2AClientWrapper] Set recipient URL: {self._recipient_url}")
    
    def _get_sync_client(self) -> httpx.Client:
        """Get or create synchronous HTTP client."""
        if self._httpx_client is None:
            # Use trust_env=False to avoid system proxy issues with LAN addresses
            self._httpx_client = httpx.Client(timeout=60.0, trust_env=False)
        return self._httpx_client
    
    def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_httpx_client is None:
            # Use trust_env=False to avoid system proxy issues with LAN addresses
            self._async_httpx_client = httpx.AsyncClient(timeout=60.0, trust_env=False)
        return self._async_httpx_client
    
    def sync_send_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a task/message synchronously (blocking).
        
        This method sends a JSON-RPC request to the recipient's A2A endpoint
        and blocks until a response is received.
        
        Args:
            payload: Message payload dict (MessageSendParams format)
            
        Returns:
            Response dict from the A2A server
        """
        try:
            target_url = self.url
            logger.debug(f"[A2AClientWrapper] sync_send_task to {target_url}")
            
            # Build JSON-RPC request
            jsonrpc_request = {
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "message/send",
                "params": payload
            }
            
            client = self._get_sync_client()
            response = client.post(
                target_url,
                json=jsonrpc_request,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"[A2AClientWrapper] Response: {result}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"[A2AClientWrapper] HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"[A2AClientWrapper] Error sending task: {traceback.format_exc()}")
            raise
    
    async def send_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a task/message asynchronously.
        
        Args:
            payload: Message payload dict (MessageSendParams format)
            
        Returns:
            Response dict from the A2A server
        """
        try:
            target_url = self.url
            logger.debug(f"[A2AClientWrapper] async send_task to {target_url}")
            
            # Build JSON-RPC request
            jsonrpc_request = {
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "message/send",
                "params": payload
            }
            
            client = self._get_async_client()
            response = await client.post(
                target_url,
                json=jsonrpc_request,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"[A2AClientWrapper] Response: {result}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"[A2AClientWrapper] HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"[A2AClientWrapper] Error sending task: {traceback.format_exc()}")
            raise
    
    def send_message_sync(
        self,
        message: Message,
        session_id: Optional[str] = None,
        accepted_output_modes: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send an A2A Message synchronously.
        
        Higher-level method that takes a Message object directly.
        
        Args:
            message: A2A Message object
            session_id: Optional session ID
            accepted_output_modes: List of accepted output modes
            metadata: Optional metadata dict
            
        Returns:
            Response dict from the A2A server
        """
        # Build payload dict directly instead of using MessageSendParams
        payload = {
            "message": message.model_dump() if hasattr(message, 'model_dump') else message,
            "configuration": {
                "acceptedOutputModes": accepted_output_modes or ["text", "json"],
            },
            "metadata": metadata
        }
        return self.sync_send_task(payload)
    
    async def send_message_async(
        self,
        message: Message,
        session_id: Optional[str] = None,
        accepted_output_modes: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send an A2A Message asynchronously.
        
        Args:
            message: A2A Message object
            session_id: Optional session ID
            accepted_output_modes: List of accepted output modes
            metadata: Optional metadata dict
            
        Returns:
            Response dict from the A2A server
        """
        # Build payload dict directly instead of using MessageSendParams
        payload = {
            "message": message.model_dump() if hasattr(message, 'model_dump') else message,
            "configuration": {
                "acceptedOutputModes": accepted_output_modes or ["text", "json"],
            },
            "metadata": metadata
        }
        return await self.send_task(payload)
    
    def close(self):
        """Close HTTP clients and release resources."""
        if self._httpx_client:
            self._httpx_client.close()
            self._httpx_client = None
        if self._async_httpx_client:
            # Note: async client should be closed in async context
            # This is a best-effort cleanup
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._async_httpx_client.aclose())
                else:
                    loop.run_until_complete(self._async_httpx_client.aclose())
            except Exception:
                pass
            self._async_httpx_client = None
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()

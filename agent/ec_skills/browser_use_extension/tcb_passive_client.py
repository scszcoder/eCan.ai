"""
CN TCB SSE Passive Command Client

Connects to TCB SSE endpoint for passive command subscriptions.
Used as alternative to AppSyncPassiveClient for CN version.
"""

import asyncio
import json
import ssl
import certifi
import traceback
from typing import Callable, Optional, TYPE_CHECKING

import aiohttp

from utils.logger_helper import logger_helper as logger
from .passive_protocol import PassiveBrowserCommand

if TYPE_CHECKING:
    pass


class TCBPassiveClient:
    """
    CN TCB SSE client for passive command subscriptions.
    
    Subscribes to onPassiveCommand via SSE endpoint:
    GET /api/events?topic=onPassiveCommand&runId=xxx&clientId=xxx
    
    Each event frame format:
        event: onPassiveCommand
        data: {"topic":"onPassiveCommand","payload":{...}}
    """
    
    def __init__(
        self,
        *,
        sse_endpoint: str,
        auth_token: str,
        run_id: str,
        client_id: str,
        on_command_received: Callable[[PassiveBrowserCommand], None],
        on_error: Callable[[Exception], None] | None = None,
    ):
        self._sse_endpoint = sse_endpoint
        self._auth_token = auth_token
        self._run_id = run_id
        self._client_id = client_id
        self._on_command_received = on_command_received
        self._on_error = on_error
        self._stopped = False
        self._client: Optional[aiohttp.ClientSession] = None
        
    def _build_sse_url(self) -> str:
        """Build SSE URL with topic and parameters."""
        params = [
            ("topic", "onPassiveCommand"),
            ("runId", self._run_id),
            ("clientId", self._client_id),
        ]
        if self._auth_token:
            params.append(("token", self._auth_token))
        
        query = "&".join(f"{k}={v}" for k, v in params)
        return f"{self._sse_endpoint}?{query}"
    
    async def start(self) -> None:
        """Start the SSE connection and listen for commands."""
        if self._stopped:
            return
            
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        timeout = aiohttp.ClientTimeout(total=0)  # No timeout for SSE
        
        self._client = aiohttp.ClientSession()
        
        try:
            url = self._build_sse_url()
            logger.info(f"[TCBPassiveClient] Connecting to SSE: {url[:100]}")
            
            async with self._client.get(
                url,
                headers={
                    'Accept': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                },
                timeout=timeout,
                ssl=ssl_context,
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(f"SSE connection failed: status={response.status}, body={body[:200]}")
                
                logger.info(f"[TCBPassiveClient] SSE connected, listening for commands...")
                
                current_event = None
                async for line in response.content:
                    if self._stopped:
                        break
                        
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    
                    # SSE comment (connection confirmation, pings)
                    if line.startswith(':'):
                        if 'connected' in line:
                            logger.info(f"[TCBPassiveClient] SSE: {line}")
                        continue
                    
                    # SSE ping
                    if line.startswith(': ping'):
                        continue
                    
                    # Event name
                    if line.startswith('event: '):
                        current_event = line[7:].strip()
                        continue
                    
                    # Data
                    if line.startswith('data: '):
                        if current_event == 'onPassiveCommand':
                            data_str = line[6:].strip()
                            try:
                                data = json.loads(data_str)
                                payload = data.get('payload', {})
                                await self._handle_command(payload)
                            except json.JSONDecodeError:
                                logger.warning(f"[TCBPassiveClient] Invalid JSON: {data_str[:100]}")
                        current_event = None
                        continue
                    
                    current_event = None
        
        except asyncio.CancelledError:
            logger.info("[TCBPassiveClient] SSE connection cancelled")
        except Exception as e:
            logger.error(f"[TCBPassiveClient] SSE error: {e}\n{traceback.format_exc()}")
            if self._on_error:
                try:
                    self._on_error(e)
                except Exception:
                    pass
        finally:
            if self._client:
                await self._client.close()
                self._client = None
    
    async def _handle_command(self, payload: dict) -> None:
        """Handle received command payload."""
        try:
            cmd = PassiveBrowserCommand(
                run_id=payload.get('runId', ''),
                client_id=payload.get('clientId', ''),
                step_id=payload.get('stepId', ''),
                command=payload.get('command', {}),
                actions=payload.get('actions', []),
            )
            self._on_command_received(cmd)
        except Exception as e:
            logger.error(f"[TCBPassiveClient] Error handling command: {e}")
    
    async def stop(self) -> None:
        """Stop the SSE connection."""
        self._stopped = True
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
        logger.info("[TCBPassiveClient] Stopped")


def make_tcb_passive_client_from_mainwin(
    mainwin,
    route_command: Callable[[PassiveBrowserCommand], bool],
) -> Optional[TCBPassiveClient]:
    """
    Create a TCBPassiveClient using MainWindow's configuration.
    
    Args:
        mainwin: MainWindow instance
        route_command: Callback to route commands to tasks
        
    Returns:
        Configured TCBPassiveClient or None if not CN version
    """
    from utils.app_env import is_cn
    
    if not is_cn():
        logger.info("[TCBPassiveClient] Not CN version, skipping")
        return None
    
    sse_endpoint = mainwin.getSSEApiEndpoint()
    if not sse_endpoint:
        # Fallback to GraphQL endpoint
        graphql_endpoint = mainwin.getWanApiEndpoint()
        if graphql_endpoint:
            sse_endpoint = graphql_endpoint.replace('/api/graphql', '/api/events')
        else:
            logger.error("[TCBPassiveClient] No SSE endpoint configured")
            return None
    
    auth_token = mainwin.get_auth_token()
    client_id = mainwin.getAcctSiteID() or "client_001"
    
    import os
    run_id = (os.environ.get("EC_BROWSER_PASSIVE_RUN_ID") or "").strip()
    if not run_id or run_id == "*":
        run_id = "0123456789"
    
    def on_command(cmd: PassiveBrowserCommand) -> None:
        try:
            logger.info(f"[TCBPassiveClient] Received command: run_id={cmd.run_id}, step_id={cmd.step_id}")
            route_command(cmd)
        except Exception as e:
            logger.error(f"[TCBPassiveClient] Error routing command: {e}")
    
    def on_error(e: Exception) -> None:
        logger.error(f"[TCBPassiveClient] Error: {e}")
    
    return TCBPassiveClient(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token or "",
        run_id=run_id,
        client_id=client_id,
        on_command_received=on_command,
        on_error=on_error,
    )

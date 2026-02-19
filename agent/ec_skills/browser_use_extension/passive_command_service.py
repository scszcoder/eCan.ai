"""
Passive Command Service - Routes passive browser commands to tasks.

This service is launched as a background service in MainGUI.py.
It subscribes to onPassiveCommand via AppSync WebSocket and routes
commands to the appropriate task's queue based on run_id.
"""

import asyncio
from typing import Callable, Optional, TYPE_CHECKING

from utils.logger_helper import logger_helper as logger

from .appsync_passive_client import AppSyncPassiveClient, AppSyncPassiveClientConfig
from .passive_protocol import PassiveBrowserCommand

if TYPE_CHECKING:
    pass


class PassiveCommandService:
    """
    Service that subscribes to passive commands and routes them to tasks.
    
    This service:
    1. Connects to AppSync WebSocket
    2. Subscribes to onPassiveCommand(runId, clientId)
    3. When command received, routes to appropriate task queue via callback
    
    Usage:
        service = PassiveCommandService(
            config=config,
            route_command=lambda cmd: route_to_task(cmd),
        )
        await service.start()
    """
    
    def __init__(
        self,
        *,
        config: AppSyncPassiveClientConfig,
        route_command: Callable[[PassiveBrowserCommand], bool],
        on_error: Callable[[Exception], None] | None = None,
    ):
        """
        Initialize the passive command service.
        
        Args:
            config: AppSync connection configuration
            route_command: Callback to route commands to tasks. Returns True if routed successfully.
            on_error: Optional error callback
        """
        self._config = config
        self._route_command = route_command
        self._on_error = on_error
        self._client: Optional[AppSyncPassiveClient] = None
        self._started = False
    
    async def start(self) -> None:
        """Start the service and begin listening for commands."""
        if self._started:
            logger.info("[PassiveCommandService] Already started, stopping old subscription first")
            await self.stop()
        
        def on_command(cmd: PassiveBrowserCommand) -> None:
            """Handle incoming command by routing to task."""
            try:
                action_names = [next(iter(a.keys()), "?") for a in (cmd.actions or []) if isinstance(a, dict)]
                logger.info(f"[PassiveCommandService] Received command: type={cmd.type}, run_id={cmd.run_id}, step_id={cmd.step_id}, actions={action_names}")
                success = self._route_command(cmd)
                if not success:
                    logger.warning(f"[PassiveCommandService] Failed to route command: {cmd.run_id}/{cmd.step_id}")
            except Exception as e:
                logger.error(f"[PassiveCommandService] Error routing command: {e}")
                if self._on_error:
                    try:
                        self._on_error(e)
                    except Exception:
                        pass
        
        def on_error(e: Exception) -> None:
            """Handle WebSocket errors."""
            logger.error(f"[PassiveCommandService] WebSocket error: {e}")
            if self._on_error:
                try:
                    self._on_error(e)
                except Exception:
                    pass
        
        self._client = AppSyncPassiveClient(
            config=self._config,
            on_command_received=on_command,
            on_error=on_error,
        )
        
        await self._client.start()
        self._started = True
        logger.info(f"[PassiveCommandService] Started - listening for run_id={self._config.run_id}, client_id={self._config.client_id}")
    
    async def stop(self) -> None:
        """Stop the service and close connections."""
        if self._client:
            await self._client.stop()
            self._client = None
        self._started = False
        logger.info("[PassiveCommandService] Stopped")
    
    @property
    def is_running(self) -> bool:
        """Check if the service is running."""
        return self._started


def make_passive_command_service_from_mainwin(
    mainwin,
    route_command: Callable[[PassiveBrowserCommand], bool],
) -> PassiveCommandService:
    """
    Create a PassiveCommandService using MainWindow's configuration.
    
    Args:
        mainwin: MainWindow instance with API endpoint getters
        route_command: Callback to route commands to tasks
        
    Returns:
        Configured PassiveCommandService
    """
    from .appsync_passive_client import _derive_realtime_endpoint, _derive_api_host
    
    http_endpoint = mainwin.getWanApiEndpoint()
    ws_endpoint = mainwin.getWSApiEndpoint()

    # Ensure WS subscription targets the same AppSync API as the HTTP endpoint.
    # Some client configs may have stale ws_api_endpoint/ws_api_host values
    # (pointing at a different AppSync API), which makes the subscription
    # receive events with unexpected shapes / null AWSJSON.
    derived_ws_endpoint = _derive_realtime_endpoint(http_endpoint)
    if not ws_endpoint:
        ws_endpoint = derived_ws_endpoint
    else:
        try:
            http_host = _derive_api_host(http_endpoint, "")
            ws_host = _derive_api_host("", ws_endpoint)
            # If the AppSync API host differs, override WS endpoint.
            if http_host and ws_host and http_host != ws_host:
                logger.warning(
                    "[PassiveCommandService] ws_api_endpoint host mismatch; overriding to match wan_api_endpoint "
                    f"(http_host={http_host}, ws_host={ws_host}, ws_endpoint={ws_endpoint})"
                )
                ws_endpoint = derived_ws_endpoint
        except Exception:
            ws_endpoint = derived_ws_endpoint

    api_host = mainwin.getWSApiHost()
    derived_api_host = _derive_api_host(http_endpoint, ws_endpoint)
    if not api_host:
        api_host = derived_api_host
    else:
        try:
            if derived_api_host and api_host.strip() and api_host.strip() != derived_api_host:
                logger.warning(
                    "[PassiveCommandService] ws_api_host mismatch; overriding to match wan_api_endpoint "
                    f"(api_host={api_host}, derived_api_host={derived_api_host})"
                )
                api_host = derived_api_host
        except Exception:
            api_host = derived_api_host
    
    auth_token = mainwin.get_auth_token()
    client_id = mainwin.getAcctSiteID()
    
    # AppSync subscriptions require exact match - wildcards don't work
    # Default to "0123456789" for testing; in production, use specific run_id
    import os
    run_id = (os.environ.get("EC_BROWSER_PASSIVE_RUN_ID") or "").strip()
    if not run_id or run_id == "*":
        run_id = "0123456789"
        logger.warning(f"[PassiveCommandService] EC_BROWSER_PASSIVE_RUN_ID not set or '*', defaulting to '{run_id}'")

    # Helpful diagnostics (avoid logging secrets)
    _tok = (auth_token or "").strip()
    _auth_type = "NONE"
    if _tok.lower().startswith("bearer ") or _tok.count(".") >= 2:
        _auth_type = "AUTHORIZATION"
    elif _tok:
        _auth_type = "API_KEY"
    logger.info(
        "[PassiveCommandService] AppSync config "
        f"run_id={run_id}, client_id={client_id}, auth_type={_auth_type}, token_len={len(_tok)}, "
        f"http_endpoint={http_endpoint}, ws_endpoint={ws_endpoint}, api_host={api_host}"
    )
    
    config = AppSyncPassiveClientConfig(
        http_endpoint=http_endpoint,
        ws_endpoint=ws_endpoint,
        api_host=api_host,
        auth_token=auth_token,
        run_id=run_id,
        client_id=client_id,
    )
    
    return PassiveCommandService(
        config=config,
        route_command=route_command,
    )

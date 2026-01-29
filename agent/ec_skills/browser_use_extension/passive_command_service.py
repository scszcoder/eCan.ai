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
            logger.warning("[PassiveCommandService] Already started")
            return
        
        def on_command(cmd: PassiveBrowserCommand) -> None:
            """Handle incoming command by routing to task."""
            try:
                logger.info(f"[PassiveCommandService] Received command: run_id={cmd.run_id}, step_id={cmd.step_id}")
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
    
    if not ws_endpoint:
        ws_endpoint = _derive_realtime_endpoint(http_endpoint)
    
    api_host = mainwin.getWSApiHost()
    if not api_host:
        api_host = _derive_api_host(http_endpoint, ws_endpoint)
    
    auth_token = mainwin.get_auth_token()
    client_id = mainwin.getAcctSiteID()
    
    # Use "*" as run_id to subscribe to all runs for this client
    # The routing callback will filter by actual task run_id
    run_id = "*"
    
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

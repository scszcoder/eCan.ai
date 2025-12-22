"""
Ad Banner Handler
Handles pushing advertisements to the frontend
"""
from typing import Any, Optional, Dict

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


@IPCHandlerRegistry.handler('push_ad')
def handle_push_ad(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Push an advertisement to the frontend.
    
    Params:
        bannerText: str - Text to display in the scrolling banner
        popupHtml: str - HTML content for the popup (shown when banner is clicked)
        durationMs: int - How long the ad should be displayed (default: 60000ms = 1 minute)
    
    Example:
        ipc.invoke('push_ad', {
            'bannerText': '🎉 Special Offer! 50% off all plans!',
            'popupHtml': '<div>...</div>',
            'durationMs': 60000
        })
    """
    try:
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')
        
        banner_text = params.get('bannerText')
        popup_html = params.get('popupHtml')
        duration_ms = params.get('durationMs', 60000)
        
        if not banner_text and not popup_html:
            return create_error_response(
                request, 
                'INVALID_PARAMS', 
                'At least one of bannerText or popupHtml is required'
            )
        
        logger.info(f"[AdHandler] Pushing ad: banner={bool(banner_text)}, popup={bool(popup_html)}, duration={duration_ms}ms")
        
        # The actual push to frontend happens via the IPC response
        # The frontend handler will receive this and update the ad store
        return create_success_response(request, {
            'bannerText': banner_text,
            'popupHtml': popup_html,
            'durationMs': duration_ms,
            'message': 'Ad pushed successfully'
        })
        
    except Exception as e:
        logger.error(f"[AdHandler] Error pushing ad: {e}")
        return create_error_response(request, 'AD_PUSH_ERROR', str(e))


def push_ad_to_frontend(banner_text: str = None, popup_html: str = None, duration_ms: int = 60000):
    """
    Utility function to push an ad to the frontend from anywhere in the backend.
    
    This broadcasts the ad to all connected frontends.
    
    Args:
        banner_text: Text to display in the scrolling banner
        popup_html: HTML content for the popup
        duration_ms: How long the ad should be displayed (default: 60000ms)
    
    Example:
        from gui.ipc.w2p_handlers.ad_handler import push_ad_to_frontend
        push_ad_to_frontend(
            banner_text='🎉 Special Offer!',
            popup_html='<div>Click here for details</div>',
            duration_ms=120000  # 2 minutes
        )
    """
    try:
        from gui.ipc.api import IPCAPI
        
        try:
            ipc_api = IPCAPI.get_instance()
        except RuntimeError:
            logger.warning("[AdHandler] IPCAPI not initialized yet")
            return False
        
        def callback(response):
            if response.success:
                logger.info(f"[AdHandler] Ad push confirmed by frontend")
            else:
                logger.warning(f"[AdHandler] Ad push failed: {response.error}")
        
        # Use the IPCAPI to send the push_ad request
        ipc_api._send_request(
            'push_ad',
            params={
                'bannerText': banner_text,
                'popupHtml': popup_html,
                'durationMs': duration_ms
            },
            callback=callback
        )
        
        logger.info(f"[AdHandler] Ad push request sent: banner={bool(banner_text)}, popup={bool(popup_html)}")
        return True
        
    except Exception as e:
        logger.error(f"[AdHandler] Error pushing ad: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

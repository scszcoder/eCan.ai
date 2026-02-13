"""
Monkey-patch browser_use BrowserSession to increase navigation timeout.

browser_use hardcodes page readiness timeout at 4s (cross-domain) / 2s (same-domain)
in BrowserSession._navigate_and_wait. This is too short for many real-world sites
(e.g. baidu.com, amazon.com) that have heavy async loading.

This patch increases the defaults to reduce "Page readiness timeout" warnings.
The patch is idempotent — calling it multiple times is safe.
"""


from utils.logger_helper import logger_helper as logger

_patched = False


def patch_navigation_timeout(cross_domain_timeout: float = 10.0, same_domain_timeout: float = 5.0):
    """
    Patch BrowserSession._navigate_and_wait to use larger default timeouts.
    
    Args:
        cross_domain_timeout: Timeout for cross-domain navigation (default: 10s, was 4s)
        same_domain_timeout: Timeout for same-domain navigation (default: 5s, was 2s)
    """
    global _patched
    if _patched:
        return
    
    try:
        from browser_use.browser.session import BrowserSession
        import asyncio
        
        original_navigate_and_wait = BrowserSession._navigate_and_wait
        
        async def _patched_navigate_and_wait(self, url: str, target_id: str, timeout: float | None = None):
            """Patched version with increased default timeouts."""
            if timeout is None:
                # Use our increased timeouts instead of the hardcoded 4s/2s
                try:
                    target = self.session_manager.get_target(target_id)
                    current_url = target.url
                    same_domain = (
                        url.split('/')[2] == current_url.split('/')[2]
                        if url.startswith('http') and current_url.startswith('http')
                        else False
                    )
                    timeout = same_domain_timeout if same_domain else cross_domain_timeout
                except Exception:
                    timeout = cross_domain_timeout
            
            return await original_navigate_and_wait(self, url, target_id, timeout=timeout)
        
        BrowserSession._navigate_and_wait = _patched_navigate_and_wait
        _patched = True
        logger.info(f"[SessionPatch] ✅ Patched navigation timeout: cross-domain={cross_domain_timeout}s, same-domain={same_domain_timeout}s")
        
    except Exception as e:
        logger.warning(f"[SessionPatch] ⚠️ Failed to patch navigation timeout: {e}")

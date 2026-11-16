"""A frame that disappears while the page is read no longer blanks the whole page.

browser-use reads the accessibility tree of every frame with one ``asyncio.gather``
(``DomService._get_ax_tree_for_all_frames``, 0.12.x). An ad iframe that is removed
between ``Page.getFrameTree`` and its ``getFullAXTree`` fails with "Frame with the
given frameId is not found", which fails the gather and so the whole DOM build: the
model is handed a minimal state with 0 elements. On eBay's sold-items search
(2026-11-15, yj_ebay_market_research) a fully loaded 9,515-node page was reported
blank this way and the run aborted.

Here a vanished child frame is skipped; a failure of the main frame still raises.
"""
from __future__ import annotations

import asyncio

from utils.logger_helper import logger_helper as logger

_installed = False


async def _get_ax_tree_for_all_frames(self, target_id):
    cdp_session = await self.browser_session.get_or_create_cdp_session(target_id=target_id, focus=False)
    frame_tree = await cdp_session.cdp_client.send.Page.getFrameTree(session_id=cdp_session.session_id)

    def collect_all_frame_ids(node) -> list:
        ids = [node['frame']['id']]
        for child in node.get('childFrames') or []:
            ids.extend(collect_all_frame_ids(child))
        return ids

    frame_ids = collect_all_frame_ids(frame_tree['frameTree'])
    ax_trees = await asyncio.gather(
        *(cdp_session.cdp_client.send.Accessibility.getFullAXTree(
            params={'frameId': frame_id}, session_id=cdp_session.session_id) for frame_id in frame_ids),
        return_exceptions=True,
    )
    if isinstance(ax_trees[0], BaseException):
        raise ax_trees[0]
    merged = []
    for frame_id, ax_tree in zip(frame_ids, ax_trees):
        if isinstance(ax_tree, BaseException):
            logger.debug(f"[vanished-frame-patch] skipped frame {frame_id}: {ax_tree}")
            continue
        merged.extend(ax_tree['nodes'])
    return {'nodes': merged}


def install() -> bool:
    """Patch browser-use's DomService once. False when it is not importable."""
    global _installed
    if _installed:
        return True
    try:
        from browser_use.dom.service import DomService
    except Exception as exc:
        logger.warning(f"[vanished-frame-patch] browser-use DomService not importable: {exc}")
        return False
    DomService._get_ax_tree_for_all_frames = _get_ax_tree_for_all_frames
    _installed = True
    return True

"""A child frame that disappears mid-read is skipped instead of blanking the page."""
import asyncio
from types import SimpleNamespace

import pytest

from agent.ec_skills.browser_use_extension import vanished_frame_patch as vf


class _Send:
    def __init__(self, missing):
        self.missing = missing
        self.Page = SimpleNamespace(getFrameTree=self._tree)
        self.Accessibility = SimpleNamespace(getFullAXTree=self._ax)

    async def _tree(self, session_id=None):
        return {'frameTree': {'frame': {'id': 'main'},
                              'childFrames': [{'frame': {'id': 'ad'}}, {'frame': {'id': 'video'}}]}}

    async def _ax(self, params, session_id=None):
        if params['frameId'] in self.missing:
            raise RuntimeError({'code': -32602, 'message': 'Frame with the given frameId is not found.'})
        return {'nodes': [params['frameId']]}


def _service(missing):
    session = SimpleNamespace(session_id='s', cdp_client=SimpleNamespace(send=_Send(missing)))

    async def get_session(target_id, focus):
        return session
    return SimpleNamespace(browser_session=SimpleNamespace(get_or_create_cdp_session=get_session))


def test_vanished_child_frame_is_skipped():
    out = asyncio.run(vf._get_ax_tree_for_all_frames(_service({'ad'}), 't'))
    assert out == {'nodes': ['main', 'video']}


def test_main_frame_failure_still_raises():
    with pytest.raises(RuntimeError):
        asyncio.run(vf._get_ax_tree_for_all_frames(_service({'main'}), 't'))


def test_install_replaces_browser_use_method():
    from browser_use.dom.service import DomService
    assert vf.install()
    assert DomService._get_ax_tree_for_all_frames is vf._get_ax_tree_for_all_frames

"""Follow-ups batch tests (post Phase 1-4, 2026-08-23).

Covers docs/SHARED_SKILL_MULTI_TASK_PLAN.md "Follow-ups batch":
- skill_owner survives persistence via the config-JSON fold (was silently
  dropped by add_skill's column filter — B: store download flow).
- The read-back path prefers top-level skill_owner, then config, then owner.
- Phase 5a: typing lock is per-session; dispatch-inflight keys carry an
  optional session component. Single-session (default) behavior unchanged.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from agent.db.core.base import Base
from agent.db.services.db_skill_service import DBSkillService


@pytest.fixture
def service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return DBSkillService(engine=engine)


class TestSkillOwnerPersistence:
    def test_add_skill_folds_skill_owner_into_config(self, service):
        result = service.add_skill({
            'id': 'sk_1', 'name': 'store skill', 'owner': 'buyer@example.com',
            'version': '1.0', 'skill_owner': 'author@example.com',
            'config': {'run_mode': 'released'},
        })
        assert result['success']
        row = service.get_skill_by_id('sk_1')['data']
        assert row['config']['skill_owner'] == 'author@example.com'
        assert row['config']['run_mode'] == 'released'  # existing config preserved

    def test_add_skill_without_config_still_persists_author(self, service):
        service.add_skill({
            'id': 'sk_2', 'name': 's', 'owner': 'buyer', 'version': '1',
            'skill_owner': 'author@example.com',
        })
        row = service.get_skill_by_id('sk_2')['data']
        assert row['config']['skill_owner'] == 'author@example.com'

    def test_update_without_config_does_not_clobber(self, service):
        """A partial update carrying skill_owner but no config must NOT
        synthesize a config dict (would overwrite the row's whole config)."""
        service.add_skill({
            'id': 'sk_3', 'name': 's', 'owner': 'buyer', 'version': '1',
            'skill_owner': 'author@example.com', 'config': {'keep': 'me'},
        })
        service.update_skill('sk_3', {'skill_owner': 'other@example.com', 'name': 's2'})
        row = service.get_skill_by_id('sk_3')['data']
        assert row['config'] == {'keep': 'me', 'skill_owner': 'author@example.com'}
        assert row['name'] == 's2'

    def test_readback_prefers_toplevel_then_config_then_owner(self):
        from agent.ec_skills.build_agent_skills import _fill_skill_from_db_view
        from agent.db.models.skill_model import DBAgentSkill
        from agent.ec_skill import EC_Skill

        def fill(row):
            sk = EC_Skill(name='x', description='d')
            _fill_skill_from_db_view(sk, DBAgentSkill.view(row))
            return sk.skill_owner

        base = {'id': 'i', 'name': 'n', 'owner': 'buyer@x', 'version': '1'}
        assert fill({**base, 'skill_owner': 'top@x', 'config': {'skill_owner': 'cfg@x'}}) == 'top@x'
        assert fill({**base, 'config': {'skill_owner': 'cfg@x'}}) == 'cfg@x'
        assert fill(base) == 'buyer@x'


class TestPhase5aSessionScoping:
    def test_typing_lock_sessions_isolated(self):
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import typing_lock as tl

        tl.reset()
        try:
            assert tl.try_acquire('custA', session_key='shop1')
            assert not tl.try_acquire('custB', session_key='shop1')  # blocked, same shop
            assert tl.try_acquire('custB', session_key='shop2')      # other shop unaffected
            assert tl.holder('shop1') == 'custA'
            assert tl.holder('shop2') == 'custB'
            # a caller that names no shop contends with every shop: it may cost
            # parallelism, never let two sends race inside one shop's page
            assert not tl.try_acquire('custC')
            tl.release('custA', session_key='shop1')
            assert tl.holder('shop1') == ''
            assert tl.holder('shop2') == 'custB'                     # untouched
            tl.release('custB', session_key='shop2')
            assert tl.try_acquire('custC')                           # unkeyed, all free
            assert not tl.try_acquire('custD', session_key='shop1')  # ...and it blocks shops
        finally:
            tl.reset()

    def test_typing_lock_default_session_behavior_unchanged(self):
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import typing_lock as tl

        tl.reset()
        try:
            assert tl.try_acquire('custA')
            assert tl.try_acquire('custA')      # re-entrant
            assert not tl.try_acquire('custB')  # contended
            tl.release('custB')                 # non-holder release is a no-op
            assert tl.holder() == 'custA'
        finally:
            tl.reset()

    def test_dispatch_inflight_session_keys(self):
        from agent.ec_skills import build_node as bn

        bn._dispatch_inflight.clear()
        try:
            bn._mark_dispatch_inflight('小明')                       # single-shop (default)
            bn._mark_dispatch_inflight('小明', session_key='shop2')  # same nickname, other shop
            assert bn._is_dispatch_inflight('小明') > 0
            assert bn._is_dispatch_inflight('小明', session_key='shop2') > 0
            bn._clear_dispatch_inflight('小明')
            assert bn._is_dispatch_inflight('小明') == 0.0
            assert bn._is_dispatch_inflight('小明', session_key='shop2') > 0  # isolated
        finally:
            bn._dispatch_inflight.clear()


class TestCompanionTaskVarInheritance:
    def test_worker_message_carries_and_applies_vars(self):
        """WorkerMessage task_vars land in task.metadata and the run state
        (cloud-worker half of hybrid task_vars)."""
        from agent.ec_skills.prep_skills_run import apply_task_vars

        task = SimpleNamespace(metadata={'task_vars': {'shop_name': 'Shop A'},
                                         'browser_identity': {'profile': 'shop-a'}})
        state = {}
        apply_task_vars(task, state)
        assert state['prompt_refs']['shop_name'] == 'Shop A'
        assert state['attributes']['browser_profile'] == 'shop-a'

"""Phase 4 tests: retire copy-per-agent — skill dedupe + author prompt owner.

Covers docs/SHARED_SKILL_MULTI_TASK_PLAN.md Phase 4:
- ``DBSkillService.find_duplicate_skills`` groups identical-diagram copies
  and picks the earliest as canonical (code skills / diagram-less excluded).
- ``DBSkillService.merge_skill_references`` re-points agent-skill and
  task-skill relationships, dropping rows that would violate the unique
  constraints.
- ``_compile_skill_workflow_from_flow`` compiles with the AUTHOR
  (``skill_obj.skill_owner``) as the flow owner so prompts of store/rented
  skills resolve under the author's partition.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

from agent.db.core.base import Base
from agent.db.models.skill_model import DBAgentSkill
from agent.db.models.association_models import DBAgentSkillRel, DBAgentTaskSkillRel
from agent.db.services.db_skill_service import DBSkillService


DIAGRAM_A = {"nodes": [{"id": "n1", "type": "llm"}], "edges": []}
DIAGRAM_B = {"nodes": [{"id": "n2", "type": "code"}], "edges": []}


@pytest.fixture
def service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return DBSkillService(engine=engine)


def _add_skill(service, skill_id, name, diagram=None, source='ui', created=None, owner='tester'):
    with service.session_scope() as s:
        s.add(DBAgentSkill(
            id=skill_id, name=name, owner=owner, version='1.0',
            diagram=diagram, source=source,
            created_at=created or datetime.utcnow(),
        ))


def _add_agent_rel(service, agent_id, skill_id):
    with service.session_scope() as s:
        s.add(DBAgentSkillRel(agent_id=agent_id, skill_id=skill_id))


def _add_task_rel(service, task_id, skill_id):
    with service.session_scope() as s:
        s.add(DBAgentTaskSkillRel(task_id=task_id, skill_id=skill_id))


class TestFindDuplicateSkills:
    def test_groups_identical_diagrams(self, service):
        t0 = datetime(2026, 1, 1)
        _add_skill(service, 'sk_old', 'bot copy 1', DIAGRAM_A, created=t0)
        _add_skill(service, 'sk_new', 'bot copy 2', DIAGRAM_A, created=t0 + timedelta(days=1))
        _add_skill(service, 'sk_other', 'different bot', DIAGRAM_B)

        result = service.find_duplicate_skills('tester')
        assert result['success']
        groups = result['data']
        assert len(groups) == 1
        assert groups[0]['canonical']['id'] == 'sk_old'  # earliest created wins
        assert [d['id'] for d in groups[0]['duplicates']] == ['sk_new']

    def test_excludes_code_and_diagramless_skills(self, service):
        _add_skill(service, 'sk_c1', 'code skill', DIAGRAM_A, source='code')
        _add_skill(service, 'sk_c2', 'code skill 2', DIAGRAM_A, source='code')
        _add_skill(service, 'sk_n1', 'no diagram 1', None)
        _add_skill(service, 'sk_n2', 'no diagram 2', None)

        result = service.find_duplicate_skills('tester')
        assert result['success']
        assert result['data'] == []

    def test_other_owner_not_included(self, service):
        _add_skill(service, 'sk_1', 'a', DIAGRAM_A, owner='tester')
        _add_skill(service, 'sk_2', 'b', DIAGRAM_A, owner='someone_else')

        result = service.find_duplicate_skills('tester')
        assert result['data'] == []


class TestMergeSkillReferences:
    def test_repoints_agent_and_task_rels(self, service):
        _add_skill(service, 'sk_canon', 'bot', DIAGRAM_A)
        _add_skill(service, 'sk_dup', 'bot copy', DIAGRAM_A)
        _add_agent_rel(service, 'agent_1', 'sk_dup')
        _add_task_rel(service, 'task_1', 'sk_dup')

        result = service.merge_skill_references('sk_dup', 'sk_canon')
        assert result['success']
        assert result['data'] == {
            'agent_rels_moved': 1, 'agent_rels_dropped': 0,
            'task_rels_moved': 1, 'task_rels_dropped': 0,
        }
        with service.session_scope() as s:
            assert s.query(DBAgentSkillRel).filter_by(skill_id='sk_canon').count() == 1
            assert s.query(DBAgentTaskSkillRel).filter_by(skill_id='sk_canon').count() == 1
            assert s.query(DBAgentSkillRel).filter_by(skill_id='sk_dup').count() == 0

    def test_drops_rel_when_target_already_bound(self, service):
        """Agent already has the canonical skill → duplicate rel is deleted,
        not re-pointed (would violate the unique constraint)."""
        _add_skill(service, 'sk_canon', 'bot', DIAGRAM_A)
        _add_skill(service, 'sk_dup', 'bot copy', DIAGRAM_A)
        _add_agent_rel(service, 'agent_1', 'sk_canon')
        _add_agent_rel(service, 'agent_1', 'sk_dup')

        result = service.merge_skill_references('sk_dup', 'sk_canon')
        assert result['success']
        assert result['data']['agent_rels_dropped'] == 1
        assert result['data']['agent_rels_moved'] == 0
        with service.session_scope() as s:
            assert s.query(DBAgentSkillRel).filter_by(agent_id='agent_1').count() == 1

    def test_same_id_rejected(self, service):
        result = service.merge_skill_references('sk_x', 'sk_x')
        assert not result['success']


class TestAuthorOwnerCompilation:
    def _compile(self, skill_owner, flow):
        from agent.ec_skills.build_agent_skills import _compile_skill_workflow_from_flow

        captured = {}

        def fake_convert(flow_arg, **kwargs):
            captured['flow'] = flow_arg
            return None, []

        skill_obj = SimpleNamespace(name='store_skill', skill_owner=skill_owner,
                                    set_work_flow=lambda wf: None)
        with patch('agent.ec_skills.build_agent_skills.flowgram2langgraph_v2',
                   side_effect=fake_convert):
            _compile_skill_workflow_from_flow(
                skill_obj=skill_obj, flow_for_convert=flow, bundle_dict=None)
        return captured['flow']

    def test_author_overrides_local_owner(self):
        flow = {'owner': 'buyer@example.com', 'workFlow': {'nodes': [], 'edges': []}}
        compiled_flow = self._compile('author@example.com', flow)
        assert compiled_flow['owner'] == 'author@example.com'
        # original dict untouched (copy, not mutation)
        assert flow['owner'] == 'buyer@example.com'

    def test_self_authored_skill_unchanged(self):
        flow = {'owner': 'me@example.com', 'workFlow': {'nodes': [], 'edges': []}}
        compiled_flow = self._compile('me@example.com', flow)
        assert compiled_flow is flow  # no copy needed

    def test_empty_skill_owner_keeps_flow_owner(self):
        flow = {'owner': 'me@example.com', 'workFlow': {'nodes': [], 'edges': []}}
        compiled_flow = self._compile('', flow)
        assert compiled_flow['owner'] == 'me@example.com'

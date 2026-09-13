"""The cloud agent loader — why a WeChat owner saw zero of their three agents.

Reported 2026-09-12: the desktop showed no agents. The server was proved fine
(the same query with that session returns all three), and the run log showed the
response arriving with the agents in it, immediately followed by::

    WARNING - No agents data returned from cloud
    [MainWindow] Parallel loading completed: Code-built: 0, DB: 0, Cloud: 0

Four defects on one path, each of which alone produces exactly that outcome:

1. ``send_get_agents_request_to_cloud`` returns the parsed ``queryAgents`` list,
   but the caller tested for a ``{'body': ...}`` Lambda-proxy envelope. A list
   never matches, so every cloud load reported "no agents" while holding them.
2. ``schema.from_cloud`` keeps only mapped columns and the cloud carries an
   agent's skill/task ids inside ``extra_data``; ``gen_new_agent`` reads
   ``ajs['skills']`` and raised KeyError, swallowed by the outer except.
3. ``gen_new_agent``'s debug line indexed ``all_skills[0]`` — on a fresh profile
   (no local skills yet) that is an IndexError, swallowed the same way.
4. The cloud sends ``description: null`` and ``AgentCard.description`` is a
   required ``str``, so pydantic rejected every agent — found by the test for 3,
   not by reading the code.

The shape of the bug is worth more than the fix: each failure was caught by a
broad ``except`` and reported as "no agents", which is indistinguishable from an
account that genuinely has none. The tests therefore assert the agents arrive,
not merely that nothing raised.
"""

import json
import types

import pytest

from agent.ec_agents import agent_utils


# A real row, from the run log (owner is the bare openid; the skill/task ids
# live double-encoded inside extra_data).
CLOUD_AGENT = {
    "id": "agent_ade75aa77b7c4d01",
    "owner": "o3YBk2dxaRe3LKqJXCf5z3PfvD5M",
    "name": "李四",
    "title": "{}",
    "supervisor_id": None,
    "birthday": "2026-08-17",
    "gender": "male",
    "personalities": "{}",
    "status": "active",
    "rank": None,
    "vehicle_id": "1",
    "avatar_resource_id": None,
    "description": None,
    "url": None,
    "version": None,
    "extra_data": json.dumps({
        "notes": json.dumps({
            "owner": "wechat_b603a407904569a4ea88f9ac",
            "skills": ["skill_71209937ed7449bf"],
            "tasks": ["task_a83668efa3a64e56"],
            "org_ids": ["org_root_x"],
        })
    }),
}


class _MainWin:
    """A main window with nothing loaded yet — a freshly-created profile."""

    def __init__(self, skills=None, tasks=None):
        self.llm = object()
        self.browser_use_llm = object()
        self.agent_skills = skills if skills is not None else []
        self.agent_tasks = tasks if tasks is not None else []
        self.agents = []
        self.user = "wechat_o3YBk2dxaRe3LKqJXCf5z3PfvD5M@local"

    def get_auth_token(self):
        return "session-token"

    def getWanApiEndpoint(self):
        return "https://example.invalid/api/graphql"


@pytest.fixture
def loaded(monkeypatch):
    """Run load_agents_from_cloud against a canned queryAgents response."""

    def _run(response, mainwin=None, agent_factory=None):
        mainwin = mainwin or _MainWin()
        monkeypatch.setattr(
            "agent.cloud_api.cloud_api.send_get_agents_request_to_cloud",
            lambda session, token, endpoint: response,
        )
        if agent_factory is None:
            # Stand in for EC_Agent construction, which needs a real app.
            def agent_factory(mainwin, ajs):
                return types.SimpleNamespace(
                    id=ajs["id"], name=ajs["name"],
                    skills=ajs.get("skills"), tasks=ajs.get("tasks"),
                )
        monkeypatch.setattr(agent_utils, "gen_new_agent", agent_factory)
        return agent_utils.load_agents_from_cloud(mainwin), mainwin

    return _run


# ===========================================================================
# Defect 1 — the response envelope
# ===========================================================================

def test_a_plain_list_of_agents_is_loaded(loaded):
    """This is what the server actually returns, and it produced zero agents."""
    agents, mainwin = loaded([CLOUD_AGENT])
    assert [a.name for a in agents] == ["李四"]
    assert mainwin.agents == agents


def test_three_agents_arrive_as_three(loaded):
    rows = [dict(CLOUD_AGENT, id=f"agent_{i}", name=f"agent-{i}") for i in range(3)]
    agents, _ = loaded(rows)
    assert len(agents) == 3


def test_the_legacy_body_envelope_still_works(loaded):
    """Kept so an older backend shape does not silently start returning zero."""
    agents, _ = loaded({"body": json.dumps([CLOUD_AGENT])})
    assert [a.name for a in agents] == ["李四"]


def test_an_empty_account_is_not_an_error(loaded):
    agents, _ = loaded([])
    assert agents == []


def test_an_error_object_yields_no_agents(loaded):
    """The error paths return the GraphQL error, not a list."""
    agents, _ = loaded({"message": "UNAUTHENTICATED"})
    assert agents == []


# ===========================================================================
# Defect 2 — relations the conversion drops
# ===========================================================================

def test_skill_and_task_ids_survive_the_conversion(loaded):
    """gen_new_agent reads them as comma-separated strings, or raises KeyError."""
    agents, _ = loaded([CLOUD_AGENT])
    assert agents[0].skills == "skill_71209937ed7449bf"
    assert agents[0].tasks == "task_a83668efa3a64e56"


def test_an_agent_with_unreadable_extra_data_still_appears(loaded):
    """Better to list an agent with no skills than to lose the agent."""
    agents, _ = loaded([dict(CLOUD_AGENT, extra_data="{not json at all")])
    assert [a.name for a in agents] == ["李四"]
    assert agents[0].skills == ""


def test_an_agent_with_no_extra_data_still_appears(loaded):
    agents, _ = loaded([{k: v for k, v in CLOUD_AGENT.items() if k != "extra_data"}])
    assert len(agents) == 1


# ===========================================================================
# Defect 3 — gen_new_agent on a profile with nothing loaded yet
# ===========================================================================

@pytest.fixture
def built(monkeypatch):
    """gen_new_agent with EC_Agent stubbed — constructing a real one needs an app."""
    built = {}

    class _Stub:
        def __init__(self, mainwin=None, skill_llm=None, llm=None, task="",
                     card=None, skills=None, tasks=None):
            self.card = card
            self.skills = skills or []
            self.tasks = tasks or []
            built["agent"] = self

    monkeypatch.setattr(agent_utils, "EC_Agent", _Stub)
    return built


def _skill(skill_id, name):
    from agent.ec_skill import EC_Skill

    return EC_Skill(id=skill_id, name=name, description="", tags=[])


def test_gen_new_agent_survives_an_empty_skill_list(built):
    """A fresh profile has no local skills; indexing all_skills[0] dropped every
    agent being loaded, and the except above turned that into "no agents"."""
    mainwin = _MainWin(skills=[], tasks=[])
    agent = agent_utils.gen_new_agent(mainwin, {
        "id": "agent_1", "name": "李四", "description": None,
        "skills": "", "tasks": "",
    })
    assert agent is not None
    assert agent.card.name == "李四"
    # description=None is what the cloud sends, and AgentCard requires a string
    assert agent.card.description == ""


def test_gen_new_agent_tolerates_missing_relation_keys(built):
    """A dict built from a cloud row legitimately has neither key."""
    mainwin = _MainWin()
    agent = agent_utils.gen_new_agent(mainwin, {"id": "agent_1", "name": "李四"})
    assert agent is not None


def test_gen_new_agent_attaches_known_skills(built):
    """The happy path still works: ids that match local skills are attached."""
    mainwin = _MainWin(skills=[_skill("skill_71209937ed7449bf", "飞鸽客服前台00")])
    agent = agent_utils.gen_new_agent(mainwin, {
        "id": "agent_1", "name": "李四",
        "skills": "skill_71209937ed7449bf", "tasks": "",
    })
    assert agent is not None
    assert [s.id for s in agent.card.skills] == ["skill_71209937ed7449bf"]

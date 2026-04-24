"""
Cloud API Mock Server for offline development testing.

Provides in-memory mock implementations of Cloud API endpoints,
allowing integration tests to run without a real cloud connection.

Usage:
    mock = CloudAPIMockServer()
    mock.mock_add_skill(session, [skill])
    mock.mock_get_agents(session)
"""

import threading
from typing import Any, Callable
from tests.framework.data_factory import _gen_id


class CloudAPIMockServer:
    """
    In-memory mock of the Cloud API backend.

    Stores entities in memory per-instance. Each test gets a fresh
    instance, ensuring complete isolation.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()  # ReentrantLock - safe for nested calls
        self._storage: dict[str, list[dict]] = {
            "agents": [],
            "skills": [],
            "tasks": [],
            "tools": [],
            "knowledges": [],
            "organizations": [],
            "avatars": [],
            "prompts": [],
            "vehicles": [],
        }
        self._error_injections: dict[str, Exception] = {}

    # -------------------------------------------------------------------------
    # Storage helpers
    # -------------------------------------------------------------------------

    def _find(self, entity: str, entity_id: str) -> dict | None:
        with self._lock:
            for item in self._storage.get(entity, []):
                if item.get("id") == entity_id or item.get("askid") == entity_id:
                    return item
            return None

    def _upsert(self, entity: str, item: dict) -> None:
        with self._lock:
            existing = self._find(entity, item.get("id") or item.get("askid"))
            if existing:
                existing.update(item)
            else:
                self._storage.setdefault(entity, []).append(item)

    def _remove(self, entity: str, entity_id: str) -> bool:
        with self._lock:
            items = self._storage.get(entity, [])
            for i, item in enumerate(items):
                if item.get("id") == entity_id or item.get("askid") == entity_id:
                    items.pop(i)
                    return True
            return False

    def inject_error(self, method: str, error: Exception) -> None:
        """Inject a deliberate error for a given method."""
        self._error_injections[method] = error

    def clear_storage(self) -> None:
        """Clear all stored entities."""
        with self._lock:
            for key in self._storage:
                self._storage[key].clear()

    def get_storage(self) -> dict[str, list[dict]]:
        """Return a deep copy of current storage."""
        import copy
        with self._lock:
            return copy.deepcopy(self._storage)

    # -------------------------------------------------------------------------
    # Agent API mocks
    # -------------------------------------------------------------------------

    def mock_add_agents(self, session: Any, agents: list[dict]) -> dict:
        if "agent_add" in self._error_injections:
            raise self._error_injections["agent_add"]
        for agent in agents:
            self._upsert("agents", agent)
        return {"success": True, "count": len(agents), "data": agents}

    def mock_get_agents(self, session: Any, token: str, filters: dict | None = None) -> dict:
        if "agent_get" in self._error_injections:
            raise self._error_injections["agent_get"]
        with self._lock:
            agents = list(self._storage.get("agents", []))
        return {"data": {"agents": agents}}

    def mock_update_agents(self, session: Any, agents: list[dict]) -> dict:
        for agent in agents:
            self._upsert("agents", agent)
        return {"success": True, "count": len(agents)}

    def mock_remove_agents(self, session: Any, agent_ids: list[dict]) -> dict:
        count = 0
        for entry in agent_ids:
            entity_id = entry.get("id") or entry.get("askid")
            if self._remove("agents", entity_id):
                count += 1
        return {"success": True, "count": count}

    # -------------------------------------------------------------------------
    # Skill API mocks
    # -------------------------------------------------------------------------

    def mock_add_skills(self, session: Any, skills: list[dict]) -> dict:
        if "skill_add" in self._error_injections:
            raise self._error_injections["skill_add"]
        for skill in skills:
            self._upsert("skills", skill)
        return {"success": True, "count": len(skills), "data": skills}

    def mock_get_skills(self, session: Any, token: str, filters: dict | None = None) -> dict:
        if "skill_get" in self._error_injections:
            raise self._error_injections["skill_get"]
        with self._lock:
            skills = list(self._storage.get("skills", []))
        return {"data": {"skills": skills}}

    def mock_update_skills(self, session: Any, skills: list[dict]) -> dict:
        for skill in skills:
            self._upsert("skills", skill)
        return {"success": True, "count": len(skills)}

    def mock_remove_skills(self, session: Any, skill_ids: list[dict]) -> dict:
        count = 0
        for entry in skill_ids:
            entity_id = entry.get("id") or entry.get("askid")
            if self._remove("skills", entity_id):
                count += 1
        return {"success": True, "count": count}

    # -------------------------------------------------------------------------
    # Task API mocks
    # -------------------------------------------------------------------------

    def mock_add_tasks(self, session: Any, tasks: list[dict]) -> dict:
        for task in tasks:
            self._upsert("tasks", task)
        return {"success": True, "count": len(tasks), "data": tasks}

    def mock_get_tasks(self, session: Any, token: str, filters: dict | None = None) -> dict:
        with self._lock:
            tasks = list(self._storage.get("tasks", []))
        return {"data": {"tasks": tasks}}

    def mock_update_tasks(self, session: Any, tasks: list[dict]) -> dict:
        for task in tasks:
            self._upsert("tasks", task)
        return {"success": True, "count": len(tasks)}

    def mock_remove_tasks(self, session: Any, task_ids: list[dict]) -> dict:
        count = 0
        for entry in task_ids:
            entity_id = entry.get("id") or entry.get("askid")
            if self._remove("tasks", entity_id):
                count += 1
        return {"success": True, "count": count}

    # -------------------------------------------------------------------------
    # Tool API mocks
    # -------------------------------------------------------------------------

    def mock_add_tools(self, session: Any, tools: list[dict]) -> dict:
        for tool in tools:
            self._upsert("tools", tool)
        return {"success": True, "count": len(tools), "data": tools}

    def mock_get_tools(self, session: Any, token: str, filters: dict | None = None) -> dict:
        with self._lock:
            tools = list(self._storage.get("tools", []))
        return {"data": {"tools": tools}}

    def mock_remove_tools(self, session: Any, tool_ids: list[dict]) -> dict:
        count = 0
        for entry in tool_ids:
            entity_id = entry.get("id") or entry.get("askid")
            if self._remove("tools", entity_id):
                count += 1
        return {"success": True, "count": count}

    # -------------------------------------------------------------------------
    # Knowledge API mocks
    # -------------------------------------------------------------------------

    def mock_add_knowledge(self, session: Any, knowledges: list[dict]) -> dict:
        for k in knowledges:
            self._upsert("knowledges", k)
        return {"success": True, "count": len(knowledges)}

    def mock_get_knowledge(self, session: Any, token: str, filters: dict | None = None) -> dict:
        with self._lock:
            knowledges = list(self._storage.get("knowledges", []))
        return {"data": {"knowledges": knowledges}}

    def mock_remove_knowledge(self, session: Any, knowledge_ids: list[dict]) -> dict:
        count = 0
        for entry in knowledge_ids:
            if self._remove("knowledges", entry.get("id", "")):
                count += 1
        return {"success": True, "count": count}

    # -------------------------------------------------------------------------
    # Account info mock
    # -------------------------------------------------------------------------

    def mock_account_info(self, session: Any, acct_ops: list[dict]) -> dict:
        return {
            "data": {
                "account_info": {
                    "user_id": "test_user_123",
                    "username": "unittest@test.com",
                    "plan": "free",
                    "quota_used": 0,
                    "quota_limit": 100,
                }
            }
        }

"""
Test Data Factory - Generates reproducible test data for eCan.ai entities.

Usage:
    from tests.framework.data_factory import AgentFactory, SkillFactory

    agent = AgentFactory.create(name="My Test Agent")
    skill = SkillFactory.create_with_flowgram()
    agents = AgentFactory.create_batch(5)
"""

import uuid
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _gen_id(prefix: str) -> str:
    return f"test_{prefix}_{uuid.uuid4().hex[:8]}"


# ============================================================================
# Agent Factory
# ============================================================================

class AgentFactory:
    """Factory for creating test Agent entities."""

    @staticmethod
    def create(
        name: str = "Test Agent",
        owner: str = "unittest@test.com",
        description: str = "Auto-generated test agent",
        status: str = "active",
        agent_type: str = "general",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("agent"),
            "owner": owner,
            "name": name,
            "description": description,
            "status": status,
            "agent_type": agent_type,
            "version": "1.0.0",
            "created_at": _utc_now(),
            **overrides,
        }

    @staticmethod
    def create_batch(count: int, **kwargs: Any) -> list[dict]:
        return [AgentFactory.create(**kwargs) for _ in range(count)]


# ============================================================================
# Skill Factory
# ============================================================================

class SkillFactory:
    """Factory for creating test Skill entities."""

    @staticmethod
    def create(
        name: str = "Test Skill",
        owner: str = "unittest@test.com",
        description: str = "Auto-generated test skill",
        version: str = "1.0.0",
        status: str = "draft",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("skill"),
            "askid": _gen_id("skill"),  # legacy field
            "owner": owner,
            "name": name,
            "description": description,
            "version": version,
            "status": status,
            "path": "",
            "source": "",
            "flowgram": {},
            "langgraph": {},
            "public": False,
            "rentable": False,
            "price": 0.0,
            "created_at": _utc_now(),
            **overrides,
        }

    @staticmethod
    def create_with_flowgram(name: str = "Test Flowgram Skill", **kwargs: Any) -> dict:
        flowgram = {
            "skillName": name,
            "owner": kwargs.get("owner", "unittest@test.com"),
            "workFlow": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {
                        "id": "code_1",
                        "type": "code",
                        "data": {
                            "script": {"content": "def main(state):\n    return state\n"}
                        },
                    },
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"sourceNodeID": "start", "targetNodeID": "code_1"},
                    {"sourceNodeID": "code_1", "targetNodeID": "end"},
                ],
            },
        }
        return SkillFactory.create(name=name, flowgram=flowgram, **kwargs)

    @staticmethod
    def create_batch(count: int, **kwargs: Any) -> list[dict]:
        return [SkillFactory.create(**kwargs) for _ in range(count)]


# ============================================================================
# Task Factory
# ============================================================================

class TaskFactory:
    """Factory for creating test Task entities."""

    @staticmethod
    def create(
        name: str = "Test Task",
        owner: str = "unittest@test.com",
        description: str = "Auto-generated test task",
        status: str = "pending",
        task_type: str = "general",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("task"),
            "owner": owner,
            "name": name,
            "description": description,
            "status": status,
            "task_type": task_type,
            "version": "1.0.0",
            "created_at": _utc_now(),
            **overrides,
        }

    @staticmethod
    def create_batch(count: int, **kwargs: Any) -> list[dict]:
        return [TaskFactory.create(**kwargs) for _ in range(count)]


# ============================================================================
# Tool Factory
# ============================================================================

class ToolFactory:
    """Factory for creating test Tool entities."""

    @staticmethod
    def create(
        name: str = "Test Tool",
        owner: str = "unittest@test.com",
        description: str = "Auto-generated test tool",
        tool_type: str = "mcp",
        status: str = "active",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("tool"),
            "owner": owner,
            "name": name,
            "description": description,
            "tool_type": tool_type,
            "status": status,
            "version": "1.0.0",
            "created_at": _utc_now(),
            **overrides,
        }


# ============================================================================
# Knowledge Factory
# ============================================================================

class KnowledgeFactory:
    """Factory for creating test Knowledge entities."""

    @staticmethod
    def create(
        name: str = "Test Knowledge",
        owner: str = "unittest@test.com",
        description: str = "Auto-generated test knowledge",
        knowledge_type: str = "general",
        status: str = "active",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("knowledge"),
            "owner": owner,
            "name": name,
            "description": description,
            "knowledge_type": knowledge_type,
            "status": status,
            "version": "1.0.0",
            "public": False,
            "created_at": _utc_now(),
            **overrides,
        }


# ============================================================================
# Organization Factory
# ============================================================================

class OrganizationFactory:
    """Factory for creating test Organization entities."""

    @staticmethod
    def create(
        name: str = "Test Organization",
        description: str = "Auto-generated test organization",
        org_type: str = "test",
        status: str = "active",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("org"),
            "name": name,
            "description": description,
            "org_type": org_type,
            "status": status,
            "version": "1.0.0",
            "created_at": _utc_now(),
            **overrides,
        }


# ============================================================================
# Avatar Factory
# ============================================================================

class AvatarFactory:
    """Factory for creating test Avatar entities."""

    @staticmethod
    def create(
        name: str = "Test Avatar",
        owner: str = "unittest@test.com",
        description: str = "Auto-generated test avatar",
        resource_type: str = "image",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("avatar"),
            "owner": owner,
            "name": name,
            "description": description,
            "resource_type": resource_type,
            "image_path": "gui_v2/public/assets/gifs/agent0.mp4",
            "cloud_synced": True,
            "is_public": True,
            "created_at": _utc_now(),
            **overrides,
        }


# ============================================================================
# Prompt Factory
# ============================================================================

class PromptFactory:
    """Factory for creating test Prompt entities."""

    @staticmethod
    def create(
        name: str = "Test Prompt",
        owner: str = "unittest@test.com",
        content: str = "You are a helpful assistant.",
        category: str = "test",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("prompt"),
            "owner": owner,
            "version": "1.0.0",
            "prompt": {
                "name": name,
                "content": content,
                "category": category,
            },
            "created_at": _utc_now(),
            **overrides,
        }


# ============================================================================
# Vehicle Factory
# ============================================================================

class VehicleFactory:
    """Factory for creating test Vehicle entities."""

    @staticmethod
    def create(
        name: str = "Test Vehicle",
        description: str = "Auto-generated test vehicle",
        status: str = "active",
        vehicle_type: str = "general",
        **overrides: Any,
    ) -> dict:
        return {
            "id": _gen_id("vehicle"),
            "name": name,
            "description": description,
            "status": status,
            "vehicle_type": vehicle_type,
            "version": "1.0.0",
            "created_at": _utc_now(),
            **overrides,
        }

"""
eCan.ai Testing Framework
==========================
Core testing infrastructure for development-stage automated testing.

Structure:
    framework/          - Core framework modules
    fixtures/           - Reusable pytest fixtures
    unit/               - Unit tests (pure functions, no I/O)
    integration/        - Integration tests (mocked dependencies)
    smoke/              - Smoke tests (critical path validation)
    e2e/                - End-to-end tests (full flow via WebSocket)
"""

from tests.framework.data_factory import (
    AgentFactory,
    SkillFactory,
    TaskFactory,
    ToolFactory,
    KnowledgeFactory,
    OrganizationFactory,
)

from tests.framework.test_client import ECTestClient
from tests.framework.mock_server import CloudAPIMockServer
from tests.framework.runners import ECTestRunner
from tests.framework.reporters import TestReporter

__all__ = [
    "AgentFactory",
    "SkillFactory",
    "TaskFactory",
    "ToolFactory",
    "KnowledgeFactory",
    "OrganizationFactory",
    "ECTestClient",
    "CloudAPIMockServer",
    "ECTestRunner",
    "TestReporter",
]

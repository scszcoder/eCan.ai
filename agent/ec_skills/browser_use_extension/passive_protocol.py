from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class PassiveBrowserCommand(BaseModel):
    """Cloud -> Client.

    A single 'step' request to execute 1..N browser-use actions.

    Transport agnostic: can be sent over websocket, HTTP long-poll, AppSync, etc.
    """

    schema_version: int = Field(default=1)
    type: Literal["browser_use_passive_step"] = Field(default="browser_use_passive_step")

    # Correlation
    run_id: str
    step_id: str

    # Identity / routing (optional but recommended)
    acct_site_id: str | None = None
    agent_id: str | None = None
    skill_id: str | None = None
    node_id: str | None = None

    # Browser actions (browser-use action dicts)
    actions: list[dict[str, dict[str, Any]]] = Field(default_factory=list)

    # Controls
    include_screenshot: bool = False
    stop_on_error: bool = True


class PassiveBrowserStepResult(BaseModel):
    """Client -> Cloud.

    Returned after executing the requested actions.
    """

    schema_version: int = Field(default=1)
    type: Literal["browser_use_passive_step_result"] = Field(default="browser_use_passive_step_result")

    # Correlation
    run_id: str
    step_id: str

    ok: bool = True
    elapsed_ms: int = 0

    # Echo executed actions + results
    actions: list[dict[str, dict[str, Any]]] = Field(default_factory=list)
    action_results: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # Browser snapshot (already pruned + privacy-filtered by client)
    browser: dict[str, Any] = Field(default_factory=dict)


class PassiveBrowserHello(BaseModel):
    """Client -> Cloud.

    Useful for websocket: client announces capabilities.
    """

    schema_version: int = Field(default=1)
    type: Literal["browser_use_passive_hello"] = Field(default="browser_use_passive_hello")

    agent_id: str | None = None
    client_id: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)

"""
Group A2A sends — fan one payload out to many agents in parallel.

Built on top of ``router.send_to_agent`` (which picks LAN vs WAN per call)
and ``query.find_agents`` (which picks the recipients from filters).

Two main public functions:

    send_to_group(agent_ids, payload)
        Parallel fanout to an explicit list. Returns a per-agent result map.

    send_to_skill(skill, payload, mode="any" | "all" | "n=N")
        Find agents offering ``skill`` and dispatch. "any" picks the first
        reachable, "all" broadcasts to every match, "n=3" sends to the
        top-3 by transport preference (useful for quorum patterns).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, Optional

from agent.a2a.discovery.directory import AgentEndpoint
from agent.a2a.discovery.query import find_agents
from agent.a2a.discovery.router import SendOutcome, SendResult, send_to_agent
from utils.logger_helper import logger_helper as logger


@dataclass
class GroupSendReport:
    """Aggregate result of a fanout send.

    ``per_agent`` maps agent_id → SendOutcome. ``targets`` lists the
    endpoints we attempted (lets the caller see who we picked even when
    none succeeded — handy for "no agent offers skill X" UX).
    """
    targets: list[AgentEndpoint]
    per_agent: dict[str, SendOutcome]

    @property
    def succeeded(self) -> list[str]:
        return [aid for aid, o in self.per_agent.items() if o.success]

    @property
    def failed(self) -> list[str]:
        return [aid for aid, o in self.per_agent.items() if not o.success]

    @property
    def all_succeeded(self) -> bool:
        return bool(self.per_agent) and not self.failed

    @property
    def any_succeeded(self) -> bool:
        return any(o.success for o in self.per_agent.values())

    def summary(self) -> str:
        return (
            f"targets={len(self.targets)} succeeded={len(self.succeeded)} "
            f"failed={len(self.failed)}"
        )


async def send_to_group(
    agent_ids: Iterable[str],
    payload: dict,
    *,
    from_agent_id: Optional[str] = None,
    timeout: float = 15.0,
    max_concurrency: int = 8,
) -> GroupSendReport:
    """Parallel fanout to an explicit list of agent_ids.

    Bounds concurrency with a semaphore so a 50-agent broadcast doesn't
    open 50 simultaneous HTTP sockets / WS publishes.
    """
    ids = [a for a in agent_ids if a]
    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _send_one(aid: str) -> tuple[str, SendOutcome]:
        async with sem:
            try:
                outcome = await send_to_agent(
                    aid, payload, from_agent_id=from_agent_id, timeout=timeout
                )
            except Exception as e:
                outcome = SendOutcome(SendResult.UNREACHABLE, False, error=str(e))
            return aid, outcome

    if not ids:
        return GroupSendReport(targets=[], per_agent={})

    results = await asyncio.gather(*[_send_one(a) for a in ids])
    per_agent = dict(results)

    # Build the matching endpoint snapshot for caller introspection.
    from agent.a2a.discovery.directory import get_directory
    d = get_directory()
    targets = [ep for ep in (d.lookup(a) for a in ids) if ep is not None]

    logger.info(
        f"[discovery.group] send_to_group attempted={len(ids)} "
        f"succeeded={sum(1 for o in per_agent.values() if o.success)}"
    )
    return GroupSendReport(targets=targets, per_agent=per_agent)


async def send_to_skill(
    skill: str,
    payload: dict,
    *,
    mode: str = "any",
    from_agent_id: Optional[str] = None,
    timeout: float = 15.0,
    role: Optional[str] = None,
    machine_id: Optional[str] = None,
    exclude_self: bool = True,
    max_concurrency: int = 8,
) -> GroupSendReport:
    """Find agents offering ``skill`` and dispatch.

    Modes:
        "any" — first reachable wins; remaining matches are not contacted.
        "all" — broadcast to every match.
        "n=K" — top K by transport preference (LAN-direct first).
    """
    matches = find_agents(
        skill=skill,
        role=role,
        machine_id=machine_id,
        reachable=True,
        exclude_self=exclude_self,
    )

    mode_l = (mode or "any").strip().lower()
    if mode_l == "any":
        for ep in matches:
            outcome = await send_to_agent(
                ep.agent_id, payload, from_agent_id=from_agent_id, timeout=timeout
            )
            if outcome.success:
                return GroupSendReport(targets=[ep], per_agent={ep.agent_id: outcome})
            logger.info(
                f"[discovery.group] send_to_skill(any) {ep.agent_id} failed "
                f"({outcome.error}); trying next match"
            )
        # No match succeeded; report empty per_agent + the candidates we tried.
        return GroupSendReport(targets=matches, per_agent={})

    if mode_l == "all":
        return await send_to_group(
            [ep.agent_id for ep in matches],
            payload,
            from_agent_id=from_agent_id,
            timeout=timeout,
            max_concurrency=max_concurrency,
        )

    if mode_l.startswith("n="):
        try:
            n = int(mode_l.split("=", 1)[1])
        except (ValueError, IndexError):
            n = 1
        n = max(1, n)
        chosen = matches[:n]
        return await send_to_group(
            [ep.agent_id for ep in chosen],
            payload,
            from_agent_id=from_agent_id,
            timeout=timeout,
            max_concurrency=max_concurrency,
        )

    raise ValueError(
        f"send_to_skill mode must be 'any', 'all', or 'n=K' — got {mode!r}"
    )


async def broadcast_to_role(
    role: str,
    payload: dict,
    *,
    from_agent_id: Optional[str] = None,
    timeout: float = 15.0,
    max_concurrency: int = 8,
) -> GroupSendReport:
    """Broadcast to every reachable agent in a given role.

    Common pattern: notify all "manager" agents across the fleet that
    something happened.
    """
    matches = find_agents(role=role, reachable=True)
    return await send_to_group(
        [ep.agent_id for ep in matches],
        payload,
        from_agent_id=from_agent_id,
        timeout=timeout,
        max_concurrency=max_concurrency,
    )

"""CN (Tencent CloudBase) cloud worker entrypoint.

The CN counterpart of worker_main.py's single mode. Instead of receiving an
S3-assembled payload, it receives only task/owner identifiers (the contract
the CN worker-launcher and TencentScheduler already emit) and loads the
authoritative task + skill definitions from the CN GraphQL backend:

    task (getAgentTasks) -> ordered skills (queryTaskSkillRelations ->
    getAgentSkills) -> skill folder materialized locally (diagram straight
    from the DB, or code files downloaded from COS via reqFileOp) ->
    _run_skill_once (cloud-agnostic execution core, reused from worker_main).

Status/log reporting goes through publishSkillEditorStreamEvent (same event
contract as the AWS worker) and a run-state JSON in COS under runlogs/runs/.

Input (either form):
  --message-json '{"owner_id": ..., "task_id": ..., "options": {...}}'
  env ECAN_TASK_OWNER / ECAN_TASK_ID / ECAN_TASK_PARAMS   (TKE launcher shape)

Auth: ECAN_TCB_ACCESS_TOKEN or ECAN_TCB_REFRESH_TOKEN (see cn_backend.py).
Modes:
  --mode single   one task, then exit (the launcher contract above)
  --mode serve    stay up and take work item after work item (Phase 5;
                  loop in cn_serve.py, same per-item core)

Not yet ported from the AWS worker: WS control listener (cancel/pause),
passive browser (L2C) transport, cloud prompt loader.
"""

import argparse
import asyncio
import json
import os
import shutil
import signal
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# The CN worker always runs headless in a container; force cloud-mode logging
# (cloud_logger's other probes are AWS-specific: ECS metadata / Lambda env).
os.environ.setdefault("ECAN_CLOUD_MODE", "1")
os.environ.setdefault("ECAN_APP_ID", "cn")

from utils.logger_helper import logger_helper as logger

from agent.cloud_worker.cn_backend import CNBackendClient, CNBackendError
from agent.cloud_worker.cloud_logger import configure_cloud_logger, stop_cloud_logger

DEFAULT_TIMEOUT_SECONDS = 10800


@dataclass(frozen=True)
class CNWorkerMessage:
    owner_id: str
    task_id: str
    options: Dict[str, Any]


def _parse_cn_message(message_json: str) -> CNWorkerMessage:
    """Message from --message-json, falling back to the launcher env contract."""
    data: Dict[str, Any] = {}
    if message_json:
        data = json.loads(message_json) if isinstance(message_json, str) else dict(message_json)
    owner = str(data.get("owner_id") or data.get("owner") or os.getenv("ECAN_TASK_OWNER") or "")
    task_id = str(data.get("task_id") or data.get("taskId") or os.getenv("ECAN_TASK_ID") or "")
    options = data.get("options") or data.get("meta_data") or {}
    if not options:
        try:
            options = json.loads(os.getenv("ECAN_TASK_PARAMS") or "{}")
        except Exception:
            options = {}
    missing = [k for k, v in (("owner_id", owner), ("task_id", task_id)) if not v]
    if missing:
        raise ValueError(f"CN worker message missing required fields: {', '.join(missing)}")
    return CNWorkerMessage(owner_id=owner, task_id=task_id, options=dict(options))


def _prompt_from_test_inputs(test_inputs: Any) -> str:
    """The value for ``WorkerMessage.prompt`` — the visitor's bare sentence.

    This is a contract, not a formatting choice. ``worker_main._run_skill_once``
    puts ``msg.prompt`` into ``in_msg.params.message.parts[0].text``; that path
    is the FIRST candidate in ``prep_skills_run._extract_chat_message_input_patch``,
    which copies it (stripped) into ``state["input"]``; and an LLM node's
    user-turn template defaults to ``{{input}}``. So whatever lands here is
    literally what the model is asked.

    It used to be ``json.dumps(test_inputs)``, so a serving turn asked the model
    to answer ``{"text": "…", "conversation_id": ""}`` rather than the question
    inside it.

    Anything without a ``text`` string keeps the legacy envelope: a
    launcher-run skill whose prompt template expects its testInputs as JSON
    still receives them that way.
    """
    if isinstance(test_inputs, dict):
        text = test_inputs.get("text")
        if isinstance(text, str) and text.strip():
            return text
    return json.dumps(test_inputs, ensure_ascii=False)


def _materialize_diagram_skill(skill: Dict[str, Any], work_dir: Path) -> Path:
    """Write a DB-held flowgram diagram as the on-disk folder layout that
    load_skill_from_folder expects (mirrors worker_main._save_flowgram_to_s3,
    minus the S3 round-trip)."""
    name = (skill.get("name") or "skill").strip()
    folder_name = name if name.endswith("_skill") else f"{name}_skill"
    base = folder_name[: -len("_skill")]
    diagram = skill.get("diagram") or {}
    if isinstance(diagram, str):
        diagram = json.loads(diagram)

    skill_root = work_dir / folder_name
    diagram_dir = skill_root / "diagram_dir"
    diagram_dir.mkdir(parents=True, exist_ok=True)
    (diagram_dir / f"{base}_skill.json").write_text(
        json.dumps(diagram, ensure_ascii=False), encoding="utf-8"
    )
    bundle = diagram.get("bundle")
    if bundle:
        (diagram_dir / f"{base}_skill_bundle.json").write_text(
            json.dumps(bundle, ensure_ascii=False), encoding="utf-8"
        )
    data_mapping = diagram.get("dataMapping") or diagram.get("data_mapping")
    if data_mapping:
        (skill_root / "data_mapping.json").write_text(
            json.dumps(data_mapping, ensure_ascii=False), encoding="utf-8"
        )
    return skill_root


async def _materialize_cos_skill(
    client: CNBackendClient, skill: Dict[str, Any], work_dir: Path
) -> Path:
    """Download a code-based skill folder from COS (my_skills/ then skills/)."""
    name = (skill.get("name") or "").strip()
    folder_name = name if name.endswith("_skill") else f"{name}_skill"
    candidates = [name, folder_name] if name != folder_name else [name]
    for cand in candidates:
        for marker in ("my_skills/", "skills/"):
            dest = work_dir / cand
            count = await client.download_prefix_to_dir(marker, cand, dest)
            if count > 0:
                return dest
    raise CNBackendError(
        f"No COS files found for skill '{name}' under my_skills/ or skills/"
    )


def _diagram_has_nodes(skill: Dict[str, Any]) -> bool:
    diagram = skill.get("diagram") or {}
    if isinstance(diagram, str):
        try:
            diagram = json.loads(diagram)
        except Exception:
            return False
    return bool(isinstance(diagram, dict) and diagram.get("nodes"))


async def _publish_event(
    client: CNBackendClient,
    *,
    owner: str,
    run_id: str,
    event_type: str,
    payload: Dict[str, Any],
    flowgram_id: Optional[str] = None,
) -> None:
    """publishSkillEditorStreamEvent — same event contract as the AWS worker."""
    try:
        from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig, publish_skill_editor_stream_event

        await publish_skill_editor_stream_event(
            config=AppSyncApiKeyConfig(
                http_endpoint=client.endpoint,
                api_key="",
                auth_token=client.access_token,
            ),
            owner=owner,
            session_id=run_id,
            flowgram_id=flowgram_id,
            event_type=event_type,
            payload=payload,
        )
    except Exception as exc:
        logger.warning(f"[cn_worker] failed to publish {event_type}: {exc}")


async def _save_run_state(
    client: CNBackendClient, run_id: str, state: Dict[str, Any]
) -> None:
    try:
        await client.upload_json("runlogs/runs/", f"{run_id}.json", state)
    except Exception as exc:
        logger.warning(f"[cn_worker] failed to save run state: {exc}")


async def run_single_cn(message_json: str) -> Optional[Dict[str, Any]]:
    msg = _parse_cn_message(message_json)
    client = CNBackendClient.from_env()

    run_id = str(msg.options.get("run_id") or f"cn-{msg.task_id}-{uuid.uuid4().hex[:8]}")
    started = time.time()
    logger.info(f"[cn_worker] run {run_id}: owner={msg.owner_id} task={msg.task_id}")

    task = await client.get_task(msg.task_id)
    skills = await client.get_task_skills(msg.task_id)
    if not skills:
        raise CNBackendError(f"Task {msg.task_id} has no linked skills (agent_task_skill_rels)")
    skill = skills[0]
    skill_id = str(skill.get("id") or "")
    skill_name = str(skill.get("name") or "")

    configure_cloud_logger(
        appsync_url=client.endpoint,
        appsync_api_key="",
        owner=msg.owner_id,
        session_id=run_id,
        flowgram_id=skill_id,
        auth_token=client.access_token,
    )

    run_state: Dict[str, Any] = {
        "run_id": run_id,
        "owner": msg.owner_id,
        "task_id": msg.task_id,
        "task_name": task.get("name"),
        "skill_id": skill_id,
        "skill_name": skill_name,
        "status": "running",
        "started_at": started,
    }
    base_payload = {
        "run_id": run_id,
        "task_id": msg.task_id,
        "skill_id": skill_id,
        "skill_name": skill_name,
    }
    await _save_run_state(client, run_id, run_state)
    await _publish_event(
        client, owner=msg.owner_id, run_id=run_id, flowgram_id=skill_id,
        event_type="run_started", payload={**base_payload, "status": "running"},
    )

    work_dir = Path(tempfile.mkdtemp(prefix=f"cn_skill_{run_id}_"))
    try:
        if _diagram_has_nodes(skill):
            skill_root = _materialize_diagram_skill(skill, work_dir)
        else:
            skill_root = await _materialize_cos_skill(client, skill, work_dir)

        # Imported lazily: worker_main pulls in the full agent stack at import.
        from agent.cloud_worker.worker_main import WorkerMessage, _find_skill_folder, _run_skill_once

        skill_root = _find_skill_folder(skill_root)
        test_inputs = (
            msg.options.get("testInputs")
            or msg.options.get("test_inputs")
            or msg.options
        )
        # Shared-skill per-task variables: the fetched task record's
        # metadata/settings JSON may carry task_vars / browser_identity —
        # pass them through so _run_skill_once seeds them into the run
        # state (SHARED_SKILL_MULTI_TASK_PLAN).
        task_settings = task.get("metadata") or task.get("settings") or {}
        if not isinstance(task_settings, dict):
            task_settings = {}
        _tv = task_settings.get("task_vars")
        _bi = task_settings.get("browser_identity")
        if isinstance(_tv, dict) and _tv:
            logger.info(f"[cn_worker] run {run_id}: task_vars keys={sorted(_tv.keys())}")

        worker_msg = WorkerMessage(
            user_email=msg.owner_id,
            chat_id=run_id,
            sender_id=skill_id or msg.task_id,
            skill_name=skill_name,
            prompt=_prompt_from_test_inputs(test_inputs),
            task_vars=_tv if isinstance(_tv, dict) else None,
            browser_identity=_bi if isinstance(_bi, dict) else None,
            # Phase 2.2: when the caller knows which conversation this run
            # belongs to (serving mode does — the turn says so), the checkpoint
            # thread is keyed on the conversation instead of this one run.
            thread_id=str(msg.options.get("thread_id") or "") or None,
        )
        # Off the event loop, deliberately. _run_skill_once is synchronous and
        # ends in execute_task_hybrid, which builds its OWN event loop and calls
        # run_until_complete — illegal from inside a running loop, so called
        # here it raised "Cannot run the event loop while another loop is
        # running" every time and silently took the sync fallback. Two costs:
        # the whole turn blocked this loop, so heartbeats could not fire (a turn
        # over TURN_STALE_SECONDS got reaped and answered twice by another pod),
        # and turns serialised however much capacity the pod advertised.
        # A thread gives the core a loop-free home; to_thread copies the context,
        # so the turn's usage window comes with it.
        result = await asyncio.to_thread(
            _run_skill_once, msg=worker_msg, skill_root=skill_root
        )
        logger.info(f"[cn_worker] run {run_id} completed: {str(result)[:500]}")

        run_state.update(status="completed", finished_at=time.time())
        await _save_run_state(client, run_id, run_state)
        await _publish_event(
            client, owner=msg.owner_id, run_id=run_id, flowgram_id=skill_id,
            event_type="run_completed", payload={**base_payload, "status": "completed"},
        )
        # Returned, not just logged: serving mode reports it back to the queue
        # as the turn's result, which is what reaches the end user.
        return result
    except Exception as exc:
        run_state.update(status="failed", error=str(exc), finished_at=time.time())
        await _save_run_state(client, run_id, run_state)
        await _publish_event(
            client, owner=msg.owner_id, run_id=run_id, flowgram_id=skill_id,
            event_type="run_failed",
            payload={**base_payload, "status": "failed", "error": str(exc)},
        )
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        stop_cloud_logger()


async def run_single_cn_with_timeout(message_json: str, timeout_seconds: int) -> None:
    try:
        await asyncio.wait_for(run_single_cn(message_json), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(f"[cn_worker] execution exceeded timeout of {timeout_seconds}s")
        raise SystemExit(f"cn_worker timed out after {timeout_seconds}s")


async def _serve_cn(intake_kind: str = "stdin") -> None:
    """Phase 5: stay up and take work item after work item.

    The loop lives in cn_serve; the per-item core is run_single_cn, so serving
    and single-shot execute identical code.

    Two intakes: ``stdin`` (NDJSON, a sidecar or a local smoke test) and
    ``fleet`` (claim from the server-side turn queue, heartbeat what we hold,
    report the outcome with cost).
    """
    from agent.cloud_worker.cn_serve import Capacity, Shutdown, fleet_intake, make_turn_handler, serve, stdin_intake

    if intake_kind != "fleet":
        await serve(stdin_intake())
        return

    from agent.cloud_worker.fleet_client import FleetClient
    from agent.ec_agents.vehicle_affinity import set_assigned_vehicle_id

    # A pod is cattle: the scheduler says which vehicle it is, and that has to
    # be settled before anything resolves an id from the machine (Phase 6).
    assigned = (os.getenv("ECAN_VEHICLE_ID") or "").strip()
    if assigned:
        set_assigned_vehicle_id(assigned)

    fleet = FleetClient.from_env()
    vehicle = await fleet.register_vehicle()
    logger.info(
        f"[cn_worker] joined fleet as vehicle={fleet.vehicle_id} "
        f"capabilities={fleet.capabilities} capacity={fleet.capacity} -> {vehicle}"
    )

    # One Capacity shared by the loop and the intake: the loop bounds how many
    # turns run at once, the intake stops CLAIMING while full. Same number the
    # pod advertised as max_concurrent_tasks a moment ago, so what the scheduler
    # believes and what the pod does cannot drift apart.
    capacity = Capacity(fleet.capacity)

    # Kubernetes sends SIGTERM then waits terminationGracePeriodSeconds. Handle
    # it: stop claiming at once, finish what is in flight, then exit. Without
    # this a scale-down kills the pod mid-turn and the customer waits for the
    # server's reaper to spot a stale heartbeat — silence for no reason.
    shutdown = Shutdown()
    loop = asyncio.get_running_loop()
    for signame in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, signame, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, shutdown.request)
        except NotImplementedError:
            # Windows dev boxes: no add_signal_handler on the proactor loop.
            signal.signal(sig, lambda *_: shutdown.request())

    try:
        await serve(
            fleet_intake(fleet, capacity=capacity, shutdown=shutdown),
            handler=make_turn_handler(fleet),
            capacity=capacity,
            shutdown=shutdown,
        )
    finally:
        # Leave the roster deliberately rather than being reaped 6 minutes later.
        try:
            await fleet.offline_vehicle()
        except Exception as exc:
            logger.warning(f"[cn_worker] could not deregister cleanly: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ecan-cn-cloud-worker")
    parser.add_argument("--mode", choices=["single", "serve"], default="single")
    parser.add_argument(
        "--intake", choices=["stdin", "fleet"],
        default=(os.getenv("ECAN_SERVE_INTAKE") or "stdin").strip() or "stdin",
        help="serve mode only: where work comes from",
    )
    parser.add_argument("--message-json", default=os.getenv("ECAN_WORKER_MESSAGE_JSON", ""))
    parser.add_argument(
        "--timeout", type=int,
        default=int(os.getenv("ECAN_WORKER_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
    )
    args = parser.parse_args()

    t0 = time.time()
    logger.info(
        f"[cn_worker] starting mode={args.mode} "
        f"{'intake=' + args.intake + ' ' if args.mode == 'serve' else ''}"
        f"timeout={args.timeout}s"
    )
    try:
        if args.mode == "serve":
            # No wall-clock timeout: a serving pod is supposed to stay up.
            asyncio.run(_serve_cn(args.intake))
        elif args.timeout > 0:
            asyncio.run(run_single_cn_with_timeout(args.message_json, args.timeout))
        else:
            asyncio.run(run_single_cn(args.message_json))
    finally:
        logger.info(f"[cn_worker] exiting after {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()

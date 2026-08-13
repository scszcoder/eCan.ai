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
Not yet ported from the AWS worker: WS control listener (cancel/pause),
passive browser (L2C) transport, cloud prompt loader.
"""

import argparse
import asyncio
import json
import os
import shutil
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


async def run_single_cn(message_json: str) -> None:
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
        worker_msg = WorkerMessage(
            user_email=msg.owner_id,
            chat_id=run_id,
            sender_id=skill_id or msg.task_id,
            skill_name=skill_name,
            prompt=json.dumps(test_inputs, ensure_ascii=False),
        )
        result = _run_skill_once(msg=worker_msg, skill_root=skill_root)
        logger.info(f"[cn_worker] run {run_id} completed: {str(result)[:500]}")

        run_state.update(status="completed", finished_at=time.time())
        await _save_run_state(client, run_id, run_state)
        await _publish_event(
            client, owner=msg.owner_id, run_id=run_id, flowgram_id=skill_id,
            event_type="run_completed", payload={**base_payload, "status": "completed"},
        )
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="ecan-cn-cloud-worker")
    parser.add_argument("--mode", choices=["single"], default="single")
    parser.add_argument("--message-json", default=os.getenv("ECAN_WORKER_MESSAGE_JSON", ""))
    parser.add_argument(
        "--timeout", type=int,
        default=int(os.getenv("ECAN_WORKER_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
    )
    args = parser.parse_args()

    t0 = time.time()
    logger.info(f"[cn_worker] starting mode={args.mode} timeout={args.timeout}s")
    try:
        if args.timeout > 0:
            asyncio.run(run_single_cn_with_timeout(args.message_json, args.timeout))
        else:
            asyncio.run(run_single_cn(args.message_json))
    finally:
        logger.info(f"[cn_worker] exiting after {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()

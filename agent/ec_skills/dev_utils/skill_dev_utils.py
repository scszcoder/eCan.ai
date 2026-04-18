from utils.logger_helper import logger_helper as logger
from agent.ec_skill import EC_Skill, NodeState
from agent.ec_skills.flowgram2langgraph_v2 import flowgram2langgraph_v2
from utils.logger_helper import get_traceback
from agent.ec_agents.create_dev_task import create_skill_dev_task
import json
from typing import Any, Dict, Optional


def _load_dev_mapping_rules(skill_payload):
    """Load mapping rules from inline dev payload only."""
    if not isinstance(skill_payload, dict):
        return None

    inline_candidates = [
        skill_payload.get("data_mapping"),
        skill_payload.get("dataMapping"),
        (skill_payload.get("diagram") or {}).get("data_mapping") if isinstance(skill_payload.get("diagram"), dict) else None,
        (skill_payload.get("diagram") or {}).get("dataMapping") if isinstance(skill_payload.get("diagram"), dict) else None,
    ]
    for cand in inline_candidates:
        if isinstance(cand, dict) and cand:
            logger.info("[setup_dev_skill] Loaded mapping rules from inline payload")
            return cand

    return None

async def create_test_dev_skill(mainwin):
    try:
        test_dev_skill = EC_Skill(
            name="test skill under development",
            description="test run on a skill under development.",
            source="code"  # Mark as code-generated skill
        )        
        # Attach optional mapping_rules for testing the DSL. These are additive and won't break defaults.
        test_dev_skill.mapping_rules = {
            "mappings": [
                # Map a synthetic event field into tool_input and resume
                {
                    "from": ["event.data.sample_tool_input"],
                    "to": [
                        {"target": "state.tool_input.sample"},
                        {"target": "resume.sample_tool_input"}
                    ],
                    "on_conflict": "overwrite"
                },
                # Map synthetic meta into state.metadata for downstream nodes
                {
                    "from": ["event.data.sample_meta"],
                    "to": [
                        {"target": "state.metadata.extra"}
                    ],
                    "on_conflict": "merge_deep"
                }
            ],
            "options": {"strict": False}
        }
    except Exception as e:
        err_msg = get_traceback(e, "ErrorCreateTestDevSkill")
        logger.error(err_msg)
        test_dev_skill = None

    return test_dev_skill

def setup_dev_skill(mainwin, skill):
    try:
        logger.debug(f"[setup_dev_skill] All main task names: {[task.name for task in mainwin.agent_tasks]}")
        dev_run_task = next((task for task in mainwin.agent_tasks if "run task for skill under development" in task.name.lower()), None)
        logger.debug(f"[setup_dev_skill] Dev run task: {dev_run_task}")
        
        # Wait for agents to be loaded (with timeout)
        import time
        max_wait_seconds = 30  # Increased from 10s to 30s for slower startups
        wait_interval = 0.5
        elapsed = 0
        
        agents_list = getattr(mainwin, 'agents', None) or []
        while not agents_list and elapsed < max_wait_seconds:
            logger.info(f"[setup_dev_skill] Waiting for agents to load... ({elapsed:.1f}s)")
            time.sleep(wait_interval)
            elapsed += wait_interval
            agents_list = getattr(mainwin, 'agents', None) or []
        
        logger.info(f"[setup_dev_skill] Available agents: {len(agents_list)} -> {[getattr(getattr(ag, 'card', None), 'name', '?') for ag in agents_list]}")
        tester_agent = next((ag for ag in agents_list if "test" in ag.card.name.lower()), None)
        if tester_agent is None and agents_list:
            tester_agent = agents_list[0]
            logger.info(f"[setup_dev_skill] No 'test' agent found, falling back to first agent: {tester_agent.card.name}")
        if tester_agent is None:
            logger.warning(f"[setup_dev_skill] No agents available at all in mainwin.agents after waiting {max_wait_seconds}s!")
        logger.debug("tester_agent: ", type(skill), tester_agent)
        
        # Parse skill if it's a JSON string
        if isinstance(skill, str):
            try:
                skill = json.loads(skill)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[setup_dev_skill] Failed to parse skill as JSON, using as-is")
        
        # Log the skill name being received from frontend
        skill_name = None
        if isinstance(skill, dict):
            skill_name = skill.get("skillName") or skill.get("diagram", {}).get("skillName") or "UNKNOWN"
        logger.info(f"[setup_dev_skill] 📥 Received skill from frontend: '{skill_name}'")
        logger.debug(f"[setup_dev_skill] Skill type: {type(skill)}, is dict: {isinstance(skill, dict)}")
        if isinstance(skill, dict):
            logger.debug(f"[setup_dev_skill] Skill keys: {list(skill.keys())}")
        
        # Unpack the workflow and the list of breakpoints
        # Accept either a top-level flow or a wrapper with a 'diagram' containing workFlow/bundle
        flow_payload = skill.get("diagram") if isinstance(skill, dict) else None
        if not flow_payload and isinstance(skill, dict):
            flow_payload = skill
        bundle_json = (flow_payload.get("bundle") if isinstance(flow_payload, dict) else None)
        try:
            bcnt = len((bundle_json or {}).get("sheets", [])) if isinstance(bundle_json, dict) else 0
            logger.debug(f"[setup_dev_skill] Bundle sheets to pass: {bcnt}")
        except Exception:
            pass
        
        logger.info(f"[setup_dev_skill] 🔄 Converting skill '{skill_name}' to LangGraph workflow...")
        # Use v2 layered converter (flat mode for now)
        bp_mgr = getattr(tester_agent, 'runner', None).bp_manager if tester_agent and getattr(tester_agent, 'runner', None) else None
        skill_under_dev, breakpoints = flowgram2langgraph_v2(flow_payload or skill, bundle_json=bundle_json, enable_subgraph=False, bp_mgr=bp_mgr)
        logger.info(f"[setup_dev_skill] ✅ LangGraph skill converted for '{skill_name}'")
        
        # Ensure the dev_run_task exists before using it; if missing, create and register it
        if not dev_run_task:
            logger.info("[setup_dev_skill] Dev run task missing - creating one now...")
            try:
                new_task = create_skill_dev_task(mainwin)
                if new_task:
                    mainwin.agent_tasks.append(new_task)
                    dev_run_task = new_task
                    logger.info("Created and registered 'dev:run task for skill under development'.")
                else:
                    raise RuntimeError("create_skill_dev_task returned None")
            except Exception as ce:
                raise RuntimeError("Dev run task not found and auto-creation failed.") from ce

        # Ensure the dev task is also in the tester agent's own task list
        # (launch_dev_run_task searches self.tasks, not mainwin.agent_tasks)
        if tester_agent and dev_run_task:
            agent_has_task = any(
                "run task for skill under development" in t.name.lower()
                for t in (tester_agent.tasks or [])
            )
            if not agent_has_task:
                if not hasattr(tester_agent, 'tasks') or tester_agent.tasks is None:
                    tester_agent.tasks = []
                tester_agent.tasks.append(dev_run_task)
                logger.info(f"[setup_dev_skill] Added dev_run_task to agent '{tester_agent.card.name}' tasks list")

        # Set the workflow on the task
        dev_run_task.skill.set_work_flow(skill_under_dev)

        # Ensure dev-run uses real skill mapping rules (especially node_transfers)
        # so cross-node variables like previous_node_output can be propagated.
        try:
            loaded_rules = _load_dev_mapping_rules(skill if isinstance(skill, dict) else {})
            if isinstance(loaded_rules, dict) and loaded_rules:
                dev_run_task.skill.mapping_rules = loaded_rules
                node_transfers = loaded_rules.get("node_transfers", {})
                logger.info(
                    "[setup_dev_skill] Applied mapping_rules for dev run; node_transfer_rules keys: "
                    + str(list(node_transfers.keys()) if isinstance(node_transfers, dict) else [])
                )
            else:
                logger.warning("[setup_dev_skill] No external mapping_rules resolved; using existing dev task mapping_rules")
        except Exception as _map_e:
            logger.warning(f"[setup_dev_skill] Failed applying external mapping_rules: {_map_e}")

        # Preserve the original flowgram diagram so _amend_event_routing_for_task
        # can inspect pend_event nodes (including those nested inside loops/blocks)
        dev_run_task.skill.diagram = flow_payload or skill

        # Inject toolset/skillset prompt variables from the frontend skill payload
        try:
            if isinstance(skill, dict) and (skill.get("toolsets") or skill.get("skillsets")):
                from agent.ec_skills.build_agent_skills import _inject_toolset_skillset_variables
                _inject_toolset_skillset_variables(dev_run_task.skill, skill)
        except Exception as _ts_err:
            logger.debug(f"[setup_dev_skill] Toolset/skillset injection skipped: {_ts_err}")

        # Set the breakpoints on the runner's breakpoint manager
        if tester_agent and breakpoints:
            logger.debug(f"[setup_dev_skill] Setting breakpoints: {breakpoints}")
            tester_agent.runner.bp_manager.set_breakpoints(breakpoints)
            logger.info(f"Breakpoints set for dev run: {breakpoints}")
            logger.info(f"BreakpointManager now holds: {tester_agent.runner.bp_manager.get_breakpoints()}")

    except Exception as e:
        # Get the traceback information
        err_msg = get_traceback(e, "ErrorSetupDevSkill")
        logger.error(err_msg)
        tester_agent = None

    return tester_agent

def find_tester_agent(mainwin):
    try:
        tester_agent = next((ag for ag in mainwin.agents if "test" in ag.card.name.lower()), None)
        if tester_agent is None and mainwin.agents:
            tester_agent = mainwin.agents[0]
            logger.info(f"[find_tester_agent] No 'test' agent found, falling back to first agent: {tester_agent.card.name}")
    except Exception as e:
        # Get the traceback information
        err_msg = get_traceback(e, "ErrorFindTesterAgent")
        tester_agent = None

    return tester_agent

def run_dev_skill(mainwin, skill):
    logger.debug("run_dev_skill>>>>>>>>")
    # get langgraph created and compiled, find tester agent who will be running the dev skill.
    tester_agent = setup_dev_skill(mainwin, skill)

    if tester_agent:
        logger.debug("tester_agent found >>>>>>>>")
        init_state = NodeState(
            messages=[],
            input="",
            attachments=[],
            prompts=[],
            history=[],
            attributes={
            },
            result={"llm_result": {"all_done": False, "work_done": False}},
            tool_input={},
            tool_result={},
            threads = [],
            metadata = {},
            error="",
            retries=3,
            condition=False,
            case="",
            goals=[]
        )
        results = tester_agent.launch_dev_run_task(init_state)
        run_results = {
            "success": True,
            "error": "",
            "run_status": results,
            "run_id": results.get("run_id"),
            "task_id": results.get("task_id"),
        }
    else:
        logger.debug("tester_agent NOT found >>>>>>>>")
        run_results = {"success": False, "error": "ErrorSetupDevSkill", "run_status": None}

    return run_results

def _extract_cancel_identifiers(cancel_payload: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Extract task/run identifiers from cancel request payload."""
    payload = cancel_payload if isinstance(cancel_payload, dict) else {}

    requested_task_id = payload.get("task_id") or payload.get("taskId")
    requested_run_id = payload.get("run_id") or payload.get("runId")
    requested_skill_id = payload.get("skill_id") or payload.get("skillId")
    requested_skill_name = payload.get("skill_name") or payload.get("skillName")

    skill_payload = payload.get("skill")
    if isinstance(skill_payload, str):
        try:
            skill_payload = json.loads(skill_payload)
        except Exception:
            skill_payload = {}

    if isinstance(skill_payload, dict):
        requested_task_id = requested_task_id or skill_payload.get("task_id") or skill_payload.get("taskId")
        requested_run_id = requested_run_id or skill_payload.get("run_id") or skill_payload.get("runId")
        requested_skill_id = requested_skill_id or skill_payload.get("skill_id") or skill_payload.get("skillId")
        requested_skill_name = requested_skill_name or skill_payload.get("skill_name") or skill_payload.get("skillName")

    return {
        "task_id": str(requested_task_id) if requested_task_id else None,
        "run_id": str(requested_run_id) if requested_run_id else None,
        "skill_id": str(requested_skill_id) if requested_skill_id else None,
        "skill_name": str(requested_skill_name) if requested_skill_name else None,
    }


def _matches_cancel_target(task: Any, requested_task_id: Optional[str], requested_run_id: Optional[str]) -> bool:
    task_id = str(getattr(task, "id", "") or "")
    run_id = str(getattr(task, "run_id", "") or "")
    task_state = getattr(task, "state", None) or {}
    cloud_run_id = str(task_state.get("cloud_run_id", "") or "") if isinstance(task_state, dict) else ""

    if requested_task_id and requested_task_id in {task_id, run_id, cloud_run_id}:
        return True
    if requested_run_id and requested_run_id in {task_id, run_id, cloud_run_id}:
        return True
    return False


def _matches_skill_target(task: Any, requested_skill_id: Optional[str], requested_skill_name: Optional[str]) -> bool:
    task_skill = getattr(task, "skill", None)
    task_skill_id = str(
        getattr(task_skill, "id", None)
        or getattr(task, "skill_id", None)
        or ""
    )
    task_skill_name = str(
        getattr(task_skill, "name", None)
        or getattr(task, "skill_name", None)
        or ""
    )
    task_name = str(getattr(task, "name", "") or "")

    if requested_skill_id and task_skill_id and task_skill_id == requested_skill_id:
        return True

    if requested_skill_name:
        expected_name = requested_skill_name.lower()
        if task_skill_name and task_skill_name.lower() == expected_name:
            return True
        if task_name and expected_name in task_name.lower():
            return True

    return False


def _collect_candidate_tasks(mainwin):
    candidates = []
    seen_obj_ids = set()
    for ag in getattr(mainwin, "agents", []) or []:
        agent_name = getattr(getattr(ag, "card", None), "name", "?")
        runner = getattr(ag, "runner", None)

        for _task in (getattr(runner, "tasks", {}) or {}).values() if runner else []:
            if _task is None:
                continue
            _obj_id = id(_task)
            if _obj_id in seen_obj_ids:
                continue
            seen_obj_ids.add(_obj_id)
            candidates.append((agent_name, _task, "runner.tasks"))

        for _task in getattr(ag, "tasks", []) or []:
            if _task is None:
                continue
            _obj_id = id(_task)
            if _obj_id in seen_obj_ids:
                continue
            seen_obj_ids.add(_obj_id)
            candidates.append((agent_name, _task, "agent.tasks"))

        _dev_runner = getattr(runner, "dev_runner", None) if runner else None
        _dev_task = getattr(_dev_runner, "_dev_task", None) if _dev_runner else None
        if _dev_task is not None:
            _obj_id = id(_dev_task)
            if _obj_id not in seen_obj_ids:
                seen_obj_ids.add(_obj_id)
                candidates.append((agent_name, _dev_task, "dev_runner._dev_task"))

    return candidates




def _cleanup_browser_session_cache():
    """
    Cleanup cached browser sessions after task cancellation.
    Delegates to build_node.cleanup_stale_browser_sessions() to avoid
    hard-coding module paths and to share the same thread-safe implementation.
    """
    try:
        from agent.ec_skills.build_node import cleanup_stale_browser_sessions
        cleanup_stale_browser_sessions()
    except Exception as e:
        logger.debug(f"[cancel_run_dev_skill] Browser cleanup skipped: {e}")


def _stop_task_obj(task: Any, reason: str = "ipc_cancel_run_skill") -> bool:
    try:
        if hasattr(task, "stop") and callable(task.stop):
            task.stop(reason=reason, force=True)
            return True
        if hasattr(task, "cancel") and callable(task.cancel):
            task.cancel()
            return True
    except Exception as _stop_err:
        logger.warning(f"[cancel_run_dev_skill] Failed to stop task object: {_stop_err}")
    return False


def cancel_run_dev_skill(mainwin, cancel_payload: Optional[Dict[str, Any]] = None):
    target_agent = None
    identifiers = _extract_cancel_identifiers(cancel_payload)
    requested_task_id = identifiers.get("task_id")
    requested_run_id = identifiers.get("run_id")
    requested_skill_id = identifiers.get("skill_id")
    requested_skill_name = identifiers.get("skill_name")

    logger.info(
        "[cancel_run_dev_skill] Requested cancel identifiers: "
        f"task_id={requested_task_id}, run_id={requested_run_id}, "
        f"skill_id={requested_skill_id}, skill_name={requested_skill_name}"
    )

    candidates = _collect_candidate_tasks(mainwin)

    # 1) Direct cancel path: if caller provides task_id/run_id, cancel the real running task first.
    # This is required for auto-chatter tasks where dev_runner._dev_task may be None.
    if requested_task_id or requested_run_id:
        matched = []
        for agent_name, _task, from_path in candidates:
            if _matches_cancel_target(_task, requested_task_id, requested_run_id):
                matched.append((agent_name, _task, from_path))

        if matched:
            stopped = False
            for agent_name, task_obj, from_path in matched:
                task_id = getattr(task_obj, "id", None)
                run_id = getattr(task_obj, "run_id", None)
                logger.info(
                    "[cancel_run_dev_skill] Direct cancel hit: "
                    f"agent={agent_name}, from={from_path}, task_id={task_id}, run_id={run_id}"
                )
                if _stop_task_obj(task_obj):
                    stopped = True


                # Cleanup browser session cache after task cancellation
                try:
                    _cleanup_browser_session_cache()
                except Exception as _cleanup_err:
                    logger.debug(f"[cancel_run_dev_skill] Browser cleanup skipped: {_cleanup_err}")
            if stopped:
                return {
                    "success": True,
                    "error": "",
                    "run_status": {
                        "mode": "direct_task_cancel",
                        "requested_task_id": requested_task_id,
                        "requested_run_id": requested_run_id,
                        "matched_count": len(matched),
                    },
                }

        logger.warning(
            "[cancel_run_dev_skill] Direct cancel found no matching task for "
            f"task_id={requested_task_id}, run_id={requested_run_id}; fallback to dev-run path"
        )

    # 2) Skill-based fallback: if run_id/task_id is missing/wrong, still cancel the current running
    # skill task by skill_id/skill_name (covers auto-chatter task IDs that frontend may not know).
    if requested_skill_id or requested_skill_name:
        skill_matched = []
        for agent_name, _task, from_path in candidates:
            if _matches_skill_target(_task, requested_skill_id, requested_skill_name):
                skill_matched.append((agent_name, _task, from_path))

        if skill_matched:
            stopped = False
            for agent_name, task_obj, from_path in skill_matched:
                task_id = getattr(task_obj, "id", None)
                run_id = getattr(task_obj, "run_id", None)
                logger.info(
                    "[cancel_run_dev_skill] Skill fallback cancel hit: "
                    f"agent={agent_name}, from={from_path}, task_id={task_id}, run_id={run_id}, "
                    f"skill_id={requested_skill_id}, skill_name={requested_skill_name}"
                )
                if _stop_task_obj(task_obj):
                    stopped = True

            if stopped:
                return {
                    "success": True,
                    "error": "",
                    "run_status": {
                        "mode": "skill_fallback_cancel",
                        "requested_skill_id": requested_skill_id,
                        "requested_skill_name": requested_skill_name,
                        "matched_count": len(skill_matched),
                    },
                }

        logger.warning(
            "[cancel_run_dev_skill] Skill fallback found no matching task for "
            f"skill_id={requested_skill_id}, skill_name={requested_skill_name}; fallback to dev-run path"
        )

    # Prefer the agent that currently owns an active dev task.
    # Using only find_tester_agent() can select an idle runner and make cancel no-op
    # (observed as "task already done!" while another agent keeps running).
    try:
        for ag in getattr(mainwin, "agents", []) or []:
            runner = getattr(ag, "runner", None)
            dev_runner = getattr(runner, "dev_runner", None)
            dev_task = getattr(dev_runner, "_dev_task", None) if dev_runner else None
            if dev_task is not None:
                target_agent = ag
                logger.info(
                    f"[cancel_run_dev_skill] Routing cancel to active agent: {getattr(getattr(ag, 'card', None), 'name', '?')} "
                    f"(task_id={getattr(dev_task, 'id', None)}, run_id={getattr(dev_task, 'run_id', None)})"
                )
                break
    except Exception as _scan_err:
        logger.warning(f"[cancel_run_dev_skill] Failed scanning active dev task owner: {_scan_err}")

    # Fallback to original behavior for compatibility.
    if target_agent is None:
        target_agent = find_tester_agent(mainwin)

    if target_agent:
        _runner = getattr(target_agent, "runner", None)
        _dev_runner = getattr(_runner, "dev_runner", None)
        _target_task = getattr(_dev_runner, "_dev_task", None) if _dev_runner else None
        logger.info(
            "[cancel_run_dev_skill] Cancel target details: "
            f"agent={getattr(getattr(target_agent, 'card', None), 'name', '?')}, "
            f"task_id={getattr(_target_task, 'id', None)}, run_id={getattr(_target_task, 'run_id', None)}"
        )

        results = target_agent.cancel_dev_run_task()
        run_results = {"success": True, "error": "", "run_status": results}
    else:
        run_results = {"success": False, "error": "ErrorCancelRunDevSkill", "run_status": None}

    return run_results

def pause_run_dev_skill(mainwin):
    tester_agent = find_tester_agent(mainwin)
    if tester_agent:
        results = tester_agent.pause_dev_run_task()
        run_results = {"success": True, "error": "", "run_status": results}
    else:
        run_results = {"success": False, "error": "ErrorPauseRunDevSkill", "run_status": None}

    return run_results

def step_run_dev_skill(mainwin):
    tester_agent = find_tester_agent(mainwin)
    if tester_agent:
        results = tester_agent.step_dev_run_task()
        run_results = {"success": True, "error": "", "run_status": results}
    else:
        run_results = {"success": False, "error": "ErrorStepRunDevSkill", "run_status": None}

    return run_results

def resume_run_dev_skill(mainwin):
    tester_agent = find_tester_agent(mainwin)
    if tester_agent:
        results = tester_agent.resume_dev_run_task()
        run_results = {"success": True, "error": "", "run_status": results}
    else:
        run_results = {"success": False, "error": "ErrorResumeRunDevSkill", "run_status": None}

    return run_results

def set_bps_dev_skill(mainwin, bps):
    tester_agent = find_tester_agent(mainwin)
    if tester_agent:
        results = tester_agent.runner.set_bps_dev_skill(bps)
        run_results = {"success": True, "error": "", "run_status": results}
    else:
        run_results = {"success": False, "error": "ErrorSetBpsDevSkill", "run_status": None}

    return run_results

def clear_bps_dev_skill(mainwin, bps):
    tester_agent = find_tester_agent(mainwin)
    if tester_agent:
        results = tester_agent.runner.clear_bps_dev_skill(bps)
        run_results = {"success": True, "error": "", "run_status": results}
    else:
        run_results = {"success": False, "error": "ErrorClearBpsDevSkill", "run_status": None}

    return run_results


def build_skill(run_context: dict | None = None, mainwin=None) -> EC_Skill:
    """
    Standard entry point for skill building system.
    
    ⚠️ IMPORTANT: This function is currently NOT actively used!
    
    Current Loading Method:
    -----------------------
    This skill is loaded via build_agent_skills_parallel() which directly calls:
        await create_test_dev_skill(mainwin)
    
    When Would This Be Used:
    ------------------------
    This build_skill() function would only be called if:
    1. This skill file is moved to ec_skills/ as an external/plugin skill
    2. It's NOT hardcoded in build_agent_skills_parallel()
    3. The system uses build_agent_skills_from_files() for dynamic loading
    
    Why Keep It:
    ------------
    - Future plugin architecture support
    - Backward compatibility
    - Standard interface for all code-based skills
    
    Special Note:
    -------------
    This is a development/testing skill without a predefined workflow.
    The workflow is dynamically set when running tests via setup_dev_skill().
    
    See: agent/ec_skills/skill_build_template.py for detailed documentation
    """
    from agent.ec_skills.skill_build_template import sync_to_async_bridge
    return sync_to_async_bridge(create_test_dev_skill, mainwin, run_context)



from utils.logger_helper import logger_helper as logger
from agent.ec_skill import EC_Skill, NodeState
from agent.ec_skills.flowgram2langgraph_v2 import flowgram2langgraph_v2
from utils.logger_helper import get_traceback
from agent.ec_agents.create_dev_task import create_skill_dev_task

async def create_test_dev_skill(mainwin):
    try:
        test_dev_skill = EC_Skill(name="test skill under development", description="test run on a skill under development.")
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
        tester_agent = next((ag for ag in mainwin.agents if "test" in ag.card.name.lower()), None)
        logger.debug("tester_agent: ", type(skill), tester_agent)
        
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
        # Use v2 layered converter (flat mode for now)
        bp_mgr = getattr(tester_agent, 'runner', None).bp_manager if tester_agent and getattr(tester_agent, 'runner', None) else None
        skill_under_dev, breakpoints = flowgram2langgraph_v2(flow_payload or skill, bundle_json=bundle_json, enable_subgraph=False, bp_mgr=bp_mgr)
        logger.debug("langgraph skill converted....")
        
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

        # Set the workflow on the task
        dev_run_task.skill.set_work_flow(skill_under_dev)

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
            result={},
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
        run_results = {"success": True, "error": "", "run_status": results}
    else:
        logger.debug("tester_agent NOT found >>>>>>>>")
        run_results = {"success": False, "error": "ErrorSetupDevSkill", "run_status": None}

    return run_results

def cancel_run_dev_skill(mainwin):
    tester_agent = find_tester_agent(mainwin)
    if tester_agent:
        results = tester_agent.cancel_dev_run_task()
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



from utils.logger_helper import logger_helper as logger
from agent.ec_skill import EC_Skill, NodeState
from agent.ec_skills.flowgram2langgraph import flowgram2langgraph
from utils.logger_helper import get_traceback

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
        print("all main task names:", [task.name for task in mainwin.agent_tasks])
        dev_run_task = next((task for task in mainwin.agent_tasks if "run task for skill under development" in task.name.lower()), None)
        print("dev_run_task: ", dev_run_task)
        tester_agent = next((ag for ag in mainwin.agents if "test" in ag.card.name.lower()), None)
        logger.debug("tester_agent: ", type(skill), tester_agent)
        
        # Unpack the workflow and the list of breakpoints
        skill_under_dev, breakpoints = flowgram2langgraph(skill)
        logger.debug("langgraph skill converted....")
        
        # Set the workflow on the task
        dev_run_task.skill.set_work_flow(skill_under_dev)

        # Set the breakpoints on the runner's breakpoint manager
        if tester_agent and breakpoints:
            print("SETTING BREAKPOINTS:", breakpoints)
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
    tester_agent = setup_dev_skill(mainwin, skill)

    if tester_agent:
        logger.debug("tester_agent found >>>>>>>>")
        init_state = NodeState(
            messages=[],
            input="",
            attachments=[],
            prompts=[],
            formatted_prompts=[],
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



from typing import TypedDict
import uuid
from datetime import datetime

from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt, Command
from langgraph.func import entrypoint, task
from langgraph.graph import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages.utils import (
    # highlight-next-line
    trim_messages,
    # highlight-next-line
    count_tokens_approximately
# highlight-next-line
)
from langgraph.prebuilt import create_react_agent
from langmem.short_term import SummarizationNode
from langgraph.store.base import BaseStore

from scipy.stats import chatterjeexi
import io
import os
import base64

from agent.chats.chat_utils import gui_a2a_send_chat
from agent.ec_skills.file_utils.file_utils import extract_file_text
from agent.ec_skill import NodeState, WorkFlowContext, EC_Skill, node_builder
from agent.ec_skills.dev_defs import BreakpointManager

from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from agent.agent_service import get_agent_by_id
from agent.mcp.local_client import mcp_call_tool
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from agent.ec_skills.common_nodes import (
    DEFAULT_CHATTER_MAPPING_RULES,
    PUBLIC_OWNER,
    llm_node_with_raw_files,
    pend_for_human_input_node,
    chat_or_work
)


THIS_SKILL_NAME = "self_test_chatter"
DESCRIPTION = (
    "Chat assistant to self test. "
    "talk to human or other agents, mostly respond to their requests to do self test or query current status or available tests."
)


def _ensure_context(ctx: WorkFlowContext) -> WorkFlowContext:
    """Get params that configure the search algorithm."""
    if ctx.this_node:
        if ctx.this_node.get("name", ""):
            ctx.this_node = ctx.this_node
    else:
        ctx.node = {"name": ""}



def run_test_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    logger.debug("run_test_node:", state)

    # obtain the raw message from state
    raw_message = state["messages"][-1]
    logger.debug("[run_test_node] raw_message:", raw_message)

    # assume raw message is formated like this: "t <test_name> {<test_params>}" or "e <event_name> {<event_params>}"
    # where test_params and event_params would be in json format, but they are optional if {...} is not supplied we'll
    # just assume default parameters. so the raw message can be "t <test_name>" or "e <event_name>"
    # for test, simply call a function run_test(test_name, test_params=None),
    # for event, simply call a function simulate_event(event_name, event_params=None)

    try:
        import re
        import json
        
        # Extract the message content
        if hasattr(raw_message, 'content'):
            message_text = raw_message.content
        elif isinstance(raw_message, str):
            message_text = raw_message
        else:
            message_text = str(raw_message)
        
        logger.debug(f"Parsing message: {message_text}")
        
        # First, extract the command after "execute" keyword
        # Pattern: anything followed by "execute" followed by the actual command
        execute_pattern = r'.*\bexecute\b\s+(.+)$'
        execute_match = re.search(execute_pattern, message_text.strip(), re.IGNORECASE)
        
        if execute_match:
            # Extract the command after "execute"
            command_string = execute_match.group(1).strip()
            logger.debug(f"Extracted command after 'execute': {command_string}")
        else:
            # No "execute" keyword found, use the whole message
            command_string = message_text.strip()
            logger.debug(f"No 'execute' keyword found, using full message: {command_string}")
        
        # Parse the command format: "t <name> {params}" or "e <name> {params}"
        # Pattern: (t|e) followed by name, optionally followed by JSON params
        pattern = r'^([te])\s+(\w+)(?:\s+(\{.*\}))?$'
        match = re.match(pattern, command_string)
        
        if not match:
            result = {
                "error": f"Invalid command format. Expected 't <test_name> {{params}}' or 'e <event_name> {{params}}', got: {command_string}"
            }
            state["result"] = result
            return state
        
        command_type = match.group(1)  # 't' or 'e'
        name = match.group(2)
        params_str = match.group(3)
        
        # Parse params if provided
        params = None
        if params_str:
            try:
                params = json.loads(params_str)
            except json.JSONDecodeError as e:
                result = {
                    "error": f"Invalid JSON parameters: {params_str}. Error: {str(e)}"
                }
                state["result"] = result
                return state
        
        # Execute based on command type
        if command_type == 't':
            # Run test
            logger.debug(f"Running test: {name} with params: {params}")
            result = run_test(mainwin, name, params)
        elif command_type == 'e':
            # Simulate event
            logger.debug(f"Simulating event: {name} with params: {params}")
            result = simulate_event(self_agent, mainwin, name, params)
        else:
            result = {"error": f"Unknown command type: {command_type}"}
        
        state["result"] = result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRunTestNode")
        logger.error(err_trace)
        state["result"] = {"error": err_trace}
    
    return state


def run_test(mainwin, test_name: str, test_params: dict = None) -> dict:
    """
    Execute a specific test by name.
    
    Args:
        mainwin: Main window instance
        test_name: Name of the test to run
        test_params: Optional parameters for the test
        
    Returns:
        dict: Test execution result
    """
    try:
        logger.debug(f"Executing test: {test_name} with params: {test_params}")
        
        # Import test functions
        from tests.unittests import run_default_tests
        
        # Map test names to test functions
        if test_name == "default" or test_name == "all":
            result = run_default_tests(mainwin, test_params)
        else:
            # For specific tests, you can add more mappings here
            result = {
                "status": "error",
                "message": f"Unknown test: {test_name}. Available tests: default, all"
            }
        
        return {
            "status": "success",
            "test_name": test_name,
            "result": result
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRunTest")
        logger.error(err_trace)
        return {
            "status": "error",
            "test_name": test_name,
            "error": err_trace
        }


def simulate_event(agent, mainwin, event_name: str, event_params: dict = None) -> dict:
    """
    Simulate a specific event by name.
    
    Args:
        agent: The agent running this skill
        mainwin: Main window instance
        event_name: Name of the event to simulate
        event_params: Optional parameters for the event
        
    Returns:
        dict: Event simulation result
    """
    try:
        logger.debug(f"Simulating event: {event_name} with params: {event_params}")
        
        # 1) Find the skill development task of this agent
        agent_tasks = mainwin.agent_tasks
        skill_dev_task = next(
            (task for task in agent_tasks if task.name == "dev:run task for skill under development"),
            None
        )
        
        if not skill_dev_task:
            return {
                "status": "error",
                "event_name": event_name,
                "error": "Skill development task not found"
            }
        
        # 2) Create a normalized event object
        from agent.ec_tasks.resume import normalize_event
        
        # Build the event message data
        event_data = {
            "method": f"{event_name}",
            "params": event_params or {},
            "metadata": {
                "source": "self_test",
                "agent_id": agent.card.id if hasattr(agent, 'card') else None,
                "timestamp": str(datetime.now())
            }
        }
        
        normalized_event = normalize_event(
            event_type=event_name,
            msg=event_data,
            src="self_test",
            tag=f"simulated_{event_name}",
            ctx={"simulated": True}
        )
        
        logger.debug(f"Normalized event created: {normalized_event}")
        
        # 3) Put this event object onto skill dev task's queue
        if skill_dev_task.queue:
            skill_dev_task.queue.put_nowait(normalized_event)
            logger.debug(f"Event '{event_name}' queued to skill dev task: {skill_dev_task.name}")
            
            result = {
                "status": "success",
                "event_name": event_name,
                "message": f"Event '{event_name}' simulated and queued successfully",
                "params": event_params,
                "task": skill_dev_task.name
            }
        else:
            result = {
                "status": "error",
                "event_name": event_name,
                "error": "Skill dev task has no queue"
            }
        
        return result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSimulateEvent")
        logger.error(err_trace)
        return {
            "status": "error",
            "event_name": event_name,
            "error": err_trace
        }


async def create_self_test_chatter_skill(mainwin=None, run_context: dict | None = None):
    try:
        # Inject dependencies on first call
        print("building self_test_chatter_skill..................")
        self_test_chatter_skill = EC_Skill(name=THIS_SKILL_NAME, description=DESCRIPTION)
        self_test_chatter_skill.mapping_rules["developing"]["mappings"] = DEFAULT_CHATTER_MAPPING_RULES
        self_test_chatter_skill.mapping_rules["released"]["mappings"] = DEFAULT_CHATTER_MAPPING_RULES
        mcp_client = mainwin.mcp_client
        # Build workflow graph
        wf = StateGraph(NodeState, WorkFlowContext)

        # Breakpoint manager for debug toggles
        bp_manager = BreakpointManager()

        # Chat lane
        wf.add_node("tester_chat", node_builder(llm_node_with_raw_files, "tester_chat", THIS_SKILL_NAME, PUBLIC_OWNER, bp_manager))
        wf.add_node("pend_for_next_human_msg",
                    node_builder(pend_for_human_input_node, "pend_for_next_human_msg", THIS_SKILL_NAME, PUBLIC_OWNER,
                                 bp_manager))
        wf.add_node("do_work",
                    node_builder(run_test_node, "do_work", THIS_SKILL_NAME, PUBLIC_OWNER, bp_manager))
        wf.add_conditional_edges("tester_chat", chat_or_work, ["pend_for_next_human_msg", "do_work"])
        wf.add_edge("pend_for_next_human_msg", "tester_chat")

        # Collect specs -> query components (prep -> MCP -> post)
        wf.add_edge("do_work", END)
        wf.set_entry_point("tester_chat")

        self_test_chatter_skill.set_work_flow(wf)
        # Store manager so caller can close it after using the skill
        self_test_chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("self_test_chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        err_msg = get_traceback(e, "ErrorCreateSelfTestChatterSkill")
        logger.debug(err_msg)
        return None

    return self_test_chatter_skill


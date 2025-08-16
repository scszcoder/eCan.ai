from typing import TypedDict
import uuid

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

from agent.chats.chat_utils import a2a_send_chat
from agent.ec_skills.file_utils.file_utils import extract_file_text
from bot.Logger import *
from agent.ec_skill import *
from agent.ec_skills.llm_hooks.llm_hooks import run_pre_llm_hook, run_post_llm_hook
from utils.logger_helper import get_agent_by_id, get_traceback
from utils.logger_helper import logger_helper as logger
from agent.mcp.local_client import mcp_call_tool
from agent.chats.tests.test_notifications import sample_metrics_0
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from agent.ec_skills.llm_utils.llm_utils import prep_multi_modal_content, llm_node_with_raw_files


THIS_SKILL_NAME = "chatter for ecan.ai search parts and components web site"

def _ensure_context(ctx: WorkFlowContext) -> WorkFlowContext:
    """Get params that configure the search algorithm."""
    if ctx.this_node:
        if ctx.this_node.get("name", ""):
            ctx.this_node = ctx.this_node
    else:
        ctx.node = {"name": ""}

# this node will call ecan.ai api to obtain parametric filters of the searched components
def get_user_parametric_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    webdriver = mainwin.webdriver
    try:
        url = state["messages"][0]
        webdriver.switch_to.window(webdriver.window_handles[0])
        time.sleep(3)
        webdriver.execute_script(f"window.open('{url}', '_blank');")

        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state.error = get_traceback(e, "ErrorGetUserParametricNode")
        logger.debug(state.error)
        return state


def pend_for_human_input_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    print("pend_for_human_input_node:", state)
    if state.get("tool_result", None):
        qa_form = state.get("tool_result").get("qa_form", None)
        notification = state.get("tool_result").get("notification", None)
    else:
        qa_form = None
        notification = None

    interrupted = interrupt( # (1)!
        {
            "prompt_to_human": state["result"], # (2)!
            "qa_form_to_human": qa_form,
            "notification_to_human": notification
        }
    )
    print("node running:", runtime.context.current_node)
    print("interrupted:", interrupted)
    return {
        "pended": interrupted # (3)!
    }

def examine_filled_specs_node(state):
    if state["result"]:
        state["condition"] = True
    else:
        state["condition"] = False

def confirm_FOM_node(state):
    if state["result"]:
        state["condition"] = True
    else:
        state["condition"] = False

def pend_for_result_message_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    print("pend_for_human_input_node:", state)
    if state.get("tool_result", None):
        qa_form = state.get("tool_result").get("qa_form", None)
        notification = state.get("tool_result").get("notification", None)
    else:
        qa_form = None
        notification = None

    interrupted = interrupt( # (1)!
        {
            "prompt_to_human": state["result"], # (2)!
            "qa_form_to_human": qa_form,
            "notification_to_human": notification
        }
    )
    print("node running:", runtime.context.current_node)
    print("interrupted:", interrupted)
    return {
        "pended": interrupted # (3)!
    }



def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    print("chat_or_work input:", state)
    if isinstance(state['result'], dict):
        state_output = state['result']
        if state_output.get("job_related", False):
            return "more_analysis_app"
        else:
            return "casually_respond_and_pend_for_next_human_msg"
    else:
        return "casually_respond_and_pend_for_next_human_msg"


def is_preliminary_component_info_ready(state: NodeState, *, runtime: Runtime) -> str:
    print("is_preliminary_component_info_ready input:", state)
    if state['condition']:
        return "query_component_specs"
    else:
        return "respond_and_pend_for_next_human_msg"

def all_requirement_filled(state: NodeState) -> str:
    print("all_requirement_filled:", state)
    if state["all_requirement_filled"]:
        return True
    return False


# for now, the raw files can only be pdf, PNG(.png) JPEG (.jpeg and .jpg) WEBP (.webp) Non-animated GIF (.gif),
# .wav (.mp3) and .mp4
def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    try:
        print("in llm_node_with_raw_files....")
        user_input = state.get("input", "")
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        print("run time:", runtime)
        current_node_name = runtime.context["this_node"].get("name")
        # print("current node:", current_node)
        nodes = [{"askid": "skid0", "name": current_node_name}]
        full_node_name = f"{THIS_SKILL_NAME}:{current_node_name}"
        nodes_prompts = run_pre_llm_hook(current_node_name, agent, state)

        print("networked prompts:", nodes_prompts)
        node_prompt = nodes_prompts[0]

        mm_content = prep_multi_modal_content(state, runtime)
        langchain_prompt = ChatPromptTemplate.from_messages(node_prompt)
        formatted_prompt = langchain_prompt.format_messages(component_info=state["input"], categories=state["attributes"]["categories"])


        llm = ChatOpenAI(model="gpt-4.1-2025-04-14")


        print("chat node: llm prompt ready:", formatted_prompt)
        response = llm.invoke(formatted_prompt)
        print("chat node: LLM response:", response)
        # Parse the response
        run_post_llm_hook(current_node_name, agent, state, response)

    except Exception as e:
        # Get the traceback information
        err_trace = get_traceback(e, "ErrorLLMNodeWithRawFiles")
        logger.debug(err_trace)



def query_component_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        print("about to query components:", type(state), state)
        loop = asyncio.get_event_loop()
    except RuntimeError as e:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            tool_result = loop.run_until_complete(mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]} ))
            # tool_result = await mainwin.mcp_client.call_tool(
            #     "os_connect_to_adspower", arguments={"input": state.tool_input}
            # )
            print("query components completed:", type(tool_result), tool_result)
            if "completed" in tool_result.content[0].text:
                state.result = tool_result.content[0].text
                state.tool_result = getattr(tool_result, 'meta', None)
            else:
                state["error"] = tool_result.content[0].text

            return state
        except Exception as e:
            state['error'] = get_traceback(e, "ErrorGoToSiteNode0")
            logger.debug(state['error'])
            return state
        finally:
            loop.close()
    else:
        try:
            tool_result = loop.run_until_complete(
                mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]}))
            # tool_result = await mainwin.mcp_client.call_tool(
            #     "os_connect_to_adspower", arguments={"input": state.tool_input}
            # )
            print("old loop query components tool completed:", type(tool_result), tool_result)
            if "completed" in tool_result.content[0].text:
                state.result = tool_result.content[0].text
                state.tool_result = getattr(tool_result, 'meta', None)
            else:
                state["error"] = tool_result.content[0].text

            return state
        except Exception as e:
            state['error'] = get_traceback(e, "ErrorGoToSiteNode1")
            logger.debug(state['error'])
            return state

# this function takes the prompt generated by LLM from the previous node and puts ranking method template
# into the right place. This way, the correct data can be passed onto the GUI side of the chat interface.
def prep_ranking_method_template_node(state: NodeState) -> NodeState:
    try:
        ranking_method_template = sample_metrics_0
        if state.get("tool_result", None):
            state["tool_result"]["qa_form_to_human"] = ranking_method_template
        # highlight-next-line
        else:
            state["tool_result"] = {"qa_form_to_human": ranking_method_template}
        return state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorPrepRankingMethodTemplateNode")
        logger.debug(state['error'])
        return state


def prep_component_specs_qa_form_node(state: NodeState) -> NodeState:
    try:
        component_specs_qa_form = state.get("result", {})
        if state.get("tool_result", None):
            state["tool_result"]["qa_form_to_human"] = component_specs_qa_form
        # highlight-next-line
        else:
            state["tool_result"] = {"qa_form_to_human": component_specs_qa_form}
        return state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorPrepComponentSpecsQaFormNode")
        logger.debug(state['error'])
        return state

def request_FOM_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    print("run_search_node:", state)

    # send self a message to trigger the real component search work-flow
    result = self_agent.a2a_send_chat_message(self_agent, {"message": "search_parts_request", "params": state.attributes})
    state.result = result
    return state


def run_search_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    print("run_search_node:", state)

    # send self a message to trigger the real component search work-flow
    result = self_agent.a2a_send_chat_message(self_agent, {"message": "search_parts_request", "params": state.attributes})
    state.result = result
    return state

def are_component_specs_filled(state):
    print("is_result_ready input:", state)
    if state['condition']:
        return "send_FOM_request"
    else:
        return "respond_and_pend_for_next_human_msg1"


def is_FOM_filled(state):
    print("is_result_ready input:", state)
    if state['condition']:
        return "show_results"
    else:
        return "pend_for_result"


def is_result_ready(state):
    print("is_result_ready input:", state)
    if state['condition']:
        return "show_results"
    else:
        return "pend_for_result"



# grab results, stuff it into a message and send to human twin agent for
def show_results_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

    print("show_results_node:", state)

    # send self a message to trigger the real component search work-flow
    result = self_agent.a2a_send_chat_message(twin_agent,
                                              {"message": "search_parts_results", "search_results": state.tool_result})
    state.result = result
    return state


async def create_search_parts_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_chatter_skill = EC_Skill(name="chatter for ecan.ai search parts and components web site",
                             description="chat with human or other agents to help search a part/component or a product on 1688 website.")

        llm = ChatOpenAI(model="gpt-4.1-2025-04-14", temperature=0.5)
        print("llm loaded:", llm)


        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("chat", node_wrapper(llm_node_with_raw_files, "chat"))
        workflow.set_entry_point("chat")
        # workflow.add_node("goto_site", goto_site)
        workflow.add_node("casually_respond_and_pend_for_next_human_msg", node_wrapper(llm_node_with_raw_files, "casually_respond_and_pend_for_next_human_msg"))
        workflow.add_node("more_analysis_app", node_wrapper(llm_node_with_raw_files, "more_analysis_app"))
        workflow.add_conditional_edges("chat", chat_or_work, ["casually_respond_and_pend_for_next_human_msg", "more_analysis_app"])
        workflow.add_edge("casually_respond_and_pend_for_next_human_msg", "chat")


        workflow.add_node("respond_and_pend_for_next_human_msg0", node_wrapper(llm_node_with_raw_files, "respond_and_pend_for_next_human_msg0"))
        workflow.add_node("query_component_specs", query_component_specs_node)

        workflow.add_conditional_edges("more_analysis_app", is_preliminary_component_info_ready, ["query_component_specs", "respond_and_pend_for_next_human_msg0"])
        workflow.add_edge("respond_and_pend_for_next_human_msg0", "more_analysis_app")      # chat infinite loop


        workflow.add_node("pend_for_human_input_fill_specs", pend_for_human_input_node)
        # workflow.add_node("request_oem_part_number", request_oem_part_number_node)
        workflow.add_edge("query_component_specs", "pend_for_human_input_fill_specs")
        workflow.add_node("examine_filled_specs", examine_filled_specs_node)

        workflow.add_node("respond_and_pend_for_next_human_msg1", node_wrapper(llm_node_with_raw_files, "respond_and_pend_for_next_human_msg1"))

        workflow.add_conditional_edges("examine_filled_specs", are_component_specs_filled, ["request_FOM", "respond_and_pend_for_next_human_msg1"])
        workflow.add_edge("respond_and_pend_for_next_human_msg1", "examine_filled_specs")

        workflow.add_node("request_FOM", request_FOM_node)

        workflow.add_node("pend_for_human_input_fill_FOM", pend_for_human_input_node)
        workflow.add_node("confirm_FOM", confirm_FOM_node)

        workflow.add_node("respond_and_pend_for_next_human_msg2", node_wrapper(llm_node_with_raw_files, "respond_and_pend_for_next_human_msg2"))

        workflow.add_conditional_edges("confirm_FOM", is_FOM_filled, ["run_search", "respond_and_pend_for_next_human_msg2"])
        workflow.add_edge("respond_and_pend_for_next_human_msg2", "confirm_FOM")


        workflow.add_node("run_search", run_search_node)
        workflow.add_node("pend_for_result", pend_for_result_message_node)

        workflow.add_node("show_results", show_results_node)
        workflow.add_conditional_edges("run_search", is_result_ready, ["show_results", "pend_for_result"])
        workflow.add_edge("show_results", END)


        searcher_chatter_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        searcher_chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("search1688chatter_skill build is done!")

    except Exception as e:
        errMsg = get_traceback(e, "ErrorCreateSearchPartsChatterSkill")
        logger.debug(errMsg)
        return None

    return searcher_chatter_skill


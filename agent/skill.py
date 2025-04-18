from typing import Any, Dict, List, Literal, Optional, Type, Callable, Annotated
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
import uuid
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph, START
from langgraph.graph.graph import CompiledGraph
from langgraph.graph.message import AnyMessage, add_messages
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from typing_extensions import TypedDict
from langgraph.prebuilt import tools_condition
import json
import traceback


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

class Skill(BaseModel):
    id: str = str(uuid.uuid4())
    work_flow: StateGraph = StateGraph(State)        # {"app_name": "app_context", ....} "ecbot" being the internal rpa runs.
    runnable: CompiledGraph = None
    owner: str = ""
    name: str = "generic"
    description: str = "to do and not to do"
    config: dict = {}
    ui_info: dict = {"text": "skill", "icon": ""}
    objectives: [str] = []
    need_inputs: [dict] = []
    version: str = "0.0.0"

    tags: List[str] | None = None
    examples: List[str] | None = None
    inputModes: List[str] | None = None
    outputModes: List[str] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_config(self):
        return self.config

    def get_ui_info(self):
        return self.ui_info

    def set_runnable(self, compiled_graph):
        self.runnable = compiled_graph

    def get_runnable(self):
        return self.runnable

    def loadFromFile(self, sk_json_file):
        with open(sk_json_file, "r") as skjsf:
            sk_js = json.load(skjsf)
            self.set_ui_info(sk_js["ui_info"])


def build_agent_skills(llm, skill_path=""):
    skills = []
    if not skill_path:
        skills.append(create_rpa_helper_skill(llm))
    else:
        skills = build_agent_skills_from_files(llm, skill_path)
    return skills

def build_agent_skills_from_files(llm, skill_path=""):
    return []

def create_rpa_helper_skill(mainwin):
    try:
        llm = mainwin.llm
        helper_skill = Skill(name="ecbot rpa helper",
                             description="help fix failures during ecbot RPA runs.")

        with MultiServerMCPClient(
                {
                    "E-Commerce Agents Service": {
                        # make sure you start your weather server on port 8000
                        "url": "http://localhost:4668/sse",
                        "transport": "sse",
                    }
                }
        ) as client:
            # create_react_agent(
            # 	self.model, tools=self.tools, checkpointer=memory, prompt=self.SYSTEM_INSTRUCTION,
            # 	response_format=ResponseFormat
            # )
            mcp_agent = create_react_agent(llm, client.get_tools())
            helper_skill.set_runnable(mcp_agent)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPAHelperSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPAHelperSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None

    return helper_skill


def create_rpa_operator_skill(mainwin):
    try:
        llm = mainwin.llm
        helper_skill = Skill(name="ecbot rpa operator",
                             description="help run ecbot RPA works.")

        with MultiServerMCPClient(
                {
                    "E-Commerce Agents Service": {
                        # make sure you start your weather server on port 8000
                        "url": "http://localhost:4668/sse",
                        "transport": "sse",
                    }
                }
        ) as client:
            # create_react_agent(
            # 	self.model, tools=self.tools, checkpointer=memory, prompt=self.SYSTEM_INSTRUCTION,
            # 	response_format=ResponseFormat
            # )
            mcp_agent = create_react_agent(llm, client.get_tools())
            helper_skill.set_runnable(mcp_agent)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPAOperatorSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPAOperatorSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None

    return helper_skill



def create_rpa_supervisor_skill(mainwin):
    try:
        llm = mainwin.llm
        helper_skill = Skill(name="ecbot rpa supervisor",
                             description="Supervise ecbot RPA operators.")

        with MultiServerMCPClient(
                {
                    "E-Commerce Agents Service": {
                        # make sure you start your weather server on port 8000
                        "url": "http://localhost:4668/sse",
                        "transport": "sse",
                    }
                }
        ) as client:
            # create_react_agent(
            # 	self.model, tools=self.tools, checkpointer=memory, prompt=self.SYSTEM_INSTRUCTION,
            # 	response_format=ResponseFormat
            # )
            mcp_agent = create_react_agent(llm, client.get_tools())
            helper_skill.set_runnable(mcp_agent)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPASupervisorSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPASupervisorSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None

    return helper_skill
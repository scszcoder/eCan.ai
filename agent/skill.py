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

def create_rpa_helper_skill(llm):
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
    return helper_skill
from typing import Any, Dict, List
import copy
import json
from typing import  Annotated
from pydantic import BaseModel, Field, ConfigDict, model_validator
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from typing import List, Any, Annotated, Literal
import uuid
from langmem.short_term import RunningSummary


from dataclasses import dataclass
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import MessagesState, BaseMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import InMemorySaver
#from sqlalchemy.testing.suite.test_reflection import metadata
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore

from typing_extensions import TypedDict
from agent.mcp.server.tool_schemas import tool_schemas
from agent.a2a.common.types import AgentSkill
import json
import time
import random

import operator
from utils.logger_helper import logger_helper as logger, get_traceback
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from utils.logger_helper import logger_helper as logger, get_traceback
from agent.ec_tasks.resume import build_node_transfer_patch
# ---------------------------------------------------------------------------
# ── 1.  Typed State for LangGraph ───────────────────────────────────────────
# ---------------------------------------------------------------------------
class State(TypedDict):
    """Top‑level LangGraph state object."""
    messages: Annotated[list[Any], "add_messages"]
    mcp_client: "MultiServerMCPClient"
    retries: int
    resolved: bool
    input: str

DEFAULT_MAPPING_RULE = {
  "developing": {
    "mappings": [
      {
        "from": ["event.data.qa_form_to_agent", "event.data.qa_form"],
        "to": [
          {"target": "state.attributes.forms.qa_form"},
          {"target": "resume.qa_form_to_agent"}
        ],
        "on_conflict": "merge_deep"
      },
      {
        "from": ["event.data.notification_to_agent", "event.data.notification"],
        "to": [
          {"target": "state.attributes.notifications.latest"},
          {"target": "resume.notification_to_agent"}
        ],
        "on_conflict": "merge_deep"
      },
      {
        "from": ["event.data.human_text"],
        "to": [
          {"target": "state.attributes.human.last_message"},
          {"target": "resume.human_text"}
        ],
        "transform": "to_string",
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.params.metadata.i_tag", "event.data.metadata.i_tag"],
        "to": [
          { "target": "event.tag" }
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.tag"],
        "to": [
          {"target": "state.attributes.cloud_task_id"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.metadata"],
        "to": [
          {"target": "state.attributes.debug.last_event_metadata"}
        ],
        "on_conflict": "overwrite"
      }
    ],
    "options": {
      "strict": False,
      "default_on_missing": None,
      "apply_order": "top_down"
    }
  },
  "released": {
    "mappings": [
      {
        "from": ["event.data.qa_form_to_agent", "event.data.qa_form"],
        "to": [
          {"target": "state.attributes.forms.qa_form"},
          {"target": "resume.qa_form_to_agent"}
        ],
        "on_conflict": "merge_deep"
      },
      {
        "from": ["event.data.notification_to_agent", "event.data.notification"],
        "to": [
          {"target": "state.attributes.notifications.latest"},
          {"target": "resume.notification_to_agent"}
        ],
        "on_conflict": "merge_deep"
      },
      {
        "from": ["event.data.human_text"],
        "to": [
          {"target": "state.attributes.human.last_message"},
          {"target": "resume.human_text"}
        ],
        "transform": "to_string",
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.params.metadata.i_tag", "event.data.metadata.i_tag"],
        "to": [
          { "target": "event.tag" }
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.tag"],
        "to": [
          {"target": "state.attributes.cloud_task_id"}
        ],
        "on_conflict": "overwrite"
      }
    ],
    "options": {
      "strict": True,
      "default_on_missing": None,
      "apply_order": "top_down"
    }
  },
  "node_transfers": {},
   "event_routing": {
    "human_chat": {"task_selector": "name_contains:chatter", "queue": ""},
    "dev_human_chat": {"task_selector": "name_contains:development", "queue": "chat_queue"},
    "a2a": {"task_selector": "name_contains:chatter", "queue": ""},
    "api_response": {"task_selector": "id:11111", "queue": ""},
    "web_hook": {"task_selector": "id:11111", "queue": ""},
    "cloud_websocket": {"task_selector": "name:search_digikey_chatter", "queue": ""},
    "web_sse": {"task_selector": "name:abc", "queue": ""},
    "rerank_search_results": {"task_selector": "name:search_digikey_chatter", "queue": ""},
    "": {"task_selector": "name:search_digikey_chatter", "queue": ""}
  }
}


def _generate_stable_id(name: str, source: str) -> str:
    """Generate a stable ID for code skills based on name, or random UUID for ui skills.
    
    Code-generated skills use 'code-skill-' prefix for easy identification.
    """
    if source == "code":
        # Use uuid5 with a namespace to generate deterministic ID from name
        namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID namespace for names
        uuid_part = str(uuid.uuid5(namespace, f"code:{name}"))
        return f"code-skill-{uuid_part}"  # Add prefix to identify code-generated skills
    return str(uuid.uuid4())


class EC_Skill(AgentSkill):
    """Holds a compiled LangGraph runnable and metadata."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    askid: int = 0
    work_flow: StateGraph = StateGraph(State)        # {"app_name": "app_context", ....} "ecbot" being the internal rpa runs.
    diagram: dict = {}
    runnable: CompiledStateGraph = None
    mcp_client: MultiServerMCPClient = None
    owner: str = ""
    name: str = "generic"
    description: str = "to do and not to do"
    config: dict = {}
    ui_info: dict = {"text": "skill", "icon": ""}
    objectives: List[str] = []
    need_inputs: List[dict] = []
    version: str = "0.0.0"
    level: str = "entry"
    path: str = ""
    run_mode: str = "released"      # has to be either "development" or "released"
    source: str = "ui"              # "code" for code-based, "example" for example skills, "ui" for UI-created
    # Optional: per-skill mapping rules for resume/state mapping DSL
    mapping_rules: dict | None = DEFAULT_MAPPING_RULE

    tags: List[str] | None = None
    examples: List[str] | None = None
    inputModes: List[str] | None = None
    outputModes: List[str] | None = None

    apps: Any = None
    limitations: Any = None
    price: int = 0
    price_model: str = ""
    public: bool = False
    rentable: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode='after')
    def _ensure_stable_id(self):
        """Automatically generate/regenerate stable ID based on name and source.
        
        This is the ONLY place where ID generation happens:
        - code skills: deterministic ID from name (code-skill-{uuid5})
        - ui skills: random UUID (only if not already set)
        
        This validator runs:
        1. After initial object creation
        2. After any field update via model_validate()
        """
        # Always regenerate ID for code skills to ensure consistency
        if self.source == "code":
            self.id = _generate_stable_id(self.name, self.source)
        # For ui skills, only generate if ID is not set or is default
        elif not self.id or self.id == str(uuid.uuid4()):
            # Keep existing ID for ui skills unless it's a default UUID
            pass
        return self
    
    def get_config(self):
        return self.config

    def get_ui_info(self):
        return self.ui_info

    def set_runnable(self, compiled_graph):
        self.runnable = compiled_graph

    def get_runnable(self):
        return self.runnable

    def set_work_flow(self, wf):
        self.work_flow = wf
        checkpointer = InMemorySaver()
        self.runnable = wf.compile(checkpointer=checkpointer)

    def get_work_flow(self):
        return self.work_flow

    def loadFromFile(self, sk_json_file):
        with open(sk_json_file, "r") as skjsf:
            sk_js = json.load(skjsf)
            self.set_ui_info(sk_js["ui_info"])

    def getWorkFlowJSON(self):
        flowJS = self.work_flow
        flowJS = {}
        return flowJS

    def to_dict(self):
        return {
            "id": self.id,
            "work_flow": self.getWorkFlowJSON(),
            "owner": self.owner,
            "name": self.name,
            "description": self.description,
            "config": self.config,
            "ui_info": self.ui_info,
            "objectives": self.objectives,
            "need_inputs": self.need_inputs,
            "version": self.version,
            "level": self.level,
            "path": self.path,
            "source": self.source,  # 'code' or 'ui'
            "tags": self.tags,
            "examples": self.examples,
            "inputModes": self.inputModes,
            "outputModes": self.outputModes,
            "apps": self.apps,
            "limitations": self.limitations,
            "price": self.price,
            "price_model": self.price_model,
            "public": self.public,
            "rentable": self.rentable,
        }


@dataclass
class SkillDTO:
    name: str
    description: str
    config: Dict[str, Any]

@dataclass
class LoadedSkill:
    dto: SkillDTO
    work_flow: StateGraph


class BaseState(MessagesState):
    messages: Annotated[List[BaseMessage], operator.add]
    my_list: List[int]
    is_last_step: bool

# def _bind_to_system_message(state):
#     print(state) # Problem here
#     return "system prompt"


# Goal for graph
class Goal(TypedDict):
    name: str
    description: str
    value_type: str
    min_val: str
    max_val: str
    formula: str
    lut: dict
    score: float
    weight: float
    sub_goals: List[dict]

class FileAttachment(TypedDict):
    name: str
    type: str
    url: str
    data: bytes


# State for LangGraph
class NodeState(TypedDict):
    input: str
    attachments: List[FileAttachment]
    prompts: List[dict]
    prompt_refs: dict
    history: List[Any]              #raw history
    summary: RunningSummary | None
    messages: List[Any]
    threads: List[dict]
    events: List[dict]
    this_node: str
    attributes: dict
    result: dict
    tool_calls: List[dict]
    tool_result: dict
    http_response: dict
    cli_input: dict
    cli_results: dict
    error: str
    retries: int
    condition: bool
    private: bool
    condition_vars: dict
    loop_end_vars: dict
    case: str
    goals: List[Goal]
    next_action: str
    breakpoint: bool
    py_script: str
    ts_script: str
    shell_script: str
    task_start_time: str
    max_steps: int
    n_steps: int
    node_start_time: str
    metadata: dict


class ToT_Context(TypedDict):
    max_depth: int
    threshold: float
    k: int
    beam_size: int


class WorkFlowContext(TypedDict, total=False):
    id: str
    topic: str
    summary: str
    msg_thread_id: str
    tot_context: dict
    app_context: dict
    this_node: dict


def node_wrapper(fn, node_name, skill_name, owner):
    def wrapped(state, *, runtime: Runtime[WorkFlowContext], store: BaseStore, **kwargs):
        # Inject node name into context or config
        runtime.context["this_node"] = {"name": node_name, "skill_name": skill_name, "owner": owner}
        return fn(state, runtime=runtime, store=store, **kwargs)
    return wrapped


def node_builder(node_fn, node_name, skill_name, owner, bp_manager, default_retries=3, base_delay=1, jitter=0.5):
    """
    A higher-order function that wraps a node's callable to add common functionality
    like retries, breakpoint handling, and context injection.
    """

    def wrapper(state: dict, *, runtime: Runtime[WorkFlowContext], store: BaseStore, **kwargs) -> dict:
        """This inner function is what gets executed by LangGraph for each node.
        It contains the retry logic and handles processing the return value.
        """ 
        # Execute the node function first
        # Safely get and cast the retry value to an integer

        # Safely get and cast the retry value to an integer
        try:
            retries = int(state.get("retry", default_retries))
        except (ValueError, TypeError):
            retries = default_retries
        attempts = 0
        last_exc = None
        result = None
        logger.info(f"[node_builder] ENTERING node={node_name}, skill={skill_name}")
        runtime.context["this_node"] = {"name": node_name, "skill_name": skill_name, "owner": owner}
        # Ensure attributes dict exists before use
        try:
            node_rules_map = None
            attrs = state.get("attributes") if isinstance(state, dict) else None
            if isinstance(attrs, dict):
                node_rules_map = attrs.get("node_transfer_rules")
            if node_rules_map is None and isinstance(state, dict):
                node_rules_map = state.get("node_transfer_rules")

            rules_for_node = None
            if isinstance(node_rules_map, dict):
                if node_name in node_rules_map and isinstance(node_rules_map[node_name], dict):
                    rules_for_node = node_rules_map[node_name]
                elif "mappings" in node_rules_map:
                    # Treat as mapping spec for this node
                    rules_for_node = node_rules_map

            if isinstance(rules_for_node, dict) and rules_for_node.get("mappings"):
                patch = build_node_transfer_patch(node_name, state, {node_name: rules_for_node})

                def _deep_merge(a: dict, b: dict) -> dict:
                    out = dict(a)
                    for k, v in b.items():
                        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                            out[k] = _deep_merge(out[k], v)
                        else:
                            out[k] = v
                    return out

                if isinstance(patch, dict) and patch:
                    # Deep-merge common sections
                    for sec in ("attributes", "metadata", "tool_input"):
                        if sec in patch:
                            base = state.get(sec) if isinstance(state.get(sec), dict) else {}
                            state[sec] = _deep_merge(base, patch[sec])
                    # Handle other keys conservatively
                    for k, v in patch.items():
                        if k in ("attributes", "metadata", "tool_input"):
                            continue
                        if k == "messages" and isinstance(v, list):
                            if isinstance(state.get("messages"), list):
                                state["messages"].extend(v)
                            else:
                                state["messages"] = list(v)
                        else:
                            state[k] = v
                logger.debug(f"[node_builder] applied node transfer mapping for {node_name}")
        except Exception as _e:
            err_msg = get_traceback(_e, "ErrorNodeBuilderWrapper")
            logger.debug(f"[node_builder] node transfer mapping skipped/failed at {node_name}: {err_msg}")

        # Utility: produce a JSON/checkpoint safe view of state (whitelist fields, avoid cycles)
        def _prune_result(res: Any) -> Any:
            # if isinstance(res, dict):
            #     forbidden = {
            #         "input","attachments","prompts","history","messages","threads","metadata",
            #         "attributes","result","tool_input","tool_result","error","retries","condition","case","goals"
            #     }
            #     # keep only non-forbidden keys from result
            #     return {k: _prune_result(v) for k, v in res.items() if k not in forbidden}
            # elif isinstance(res, list):
            #     return [_prune_result(v) for v in res]
            # else:
            #     return res
            return res

        def _safe_state_view(st: dict) -> dict:
            whitelist = [
                "input","attachments","prompts","history","messages","threads","metadata",
                "attributes","result","tool_input","tool_result","error","retries","condition","case","goals"
            ]
            out = {}
            for k in whitelist:
                v = st.get(k)
                # Prevent obvious self refs and heavy objects
                if k == "result" and v is st:
                    v = {}
                if k == "result":
                    # Always prune result to prevent nesting/recursion
                    out[k] = _prune_result(v)
                elif isinstance(v, dict):
                    # shallow copy and drop recursive 'result' if points back
                    vd = dict(v)
                    if vd.get("result") is st:
                        vd.pop("result", None)
                    out[k] = vd
                elif isinstance(v, (list, tuple, str, int, float, bool)) or v is None:
                    out[k] = copy.deepcopy(v)
                else:
                    # drop unsupported types
                    out[k] = None
            # Final JSON check; if fails, degrade fields
            try:
                json.dumps(out, ensure_ascii=False, default=str)
            except Exception:
                # best-effort: stringify any non-serializable remnants
                def _stringify(o):
                    try:
                        json.dumps(o)
                        return o
                    except Exception:
                        return str(o)
                out = {k: _stringify(v) for k, v in out.items()}
            return out

        def _notify_node_status(status_label: str, st: dict) -> None:
            """Best-effort IPC notification for this node's runtime status.

            Uses the same channel as the existing 'running' status updates,
            but also emits per-node 'completed' and 'failed' events so the
            frontend can render accurate node-level indicators.
            """
            try:
                from gui.ipc.api import IPCAPI
                import time as time_mod
                ipc = IPCAPI.get_instance()
                # Get run_id from runtime context if available
                run_id = "dev_run_singleton"  # default for dev runs
                try:
                    run_id = runtime.context.get("run_id", "dev_run_singleton")
                except Exception:
                    pass
                logger.info(f"[SIM][node_builder] sending {status_label} status for node={node_name}, run_id={run_id}")
                ipc.update_run_stat(
                    agent_task_id=run_id,
                    current_node=node_name,
                    status=status_label,
                    langgraph_state=st,
                    timestamp=int(time_mod.time() * 1000)
                )
                logger.info(f"[SIM][node_builder] status update sent successfully for node={node_name}, status={status_label}")
                # For "running" we keep a tiny delay to ensure the frontend
                # sees the node enter the running state before completion.
                if status_label == "running":
                    time_mod.sleep(0.05)
            except Exception as ex:
                import traceback
                logger.error(f"[node_builder] Failed to send {status_label} status for {node_name}: {ex}")
                logger.error(f"[node_builder] Traceback: {traceback.format_exc()}")
                pass

        # Step-once: pause at the very next node regardless of configured breakpoints
        try:
            step_once = False
            try:
                step_once = bool(runtime.context.get("step_once"))
            except Exception:
                step_once = False

            # Collect debug context for tracing
            try:
                origin = runtime.context.get("step_from")
            except Exception:
                origin = None
            try:
                skip_list_dbg = runtime.context.get("skip_bp_once", [])
            except Exception:
                skip_list_dbg = []
            logger.debug(f"[step-once] node={node_name}, origin={origin}, step_once={step_once}, skip_bp_once={skip_list_dbg}")

            if step_once:
                origin = runtime.context.get("step_from")
                # Pause at the next node (not the origin which was just skipped)
                if (not origin) or (origin != node_name):
                    logger.info(f"Step-once: pausing at {node_name} before execution.")
                    try:
                        runtime.context["step_once"] = False  # clear so it only pauses once
                    except Exception:
                        pass
                    interrupt({"paused_at": node_name, "i_tag": node_name, "state": _safe_state_view(state)})
        except GraphInterrupt:
            # Re-raise GraphInterrupt so the workflow actually pauses
            raise
        except Exception as _e:
            err_msg = get_traceback(_e, "ErrorNodeBuilderWrapper")
            logger.debug(f"[node_builder] step-once check failed at {node_name}: {err_msg}")

        # Check for breakpoints BEFORE executing the node
        # This ensures we pause before any node code runs
        if bp_manager and bp_manager.has_breakpoint(node_name):
            logger.debug(f"[breakpoint] Configured breakpoint present for node={node_name}")
            # sanitize potential self-referential result before any interrupt
            try:
                if state.get("result") is state:
                    logger.warning(f"Detected self-referential state.result at {node_name}; clearing to avoid recursion")
                    state["result"] = {}
                elif isinstance(state.get("result"), dict) and state["result"].get("result") is state:
                    logger.warning(f"Detected nested self-reference in state.result at {node_name}; trimming")
                    state["result"].pop("result", None)
            except Exception as e:
                err_msg = get_traceback(e, "ErrorNodeBuilderWrapper")
                logger.error(f"Error sanitizing state.result at {node_name}: {err_msg}")
                pass
            # Support one-shot skip using runtime.context (controlled by the task loop)
            skip_list = []
            try:
                skip_list = runtime.context.get("skip_bp_once", [])
            except Exception as e:
                err_msg = get_traceback(e, "ErrorNodeBuilderWrapper")
                logger.error(f"Error build skip list at {node_name}: {err_msg}")
                skip_list = []

            logger.debug(f"[breakpoint] skip-once list before at node={node_name}: {skip_list}")
            if isinstance(skip_list, (list, tuple)) and node_name in skip_list:
                logger.info(f"[breakpoint] Skip-once: skipping breakpoint at {node_name} per runtime.context")
                # remove it so it only skips once
                try:
                    if isinstance(skip_list, list):
                        skip_list.remove(node_name)
                        logger.debug(f"[breakpoint] skip-once list after at node={node_name}: {runtime.context.get('skip_bp_once')}")
                        runtime.context["skip_bp_once"] = skip_list
                except Exception:
                    pass
            else:
                # Check if step_once is active and this is the origin - if so, skip breakpoint
                step_once_active = runtime.context.get("step_once", False)
                step_origin = runtime.context.get("step_from", "")
                if step_once_active and step_origin == node_name:
                    logger.info(f"[breakpoint] Step-once: skipping breakpoint at origin node {node_name}")
                else:
                    # Fallback: state-based resume flag (kept for compatibility with older flows)
                    resuming_from = state.get("_resuming_from")
                    logger.debug(f"[breakpoint] check for node={node_name}, _resuming_from={resuming_from}")
                    if resuming_from == node_name:
                        logger.info(f"[breakpoint] Skipping breakpoint at {node_name} - resuming from this node (state flag)")
                        state.pop("_resuming_from", None)
                    else:
                        logger.info(f"[breakpoint] HIT at node={node_name}. Pausing before execution.")
                        interrupt({"paused_at": node_name, "i_tag": node_name, "state": _safe_state_view(state)})

        # Send running status to frontend before executing node
        # This must be OUTSIDE the retry loop and AFTER breakpoint checks
        _notify_node_status("running", state)

        # Execute the node function with retry logic
        while attempts < retries:
            try:
                # Add node context to the state, which is mutable
                if "attributes" not in state or not isinstance(state.get("attributes"), dict):
                    state["attributes"] = {}
                state["attributes"]["__this_node__"] = {"name": node_name, "skill_name": skill_name, "owner": owner}
                
                # Execute the actual node function
                result = node_fn(state, runtime=runtime, store=store)
                break  # success - exit retry loop
                
            except Exception as e:
                # Do not treat intended graph interrupt as an error: no retry, no warning
                if isinstance(e, GraphInterrupt):
                    raise e

                attempts += 1
                last_exc = e
                err_msg = get_traceback(e, "ErrorNode")
                logger.warning(f"[{node_name}] failed (attempt {attempts}/{retries}): {err_msg}")
                if attempts < retries:
                    delay = base_delay * (2 ** (attempts - 1)) + random.uniform(0, jitter)
                    time.sleep(delay)

        if last_exc:
            # Node ultimately failed after exhausting retries; report a
            # per-node failed status so the UI can render it accurately.
            try:
                if isinstance(state, dict) and not state.get("error"):
                    try:
                        state["error"] = str(last_exc)
                    except Exception:
                        pass
                _notify_node_status("failed", state)
            except Exception:
                pass
            raise last_exc

        # Process the result to ensure it's a valid dictionary for state update
        # if isinstance(result, list):
        #     # Handle cases where debugging injects an Interrupt object
        #     dict_result = next((item for item in result if isinstance(item, dict)), None)
        #     state["result"] = _prune_result(dict_result or {})
        # elif isinstance(result, dict):
        #     state["result"] = _prune_result(result)
        # else:
        #     # If the result is not a dict (e.g., None), return an empty dict to prevent errors
        #     state["result"] = result

        # Final sanitation to avoid self-referential recursion in checkpoints
        try:
            if state.get("result") is state:
                logger.warning(f"Detected self-referential state.result after exec at {node_name}; clearing")
                state["result"] = {}
            elif isinstance(state.get("result"), dict) and state["result"].get("result") is state:
                logger.warning(f"Detected nested self-reference in state.result after exec at {node_name}; trimming")
                state["result"].pop("result", None)
            # ensure pruned
            state["result"] = _prune_result(state.get("result", {}))
        except Exception:
            pass

        # Successful completion: notify frontend for this specific node.
        _notify_node_status("completed", state)

        logger.debug("[node_builder]returning state...", state)
        return state
    # The node_builder itself returns the wrapper function
    return wrapper

def is_json_parsable(s):
    try:
        json.loads(s)
        return True
    except (ValueError, TypeError):
        return False
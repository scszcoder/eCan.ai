import asyncio
from typing import Any, ClassVar, Optional,Dict, List, Literal, Type, Generic, Tuple, TypeVar, cast
from pydantic import Field
from pydantic import ConfigDict, BaseModel
import uuid
from agent.a2a.common.types import *
from agent.ec_skill import EC_Skill
from agent.ec_skills.prep_skills_run import *
import json
import os
import tempfile
import shutil
from pathlib import Path
from fastapi.responses import JSONResponse
import time
from queue import Queue, Empty
import threading
import concurrent.futures
from langgraph.types import Command
from langgraph.errors import GraphInterrupt

from datetime import datetime, timedelta
import inspect
import traceback
from datetime import datetime, timedelta
from calendar import monthrange
from langgraph.types import interrupt
from app_context import AppContext
# from agent.chats.tests.test_notifications import *
from langgraph.types import Interrupt
from agent.ec_skills.dev_defs import BreakpointManager
from agent.ec_skills.llm_utils.llm_utils import send_response_back
from utils.logger_helper import logger_helper as logger

from utils.logger_helper import get_traceback
from langgraph.errors import NodeInterrupt
from agent.tasks_resume import build_general_resume_payload, build_node_transfer_patch, normalize_event, _safe_get
from enum import Enum
from gui.ipc.api import IPCAPI
ipc = IPCAPI.get_instance()

# Dev/Run timeouts and polling intervals for queue-based resumes
# These can be tuned via environment variables during verification and later reduced/noised down
DEV_EVENT_TIMEOUT_SEC = int(os.getenv("DEV_EVENT_TIMEOUT_SEC", "300"))
DEV_EVENT_POLL_INTERVAL_SEC = float(os.getenv("DEV_EVENT_POLL_INTERVAL_SEC", "0.5"))
RUN_EVENT_TIMEOUT_SEC = int(os.getenv("RUN_EVENT_TIMEOUT_SEC", "600"))
# self.REPEAT_TYPES = ["none", "by seconds", "by minutes", "by hours", "by days", "by weeks", "by months", "by years"]
# self.WEEK_DAY_TYPES = ["M", "Tu", "W", "Th", "F", "Sa", "Su"]
# self.MONTH_TYPES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

class Priority_Types(str, Enum):
    LOW = "low"
    MID = "mid"
    HIGH = "High"
    URGENT = "Urgent"
    ASAP = "ASAP"

class Repeat_Types(str, Enum):
    NONE = "none"
    BY_SECONDS = "by seconds"
    BY_MINUTES = "by minutes"
    BY_HOURS = "by hours"
    BY_DAYS = "by days"
    BY_WEEKS = "by weeks"
    BY_MONTHS = "by months"
    BY_YEARS = "by years"

class Week_Days_Types(str, Enum):
    M = "M"
    TU = "Tu"
    W = "W"
    TH = "Th"
    F = "F"
    SA = "by weeks"
    SU = "by months"

class Month_Types(str, Enum):
    JAN = "Jan"
    FEB = "Feb"
    MAR = "Mar"
    APR = "Apr"
    MAY = "May"
    JUN = "Jun"
    JUL = "Jul"
    AUG = "Aug"
    SEP = "Sep"
    OCT = "Oct"
    NOV = "Nov"
    DEC = "Dec"

class TaskSchedule(BaseModel):
    repeat_type: Repeat_Types
    repeat_number: int
    repeat_unit: str
    start_date_time: str
    end_date_time: str
    time_out: int                # seconds.


class ManagedTask(Task):
    # Use Any to avoid strict Pydantic model_type validation between AgentSkill/EC_Skill instances
    # We only access properties (e.g., name) and never rely on Pydantic validation for this field.
    skill: Any
    state: dict
    name: str
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resume_from: Optional[str] = None
    trigger: Optional[str] = None
    task: Optional[asyncio.Task] = None
    pause_event: asyncio.Event = asyncio.Event()
    cancellation_event: threading.Event = Field(default_factory=threading.Event)
    schedule: Optional[TaskSchedule] = None
    checkpoint_nodes: Optional[List[str]] = None
    queue: Optional[Queue] = Field(default_factory=Queue)
    priority: Optional[Priority_Types] = None
    last_run_datetime: Optional[datetime] = None
    already_run_flag: bool = False
    description: str

    model_config = ConfigDict(arbitrary_types_allowed=True)
    # model_config = ConfigDict(ignored_types=('langgraph.types.Command',), arbitrary_types_allowed=True)
    # Command: ClassVar = None

    def __post_init_post_parse__(self):
        self.pause_event.set()
        self.priority = Priority_Types.LOW
        if self.checkpoint_nodes is None:
            self.checkpoint_nodes = []

    def set_skill(self, skill):
        self.skill = skill

    def to_dict(self):
        # Convert datetime to ISO format string for JSON serialization
        last_run_datetime_str = None
        if self.last_run_datetime:
            last_run_datetime_str = self.last_run_datetime.isoformat()

        # Convert schedule to dict with proper enum handling
        schedule_dict = None
        if self.schedule:
            schedule_dict = self.schedule.model_dump(mode='json')

        # Safely serialize state - filter out non-serializable objects like Interrupt
        safe_state = self._make_serializable(self.state) if self.state else None

        # Safely serialize checkpoint_nodes - filter out non-serializable objects
        safe_checkpoint_nodes = self._make_serializable(self.checkpoint_nodes) if self.checkpoint_nodes else None

        # Safely serialize metadata - filter out non-serializable objects like Pydantic models
        safe_metadata = self._make_serializable(self.metadata) if self.metadata else None

        # Safely get skill name
        skill_name = None
        if self.skill:
            skill_name = getattr(self.skill, 'name', None)
            if not skill_name:
                # If skill object doesn't have a name attribute, try to get string representation
                skill_str = str(self.skill)
                # Avoid using generic object representation
                if not skill_str.startswith('<'):
                    skill_name = skill_str
                else:
                    logger.warning(f"Task {self.name} has skill object without name attribute: {type(self.skill)}")

        taskJS = {
            "id": self.id,
            "runId": self.run_id,
            "name": self.name,
            "description": self.description,
            "skill": skill_name,
            "metadata": safe_metadata,
            "state": safe_state,
            "resume_from": self.resume_from,
            "trigger": self.trigger,
            # "pause_event": self.pause_event,
            "schedule": schedule_dict,
            "checkpoint_nodes": safe_checkpoint_nodes,
            "priority": self.priority.value if self.priority else None,
            "last_run_datetime": last_run_datetime_str,
            "already_run_flag": self.already_run_flag,
        }
        return taskJS

    def _make_serializable(self, obj):
        """
        Recursively convert objects to JSON-serializable format.
        Filters out non-serializable objects like Interrupt instances and langchain Message objects.
        """
        import json
        from langgraph.types import Interrupt

        if obj is None:
            return None

        # Handle Pydantic BaseModel objects (e.g., TaskSendParams, Message, etc.)
        if isinstance(obj, BaseModel):
            # Use model_dump with mode='json' to ensure proper serialization
            return self._make_serializable(obj.model_dump(mode='json'))

        # Handle langchain Message objects (SystemMessage, HumanMessage, AIMessage, etc.)
        # These inherit from BaseMessage and have content, type, and optional metadata
        if hasattr(obj, '__class__') and obj.__class__.__module__.startswith('langchain_core.messages'):
            try:
                return {
                    "type": obj.__class__.__name__,
                    "content": str(getattr(obj, 'content', '')),
                    "role": getattr(obj, 'type', 'unknown')
                }
            except Exception as e:
                logger.warning(f"Failed to serialize langchain message: {e}")
                return f"<langchain-message: {obj.__class__.__name__}>"

        # Handle Interrupt objects - convert to a safe representation
        if isinstance(obj, Interrupt):
            return {
                "type": "interrupt",
                "value": self._make_serializable(getattr(obj, 'value', None)),
                "id": str(getattr(obj, 'id', 'unknown'))
            }

        # Handle custom interrupt objects with checkpoint
        if hasattr(obj, '__class__') and obj.__class__.__name__ == 'InterruptWithCheckpoint':
            return {
                "type": "interrupt_with_checkpoint",
                "value": self._make_serializable(getattr(obj, 'value', None)),
                "id": str(getattr(obj, 'id', 'unknown')),
                "checkpoint_available": True  # Don't serialize the actual checkpoint
            }

        # Handle dictionaries
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                try:
                    # Skip keys that contain interrupt objects
                    if key == "__interrupt__":
                        # Convert interrupt list to safe format
                        if isinstance(value, list):
                            result[key] = [self._make_serializable(item) for item in value]
                        else:
                            result[key] = self._make_serializable(value)
                    else:
                        result[key] = self._make_serializable(value)
                except Exception as e:
                    logger.warning(f"Skipping non-serializable key '{key}': {e}")
                    result[key] = f"<non-serializable: {type(value).__name__}>"
            return result

        # Handle lists
        if isinstance(obj, (list, tuple)):
            return [self._make_serializable(item) for item in obj]

        # Handle basic types that are JSON serializable
        if isinstance(obj, (str, int, float, bool)):
            return obj

        # Try to serialize the object to test if it's JSON serializable
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            # If not serializable, convert to string representation
            return f"<non-serializable: {type(obj).__name__}>"

    def set_priority(self, p):
        self.priority = p

    def add_checkpoint_node(self, check_point):
        # Ensure checkpoint_nodes is initialized
        if self.checkpoint_nodes is None:
            self.checkpoint_nodes = []
        if check_point not in self.checkpoint_nodes:
            self.checkpoint_nodes.append(check_point)

    def remove_checkpoint_node(self, check_point):
        # Ensure checkpoint_nodes is initialized
        if self.checkpoint_nodes is None:
            self.checkpoint_nodes = []
        if check_point in self.checkpoint_nodes:
            self.checkpoint_nodes.remove(check_point)

    def cancel(self):
        """Signal the task to cancel its execution."""
        self.cancellation_event.set()


    def stream_run(self, in_msg="", *, config=None, context=None, **kwargs):
        """Run the task's skill with streaming support.

        Args:
            in_msg: Input message or state for the skill
            config: Configuration dictionary for the runnable
            **kwargs: Additional arguments to pass to the runnable's astream method
        """
        print("in_msg:", in_msg, "config:", config, "kwargs:", kwargs)
        print("self.metadata:", self.metadata)

        # Reuse a persistent config (thread_id) across runs; create and cache if missing
        effective_config = config or self.metadata.get("config")
        if effective_config is None:
            effective_config = {
                "configurable": {
                    "thread_id": str(uuid.uuid4()),
                    "store": None
                }
            }
            self.metadata["config"] = effective_config

        # If a checkpoint is provided as a kwarg, move it into config where LangGraph expects it
        if "checkpoint" in kwargs:
            try:
                effective_config["checkpoint"] = kwargs.pop("checkpoint")
            except Exception:
                # ensure config is a dict
                effective_config = dict(effective_config or {})
                effective_config["checkpoint"] = kwargs.pop("checkpoint")

        if context is None:
            context = {
                "id": str(uuid.uuid4()),
                "topic": "",
                "summary": "",
                "msg_thread_id": "",
                "tot_context": {},
                "app_context": {},
                "this_node": {"name": ""},
            }
        
        # Ensure state carries identifiers hooks can read without touching runtime context
        try:
            # Align config thread_id with our context id for consistency
            effective_config.setdefault("configurable", {})
            effective_config["configurable"].setdefault("thread_id", context.get("id"))

            # Mirror identifiers into the task's state attributes for hooks
            st = self.metadata.get("state") or {}
            attrs = st.get("attributes") or {}
            if "thread_id" not in attrs:
                attrs["thread_id"] = context.get("id")
            # Also expose the ManagedTask.run_id for traceability
            if "run_id" not in attrs:
                attrs["run_id"] = self.run_id
            st["attributes"] = attrs
            self.metadata["state"] = st
        except Exception:
            pass

        # Merge step/breakpoint control flags into config's configurable dict
        # These are read by node_builder for step control
        step_control = {}
        for key in ["step_once", "skip_bp_once", "step_from"]:
            if key in context:
                step_control[key] = context[key]
        
        if step_control:
            effective_config.setdefault("configurable", {})
            effective_config["configurable"].update(step_control)
        if not hasattr(self.skill, 'runnable') or self.skill.runnable is None:
            logger.error(f"[SKILL_MISSING] Task {self.id} skill '{self.skill.name if hasattr(self.skill, 'name') else 'UNKNOWN'}' has runnable=None!")
            logger.error(f"[SKILL_MISSING] Skill type: {type(self.skill)}, Skill attributes: {dir(self.skill)}")
            raise AttributeError(f"Skill '{self.skill.name if hasattr(self.skill, 'name') else 'UNKNOWN'}' has no runnable")
        
        logger.debug(f"[SKILL_CHECK] Task {self.id} using skill: {self.skill.name}, runnable type: {type(self.skill.runnable)}")
        print("current langgraph run time state0:", self.skill.runnable.get_state(config=effective_config))

        # Support Command inputs (e.g., Command(resume=...)) and normal state runs
        # Pass context as kwarg for runtime.context, and step control via config
        if isinstance(in_msg, Command):
            # in_args = self.metadata.get("state", {})
            print("effective config before resume:", effective_config)
            agen = self.skill.runnable.stream(in_msg, config=effective_config, context=context, **kwargs)
        else:
            in_args = self.metadata.get("state", {})
            print("in_args:", in_args)
            agen = self.skill.runnable.stream(in_args, config=effective_config, context=context, **kwargs)

        try:
            logger.debug("stream running skill:", self.skill.name, in_msg)
            logger.debug("stream_run config:", effective_config)
            logger.debug("current langgraph run time state2:", self.skill.runnable.get_state(config=effective_config))
            # Set up default config if not provided

            # Handle Command objects
            # if isinstance(in_args, Command):
            #     if in_args == Command.:
            #         # Handle reset command
            #         config["configurable"]["thread_id"] = str(uuid.uuid4())
            #         in_args = {}  # Reset input args
            # Add other command handling as needed

            # Pass through any additional kwargs to astream
            step = {}
            current_checkpoint = None
            # Initial emit: show first node as running if available
            try:
                from gui.ipc.api import IPCAPI
                ipc = IPCAPI.get_instance()
                st0 = self.skill.runnable.get_state(config=effective_config)
                node0 = ""
                try:
                    if hasattr(st0, "next") and st0.next:
                        node0 = st0.next[0]
                except Exception:
                    node0 = ""
                st0_js = st0.values if hasattr(st0, "values") else {}
                ipc.update_run_stat(
                    agent_task_id=self.run_id,
                    current_node=node0 or "",
                    status="running",
                    langgraph_state=st0_js,
                    timestamp=int(time.time() * 1000)
                )
            except Exception:
                pass

            for step in agen:
                # print("synced Step output:", step)

                # Check for cancellation signal
                if self.cancellation_event.is_set():
                    logger.info(f"Task {self.name} ({self.run_id}) received cancellation signal. Stopping.")
                    self.status.state = TaskState.CANCELED
                    break

                # self.pause_event.wait()
                self.status.message = Message(
                    role="agent",
                    parts=[TextPart(type="text", text=str(step))]
                )
                # Push running status to GUI
                try:
                    from gui.ipc.api import IPCAPI  # lazy import to avoid circular deps
                    ipc = IPCAPI.get_instance()
                    node_name = ""
                    try:
                        meta = step.get("__metadata__", {}) if isinstance(step, dict) else {}
                        node_name = meta.get("langgraph_node") or meta.get("node") or ""
                    except Exception:
                        node_name = ""
                    try:
                        st = self.skill.runnable.get_state(config=effective_config)
                        st_js = st.values if hasattr(st, "values") else {}
                        # fallback: use node name from state values if available
                        if not node_name:
                            try:
                                node_name = (
                                    ((st_js or {}).get("attributes") or {})
                                        .get("__this_node__", {})
                                        .get("name") or ""
                                )
                            except Exception:
                                pass
                        # final fallback: next node from state if still missing
                        if (not node_name) and hasattr(st, "next") and st.next:
                            try:
                                node_name = st.next[0]
                            except Exception:
                                pass
                    except Exception:
                        st_js = {}
                    ipc.update_run_stat(
                        agent_task_id=self.run_id,
                        current_node=node_name or "",
                        status="running",
                        langgraph_state=st_js,
                        timestamp=int(time.time() * 1000)
                    )
                except Exception:
                    pass
                if step.get("require_user_input") or step.get("await_agent") or step.get("__interrupt__"):
                    self.status.state = TaskState.INPUT_REQUIRED
                    print("input required...", step)
                    # yield {"success": False, "step": step}
                    if step.get("__interrupt__"):
                        interrupt_obj = step["__interrupt__"][0]
                        i_tag = interrupt_obj.value["i_tag"]

                        # Get checkpoint from LangGraph state since raw Interrupt object doesn't have it
                        current_checkpoint = self.skill.runnable.get_state(config=effective_config)
                        current_checkpoint.values["attributes"]["i_tag"] = i_tag
                        print("current checkpoint:", current_checkpoint)
                        self.add_checkpoint_node({"tag": i_tag, "checkpoint": current_checkpoint})
                        # Push paused status to GUI at interrupt
                        try:
                            from gui.ipc.api import IPCAPI
                            ipc = IPCAPI.get_instance()
                            st_js = current_checkpoint.values if hasattr(current_checkpoint, "values") else {}
                            ipc.update_run_stat(
                                agent_task_id=self.run_id,
                                current_node=i_tag or "",
                                status="paused",
                                langgraph_state=st_js,
                                timestamp=int(time.time() * 1000)
                            )
                        except Exception:
                            pass

                    break

            if self.status.state == TaskState.INPUT_REQUIRED:
                success = False
            else:
                success = True
                self.status.state = TaskState.COMPLETED
                print("task completed...")

            if not current_checkpoint:
                # record exit state
                current_checkpoint = self.skill.runnable.get_state(config=effective_config)

            run_result = {"success": success, "step": step, "cp": current_checkpoint}
            print("synced stream_run result:", run_result)
            # Push completion status to GUI
            # Note: Don't send update here if we already sent a paused status at interrupt
            # The paused node should remain highlighted until user resumes/steps
            try:
                from gui.ipc.api import IPCAPI
                ipc = IPCAPI.get_instance()
                st_js = current_checkpoint.values if hasattr(current_checkpoint, "values") else {}
                # Only send completion update if truly completed (not paused at interrupt)
                if success:
                    ipc.update_run_stat(
                        agent_task_id=self.run_id,
                        current_node="",
                        status="completed",
                        langgraph_state=st_js,
                        timestamp=int(time.time() * 1000)
                    )
                # If paused, the interrupt handler already sent the update with the correct node
            except Exception:
                pass
            return run_result

        except Exception as e:
            ex_stat = "ErrorAstreamRun:" + traceback.format_exc() + " " + str(e)
            print(f"{ex_stat}")
            return {"success": False, "Error": ex_stat}

        finally:
            # Cleanup code here
            # self.runner = None
            if self.cancellation_event.is_set():
                self.status.state = TaskState.CANCELED
            # agen.aclose()

        # Rest of the function remains the same...


    async def astream_run(self, in_msg="", *, config=None, **kwargs):
        """Run the task's skill with streaming support.

        Args:
            in_msg: Input message or state for the skill
            config: Configuration dictionary for the runnable
            **kwargs: Additional arguments to pass to the runnable's astream method
        """
        # Reuse a persistent config (thread_id) across runs; create and cache if missing
        effective_config = config or self.metadata.get("config")
        if not effective_config:
            effective_config = {
                "configurable": {
                    "thread_id": str(uuid.uuid4()),
                }
            }
            self.metadata["config"] = effective_config

        # Ensure state carries identifiers hooks can read without touching runtime context
        try:
            cfg_thread_id = (
                (effective_config or {}).get("configurable", {}).get("thread_id")
                if isinstance(effective_config, dict)
                else None
            ) or str(uuid.uuid4())
            # Keep config and state in sync
            effective_config.setdefault("configurable", {})
            effective_config["configurable"]["thread_id"] = cfg_thread_id

            st = self.metadata.get("state") or {}
            attrs = st.get("attributes") or {}
            if "thread_id" not in attrs:
                attrs["thread_id"] = cfg_thread_id
            if "run_id" not in attrs:
                attrs["run_id"] = self.run_id
            st["attributes"] = attrs
            self.metadata["state"] = st
        except Exception:
            pass

        # Normalize resume form data into state.metadata for downstream nodes expecting it
        try:
            st = self.metadata.get("state") or {}
            attrs = st.get("attributes") or {}
            meta = st.get("metadata") or {}
            has_filled = "filled_parametric_filter" in meta
            if not has_filled:
                formData = (
                    (((attrs.get("params") or {}).get("metadata") or {}).get("params") or {})
                ).get("formData")
                if formData:
                    meta["filled_parametric_filter"] = formData
                    st["metadata"] = meta
                    self.metadata["state"] = st
            # Fallback: some skills stash parametric filters under metadata.components[0].parametric_filters
            if "filled_parametric_filter" not in (st.get("metadata") or {}):
                try:
                    comps = (st.get("metadata") or {}).get("components") or []
                    if isinstance(comps, list) and comps:
                        pfs = comps[0].get("parametric_filters")
                        if pfs:
                            meta = st.get("metadata") or {}
                            # Wrap as {"fields": [...]} to satisfy helpers expecting dict["fields"]
                            meta["filled_parametric_filter"] = {"fields": pfs} if isinstance(pfs, list) else pfs
                            st["metadata"] = meta
                            self.metadata["state"] = st
                except Exception:
                    pass
        except Exception:
            pass

        # Support Command inputs (e.g., Command(resume=...)) and normal state runs
        if isinstance(in_msg, Command):
            agen = self.skill.runnable.astream(in_msg, config=effective_config, **kwargs)
        else:
            in_args = self.metadata.get("state", {})
            print("in_args:", in_args)
            agen = self.skill.runnable.astream(in_args, config=effective_config, **kwargs)
        try:
            print("astream running skill:", self.skill.name, in_msg)
            print("astream_run config:", effective_config)


            # Set up default config if not provided


            # Handle Command objects
            # if isinstance(in_args, Command):
            #     if in_args == Command.:
            #         # Handle reset command
            #         config["configurable"]["thread_id"] = str(uuid.uuid4())
            #         in_args = {}  # Reset input args
            # Add other command handling as needed

            # Pass through any additional kwargs to astream
            step = {}
            current_checkpoint = None
            # Initial emit: show first node as running if available
            try:
                from gui.ipc.api import IPCAPI
                ipc = IPCAPI.get_instance()
                st0 = self.skill.runnable.get_state(config=effective_config)
                node0 = ""
                try:
                    if hasattr(st0, "next") and st0.next:
                        node0 = st0.next[0]
                except Exception:
                    node0 = ""
                st0_js = st0.values if hasattr(st0, "values") else {}
                ipc.update_run_stat(
                    agent_task_id=self.run_id,
                    current_node=node0 or "",
                    status="running",
                    langgraph_state=st0_js,
                    timestamp=int(time.time() * 1000)
                )
            except Exception:
                pass

            async for step in agen:
                print("async Step output:", step)
                await self.pause_event.wait()
                self.status.message = Message(
                    role="agent",
                    parts=[TextPart(type="text", text=str(step))]
                )
                # Push running status to GUI
                try:
                    from gui.ipc.api import IPCAPI
                    ipc = IPCAPI.get_instance()
                    node_name = ""
                    try:
                        meta = step.get("__metadata__", {}) if isinstance(step, dict) else {}
                        node_name = meta.get("langgraph_node") or meta.get("node") or ""
                    except Exception:
                        node_name = ""
                    try:
                        st = self.skill.runnable.get_state(config=effective_config)
                        st_js = st.values if hasattr(st, "values") else {}
                        # fallback: use next node from state if metadata missing
                        if (not node_name) and hasattr(st, "next") and st.next:
                            try:
                                node_name = st.next[0]
                            except Exception:
                                pass
                    except Exception:
                        st_js = {}
                    ipc.update_run_stat(
                        agent_task_id=self.run_id,
                        current_node=node_name or "",
                        status="running",
                        langgraph_state=st_js,
                        timestamp=int(time.time() * 1000)
                    )
                except Exception:
                    pass
                if step.get("require_user_input") or step.get("await_agent") or step.get("__interrupt__"):
                    self.status.state = TaskState.INPUT_REQUIRED
                    print("input required...", step)
                    # yield {"success": False, "step": step}
                    if step.get("__interrupt__"):
                        interrupt_obj = step["__interrupt__"][0]
                        i_tag = interrupt_obj.value["i_tag"]
                        # Get checkpoint from LangGraph state since raw Interrupt object doesn't have it
                        current_checkpoint = self.skill.runnable.get_state(config=effective_config)
                        self.add_checkpoint_node({"tag": i_tag, "checkpoint": current_checkpoint})
                        # Push paused status to GUI at interrupt
                        try:
                            from gui.ipc.api import IPCAPI
                            ipc = IPCAPI.get_instance()
                            st_js = current_checkpoint.values if hasattr(current_checkpoint, "values") else {}
                            ipc.update_run_stat(
                                agent_task_id=self.run_id,
                                current_node=i_tag or "",
                                status="paused",
                                langgraph_state=st_js,
                                timestamp=int(time.time() * 1000)
                            )
                        except Exception:
                            pass
                    break

            if self.status.state == TaskState.INPUT_REQUIRED:
                success = False
            else:
                success = True
                self.status.state = TaskState.COMPLETED
                print("task completed...")

            if not current_checkpoint:
                # record exit state
                current_checkpoint = self.skill.runnable.get_state(config=effective_config)

            run_result = {"success": success, "step": step, "cp": current_checkpoint}
            print("astream_run result:", run_result)
            # Push completion status to GUI
            try:
                from gui.ipc.api import IPCAPI
                ipc = IPCAPI.get_instance()
                st_js = current_checkpoint.values if hasattr(current_checkpoint, "values") else {}
                ipc.update_run_stat(
                    agent_task_id=self.run_id,
                    current_node="",
                    status="completed" if success else "paused",
                    langgraph_state=st_js,
                    timestamp=int(time.time() * 1000)
                )
            except Exception:
                pass
            return run_result

        except Exception as e:
            ex_stat = "ErrorAstreamRun:" + traceback.format_exc() + " " + str(e)
            print(f"{ex_stat}")
            return {"success": False, "Error": ex_stat}

        finally:
            # Cleanup code here
            # self.runner = None
            if self.cancellation_event.is_set():
                self.status.state = TaskState.CANCELED
            try:
                await agen.aclose()
            except Exception:
                pass



    def exit(self):
        """Stop the task and cancel any running operations."""
        self.cancel()  # Signal cancellation
        if self.task and not self.task.done():
            self.task.cancel()

# from langgraph.types import Command
# ManagedTask.Command = Command

from agent.a2a.common.types import TaskSendParams, TextPart
Context = TypeVar('Context')

def add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)

def add_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # handle Feb 29 -> Feb 28 on non-leap years
        return dt.replace(month=2, day=28, year=dt.year + years)

def get_next_runtime(schedule: TaskSchedule) -> Tuple[datetime, bool]:
    fmt = "%Y-%m-%d %H:%M:%S:%f"
    now = datetime.now()
    print("checking start time:", schedule.start_date_time)
    start_time = datetime.strptime(schedule.start_date_time, fmt)
    end_time = datetime.strptime(schedule.end_date_time, fmt)
    repeat_number = int(schedule.repeat_number)

    if schedule.repeat_type == Repeat_Types.NONE:
        return start_time, False  # Never auto-run
    elif schedule.repeat_type == Repeat_Types.BY_SECONDS:
        delta = timedelta(seconds=repeat_number)
        elapsed = (now - start_time).total_seconds()
        intervals = max(0, int(elapsed // delta.total_seconds()))
        next_runtime = start_time + delta * (intervals + 1)
    elif schedule.repeat_type == Repeat_Types.BY_MINUTES:
        delta = timedelta(minutes=repeat_number)
        elapsed = (now - start_time).total_seconds()
        intervals = max(0, int(elapsed // delta.total_seconds()))
        next_runtime = start_time + delta * (intervals + 1)
    elif schedule.repeat_type == Repeat_Types.BY_HOURS:
        delta = timedelta(hours=repeat_number)
        elapsed = (now - start_time).total_seconds()
        intervals = max(0, int(elapsed // delta.total_seconds()))
        next_runtime = start_time + delta * (intervals + 1)
    elif schedule.repeat_type == Repeat_Types.BY_DAYS:
        print("Checking dailly schedule", repeat_number)
        delta = timedelta(days=repeat_number)
        elapsed = (now - start_time).total_seconds()
        intervals = max(0, int(elapsed // delta.total_seconds()))
        next_runtime = start_time + delta * (intervals + 1)
    elif schedule.repeat_type == Repeat_Types.BY_WEEKS:
        delta = timedelta(weeks=repeat_number)
        elapsed = (now - start_time).total_seconds()
        intervals = max(0, int(elapsed // delta.total_seconds()))
        next_runtime = start_time + delta * (intervals + 1)
    elif schedule.repeat_type == Repeat_Types.BY_MONTHS:
        next_runtime = start_time
        while next_runtime <= now:
            next_runtime = add_months(next_runtime, repeat_number)
    elif schedule.repeat_type == Repeat_Types.BY_YEARS:
        next_runtime = start_time
        while next_runtime <= now:
            next_runtime = add_years(next_runtime, repeat_number)
    else:
        raise ValueError(f"Unsupported repeat type: {schedule.repeat_type}")

    # Clamp to end_time
    if next_runtime > end_time:
        next_runtime = end_time

    should_run_now = now >= next_runtime
    return next_runtime, should_run_now


def get_runtime_bounds(schedule: TaskSchedule) -> Tuple[datetime, datetime]:
    fmt = "%Y-%m-%d %H:%M:%S:%f"
    now = datetime.now()
    start_time = datetime.strptime(schedule.start_date_time, fmt)
    end_time = datetime.strptime(schedule.end_date_time, fmt)
    repeat_number = int(schedule.repeat_number)

    if schedule.repeat_type == Repeat_Types.NONE:
        return start_time, start_time  # one-time tasks

    if schedule.repeat_type in (
        Repeat_Types.BY_SECONDS,
        Repeat_Types.BY_MINUTES,
        Repeat_Types.BY_HOURS,
        Repeat_Types.BY_DAYS,
        Repeat_Types.BY_WEEKS,
    ):
        unit_seconds = {
            Repeat_Types.BY_SECONDS: 1,
            Repeat_Types.BY_MINUTES: 60,
            Repeat_Types.BY_HOURS: 3600,
            Repeat_Types.BY_DAYS: 86400,
            Repeat_Types.BY_WEEKS: 7 * 86400,
        }[schedule.repeat_type]

        delta_seconds = unit_seconds * repeat_number
        elapsed = (now - start_time).total_seconds()
        intervals = max(0, int(elapsed // delta_seconds))
        last_runtime = start_time + timedelta(seconds=delta_seconds * intervals)
        next_runtime = last_runtime + timedelta(seconds=delta_seconds)

    elif schedule.repeat_type == Repeat_Types.BY_MONTHS:
        last_runtime = start_time
        while last_runtime <= now:
            future = add_months(last_runtime, repeat_number)
            if future > now:
                next_runtime = future
                break
            last_runtime = future
    elif schedule.repeat_type == Repeat_Types.BY_YEARS:
        last_runtime = start_time
        while last_runtime <= now:
            future = add_years(last_runtime, repeat_number)
            if future > now:
                next_runtime = future
                break
            last_runtime = future
    else:
        raise ValueError(f"Unsupported repeat type: {schedule.repeat_type}")

    # Clamp next runtime to end time
    if next_runtime > end_time:
        next_runtime = end_time
    if last_runtime > end_time:
        last_runtime = end_time

    return last_runtime, next_runtime


def get_repeat_interval_seconds(schedule: TaskSchedule) -> int:
    repeat_number = schedule.repeat_number

    if schedule.repeat_type == Repeat_Types.BY_SECONDS:
        return repeat_number
    elif schedule.repeat_type == Repeat_Types.BY_MINUTES:
        return repeat_number * 60
    elif schedule.repeat_type == Repeat_Types.BY_HOURS:
        return repeat_number * 3600
    elif schedule.repeat_type == Repeat_Types.BY_DAYS:
        return repeat_number * 86400
    elif schedule.repeat_type == Repeat_Types.BY_WEEKS:
        return repeat_number * 7 * 86400
    elif schedule.repeat_type == Repeat_Types.BY_MONTHS:
        # Rough average, for simplicity
        return repeat_number * 30 * 86400
    elif schedule.repeat_type == Repeat_Types.BY_YEARS:
        return repeat_number * 365 * 86400
    else:
        raise ValueError(f"Unsupported repeat type: {schedule.repeat_type}")


# sort t2rs by start time, the earliest will be run first.
def time_to_run(agent):
    t2rs = []
    now = datetime.now()

    for task in agent.tasks:
        # Skip tasks without schedule or non-time-based tasks
        if not task.schedule or task.schedule.repeat_type == Repeat_Types.NONE or task.trigger != "schedule":
            continue

        last_runtime, next_runtime = get_runtime_bounds(task.schedule)

        # Calculate elapsed time since last task run
        if task.last_run_datetime:
            elapsed_since_last_run = (now - task.last_run_datetime).total_seconds()
        else:
            elapsed_since_last_run = float('inf')  # If never ran before

        repeat_seconds = get_repeat_interval_seconds(task.schedule)

        overdue_time = (now - last_runtime).total_seconds()
        logger.debug("overdue:", overdue_time, repeat_seconds, elapsed_since_last_run)
        # Main logic: should we run now?
        if (now >= last_runtime and
            elapsed_since_last_run > repeat_seconds / 2 and
            not task.already_run_flag):
            t2rs.append({
                "overdue": overdue_time,
                "task": task
            })

        # Reset already_run_flag if now is close to the next scheduled run time
        if abs((next_runtime - now).total_seconds()) <= 30 * 60:
            task.already_run_flag = False

    if not t2rs:
        return None

    # Sort tasks: run the most overdue task first
    t2rs.sort(key=lambda x: x["overdue"], reverse=True)

    selected_task = t2rs[0]["task"]
    selected_task.last_run_datetime = now
    selected_task.already_run_flag = True

    return selected_task





class TaskRunnerRegistry:
    """Global registry for TaskRunner instances to allow coordinated shutdown."""
    _runners: List["TaskRunner"] = []

    @classmethod
    def register(cls, runner: "TaskRunner"):
        try:
            if runner not in cls._runners:
                cls._runners.append(runner)
        except Exception:
            pass

    @classmethod
    def unregister(cls, runner: "TaskRunner"):
        try:
            if runner in cls._runners:
                cls._runners.remove(runner)
        except Exception:
            pass

    @classmethod
    def stop_all(cls):
        for r in list(cls._runners):
            try:
                r.stop()
            except Exception:
                pass


class TaskRunner(Generic[Context]):
    def __init__(self, agent):  # includes persistence methods
        self.agent = agent
        self.tasks: Dict[str, ManagedTask] = {}
        # Skill execution thread pool for non-blocking execution
        self._skill_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=20, 
            thread_name_prefix="SkillExec"
        )
        # Track per-task state for concurrent execution
        self._task_states = {}  # {task_id: {'justStarted': bool}}
        self.bp_manager = BreakpointManager()
        self.running_tasks = []
        self.save_dir = os.path.join(agent.mainwin.my_ecb_data_homepath, "task_saves")
        os.makedirs(self.save_dir, exist_ok=True)
        self._dev_task = None  # dev-run handle for sidebar controls

        self._stop_event = threading.Event()
        TaskRunnerRegistry.register(self)
        # Note: legacy fixed global queues (chat_queue/a2a_queue/work_queue) removed.
        # Routing should be done by mapping rules to a specific ManagedTask's own queue.

    # --- Dev-run breakpoint controls (used by skill editor sidebar) ---
    def set_bps_dev_skill(self, bps: list[str] | None):
        """Set breakpoints for the current dev skill run.

        Args:
            bps: list of node names to break on.
        Returns:
            dict with success flag and current breakpoints.
        """
        try:
            nodes = bps or []
            if not isinstance(nodes, list):
                nodes = [str(nodes)]
            bp_list = [str(n) for n in nodes]
            logger.debug(f"[TaskRunner] set_bps_dev_skill called with: {bp_list}")
            self.bp_manager.set_breakpoints(bp_list)
            current = self.bp_manager.get_breakpoints()
            logger.info(f"[TaskRunner] Breakpoints set -> now: {current}")
            return {"success": True, "breakpoints": current}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def clear_bps_dev_skill(self, bps: list[str] | None = None):
        """Clear specific breakpoints, or all if none provided."""
        try:
            if bps:
                to_clear = [str(n) for n in bps]
                logger.debug(f"[TaskRunner] clear_bps_dev_skill called with: {to_clear}")
                self.bp_manager.clear_breakpoints(to_clear)
            else:
                logger.debug("[TaskRunner] clear_bps_dev_skill called with: ALL")
                self.bp_manager.clear_all()
            current = self.bp_manager.get_breakpoints()
            logger.info(f"[TaskRunner] Breakpoints cleared -> now: {current}")
            return {"success": True, "breakpoints": current}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_event_handler(self, event_type="", event_queue=None):
        # Deprecated: kept for backward API compatibility; no-op.
        return


    def _resolve_event_routing(self, event_type: str, request: Any, source: str = "") -> Optional["ManagedTask"]:
        """Use skill mapping DSL (event_routing) to choose a target task.

        Strategy:
        - Normalize the incoming request to an `event` envelope.
        - Iterate agent tasks; for each task's skill, check mapping_rules.event_routing for this event type.
        - Evaluate `task_selector` against the task (supports: id:, name:, name_contains:).
        - Return the first matching ManagedTask. No global queues.
        """
        try:
            event = normalize_event(event_type, request, src=source)
            etype = event.get("type") or event_type
        except Exception:
            etype = event_type

        logger.debug("normalized event:", etype, event)

        # First, try task-specific routing based on each task's skill mapping_rules
        try:
            tasks_list = getattr(self.agent, "tasks", []) or []
            logger.info(f"[ROUTING] Agent {self.agent.card.name} has {len(tasks_list)} tasks: {[(t.name, t.id, id(t.queue) if hasattr(t, 'queue') else None) for t in tasks_list]}")
            for t in tasks_list:
                if not t or not getattr(t, "skill", None):
                    logger.warning(f"[ROUTING] Skipping task '{t.name if t else 'None'}' - task or skill is None. This may indicate the task was not properly initialized with a skill.")
                    continue
                skill = t.skill
                rules = getattr(skill, "mapping_rules", None)
                print("rules:", rules)
                if not isinstance(rules, dict):
                    print("rules not dict?")
                    continue
                # event_routing can be at top-level; also tolerate run_mode nesting
                event_routing = rules.get("event_routing")
                if not isinstance(event_routing, dict):
                    print("event_routing not dict0?", event_routing)
                    run_mode = getattr(skill, "run_mode", None)
                    if run_mode and isinstance(rules.get(run_mode), dict):
                        event_routing = rules.get(run_mode, {}).get("event_routing")
                if not isinstance(event_routing, dict):
                    print("event_routing not dict1?", event_routing)
                    continue

                rule = event_routing.get(etype)
                if not isinstance(rule, dict):
                    print("rule not dict?", rule)
                    continue

                selector = rule.get("task_selector") or ""
                sel_ok = False
                try:
                    print("selector:", selector)
                    if selector.startswith("id:"):
                        task_id_to_match = selector.split(":", 1)[1].strip()
                        sel_ok = (t.id or "").strip() == task_id_to_match
                    elif selector.startswith("name:"):
                        rhs = selector.split(":", 1)[1].strip().lower()
                        lhs_task = (t.name or "").strip().lower()
                        lhs_skill = (getattr(getattr(t, "skill", None), "name", "") or "").strip().lower()
                        sel_ok = (lhs_task == rhs) or (lhs_skill == rhs)
                    elif selector.startswith("name_contains:"):
                        name_norm = (t.name or "").lower()
                        needle = selector.split(":", 1)[1].strip().lower()
                        sel_ok = needle in name_norm
                    else:
                        # No selector or unknown format -> treat as match for this task
                        sel_ok = True
                except Exception as e:
                    logger.error(f"[ROUTING] Error evaluating selector '{selector}': {e}")
                    sel_ok = False

                if not sel_ok:
                    continue

                # Return the matching task; caller will use its queue
                logger.info(f"[ROUTING] Matched task: name={t.name}, id={t.id}, queue={id(t.queue) if hasattr(t, 'queue') else 'None'}")
                return t
        except Exception as e:
            err_msg = get_traceback(e, "ErrorResolveEventRouting")
            logger.error(err_msg)
            pass

        # No match
        return None


    def stop(self):
        """Signal all loops to exit and notify all running tasks' queues to shut down."""
        try:
            # Signal internal stop event
            self._stop_event.set()
            # Get agent name safely - handle both dict and AgentCard object
            agent_card = getattr(self.agent, 'card', None)
            if agent_card:
                if hasattr(agent_card, 'name'):
                    agent_name = agent_card.name
                elif isinstance(agent_card, dict):
                    agent_name = agent_card.get('name', 'unknown')
                else:
                    agent_name = 'unknown'
            else:
                agent_name = 'unknown'
            logger.info(f"[TaskRunner] Stop event set for agent {agent_name}")

            # Stop all ManagedTask instances and their scheduled tasks
            try:
                for task_id, managed_task in self.tasks.items():
                    try:
                        if managed_task:
                            # Cancel the task's cancellation event
                            managed_task.cancel()
                            # Exit the task (cancels any running asyncio tasks)
                            managed_task.exit()
                            logger.debug(f"[TaskRunner] Stopped managed task: {task_id}")
                    except Exception as e:
                        logger.debug(f"[TaskRunner] Error stopping managed task {task_id}: {e}")
                        pass
            except Exception as e:
                logger.debug(f"[TaskRunner] Error stopping managed tasks: {e}")
                pass

            # Notify each agent task's queue if the task is running
            try:
                for t in getattr(self.agent, "tasks", []) or []:
                    try:
                        if not t:
                            continue
                        # Check if task status indicates it is running
                        st = getattr(getattr(t, "status", None), "state", None)
                        if st in (TaskState.SUBMITTED, TaskState.WORKING):
                            q = getattr(t, "queue", None)
                            if q is not None:
                                try:
                                    q.put_nowait({"__shutdown__": True})
                                except Exception:
                                    # Fallback to blocking put in case of bounded queues
                                    try:
                                        q.put({"__shutdown__": True})
                                    except Exception:
                                        pass
                    except Exception:
                        # Continue best-effort shutdown across tasks
                        pass
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"[TaskRunner] Error in stop method: {e}")
            pass

    def close(self):
        self.stop()
        TaskRunnerRegistry.unregister(self)

    def assign_agent(self, agent):
        self.agent = agent

    async def create_task(self, skill, state: dict, session_id: Optional[str] = None, resume_from: Optional[str] = None, trigger: Optional[str] = None) -> str:
        task_id = str(uuid.uuid4())
        
        # Validate skill before creating task
        if skill is None:
            logger.error(f"[SKILL_MISSING] Attempting to create task with skill=None!")
            logger.error(f"[SKILL_MISSING] Agent: {self.agent.name if hasattr(self.agent, 'name') else 'UNKNOWN'}")
            raise ValueError("Cannot create task with None skill")
        
        logger.info(f"[TASK_CREATE] Creating task {task_id} with skill: {skill.name if hasattr(skill, 'name') else 'UNKNOWN'}")
        if not hasattr(skill, 'runnable') or skill.runnable is None:
            logger.warning(f"[SKILL_WARNING] Skill '{skill.name if hasattr(skill, 'name') else 'UNKNOWN'}' has runnable=None at task creation")
        
        task = ManagedTask(
            id=task_id,
            sessionId=session_id,
            skill=skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger=trigger
        )
        self.tasks[task_id] = task
        return task_id


    async def run_task(self, task_id):
        tbr_task = next((task for task in self.agent.tasks if task and task.id == task_id), None)
        if tbr_task:
            if tbr_task.status.state != TaskState.WORKING and tbr_task.status.state != TaskState.INPUT_REQUIRED :
                print("start to run task: ", tbr_task.status.state)
                await tbr_task.astream_run()
            else:
                print("WARNING: no running tasks....")


    async def run_all_tasks(self):
        """
        Run all tasks with proper cleanup and exception handling
        
        Improvements:
        1. Use return_exceptions=True to prevent single task failure from affecting others
        2. Log individual task results
        3. Ensure running_tasks list is always cleared
        4. Add timeout protection
        """
        self.running_tasks = []

        # Collect all awaitable tasks
        for t in self.agent.tasks:
            if t and callable(t.task):
                try:
                    coro = t.task()  # Try calling it with no arguments
                    if inspect.isawaitable(coro):
                        self.running_tasks.append(coro)
                    else:
                        logger.warning(f"Task returned non-awaitable: {coro}")
                except TypeError as e:
                    logger.error(f"Task {t.task} requires arguments: {e}")
            elif inspect.isawaitable(t.task):
                self.running_tasks.append(t.task)
            else:
                logger.warning(f"Task is not callable or awaitable: {t.task}")

        if not self.running_tasks:
            logger.warning("No running tasks")
            return
        
        logger.info(f"Running {len(self.running_tasks)} tasks")
        
        try:
            # Use return_exceptions=True to prevent single failure from affecting all
            results = await asyncio.gather(*self.running_tasks, return_exceptions=True)
            
            # Log individual task results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Task {i} failed with exception: {result}")
                else:
                    logger.debug(f"Task {i} completed successfully")
        
        except Exception as e:
            logger.error(f"run_all_tasks failed: {e}")
        
        finally:
            # Ensure cleanup of task references to prevent memory leaks
            self.running_tasks.clear()
            logger.debug("Cleared running_tasks list")


    async def step_task(self, task_id: str):
        task = self.tasks[task_id]
        task.status.state = TaskState.WORKING
        task.pause_event.set()

        async def one_step():
            async for step in task.graph.astream(task.state):
                task.metadata["state"] = step
                task.status.state = TaskState.UNKNOWN  # or custom paused state
                task.pause_event.clear()
                break

        task.task = asyncio.create_task(one_step())

    async def run_until_node(self, task_id: str, target_node: str):
        task = self.tasks[task_id]
        task.status.state = TaskState.WORKING

        async def runner():
            async for step in task.graph.astream(task.state):
                await task.pause_event.wait()
                task.state = step
                if step.get("current_node") == target_node:
                    task.status.state = TaskState.INPUT_REQUIRED  # or use a custom PAUSED-like state
                    task.pause_event.clear()
                    return
            task.status.state = TaskState.COMPLETED

        task.task = asyncio.create_task(runner())

    async def pause_task(self, task_id: str):
        task = self.tasks[task_id]
        task.pause_event.clear()
        task.status.state = TaskState.INPUT_REQUIRED

    async def resume_task(self, task_id: str):
        task = self.tasks[task_id]
        task.pause_event.set()
        task.status.state = TaskState.WORKING

    async def cancel_task(self, task_id: str, timeout: float = 5.0):
        """
        Cancel a task and clean up resources
        
        Args:
            task_id: Task ID to cancel
            timeout: Maximum time to wait for cancellation (seconds)
        
        Raises:
            KeyError: If task doesn't exist
        """
        # 1. Check if task exists
        if task_id not in self.tasks:
            logger.warning(f"Cannot cancel non-existent task: {task_id}")
            raise KeyError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        # 2. Check if task is in terminal state
        terminal_states = (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED)
        if task.status.state in terminal_states:
            logger.debug(f"Task {task_id} is already in terminal state: {task.status.state}")
            return  # Already finished, nothing to cancel
        
        try:
            # 3. Cancel the asyncio task if exists
            if task.task:
                logger.debug(f"Cancelling asyncio task for {task_id}")
                task.task.cancel()
                
                # 4. Wait for cancellation to complete
                try:
                    await asyncio.wait_for(task.task, timeout=timeout)
                except asyncio.CancelledError:
                    logger.debug(f"Task {task_id} cancelled successfully")
                except asyncio.TimeoutError:
                    logger.warning(f"Task {task_id} cancellation timed out after {timeout}s")
                except Exception as e:
                    logger.error(f"Error while cancelling task {task_id}: {e}")
            
            # 5. Update task status
            task.status.state = TaskState.CANCELED
            task.status.message = "Task cancelled by user"
            
            # 6. Call cleanup method if exists
            if hasattr(task, 'cleanup') and callable(task.cleanup):
                try:
                    task.cleanup()
                    logger.debug(f"Task {task_id} cleanup completed")
                except Exception as e:
                    logger.warning(f"Error during task cleanup for {task_id}: {e}")
            
            # 7. Call exit method if exists
            if hasattr(task, 'exit') and callable(task.exit):
                try:
                    task.exit()
                    logger.debug(f"Task {task_id} exit completed")
                except Exception as e:
                    logger.warning(f"Error during task exit for {task_id}: {e}")
            
            # 8. Clear task queue if exists
            if hasattr(task, 'queue') and task.queue:
                try:
                    cleared_count = 0
                    while not task.queue.empty():
                        try:
                            task.queue.get_nowait()
                            cleared_count += 1
                        except Empty:
                            break
                    if cleared_count > 0:
                        logger.debug(f"Cleared {cleared_count} items from task {task_id} queue")
                except Exception as e:
                    logger.warning(f"Error clearing task queue for {task_id}: {e}")
            
            logger.info(f"Task {task_id} cancelled and cleaned up successfully")
        
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            raise

    async def schedule_task(self, task_id: str, delay: int) -> asyncio.Task:
        """
        Schedule a task to run after a delay
        
        Args:
            task_id: Task ID to run
            delay: Delay in seconds
        
        Returns:
            asyncio.Task: The scheduled task (can be cancelled)
        
        Example:
             scheduled = await runner.schedule_task("my_task", 60)
             # To cancel:
             scheduled.cancel()
        """
        async def _delayed_run():
            try:
                logger.debug(f"Task {task_id} scheduled to run in {delay}s")
                
                # Use interruptible sleep
                await asyncio.sleep(delay)
                
                # Check if task still exists
                if task_id not in self.tasks:
                    logger.warning(f"Scheduled task {task_id} no longer exists")
                    return
                
                task = self.tasks[task_id]
                
                # Check if task was cancelled during delay
                if task.status.state == TaskState.CANCELED:
                    logger.debug(f"Scheduled task {task_id} was cancelled")
                    return
                
                # Run the task
                logger.info(f"Running scheduled task {task_id}")
                try:
                    await self.run_task(task_id)
                except Exception as e:
                    logger.error(f"Error running scheduled task {task_id}: {e}")
                    # Update task status to failed
                    if task_id in self.tasks:
                        self.tasks[task_id].status.state = TaskState.FAILED
                        self.tasks[task_id].status.message = str(e)
            
            except asyncio.CancelledError:
                logger.info(f"Scheduled task {task_id} was cancelled during delay")
                raise  # Re-raise to properly mark as cancelled
            
            except Exception as e:
                logger.error(f"Unexpected error in scheduled task {task_id}: {e}")
        
        # Create and return the scheduled task
        scheduled = asyncio.create_task(_delayed_run())
        return scheduled

    def save_task(self, task_id: str):
        """
        Save task to disk with atomic write operation
        
        Args:
            task_id: Task ID to save
        
        Raises:
            KeyError: If task_id doesn't exist
            IOError: If file operation fails
        """
        # 1. Check if task exists
        if task_id not in self.tasks:
            logger.error(f"Cannot save non-existent task: {task_id}")
            raise KeyError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        # 2. Ensure directory exists
        save_dir = Path(self.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        target_file = save_dir / f"{task_id}.json"
        temp_file = None
        
        try:
            # 3. Write to temporary file first (atomic operation)
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=save_dir,
                prefix=f"{task_id}_",
                suffix=".json.tmp",
                delete=False,
                encoding='utf-8'
            ) as f:
                temp_file = f.name
                json_data = task.model_dump_json(indent=2)
                f.write(json_data)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk
            
            # 4. Atomic rename (either succeeds or fails, no partial write)
            shutil.move(temp_file, target_file)
            
            logger.debug(f"Task {task_id} saved successfully to {target_file}")
        
        except OSError as e:
            logger.error(f"Failed to save task {task_id}: {e}")
            # Clean up temporary file if exists
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            raise IOError(f"Failed to save task {task_id}: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error saving task {task_id}: {e}")
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            raise

    def load_task(self, task_id: str, skill: 'EC_Skill') -> ManagedTask:
        """
        Load task from disk with proper error handling
        
        Args:
            task_id: Task ID to load
            skill: EC_Skill instance to associate with task
        
        Returns:
            ManagedTask: The loaded task
        
        Raises:
            FileNotFoundError: If task file doesn't exist
            ValueError: If JSON is invalid or file is empty
            IOError: If file read operation fails
        """
        from pydantic import TypeAdapter
        
        file_path = Path(self.save_dir) / f"{task_id}.json"
        
        # 1. Check if file exists
        if not file_path.exists():
            logger.error(f"Task file not found: {file_path}")
            raise FileNotFoundError(f"Task file not found for task_id: {task_id}")
        
        try:
            # 2. Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                raw = f.read()
            
            # 3. Validate content is not empty
            if not raw or not raw.strip():
                logger.error(f"Task file is empty: {file_path}")
                raise ValueError(f"Task file is empty for task_id: {task_id}")
            
            # 4. Parse JSON
            try:
                base_task = TypeAdapter(Task).validate_json(raw)
            except Exception as e:
                logger.error(f"Invalid JSON in task file {file_path}: {e}")
                raise ValueError(f"Invalid JSON in task file for task_id {task_id}: {e}")
            
            # 5. Create ManagedTask
            task = ManagedTask(**base_task.model_dump(), skill=skill)
            
            # 6. Register task
            self.tasks[task_id] = task
            
            logger.debug(f"Task {task_id} loaded successfully from {file_path}")
            return task
        
        except (FileNotFoundError, ValueError):
            raise  # Re-raise known errors
        
        except Exception as e:
            logger.error(f"Failed to load task {task_id}: {e}")
            raise IOError(f"Failed to load task {task_id}: {e}")

    async def resume_on_external_event(self, task_id: str, injected_state: dict):
        task = self.tasks[task_id]
        if task.status.message:
            task.status.message.parts.append(Part(type="text", text=str(injected_state)))
        await self.resume_task(task_id)

    def sendChatMessageToGUI(self, sender_agent, chatId, msg):
        logger.debug("sendChatMessageToGUI::", msg)

        message_text = ""
        if isinstance(msg, dict):
            message_text = msg.get('llm_result', str(msg))
        elif isinstance(msg, str):
            message_text = msg
        else:
            message_text = str(msg)

        target_chat_id = chatId[0] if isinstance(chatId, list) else chatId

        try:
            mid = str(uuid.uuid4())
            msg_data = {
                "role": 'agent',
                "id": mid,
                "senderId": sender_agent.card.id,
                "senderName": sender_agent.card.name,
                "createAt": int(time.time() * 1000),
                "content": {"type": "text", "text": message_text},
                "status": "sent"
            }

            mainwin = AppContext.get_main_window()
            mainwin.db_chat_service.push_message_to_chat(target_chat_id, msg_data)

        except Exception as e:
            ex_stat = "ErrorSendChat2GUI:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")

    def sendChatFormToGUI(self, sender_agent, chatId, chatData):
        logger.debug("sendChatFormToGUI::", chatData)
        target_chat_id = chatId[0] if isinstance(chatId, list) else chatId
        try:
            mid = str(uuid.uuid4())
            msg_data = {
                "role": 'agent',
                "id": mid,
                "senderId": sender_agent.card.id,
                "senderName": sender_agent.card.name,
                "createAt": int(time.time() * 1000),
                "content": {"type": "form", "form": chatData},
                "status": "sent"
            }
            mainwin = AppContext.get_main_window()
            mainwin.db_chat_service.push_message_to_chat(target_chat_id, msg_data)
        except Exception as e:
            ex_stat = "ErrorSendChat2GUI:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")

    def sendChatNotificationToGUI(self, sender_agent, chatId, chatData):
        logger.debug("sendChatNotificationToGUI::", chatData)
        target_chat_id = chatId[0] if isinstance(chatId, list) else chatId
        try:
            mid = str(uuid.uuid4())
            msg_data = {
                "role": 'agent',
                "id": mid,
                "senderId": sender_agent.card.id,
                "senderName": sender_agent.card.name,
                "createAt": int(time.time() * 1000),
                "content": {"type": "notification", "notification": chatData},
                "status": "sent"
            }
            mainwin = AppContext.get_main_window()
            mainwin.db_chat_service.push_notification_to_chat(target_chat_id, msg_data)
        except Exception as e:
            ex_stat = "ErrorSendChat2GUI:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")


    def find_chatter_tasks(self):
        # for now, for the simplicity just find the task that's not scheduled.
        found = [task for task in self.agent.tasks if 'chatter' in task.name.lower()]
        if found:
            logger.debug(f"[find_chatter_tasks] Found task: id={found[0].id}, queue={id(found[0].queue) if hasattr(found[0], 'queue') else 'None'}")
            return found[0]
        else:
            logger.error("NO chatter tasks found!")
            return None

    def find_suitable_tasks(self, msg):
        # for now, for the simplicity just find the task that's not scheduled.
        found = []
        msg_js = json.loads(msg["message"])         # need , encoding='utf-8'?
        if msg_js['metadata']["mtype"] == "send_task":
            name_filter = (((msg_js.get('metadata') or {}).get('task') or {}).get('name') or '')
            found = [task for task in self.agent.tasks if name_filter.lower() in (task.name or "").lower()]
        elif msg_js['metadata']["mtype"] == "send_chat":
            found = [task for task in self.agent.tasks if "chatter task" in (task.name or "").lower()]
        return found

    def _extract_text_from_message(self, message) -> str:
        """Extract concatenated text from a Message object's parts list.
        Falls back gracefully if structure differs.
        """
        try:
            parts = getattr(message, "parts", None)
            if not parts and isinstance(message, dict):
                parts = message.get("parts")
            if not parts:
                # maybe plain text
                return getattr(message, "text", "") if hasattr(message, "text") else (message or "")
            texts = []
            for p in parts:
                ptype = getattr(p, "type", None) or (p.get("type") if isinstance(p, dict) else None)
                if ptype == "text":
                    txt = getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else None)
                    if txt:
                        texts.append(txt)
            return "\n".join(texts)
        except Exception:
            return ""

    def _build_resume_payload(self, task, msg) -> Tuple[Dict[str, Any], Any]:
        """Build a resume payload from incoming chat/task message.
        Uses general-purpose mapping when RESUME_PAYLOAD_V2 is enabled; otherwise falls back to legacy behavior.
        """
        # Feature-flagged path
        try:
            use_v2 = os.getenv("RESUME_PAYLOAD_V2", "true").lower() in ("1", "true", "yes", "on")
            if use_v2:
                resume_payload, resume_cp, state_patch = build_general_resume_payload(task, msg)
                # Merge state_patch into task.metadata["state"] non-invasively
                try:
                    if isinstance(state_patch, dict) and state_patch:
                        cur_state = task.metadata.get("state") if isinstance(task.metadata, dict) else None
                        if isinstance(cur_state, dict):
                            # deep merge state_patch into cur_state
                            def _deep_merge(a, b):
                                out = dict(a)
                                for k, v in b.items():
                                    if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                                        out[k] = _deep_merge(out[k], v)
                                    else:
                                        out[k] = v
                                return out
                            logger.debug("state before deep merge===>", cur_state)
                            logger.debug("patch before deep merge===>", state_patch)

                            # Preserve append semantics for list-like fields before deep-merge
                            try:
                                sp = dict(state_patch) if isinstance(state_patch, dict) else {}
                                cur = dict(cur_state) if isinstance(cur_state, dict) else {}
                                if "messages" in sp:
                                    sp_msgs = sp.pop("messages")
                                    if isinstance(sp_msgs, list):
                                        if isinstance(cur.get("messages"), list):
                                            cur_msgs = list(cur["messages"]) + list(sp_msgs)
                                        else:
                                            cur_msgs = list(sp_msgs)
                                    else:
                                        if isinstance(cur.get("messages"), list):
                                            cur_msgs = list(cur["messages"]) + [sp_msgs]
                                        else:
                                            cur_msgs = [sp_msgs]
                                    cur["messages"] = cur_msgs
                                    cur_state = cur
                                    state_patch = sp
                            except Exception:
                                pass

                            merged = _deep_merge(cur_state, state_patch)
                            logger.debug("state after deep merge===>", merged)
                            state_patch["messages"] = merged["messages"]
                            
                            # CRITICAL FIX: Sync chatId from attributes.params to messages[1]
                            # When a chat is deleted and recreated, the chatId in attributes.params gets updated,
                            # but messages[1] still holds the old chatId. This causes "chat not found" errors.
                            try:
                                # Try to get chatId from multiple locations
                                new_chat_id = _safe_get(merged, "attributes.params.chatId")
                                
                                # If not found, try attributes.params.metadata.params.chatId (for TaskSendParams)
                                if not new_chat_id:
                                    params = merged.get("attributes", {}).get("params")
                                    if hasattr(params, 'metadata') and isinstance(params.metadata, dict):
                                        metadata_params = params.metadata.get("params", {})
                                        if isinstance(metadata_params, dict):
                                            new_chat_id = metadata_params.get("chatId")
                                
                                if new_chat_id and isinstance(merged.get("messages"), list) and len(merged["messages"]) > 1:
                                    old_chat_id = merged["messages"][1]
                                    if old_chat_id != new_chat_id:
                                        logger.info(f"[_build_resume_payload] Syncing chatId in messages[1]: {old_chat_id} -> {new_chat_id}")
                                        merged["messages"][1] = new_chat_id
                                        state_patch["messages"] = merged["messages"]
                                        logger.info(f"[_build_resume_payload] Updated messages[1] to {new_chat_id}, will update checkpoint")
                            except Exception as e:
                                logger.error(f"[_build_resume_payload] Failed to sync chatId: {e}", exc_info=True)
                            
                            # this is really useless as langgraph resume will not be taking this state.....
                            task.metadata["state"] = merged
                            # Safely update checkpoint values without relying on specific LangGraph versions
                            try:
                                updated = False
                                if hasattr(resume_cp, "values"):
                                    vals = getattr(resume_cp, "values")
                                    if isinstance(vals, dict):
                                        try:
                                            vals.clear()
                                            vals.update(merged)
                                            updated = True
                                        except Exception:
                                            updated = False
                                elif isinstance(resume_cp, dict):
                                    resume_cp["values"] = merged
                                    updated = True

                                if not updated:
                                    # Try reconstructing a new checkpoint object if supported
                                    try:
                                        from langgraph.checkpoint.base import StateSnapshot  # type: ignore
                                        try:
                                            dumped = resume_cp.model_dump(mode="python")  # pydantic v2
                                        except Exception:
                                            try:
                                                dumped = resume_cp.dict()  # pydantic v1
                                            except Exception:
                                                dumped = {}
                                        if isinstance(dumped, dict):
                                            dumped["values"] = merged
                                            resume_cp = StateSnapshot(**dumped)
                                            updated = True
                                    except Exception as _ie:
                                        logger.debug(f"_build_resume_payload: cannot reconstruct StateSnapshot: {_ie}")

                                if not updated:
                                    logger.debug("_build_resume_payload: checkpoint values not updated due to unexpected type/immutability")
                            except Exception as _e:
                                logger.debug(f"_build_resume_payload: failed to set merged values on checkpoint: {_e}")

                            logger.debug("_build_resume_payload resume cp===>", resume_cp)
                    # Always include state_patch in resume payload so nodes can merge it on resume
                    try:
                        if isinstance(resume_payload, dict) and isinstance(state_patch, dict):
                            resume_payload["_state_patch"] = state_patch
                    except Exception:
                        pass
                except Exception as e:
                    err_msg = get_traceback(e, "ErrorBuildResumePayloadV2")
                    logger.debug(f"_build_resume_payload v2 state merge error: {err_msg}")
                return resume_payload, resume_cp
        except Exception as e:
            err_msg = get_traceback(e, "ErrorBuildResumePayloadV2")
            logger.debug(f"_build_resume_payload v2 failed, falling back to legacy: {err_msg}")

        # Legacy behavior (current implementation)
        try:
            if hasattr(msg, "params"):
                message = getattr(msg.params, "message", None)
                metadata = getattr(msg.params, "metadata", {}) or {}
            elif isinstance(msg, dict):
                message = msg.get("params", {}).get("message") or msg.get("message")
                metadata = msg.get("params", {}).get("metadata", {}) or msg.get("metadata", {}) or {}
            else:
                message, metadata = None, {}
            human_text = self._extract_text_from_message(message) if message else ""
            qa_form = metadata.get("qa_form_to_agent") or metadata.get("qa_form") or {}
            notification = metadata.get("notification_to_agent") or metadata.get("notification") or {}
            payload = {
                "human_text": human_text,
                "qa_form_to_agent": qa_form,
                "notification_to_agent": notification,
            }

            pending_tag = metadata.get("i_tag")

            # get all the checkpoint so that we can resume from.
            found_cp = next((cpn for cpn in task.checkpoint_nodes if cpn["tag"] == pending_tag), None)
            if found_cp:
                idx = task.checkpoint_nodes.index(found_cp)
                be_to_resumed = task.checkpoint_nodes.pop(idx)
                resume_cp = be_to_resumed["checkpoint"]
                print("resume checkpoint is: ", resume_cp)
                # Ensure the node can detect resume by injecting cloud_task_id into checkpoint state
                try:
                    # StateSnapshot typically has a .values dict-like payload
                    vals = getattr(resume_cp, "values", None)
                    if isinstance(vals, dict):
                        attrs = vals.get("attributes")
                        if not isinstance(attrs, dict):
                            attrs = {}
                            vals["attributes"] = attrs
                        if pending_tag:
                            attrs["cloud_task_id"] = pending_tag
                            # Also reflect this in our cached metadata state if present
                            st = self.metadata.get("state") if hasattr(self, "metadata") else None
                            if isinstance(st, dict):
                                st_attrs = st.get("attributes")
                                if isinstance(st_attrs, dict):
                                    st_attrs["cloud_task_id"] = pending_tag
                    else:
                        # If values isn't a dict, log but continue
                        logger.debug("_build_resume_payload: unexpected checkpoint values type; skip cloud_task_id injection")
                except Exception as e:
                    logger.debug(f"_build_resume_payload: could not inject cloud_task_id into checkpoint: {e}")
            else:
                resume_cp = None

            return payload, resume_cp
        except Exception:
            return {"human_text": ""}, None

    def sync_task_wait_in_line(self, event_type, request, source: str = ""):
        try:
            logger.debug("sync task waiting in line.....", event_type, self.agent.card.name, request)
            # Prefer mapping-DSL-based event routing to a specific task's queue
            target_task = self._resolve_event_routing(event_type, request, source)
            if target_task:
                if not hasattr(target_task, "queue") or target_task.queue is None:
                    logger.error(f"[QUEUE] Target task found but has no queue: task={target_task.name} ({target_task.id})")
                    return
                try:
                    queue_size_before = target_task.queue.qsize()
                    target_task.queue.put_nowait(request)
                    queue_size_after = target_task.queue.qsize()
                    logger.info(
                        f"[QUEUE] Message queued for task={target_task.name} ({target_task.id}), "
                        f"task_obj_id={id(target_task)}, queue_id={id(target_task.queue)}, "
                        f"queue_size: {queue_size_before} -> {queue_size_after}"
                    )
                    return
                except Exception as e:
                    logger.error(f"[QUEUE] Failed to enqueue on task queue: {e}")
            # No routing match
            logger.error(f"[QUEUE] No target task found for event type: {event_type}, target_task={target_task}")
        except Exception as e:
            ex_stat = "ErrorWaitInLine:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")


    def launch_unified_run(self, task2run=None, trigger_type="queue", *, dev_init_state=None, dev_single_run: bool = False):
        """
        Unified task execution loop supporting all trigger types.
        
        Args:
            task2run: ManagedTask to execute (None for scheduled tasks)
            trigger_type: "schedule" | "a2a_queue" | "chat_queue"
        
        Improvements:
        1. Use local variables to avoid state corruption
        2. Use interruptible waits instead of time.sleep
        3. Add error recovery with backoff
        4. Proper state management in finally block
        """
        # CRITICAL: Log IMMEDIATELY at function entry
        logger.info(f"[WORKER_THREAD] *** FUNCTION ENTRY *** agent={self.agent.card.name}, trigger_type={trigger_type}")
        if trigger_type == "dev":
            logger.info(f"[DEV] launch_unified_run started in DEV MODE: single_run={dev_single_run}, has_init_state={isinstance(dev_init_state, dict)}")
            # Local dev-exit flag scoped to this invocation
            try:
                self._dev_exit_requested = False
            except Exception:
                pass
        
        justStarted = True
        consecutive_errors = 0
        max_consecutive_errors = 10
        current_task = task2run  # Use local variable instead of modifying parameter
        logger.info(f"[WORKER_THREAD] launch_unified_run started: trigger_type={trigger_type}, agent={self.agent.card.name}, task={current_task.name if current_task else 'None'}, task_id={current_task.id if current_task else 'None'}, task_obj_id={id(current_task) if current_task else 'None'}, queue={id(current_task.queue) if current_task and hasattr(current_task, 'queue') else 'None'}")
        
        loop_count = 0
        while not self._stop_event.is_set():
            # print("in task main loop......0")
            loop_count += 1
            msg = None  # Reset message for each iteration
            message_taken_from_queue = False  # Track if we actually consumed a queue item
            # High-frequency tick for My Twin Agent only to verify loop progress and queue binding
            try:
                if "Twin" in self.agent.card.name:
                    logger.trace(
                        f"[WORKER_THREAD][Twin] Loop tick: trigger={trigger_type}, loop={loop_count}, "
                        f"task_id={getattr(current_task, 'id', None)}, task_obj_id={id(current_task)}, qid={id(current_task.queue) if current_task and hasattr(current_task,'queue') else None}"
                    )
            except Exception:
                pass
            
            # Log FIRST iteration for My Twin Agent to confirm loop is running
            if loop_count == 1 and "Twin" in self.agent.card.name:
                logger.info(f"[WORKER_THREAD] FIRST ITERATION: trigger_type={trigger_type}, agent={self.agent.card.name}")
            
            # Log every 10 iterations to show thread is alive
            # if loop_count % 10 == 0:
            #     logger.debug(f"[WORKER_THREAD] Still alive: trigger_type={trigger_type}, agent={self.agent.card.name}, loop_count={loop_count}")
            # print("in task main loop......1")
            try:
                # Log entry into try block for My Twin Agent
                if loop_count == 1 and "Twin" in self.agent.card.name:
                    logger.info(f"[WORKER_THREAD] Entered try block, trigger_type={trigger_type}")
                
                # 1. Get task and message based on trigger type
                if trigger_type == "schedule":
                    # Scheduled tasks: check if it's time to run
                    logger.trace(f"Checking schedule for agent {self.agent.card.name}")
                    current_task = time_to_run(self.agent)  # Use local variable
                    if not current_task:
                        if self._stop_event.wait(timeout=1.0):
                            break
                        continue
                    logger.debug(f"Scheduled task ready: {current_task.name}")
                    msg = None  # Scheduled tasks don't have input messages
                    
                elif trigger_type in ("a2a_queue", "chat_queue", "message", "dev"):
                    # print("in task main loop......2")
                    # Queue-based tasks: wait for messages
                    if not current_task:
                        logger.warning(f"[WORKER_THREAD] No current_task for trigger_type={trigger_type}")
                        if self._stop_event.wait(timeout=1.0):
                            break
                        continue
                    
                    # Prefer blocking get with short timeout to minimize latency and avoid empty() races
                    if loop_count % 30 == 0:
                        logger.trace(f"[WORKER_THREAD] Checking queue for task_id={current_task.id}, queue={id(current_task.queue)}")

                    # Twin-specific: log right before blocking queue.get
                    if "Twin" in self.agent.card.name:
                        try:
                            qsz = current_task.queue.qsize()
                            logger.trace(
                                f"[WORKER_THREAD][Twin] About to queue.get(timeout=0.5) for task_id={getattr(current_task,'id', None)}, qid={id(current_task.queue)}, qsize_before={qsz}"
                            )
                        except Exception:
                            pass
                    # print("in task main loop......3")
                    # DEV MODE: kick off initial run immediately without waiting for queue
                    dev_initial_kickoff = False
                    if trigger_type == "dev":
                        try:
                            # Initialize task state structure if missing
                            if current_task.id not in self._task_states:
                                self._task_states[current_task.id] = {'justStarted': True}
                            is_initial_run_probe = self._task_states[current_task.id].get('justStarted', True)
                        except Exception:
                            is_initial_run_probe = True
                        if is_initial_run_probe:
                            dev_initial_kickoff = True
                            msg = {"__dev_kickoff__": True}
                            logger.info("[DEV] Initial dev run: bypassing queue wait and executing immediately")

                    try:
                        if not dev_initial_kickoff:
                            msg = current_task.queue.get(timeout=0.5 if trigger_type != "dev" else DEV_EVENT_POLL_INTERVAL_SEC)
                            message_taken_from_queue = True
                            logger.info(f"[WORKER_THREAD] Queue NOT empty! Processing message for task={current_task.name}")
                            logger.info(f"[WORKER_THREAD] {trigger_type} message received: {type(msg)} | {msg}")
                        # Handle shutdown sentinel early for dev mode
                        if trigger_type == "dev" and isinstance(msg, dict) and msg.get("__shutdown__"):
                            logger.info("[DEV] Received shutdown signal on queue; exiting dev run.")
                            try:
                                # Store a result and request exit
                                if current_task and current_task.id in getattr(self, "_task_states", {}):
                                    self._task_states[current_task.id]['last_response'] = {"success": False, "error": "Shutdown"}
                                self._dev_exit_requested = True
                            except Exception:
                                pass
                            break

                        # For chat queue, find the appropriate chatter task
                        if trigger_type == "chat_queue":
                            logger.debug(f"[WORKER_THREAD] Finding chatter task for agent={self.agent.card.name}")
                            chatter_task = self.find_chatter_tasks()  # Use local variable
                            if not chatter_task:
                                logger.error(f"[WORKER_THREAD] No chatter task found for agent={self.agent.card.name}")
                            else:
                                logger.info(f"[WORKER_THREAD] Found chatter task: {chatter_task.name}")
                                current_task = chatter_task
                            if not current_task:
                                logger.error("[WORKER_THREAD] No chatter task found (final check)")
                                # Mark queue task as done even if no task found
                                if task2run and task2run.queue:
                                    try:
                                        task2run.queue.task_done()
                                    except:
                                        pass
                                continue
                        elif trigger_type == "a2a_queue":
                                logger.debug(f"[WORKER_THREAD] a2a queued message")

                    except Empty:
                        # No message this cycle; allow cooperative stop and continue quickly
                        if "Twin" in self.agent.card.name:
                            try:
                                qsz_now = current_task.queue.qsize()
                                logger.trace(f"[WORKER_THREAD][Twin] queue.get timeout (no message), loop={loop_count}, qid={id(current_task.queue)}, qsize_now={qsz_now}")
                            except Exception:
                                pass
                        # Enforce pending timeout logic
                        try:
                            # print("in task main loop......4")
                            state = self._task_states.get(current_task.id, {})
                            pending_since = state.get('pending_since')
                            # print("in task main loop......5", pending_since)
                            if pending_since:
                                if trigger_type == "dev":
                                    if (time.time() - pending_since) > DEV_EVENT_TIMEOUT_SEC:
                                        msg = f"[DEV] Timed out waiting for event after {DEV_EVENT_TIMEOUT_SEC}s for task_id={current_task.id}."
                                        logger.error(msg)
                                        ipc.send_skill_editor_log("error", msg)
                                        try:
                                            current_task.status.state = TaskState.FAILED
                                        except Exception:
                                            pass
                                        try:
                                            state['last_response'] = {"success": False, "error": "TimeoutWaitingForEvent"}
                                        except Exception:
                                            pass
                                        try:
                                            self._dev_exit_requested = True
                                        except Exception:
                                            pass
                                else:
                                    if (time.time() - pending_since) > RUN_EVENT_TIMEOUT_SEC:
                                        logger.error(f"[RUN] Timed out waiting for event after {RUN_EVENT_TIMEOUT_SEC}s for task_id={current_task.id}. Marking failed and resetting.")
                                        try:
                                            current_task.status.state = TaskState.FAILED
                                        except Exception:
                                            pass
                                        try:
                                            state['justStarted'] = True
                                            state['pending_since'] = None
                                        except Exception:
                                            pass
                        except Exception:
                            print("in task main loop......6 pass")
                            pass
                        if self._stop_event.wait(timeout=0.5):
                            print("in task main loop......6 break")
                            break
                        continue
                else:
                    logger.error(f"Unknown trigger_type: {trigger_type}")
                    if self._stop_event.wait(timeout=1.0):
                        break
                    continue
                print("in task main loop......7")
                # Validate task exists before proceeding
                if not current_task:
                    logger.warning(f"No valid task for trigger_type={trigger_type}")
                    continue
                
                # Add comprehensive task and skill validation
                logger.info(f"[TASK_VALIDATE] Task ID: {current_task.id}, Task name: {current_task.name}")
                if current_task.skill is None:
                    logger.error(f"[SKILL_MISSING] Task {current_task.id} ({current_task.name}) has skill=None!")
                    logger.error(f"[SKILL_MISSING] Agent: {self.agent.name if hasattr(self.agent, 'name') else 'UNKNOWN'}")
                    logger.error(f"[SKILL_MISSING] Agent skills count: {len(self.agent.skills) if hasattr(self.agent, 'skills') else 'N/A'}")
                    if hasattr(self.agent, 'skills'):
                        logger.error(f"[SKILL_MISSING] Available skills: {[s.name if hasattr(s, 'name') else str(s) for s in self.agent.skills]}")
                    continue
                
                logger.info(f"[SKILL_CHECK] Task {current_task.id} has skill: {current_task.skill.name if hasattr(current_task.skill, 'name') else 'UNKNOWN'}")
                if not hasattr(current_task.skill, 'runnable') or current_task.skill.runnable is None:
                    logger.error(f"[SKILL_MISSING] Skill '{current_task.skill.name}' has runnable=None!")
                    logger.error(f"[SKILL_MISSING] Skill type: {type(current_task.skill)}")
                    continue
                
                # 2. Execute task NON-BLOCKING (submit to executor)
                # Extract task_id for waiter resolution
                waiter_task_id = None
                try:
                    if msg and hasattr(msg, 'params') and hasattr(msg.params, 'id'):
                        waiter_task_id = msg.params.id
                    elif msg and isinstance(msg, dict):
                        attrs = msg.get('attributes')
                        if isinstance(attrs, dict) and attrs.get('params'):
                            params = attrs['params']
                            waiter_task_id = params.id if hasattr(params, 'id') else params.get('id')
                        if not waiter_task_id:
                            waiter_task_id = msg.get('params', {}).get('id') or msg.get('id')
                except Exception as e:
                    logger.error(f"Failed to extract waiter_task_id: {e}")
                
                logger.info(f"[NON_BLOCKING] Submitting skill execution to executor for task_id={waiter_task_id}")
                
                # Initialize task state if not present
                if current_task.id not in self._task_states:
                    self._task_states[current_task.id] = {'justStarted': True}
                
                # Capture state for this specific message execution
                is_initial_run = self._task_states[current_task.id]['justStarted']
                pending_since = self._task_states[current_task.id].get('pending_since')
                logger.debug(f"[WORKER_THREAD] is_initial_run={is_initial_run}, pending_since={pending_since}, trigger_type={trigger_type}")
                
                # Submit skill execution to background thread
                def _execute_skill():
                    try:
                        t_skill_start = time.time()
                        if trigger_type == "dev":
                            if is_initial_run:
                                logger.info(f"[DEV][EXECUTOR] Initial dev run for task={current_task.name} ({current_task.id}). Seeding init_state: {isinstance(dev_init_state, dict)}")
                                prepared_state = None
                                # Prepare baseline state via prep_skills_run to mirror normal runs
                                try:
                                    t_prep = time.time()
                                    prep_msg = msg if msg not in (None, {"__dev_kickoff__": True}) else None
                                    prepared_state = prep_skills_run(
                                        current_task.skill,
                                        self.agent,
                                        current_task.id,
                                        prep_msg,
                                        None
                                    )
                                    logger.debug(f"[DEV][PERF] prep_skills_run: {time.time()-t_prep:.3f}s  prepared_state: {prepared_state}")
                                except Exception as prep_err:
                                    logger.error(f"[DEV][EXECUTOR] prep_skills_run failed: {prep_err}")
                                    logger.error(traceback.format_exc())

                                def _merge_dev_state(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
                                    try:
                                        merged = dict(base or {})
                                        for k, v in (override or {}).items():
                                            existing = merged.get(k)
                                            if isinstance(existing, dict) and isinstance(v, dict):
                                                merged[k] = _merge_dev_state(existing, v)
                                            elif isinstance(existing, (list, tuple)):
                                                if isinstance(v, (list, tuple)) and any(v):
                                                    merged[k] = type(existing)(v)
                                                elif not existing and v:
                                                    merged[k] = v
                                                else:
                                                    merged[k] = existing
                                            elif isinstance(v, (list, tuple)):
                                                if v or existing is None:
                                                    merged[k] = v
                                            else:
                                                if v not in (None, "", [], {}):
                                                    merged[k] = v
                                                elif existing is None:
                                                    merged[k] = v
                                        return merged
                                    except Exception:
                                        return override or base or {}

                                final_state: Dict[str, Any] = {}
                                if isinstance(prepared_state, dict):
                                    final_state = prepared_state
                                if isinstance(dev_init_state, dict):
                                    final_state = _merge_dev_state(final_state, dev_init_state)
                                if not final_state:
                                    # Fallback to provided init state or existing metadata state
                                    if isinstance(dev_init_state, dict):
                                        final_state = dev_init_state
                                    else:
                                        final_state = current_task.metadata.get("state") or {}

                                try:
                                    current_task.metadata["state"] = final_state
                                except Exception:
                                    pass
                                t_run = time.time()
                                logger.debug(f"[DEV][EXECUTOR] final initial state to start the workflow run: {final_state}")
                                response = current_task.stream_run(final_state)
                                logger.info(f"[DEV][PERF] initial stream_run: {time.time()-t_run:.3f}s (TOTAL {time.time()-t_skill_start:.3f}s)")
                                logger.debug(f"[DEV][EXECUTOR] Initial run response: {response}")
                                return response, True
                            else:
                                logger.info(f"[DEV][EXECUTOR] Resume dev run for task={current_task.name} ({current_task.id})")
                                t_resume = time.time()
                                resume_payload, cp = self._build_resume_payload(current_task, msg)
                                logger.debug(f"[DEV][PERF] build_resume_payload: {time.time()-t_resume:.3f}s")
                                logger.debug(f"[DEV][EXECUTOR] Resume payload: {resume_payload}")
                                t_run = time.time()
                                if cp:
                                    response = current_task.stream_run(Command(resume=resume_payload), checkpoint=cp)
                                else:
                                    response = current_task.stream_run(Command(resume=resume_payload))
                                logger.info(f"[DEV][PERF] resume stream_run: {time.time()-t_run:.3f}s (TOTAL {time.time()-t_skill_start:.3f}s)")
                                logger.debug(f"[DEV][EXECUTOR] Resume run response: {response}")
                                return response, False
                        else:
                            if is_initial_run:
                                # Initial run (normal mode)
                                logger.debug(f"[EXECUTOR] Initial run: {current_task.skill.name}")
                                t_prep = time.time()
                                current_task.metadata["state"] = prep_skills_run(
                                    current_task.skill,
                                    self.agent,
                                    current_task.id,
                                    msg,
                                    None
                                )
                                logger.debug(f"[PERF] _execute_skill - prep_skills_run: {time.time()-t_prep:.3f}s")
                                t_run = time.time()
                                response = current_task.stream_run()
                                logger.debug(f"[PERF] _execute_skill - initial stream_run: {time.time()-t_run:.3f}s")
                                logger.debug(f"[PERF] _execute_skill - TOTAL: {time.time()-t_skill_start:.3f}s")
                                logger.debug(f"[EXECUTOR] Initial run response: {response}")
                                return response, True
                            else:
                                # Resume run (normal mode)
                                logger.debug(f"[EXECUTOR] Resume run: {current_task.skill.name}")
                                t_resume = time.time()
                                resume_payload, cp = self._build_resume_payload(current_task, msg)
                                logger.debug(f"[PERF] _execute_skill - build_resume_payload: {time.time()-t_resume:.3f}s")
                                logger.debug(f"[EXECUTOR] Resume payload: {resume_payload}")
                                t_run = time.time()
                                if cp:
                                    response = current_task.stream_run(Command(resume=resume_payload), checkpoint=cp, stream_mode="updates")
                                else:
                                    response = current_task.stream_run(Command(resume=resume_payload), stream_mode="updates")
                                logger.debug(f"[PERF] _execute_skill - resume stream_run: {time.time()-t_run:.3f}s")
                                logger.debug(f"[PERF] _execute_skill - TOTAL: {time.time()-t_skill_start:.3f}s")
                                logger.debug(f"[EXECUTOR] Resume run response: {response}")
                                return response, False
                    except Exception as e:
                        logger.error(f"[EXECUTOR] Skill execution failed: {e}")
                        logger.error(traceback.format_exc())
                        return None, True
                
                # Callback when skill execution completes
                def _on_skill_complete(future):
                    try:
                        t_callback_start = time.time()
                        response, task_completed = future.result()
                        logger.info(f"[NON_BLOCKING] Skill execution completed for waiter_task_id={waiter_task_id}")
                        
                        # Handle response and interrupts
                        task_interrupted = False
                        if response:
                            step = response.get('step') or {}
                            logger.debug(f"[EXECUTOR] Current Step: {step}")
                            current_state = response.get('cp')
                            
                            if isinstance(step, dict) and '__interrupt__' in step:
                                task_interrupted = True
                                interrupt_obj = step["__interrupt__"][0]
                                if "prompt_to_human" in interrupt_obj.value or "prompt_to_agent" in interrupt_obj.value:
                                    try:
                                        chatId = current_state.values.get("messages")[1]
                                    except Exception:
                                        chatId = ""
                                    if chatId:
                                        send_response_back(current_state.values)
                        
                        # Update task state for next message
                        if task_interrupted:
                            self._task_states[current_task.id]['justStarted'] = False
                        else:
                            self._task_states[current_task.id]['justStarted'] = True
                        
                        # Resolve waiter
                        if trigger_type == "schedule":
                            if response:
                                self.agent.a2a_server.task_manager.set_result(current_task.id, response)
                            else:
                                self.agent.a2a_server.task_manager.set_exception(current_task.id, RuntimeError("Task failed"))
                        elif trigger_type in ("a2a_queue", "chat_queue"):
                            if waiter_task_id:
                                logger.debug(f"[A2A] Resolving waiter for task_id={waiter_task_id}, trigger_type={trigger_type}")
                                self.agent.a2a_server.task_manager.resolve_waiter(waiter_task_id, response)
                                logger.debug(f"[PERF] _on_skill_complete - TOTAL callback time: {time.time()-t_callback_start:.3f}s")
                                logger.debug(f"[A2A] Waiter resolved for task_id={waiter_task_id}")
                            else:
                                logger.warning(f"[A2A] No waiter_task_id found for trigger_type={trigger_type}")
                    except Exception as e:
                        logger.error(f"[NON_BLOCKING] Callback error: {e}")
                        logger.error(traceback.format_exc())
                
                # Submit to executor with callback
                future = self._skill_executor.submit(_execute_skill)
                future.add_done_callback(_on_skill_complete)
                logger.info(f"[NON_BLOCKING] Skill execution submitted, continuing to poll queue (trigger_type={trigger_type})")
                
                # Reset justStarted for next iteration (will be set correctly per message)
                # Note: justStarted is now effectively stateless per-message
                
                # Reset error counter on successful submission
                consecutive_errors = 0
                
            except Exception as e:
                consecutive_errors += 1
                ex_stat = f"ErrorUnifiedRun[{trigger_type}]:" + traceback.format_exc() + " " + str(e)
                logger.error(ex_stat)
                
                # Reset state on error to retry from beginning
                justStarted = True
                
                # Check if too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({max_consecutive_errors}), stopping task loop")
                    break
                
                # Exponential backoff on errors
                backoff = min(consecutive_errors * 1, 10)
                if self._stop_event.wait(timeout=backoff):
                    break
            
            finally:
                # Ensure queue task is marked as done
                if trigger_type in ("a2a_queue", "chat_queue", "dev") and message_taken_from_queue:
                    if current_task and current_task.queue:
                        try:
                            current_task.queue.task_done()
                            if "Twin" in self.agent.card.name:
                                try:
                                    logger.debug(f"[WORKER_THREAD][Twin] task_done marked for task_id={getattr(current_task,'id', None)}, qid={id(current_task.queue)}")
                                except Exception:
                                    pass
                        except:
                            pass

            # Dev single-run exit check after each loop iteration
            if trigger_type == "dev" and dev_single_run:
                if getattr(self, "_dev_exit_requested", False):
                    logger.info("[DEV] Exit requested; breaking unified loop.")
                    break
            
            # Loop delay - use interruptible wait
            if self._stop_event.wait(timeout=1.0):
                logger.info(f"[WORKER_THREAD] Stop event set; exiting loop: trigger_type={trigger_type}, agent={self.agent.card.name}")
                break
        
        logger.info(f"launch_unified_run exiting: trigger_type={trigger_type}, agent={self.agent.card.name}")



    # DEPRECATED: Use launch_unified_run(trigger_type="schedule") instead
    def launch_scheduled_run(self, task=None):
        """DEPRECATED: This function is deprecated. Use launch_unified_run(trigger_type="schedule") instead."""
        logger.warning("[DEPRECATED] launch_scheduled_run is deprecated. Use launch_unified_run(trigger_type='schedule') instead.")
        self.launch_unified_run(task2run=task, trigger_type="schedule")


    # DEPRECATED: Use launch_unified_run(trigger_type="a2a_queue") instead
    def launch_reacted_run(self, task2run=None):
        """DEPRECATED: This function is deprecated. Use launch_unified_run(trigger_type="a2a_queue") instead."""
        logger.warning("[DEPRECATED] launch_reacted_run is deprecated. Use launch_unified_run(trigger_type='a2a_queue') instead.")
        self.launch_unified_run(task2run=task2run, trigger_type="a2a_queue")
        return  # Exit early after calling unified function



    # DEPRECATED: Use launch_unified_run(trigger_type="chat_queue") instead
    def launch_interacted_run(self, task2run=None):
        """DEPRECATED: This function is deprecated. Use launch_unified_run(trigger_type="chat_queue") instead."""
        logger.warning("[DEPRECATED] launch_interacted_run is deprecated. Use launch_unified_run(trigger_type='chat_queue') instead.")
        self.launch_unified_run(task2run=task2run, trigger_type="chat_queue")
        return  # Exit early after calling unified function
        


    def launch_dev_run(self, init_state: dict, dev_task: "ManagedTask"):
        """Register and execute a dev run task so pause/resume/step/cancel work via EC_Agent.
        This method is invoked in a background thread from EC_Agent, so it's safe to run synchronously.
        """
        try:
            log_msg = f"launch_dev_run (delegating to unified runner in DEV mode)..."
            logger.info(log_msg)
            ipc.send_skill_editor_log("log", log_msg)
            self._dev_task = dev_task
            # Ensure it is runnable and has a queue
            try:
                dev_task.pause_event.set()
            except Exception:
                pass
            if hasattr(dev_task, "status"):
                try:
                    dev_task.status.state = TaskState.WORKING
                except Exception:
                    pass
            if not hasattr(dev_task, "queue") or dev_task.queue is None:
                try:
                    logger.info("[DEV] Creating queue for dev_task as it was missing")
                    dev_task.queue = Queue()
                except Exception:
                    pass

            # Delegate to unified runner in DEV mode and return its response
            logger.info("[DEV] Delegating to launch_unified_run(trigger_type='dev') with single_run=True")
            result = self.launch_unified_run(task2run=dev_task, trigger_type="dev", dev_init_state=init_state, dev_single_run=True)
            logger.info(f"[DEV] Unified runner returned: {result}")
            return {"success": True, "result": result} if isinstance(result, dict) else {"success": False, "error": "NoResultFromUnifiedRunner"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def resume_dev_run(self):
        try:
            log_msg = f"resume_dev_run..."
            logger.info(log_msg)
            ipc.send_skill_editor_log("log", log_msg)
            if self._dev_task is None:
                return {"success": False, "error": "No dev run task"}
            # Fetch last checkpoint recorded at interrupt
            cps = getattr(self._dev_task, "checkpoint_nodes", None) or []
            if not cps:
                return {"success": False, "error": "No checkpoint to resume from"}
            last = cps[-1] or {}
            tag = last.get("tag") or last.get("i_tag") or ""
            checkpoint = last.get("checkpoint")
            if not checkpoint:
                return {"success": False, "error": "Missing checkpoint object"}

            # Build resume payload so node_builder sees the state flag on resume input
            resume_payload = {"_resuming_from": tag} if tag else {}
            # Also defensively set the flag on the checkpoint state itself
            try:
                vals = getattr(checkpoint, "values", None)
                if isinstance(vals, dict) and tag:
                    vals["_resuming_from"] = tag
                    # ensure attributes exists for any downstream readers
                    attrs = vals.get("attributes")
                    if not isinstance(attrs, dict):
                        vals["attributes"] = {}
            except Exception:
                pass

            try:
                if hasattr(self._dev_task, "status"):
                    self._dev_task.status.state = TaskState.WORKING
            except Exception:
                pass

            # Resume semantics: run until next breakpoint or completion.
            # We skip the current paused breakpoint node once to avoid re-pausing immediately at the same spot,
            # but we DO NOT set step_once so execution continues until the next interrupt or end.
            if tag:
                ctx = {"skip_bp_once": [tag]}
            else:
                ctx = {"skip_bp_once": []}

            # Make sure we resume the exact same thread as the checkpoint
            tid = None
            try:
                tid = (getattr(checkpoint, "config", {}) or {}).get("configurable", {}).get("thread_id")
            except Exception:
                pass

            saved_cfg = getattr(self._dev_task, "metadata", {}).get("config") or {}
            saved_cfg.setdefault("configurable", {})
            if tid:
                saved_cfg["configurable"]["thread_id"] = tid

            log_msg = f"[resume_dev_run] ctx={ctx}, resume_payload={resume_payload}, thread_id={saved_cfg.get('configurable', {}).get('thread_id')}"
            logger.info(log_msg)
            ipc.send_skill_editor_log("log", log_msg)

            result = self._dev_task.stream_run(Command(resume=resume_payload), checkpoint=checkpoint, context=ctx, config=saved_cfg)
            return {"success": True, "result": result}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorResumeDevRun")
            logger.error(err_msg)
            ipc.send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}

    def pause_dev_run(self):
        try:
            log_msg = f"pause_dev_run..."
            logger.info(log_msg)
            ipc.send_skill_editor_log("log", log_msg)
            if self._dev_task is None:
                return {"success": False, "error": "No dev run task"}
            try:
                self._dev_task.pause_event.clear()
            except Exception:
                pass
            if hasattr(self._dev_task, "status"):
                try:
                    self._dev_task.status.state = TaskState.INPUT_REQUIRED
                except Exception:
                    pass
            return {"success": True}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorPauseDevRun")
            logger.error(err_msg)
            ipc.send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}

    def step_dev_run(self):
        """Single-step: resume from last checkpoint and skip the paused node once."""
        try:
            if self._dev_task is None:
                return {"success": False, "error": "No dev run task"}
            cps = getattr(self._dev_task, "checkpoint_nodes", None) or []
            if not cps:
                return {"success": False, "error": "No checkpoint to step from"}
            last = cps[-1] or {}
            tag = last.get("tag") or last.get("i_tag") or ""
            checkpoint = last.get("checkpoint")
            if not checkpoint:
                return {"success": False, "error": "Missing checkpoint object"}

            # Build resume payload carrying the state flag for a single-step past breakpoint
            resume_payload = {"_resuming_from": tag} if tag else {}
            log_msg = f"resume tag: {tag}"
            logger.info(log_msg)
            ipc.send_skill_editor_log("log", log_msg)
            # Also set on checkpoint values for robustness
            try:
                vals = getattr(checkpoint, "values", None)
                if isinstance(vals, dict) and tag:
                    vals["_resuming_from"] = tag
                    if not isinstance(vals.get("attributes"), dict):
                        vals["attributes"] = {}
            except Exception:
                pass

            try:
                if hasattr(self._dev_task, "status"):
                    self._dev_task.status.state = TaskState.WORKING
            except Exception:
                pass

            # Single-step semantics: skip the paused node once, then pause at the very next node
            if tag:
                ctx = {"skip_bp_once": [tag], "step_once": True, "step_from": tag}
            else:
                ctx = {"skip_bp_once": [], "step_once": True, "step_from": ""}
            
            # Make sure we resume the exact same thread as the checkpoint
            tid = None
            try:
                tid = (getattr(checkpoint, "config", {}) or {}).get("configurable", {}).get("thread_id")
            except Exception:
                pass
            
            saved_cfg = getattr(self._dev_task, "metadata", {}).get("config") or {}
            saved_cfg.setdefault("configurable", {})
            if tid:
                saved_cfg["configurable"]["thread_id"] = tid

            log_msg = f"[step_dev_run] ctx={ctx}, resume_payload={resume_payload}, thread_id={saved_cfg.get('configurable', {}).get('thread_id')}"
            logger.info(log_msg)
            ipc.send_skill_editor_log("log", log_msg)

            result = self._dev_task.stream_run(Command(resume=resume_payload), checkpoint=checkpoint, context=ctx, config=saved_cfg)
            return {"success": True, "result": result}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorStepDevRun")
            logger.error(err_msg)
            ipc.send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}

    def cancel_dev_run(self):
        try:
            if self._dev_task is None:
                log_msg = "task already done!"
                logger.debug(log_msg)
                ipc.send_skill_editor_log("log", log_msg)
                return {"success": True}
            try:
                log_msg = "task to be cancelled."
                logger.debug(log_msg)
                ipc.send_skill_editor_log("log", log_msg)

                if hasattr(self._dev_task, "cancel"):
                    self._dev_task.cancel()
                if hasattr(self._dev_task, "exit"):
                    self._dev_task.exit()
            except Exception:
                pass
            self._dev_task = None
            return {"success": True}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorCancelDevRun")
            logger.error(err_msg)
            ipc.send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}

    def _get_serializable_state(self, task, config):
        """Helper: safely extract JSON-serializable state"""
        try:
            clean_state = task.skill.runnable.get_state(config=config)
            log_msg = f"_get_serializable_state: {clean_state}"
            logger.info(log_msg)
            ipc.send_skill_editor_log("log", log_msg)

            if hasattr(clean_state, "values") and isinstance(clean_state.values, dict):
                return clean_state.values
            return {}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorGetSerializableState Could not get clean state:")
            logger.warning(err_msg)
            ipc.send_skill_editor_log("warning", err_msg)
            return {}

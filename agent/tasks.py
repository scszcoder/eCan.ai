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
from agent.tasks_resume import build_general_resume_payload, build_node_transfer_patch, normalize_event
from enum import Enum

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
            "metadata": self.metadata,
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
        Filters out non-serializable objects like Interrupt instances.
        """
        import json
        from langgraph.types import Interrupt

        if obj is None:
            return None

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


    def _resolve_event_routing(self, event_type: str, request: Any) -> Optional["ManagedTask"]:
        """Use skill mapping DSL (event_routing) to choose a target task.

        Strategy:
        - Normalize the incoming request to an `event` envelope.
        - Iterate agent tasks; for each task's skill, check mapping_rules.event_routing for this event type.
        - Evaluate `task_selector` against the task (supports: id:, name:, name_contains:).
        - Return the first matching ManagedTask. No global queues.
        """
        try:
            event = normalize_event(event_type, request)
            etype = event.get("type") or event_type
        except Exception:
            etype = event_type

        logger.debug("normalized event:", event)

        # First, try task-specific routing based on each task's skill mapping_rules
        try:
            print(f"this agent has # tasks: {len(getattr(self.agent, 'tasks', []))}")
            for t in getattr(self.agent, "tasks", []) or []:
                print("task:", t.name, t.skill)
                if not t or not getattr(t, "skill", None):
                    continue
                skill = t.skill
                print("task required skill:", skill.name)
                rules = getattr(skill, "mapping_rules", None)
                print("mapping rules:", rules)
                if not isinstance(rules, dict):
                    continue
                # event_routing can be at top-level; also tolerate run_mode nesting
                event_routing = rules.get("event_routing")
                print("event_routing:", etype, event_routing)

                if not isinstance(event_routing, dict):
                    run_mode = getattr(skill, "run_mode", None)
                    if run_mode and isinstance(rules.get(run_mode), dict):
                        event_routing = rules.get(run_mode, {}).get("event_routing")
                if not isinstance(event_routing, dict):
                    continue

                rule = event_routing.get(etype)
                print("event_routing rule:", rule)
                if not isinstance(rule, dict):
                    continue

                selector = rule.get("task_selector") or ""
                sel_ok = False
                print("rule selector:", selector)
                try:
                    if selector.startswith("id:"):
                        sel_ok = t.id == selector.split(":", 1)[1]
                    elif selector.startswith("name:"):
                        sel_ok = (t.name or "") == selector.split(":", 1)[1]
                    elif selector.startswith("name_contains:"):
                        print("selector:", selector, event_type, t.name)
                        sel_ok = selector.split(":", 1)[1].lower() in (t.name or "").lower()
                    else:
                        # No selector or unknown format -> treat as match for this task
                        sel_ok = True
                except Exception as e:
                    sel_ok = False

                print("sel_ok:", sel_ok)

                if not sel_ok:
                    continue

                # Return the matching task; caller will use its queue
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
                                err_msg = get_traceback(_e, "ErrorBuildResumePayloadV2")
                                logger.debug(f"_build_resume_payload: failed to set merged values on checkpoint: {err_msg}")

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

    def sync_task_wait_in_line(self, event_type, request):
        try:
            logger.debug("sync task waiting in line.....", event_type, self.agent.card.name, request)
            # Prefer mapping-DSL-based event routing to a specific task's queue
            target_task = self._resolve_event_routing(event_type, request)
            if target_task and getattr(target_task, "queue", None):
                try:
                    target_task.queue.put_nowait(request)
                    logger.debug(f"task now in line for task={target_task.name} ({target_task.id})")
                    return
                except Exception:
                    logger.debug("failed to enqueue on task queue")
            # No routing match
            logger.error("No target task found for event type: " + str(event_type), target_task)
        except Exception as e:
            ex_stat = "ErrorWaitInLine:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")

    def launch_unified_run(self, task2run=None, trigger_type="queue"):
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
        justStarted = True
        consecutive_errors = 0
        max_consecutive_errors = 10
        current_task = task2run  # Use local variable instead of modifying parameter
        logger.debug(f"launch_unified_run started: trigger_type={trigger_type}, agent={self.agent.card.name}")
        
        while not self._stop_event.is_set():
            msg = None  # Reset message for each iteration
            
            try:
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
                    
                elif trigger_type in ("a2a_queue", "chat_queue", "message"):
                    # Queue-based tasks: wait for messages
                    if not current_task:
                        if self._stop_event.wait(timeout=1.0):
                            break
                        continue
                    
                    if current_task.queue.empty():
                        if self._stop_event.wait(timeout=1.0):
                            break
                        continue
                    
                    try:
                        msg = current_task.queue.get_nowait()
                        logger.trace(f"{trigger_type} message received: {type(msg)}")
                        
                        # For chat queue, find the appropriate chatter task
                        if trigger_type == "chat_queue":
                            current_task = self.find_chatter_tasks()  # Use local variable
                            if not current_task:
                                logger.error("No chatter task found")
                                # Mark queue task as done even if no task found
                                if task2run and task2run.queue:
                                    try:
                                        task2run.queue.task_done()
                                    except:
                                        pass
                                continue
                    except Empty:
                        continue
                else:
                    logger.error(f"Unknown trigger_type: {trigger_type}")
                    if self._stop_event.wait(timeout=1.0):
                        break
                    continue
                
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
                
                # 2. Execute task (initial run or resume)
                if justStarted:
                    # Initial run
                    logger.debug(f"Initial run: {current_task.skill.name}")
                    current_task.metadata["state"] = prep_skills_run(
                        current_task.skill,
                        self.agent, 
                        current_task.id, 
                        msg, 
                        None
                    )
                    response = current_task.stream_run()
                    logger.debug(f"Initial run response: {response}")
                    
                else:
                    # Resume run
                    logger.debug(f"Resume run: {current_task.skill.name}", msg)
                    # On resume, keep existing state; DSL mapping will provide a state_patch via resume payload
                    
                    # Build resume payload using mapping DSL
                    resume_payload, cp = self._build_resume_payload(current_task, msg)
                    logger.debug(f"Resume payload: {resume_payload}")
                    print(f"current cp: ", cp)

                    # note langgraph could have multiple interrupted nodes, checkpoint is
                    # critical for picking up exactly where it's left off.
                    if cp:
                        response = current_task.stream_run(
                            Command(resume=resume_payload), 
                            checkpoint=cp, 
                            stream_mode="updates"
                        )
                    else:
                        response = current_task.stream_run(
                            Command(resume=resume_payload), 
                            stream_mode="updates"
                        )
                    logger.debug(f"Resume run response: {response}")
                
                # 3. Handle response and interrupts
                # by the time we get here, we should have either
                # A) the langgraph workflow is finished.
                #  or
                # B) we hit an interrupt.
                step = response.get('step') or {}
                logger.debug(f"Current Step: {step}")
                current_state = response.get('cp')
                
                if isinstance(step, dict) and '__interrupt__' in step:
                    # Task interrupted - send prompt to GUI
                    interrupt_obj = step["__interrupt__"][0]

                    # if interrupted due to human in loop or other agent in loop
                    if "prompt_to_human" in interrupt_obj.value or "prompt_to_agent" in interrupt_obj.value:
                        # Extract chatId from message metadata
                        print("prompt_to_human:", interrupt_obj.value["prompt_to_human"], "<<<")
                        print("current state:", current_state)
                        try:
                            chatId = current_state.values.get("messages")[1]
                        except Exception:
                            chatId = ""
                            pass
                        print("chatId:", chatId, "<<<")
                        if chatId:
                            # re-org data to be sent chatId, interrupt_obj.value["qa_form_to_human"])
                            # the assumption is message to be sent is already placed properly in the state.
                            send_response_back(current_state.values)
                    justStarted = False
                else:
                    # Task completed, we flag it as justStarted for the next run.
                    justStarted = True
                
                # 4. Resolve task result
                if trigger_type == "schedule":
                    # Scheduled tasks report to task manager
                    if response:
                        self.agent.a2a_server.task_manager.set_result(current_task.id, response)
                    else:
                        self.agent.a2a_server.task_manager.set_exception(current_task.id, RuntimeError("Task failed"))
                        
                elif trigger_type in ("a2a_queue", "chat_queue"):
                    # Queue-based tasks resolve waiters
                    task_id = None
                    try:
                        if msg and hasattr(msg, 'params'):
                            task_id = msg.params.id
                        elif msg and isinstance(msg, dict):
                            task_id = msg.get('params', {}).get('id') or msg.get('id')
                    except Exception:
                        logger.error("Failed to extract task_id from message")
                    
                    if task_id:
                        self.agent.a2a_server.task_manager.resolve_waiter(task_id, response)
                
                # Reset error counter on successful execution
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
                if trigger_type in ("a2a_queue", "chat_queue"):
                    if current_task and current_task.queue:
                        try:
                            current_task.queue.task_done()
                        except:
                            pass
            
            # Loop delay - use interruptible wait
            if self._stop_event.wait(timeout=1.0):
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
        
        # OLD CODE BELOW (kept for reference, not executed)
        chatNotDone = True
        justStarted = True
        while False and not self._stop_event.is_set():
            try:
                logger.trace("checking a2a queue....", self.agent.card.name)

                if task2run:
                    try:
                        if not task2run.queue.empty():
                            msg = task2run.queue.get_nowait()
                            logger.trace("A2A message...."+ str(msg))
                            if justStarted:
                                # a message could be handled by different task, so first find
                                # a task that that's suitable to handle this message,

                                logger.debug("task2run skill name" + task2run.skill.name)
                                task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent, task2run.id, None)

                                logger.trace("task2run init state" + str(task2run.metadata["state"]))
                                logger.trace("ready to run the right task" + task2run.name + str(msg))
                                # response = await task2run.astream_run()
                                response = task2run.stream_run()

                                logger.debug("reacted task run response:", response)
                                step = response.get('step') or {}
                                if isinstance(step, dict) and '__interrupt__' in step:
                                    logger.trace("sending interrupt prompt1")
                                    logger.trace("sending interrupt prompt2")
                                    interrupt_obj = step["__interrupt__"][0]  # [0] because it's a tuple with one item
                                    prompt = interrupt_obj.value["prompt_to_human"]
                                    # now return this prompt to GUI to display
                                    chatId = msg.params.metadata['chatId']
                                    self.sendChatMessageToGUI(self.agent, chatId, prompt)
                                    justStarted = False
                                else:
                                    justStarted = True
                            else:
                                logger.debug("task2run skill name" + task2run.skill.name)
                                task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent, task2run.id, task2run.metadata["state"])

                                logger.trace("task2run init state" + str(task2run.metadata["state"]))
                                logger.trace("ready to run the right task" + task2run.name + str(msg))
                                # response = await task2run.astream_run()
                                response = task2run.stream_run()
                                logger.debug("NI, resume tick", response)
                                # Resume with the user's reply using Command(resume=...)
                                resume_payload, cp = self._build_resume_payload(task2run, msg)
                                if cp:
                                    response = task2run.stream_run(Command(resume=resume_payload), checkpoint=cp, stream_mode="updates")
                                else:
                                    response = task2run.stream_run(Command(resume=resume_payload), stream_mode="updates")

                                logger.debug("NI reacted task resume response:", response)

                                step = response.get('step') or {}
                                if isinstance(step, dict) and '__interrupt__' in step:
                                    logger.trace("sending interrupt prompt2")
                                    interrupt_obj = step["__interrupt__"][0]  # [0] because it's a tuple with one item
                                    prompt = interrupt_obj.value["prompt_to_human"]
                                    # now return this prompt to GUI to display
                                    chatId = msg.params.metadata['chatId']
                                    task_id = msg.params.metadata['msgId']
                                    logger.debug("chatId in the message", chatId)

                                    # hilData = sample_search_result0
                                    # hilData = sample_parameters_0
                                    # hilData = sample_metrics_0
                                    # self.sendChatNotificationToGUI(self.agent, chatId, hilData)
                                    # self.sendChatFormToGUI(self.agent, chatId, hilData)
                                    # self.sendChatMessageToGUI(self.agent, chatId, hilData)
                                    # self.agent.mainwin.top_gui.push_message_to_chat(chatId, hilData)
                                    self.sendChatMessageToGUI(self.agent, chatId, prompt)

                                    if interrupt_obj.value.get("qa_form_to_agent", None):
                                        self.sendChatFormToGUI(self.agent, chatId, interrupt_obj.value.get["qa_form_to_human"])
                                    elif interrupt_obj.value.get("notification_to_agent", None):
                                        self.sendChatNotificationToGUI(self.agent, chatId, interrupt_obj.value.get["notification_to_human"])


                                    justStarted = False
                                else:
                                    justStarted = True

                            task_id = msg.params.id
                            self.agent.a2a_server.task_manager.resolve_waiter(task_id, response)
                            task2run.queue.task_done()

                        # process msg here and the msg could be start a task run.
                    except asyncio.QueueEmpty:
                        logger.info("Queue unexpectedly empty when trying to get message.")
                        pass

            except Exception as e:
                ex_stat = "ErrorLaunchReactedRun:" + traceback.format_exc() + " " + str(e)
                logger.error(f"{ex_stat}")

            # await asyncio.sleep(1)  # the loop goes on.....
            time.sleep(1)


    # DEPRECATED: Use launch_unified_run(trigger_type="chat_queue") instead
    def launch_interacted_run(self, task2run=None):
        """DEPRECATED: This function is deprecated. Use launch_unified_run(trigger_type="chat_queue") instead."""
        logger.warning("[DEPRECATED] launch_interacted_run is deprecated. Use launch_unified_run(trigger_type='chat_queue') instead.")
        self.launch_unified_run(task2run=task2run, trigger_type="chat_queue")
        return  # Exit early after calling unified function
        
        # OLD CODE BELOW (kept for reference, not executed)
        cached_human_responses = ["hi!", "rag prompt", "1 rag, 2 none, 3 no, 4 no", "red", "q"]
        cached_response_index = 0
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        justStarted = True
        logger.debug("launch_interacted_run....", self.agent.card.name)
        while False and not self._stop_event.is_set():
            try:
                logger.debug("checking chat queue...." + self.agent.card.name)
                thread_config = {"configurable": {"thread_id": uuid.uuid4()}}
                if task2run:
                    if not task2run.queue.empty():
                        try:
                            msg = task2run.queue.get_nowait()
                            logger.debug("chat queue message....", type(msg), msg)
                            task2run = self.find_chatter_tasks()
                            task2run_details = str(task2run.to_dict())
                            logger.debug("matched chatter task.... %s", (task2run_details[:100] + '...') if len(task2run_details) > 100 else task2run_details)

                            if justStarted:
                                logger.debug("chatter task2run skill name", task2run.skill.name)
                                task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent, task2run.id, msg, None)
                                logger.trace("interacted task2run init state", task2run.metadata["state"])
                                logger.debug("ready to run the right task", task2run.name, type(msg), msg)
                                response = task2run.stream_run()
                                logger.debug("ineracted task run response:", response)
                                logger.debug("sending interrupt prompt1")
                                step = response.get('step') or {}
                                if isinstance(step, dict) and '__interrupt__' in step:
                                    logger.debug("sending interrupt prompt2")
                                    interrupt_obj = step["__interrupt__"][0]

                                    if "prompt_to_human" in interrupt_obj.value:
                                        prompt = interrupt_obj.value["prompt_to_human"]
                                        logger.debug("prompt to human:", prompt)
                                        chatId = msg.params.metadata['chatId']
                                        task_id = msg.params.metadata['msgId']
                                        logger.debug("chatId in the message", chatId)
                                        self.sendChatMessageToGUI(self.agent, chatId, prompt)
                                        logger.debug("prompt sent to GUI<<<<<<<<<<<")
                                    justStarted = False
                                else:
                                    justStarted = True
                                if not isinstance(msg, dict):
                                    task_id = msg.params.id
                                else:
                                    if "id" in msg['params']:
                                        task_id = msg['params']['id']
                                    elif "id" in msg:
                                        task_id = msg['id']
                                    else:
                                        task_id = ""
                                        logger.error("ERROR: lost track of task id....", msg)
                                self.agent.a2a_server.task_manager.resolve_waiter(task_id, response)
                            else:
                                logger.debug(f"interacted {task2run.skill.name} no longer initial run", msg)
                                task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent, task2run.id, msg, task2run.metadata["state"])
                                logger.debug("NI interacted task2run current state", task2run.metadata["state"])
                                resume_payload, cp = self._build_resume_payload(task2run, msg)
                                logger.debug("NI resume payload", resume_payload)

                                if cp:
                                    response = task2run.stream_run(Command(resume=resume_payload), checkpoint=cp, stream_mode="updates")
                                else:
                                    response = task2run.stream_run(Command(resume=resume_payload), stream_mode="updates")

                                logger.debug("NI interacted  task resume response:", response)
                                step = response.get('step') or {}
                                if isinstance(step, dict) and '__interrupt__' in step:
                                    logger.debug("NI sending interrupt prompt2")
                                    interrupt_obj = step["__interrupt__"][0]

                                    prompt = interrupt_obj.value["prompt_to_human"]
                                    logger.debug("NI prompt to human:", prompt)
                                    chatId = msg.params.metadata['chatId']
                                    task_id = msg.params.metadata['msgId']
                                    logger.debug("NI chatId in the message", chatId)
                                    # hilData = sample_search_result0
                                    # hilData = sample_parameters_0
                                    self.sendChatMessageToGUI(self.agent, chatId, prompt)
                                    if interrupt_obj.value.get("qa_form_to_human", None):
                                        self.sendChatFormToGUI(self.agent, chatId, interrupt_obj.value.get["qa_form_to_human"])
                                    elif interrupt_obj.value.get("notification_to_human", None):
                                        self.sendChatNotificationToGUI(self.agent, chatId,  interrupt_obj.value.get["notification_to_human"])
                                    logger.debug("NI prompt sent to GUI<<<<<<<<<<<")
                                else:
                                    justStarted = True

                                print("msg is:", type(msg), msg)
                                if not isinstance(msg, dict):
                                    task_id = msg.params.id
                                else:
                                    if "id" in msg:
                                        task_id = msg['id']
                                    elif "id" in msg['params']:
                                        task_id = msg['params']['id']
                                    else:
                                        logger.error("ERROR: lost track of task id....", msg)
                                self.agent.a2a_server.task_manager.resolve_waiter(task_id, response)

                            task2run.queue.task_done()
                        except asyncio.QueueEmpty:
                            logger.info("Queue unexpectedly empty when trying to get message.")
                            pass

                    else:
                        logger.debug("no chat message")
                        time.sleep(1)
            except Exception as e:
                ex_stat = "ErrorLaunchInteractedRun:" + traceback.format_exc() + " " + str(e)
                logger.error(f"{ex_stat}")
            time.sleep(1)

    # def launch_dev_run(self, init_state, dev_task: ManagedTask = None):
    #     """
    #     Executes a controlled, interactive development run for a given task,
    #     supporting multiple breakpoints and human/API interrupts.
    #     """
    #     web_gui = AppContext.get_web_gui()
    #     ipc_api = web_gui.get_ipc_api()
    #     if not dev_task:
    #         logger.error("launch_dev_run called without a task.")
    #         return
    #
    #     logger.info(f"Launching interactive dev run for task: {dev_task.name} with run_id: {dev_task.run_id}")
    #
    #     try:
    #         context = {
    #             "id": str(uuid.uuid4()),
    #             "topic": "",
    #             "summary": "",
    #             "msg_thread_id": "",
    #             "tot_context": {},
    #             "app_context": {},
    #             "this_node": {"name": ""},
    #         }
    #
    #         # Create a unique thread_id for the checkpointer
    #         thread_id = str(uuid.uuid4())
    #         config = {
    #             "configurable": {"thread_id": thread_id}
    #         }
    #
    #         # Start the stream with the correct config, and initial state
    #         controller = dev_task.skill.runnable.stream(init_state, context=context, config=config)
    #         stream_iterator = iter(controller)
    #
    #         # Keep track of active checkpoints (tag -> checkpoint)
    #         self.active_checkpoints = {}
    #
    #         run_status = "running"
    #         current_node = "start"
    #         event = None
    #
    #         while not dev_task.cancellation_event.is_set():
    #             try:
    #                 if run_status == "running":
    #                     # Try to advance the graph
    #                     try:
    #                         event = next(stream_iterator, None)
    #                     except GraphInterrupt as gi:
    #                         # GraphInterrupt should have checkpoint information
    #                         # Get the current state/checkpoint from LangGraph
    #                         current_state = controller.get_state(config)
    #
    #                         # Create proper interrupt object with checkpoint
    #                         interrupt_with_checkpoint = type('InterruptWithCheckpoint', (), {
    #                             'value': gi.value,
    #                             'id': getattr(gi, 'id', str(gi)),
    #                             'checkpoint': current_state
    #                         })()
    #                         event = {"__interrupt__": [interrupt_with_checkpoint]}
    #                     except Exception as e:
    #                         logger.info(f"Non-interrupt exception: {e}")
    #                         raise
    #
    #                     # Graph finished
    #                     if event is None:
    #                         logger.info(f"Dev run for {dev_task.name} has completed.")
    #                         clean_state = self._get_serializable_state(dev_task, config)
    #                         ipc_api.update_run_stat(
    #                             agent_task_id=dev_task.run_id,
    #                             current_node=None,
    #                             status="completed",
    #                             langgraph_state=clean_state,
    #                             timestamp=int(time.time() * 1000)
    #                         )
    #                         break
    #
    #                     # Extract current node from event metadata
    #                     previous_node = current_node
    #                     node_extracted = False
    #                     try:
    #                         if isinstance(event, dict):
    #                             # Log the event structure for debugging
    #                             event_keys = list(event.keys())
    #                             logger.info(f"[EventDebug] Event keys: {event_keys}, has_metadata: {'__metadata__' in event}")
    #
    #                             # LangGraph events can have metadata with node info
    #                             metadata = event.get("__metadata__", {})
    #                             if metadata:
    #                                 node_name = metadata.get("langgraph_node") or metadata.get("node")
    #                                 if node_name:
    #                                     current_node = node_name
    #                                     node_extracted = True
    #                                     if current_node != previous_node:
    #                                         logger.info(f"[NodeTransition] {previous_node} -> {current_node} (from metadata)")
    #                             # Also check for node name in the event keys (some LangGraph versions)
    #                             elif len(event) == 1 and not any(k.startswith("__") for k in event.keys()):
    #                                 # Single key that's not a special key might be the node name
    #                                 current_node = list(event.keys())[0]
    #                                 node_extracted = True
    #                                 if current_node != previous_node:
    #                                     logger.info(f"[NodeTransition] {previous_node} -> {current_node} (from event key)")
    #
    #                             if not node_extracted:
    #                                 logger.warning(f"[NodeExtraction] Failed to extract node from event. Keeping current_node='{current_node}'. Event keys: {event_keys}")
    #                     except Exception as e:
    #                         logger.debug(f"Could not extract current node from event: {e}")
    #
    #                     # Update GUI with current node during execution
    #                     try:
    #                         ipc_api.update_run_stat(
    #                             agent_task_id=dev_task.run_id,
    #                             current_node=current_node,
    #                             status=run_status,
    #                             langgraph_state=self._get_serializable_state(dev_task, config),
    #                             timestamp=int(time.time() * 1000)
    #                         )
    #                     except Exception as e:
    #                         logger.debug(f"Failed to update run stat during execution: {e}")
    #
    #                     # Handle interrupts
    #                     if isinstance(event, dict) and "__interrupt__" in event:
    #                         interrupt_obj = event["__interrupt__"][0]
    #
    #                         # Tag = business ID or fallback to node name
    #                         tag = interrupt_obj.value.get("i_tag") or f"{thread_id}:interrupt_{getattr(interrupt_obj, 'id', 'unknown')}"
    #
    #                         # Get checkpoint - either from interrupt_obj or from controller state
    #                         checkpoint = None
    #                         try:
    #                             # Try to get checkpoint from interrupt object (GraphInterrupt case)
    #                             checkpoint = getattr(interrupt_obj, 'checkpoint', None)
    #                         except Exception:
    #                             pass
    #
    #                         # If no checkpoint on interrupt object, get current state from controller
    #                         if checkpoint is None:
    #                             try:
    #                                 checkpoint = controller.get_state(config)
    #                                 logger.debug(f"Retrieved checkpoint from controller for tag {tag}")
    #                             except Exception as e:
    #                                 logger.warning(f"Could not get checkpoint for tag {tag}: {e}")
    #
    #                         if checkpoint:
    #                             self.active_checkpoints[tag] = checkpoint
    #                         else:
    #                             logger.warning(f"No checkpoint available for tag {tag}")
    #
    #                         current_node = interrupt_obj.value.get("paused_at", tag)
    #                         run_status = "paused"
    #
    #                         logger.info(f"Execution paused at node/tag: {tag}")
    #                         ipc_api.update_run_stat(
    #                             agent_task_id=dev_task.run_id,
    #                             current_node=current_node,
    #                             status="paused",
    #                             langgraph_state=self._get_serializable_state(dev_task, config),
    #                             timestamp=int(time.time() * 1000)
    #                         )
    #                         continue  # wait for GUI
    #
    #                 # If paused, wait for GUI command
    #                 if run_status == "paused":
    #                     try:
    #                         command = dev_task.queue.get(timeout=0.3)
    #                         logger.debug(f"Dev run ({dev_task.run_id}) received queue command: {command}")
    #                     except Empty:
    #                         continue
    #
    #                     # Command handling
    #                     if isinstance(command, dict):
    #                         cmd_type = command.get("type")
    #                         tag = command.get("tag")
    #                         payload = command.get("payload", {})
    #                     else:
    #                         # Legacy string-only commands
    #                         cmd_type = command
    #                         tag = None
    #                         payload = {}
    #
    #                     if cmd_type == "resume" or "chat" in cmd_type.lower() or "msg" in cmd_type.lower() or "event" in cmd_type.lower():
    #                         if not tag:
    #                             logger.warning("Resume requested but no tag specified.")
    #                             continue
    #                         checkpoint = self.active_checkpoints.pop(tag, None)
    #                         if not checkpoint:
    #                             logger.warning(f"No checkpoint found for tag {tag}")
    #                             continue
    #                         logger.info(f"Resuming execution from tag {tag}")
    #                         # Build per-node transfer patch (optional)
    #                         state_snapshot = {}
    #                         try:
    #                             state_snapshot = getattr(checkpoint, "values", {}) if checkpoint else {}
    #                         except Exception:
    #                             state_snapshot = {}
    #                         try:
    #                             node_rules = {}
    #                             try:
    #                                 node_rules = (dev_task.skill.mapping_rules or {}).get("node_transfers", {}) or {}
    #                             except Exception:
    #                                 node_rules = {}
    #                             node_patch = build_node_transfer_patch(tag, state_snapshot, node_rules) or {}
    #                             if node_patch:
    #                                 payload = self._deep_merge(payload or {}, node_patch)
    #                                 logger.info(f"Applied node transfer patch at {tag}: keys={list(node_patch.keys())}")
    #                         except Exception as e:
    #                             logger.debug(f"node transfer at resume failed: {e}")
    #                         # Inject cloud_task_id into checkpoint values for node resume detection
    #                         try:
    #                             vals = getattr(checkpoint, "values", None)
    #                             if isinstance(vals, dict):
    #                                 attrs = vals.get("attributes")
    #                                 if not isinstance(attrs, dict):
    #                                     attrs = {}
    #                                     vals["attributes"] = attrs
    #                                 attrs["cloud_task_id"] = tag
    #                         except Exception as e:
    #                             logger.debug(f"launch_dev_run resume: could not inject cloud_task_id: {e}")
    #                         # Use Command(resume=...) so interrupt() receives payload immediately
    #                         controller = dev_task.skill.runnable.stream(Command(resume=payload), checkpoint=checkpoint, config=config,
    #                                                                 context=context)
    #                         stream_iterator = iter(controller)
    #                         run_status = "running"
    #
    #                     elif cmd_type == "step":
    #                         if not tag:
    #                             logger.warning("Step requested but no tag specified.")
    #                             continue
    #                         checkpoint = self.active_checkpoints.pop(tag, None)
    #                         if not checkpoint:
    #                             logger.warning(f"No checkpoint found for tag {tag}")
    #                             continue
    #                         logger.info(f"Stepping execution from tag {tag}")
    #                         # Build per-node transfer patch (optional)
    #                         state_snapshot = {}
    #                         try:
    #                             state_snapshot = getattr(checkpoint, "values", {}) if checkpoint else {}
    #                         except Exception:
    #                             state_snapshot = {}
    #                         try:
    #                             node_rules = {}
    #                             try:
    #                                 node_rules = (dev_task.skill.mapping_rules or {}).get("node_transfers", {}) or {}
    #                             except Exception:
    #                                 node_rules = {}
    #                             node_patch = build_node_transfer_patch(tag, state_snapshot, node_rules) or {}
    #                             if node_patch:
    #                                 payload = self._deep_merge(payload or {}, node_patch)
    #                                 logger.info(f"Applied node transfer patch at {tag}: keys={list(node_patch.keys())}")
    #                         except Exception as e:
    #                             logger.debug(f"node transfer at step failed: {e}")
    #                         # Inject cloud_task_id to ensure node detects resume
    #                         try:
    #                             vals = getattr(checkpoint, "values", None)
    #                             if isinstance(vals, dict):
    #                                 attrs = vals.get("attributes")
    #                                 if not isinstance(attrs, dict):
    #                                     attrs = {}
    #                                     vals["attributes"] = attrs
    #                                 attrs["cloud_task_id"] = tag
    #                         except Exception as e:
    #                             logger.debug(f"launch_dev_run step: could not inject cloud_task_id: {e}")
    #                         controller = dev_task.skill.runnable.stream(Command(resume=payload), checkpoint=checkpoint, config=config,
    #                                                                 context=context)
    #                         stream_iterator = iter(controller)
    #                         run_status = "running"
    #
    #                     elif cmd_type == "pause":
    #                         logger.info("Pause command received — staying paused")
    #                         run_status = "paused"
    #
    #                     elif cmd_type == "cancel":
    #                         dev_task.cancel()
    #                         logger.info("Dev run cancelled by user")
    #                         break
    #
    #                 # Do not send a premature completion here. The proper completion
    #                 # notifications are already sent when the graph finishes (event is None)
    #                 # or in the StopIteration branch above. Keeping a mid-run completion
    #                 # here causes the frontend to clear the running icon immediately.
    #             except Exception as e:
    #                 err_msg = get_traceback(e, "ErrorLaunchDevRun")
    #                 logger.error(f"Exception during launch_dev_run for task {dev_task.name}: {err_msg}")
    #                 ipc_api.update_run_stat(
    #                     agent_task_id=dev_task.run_id,
    #                     current_node=current_node,
    #                     status="failed",
    #                     langgraph_state={"error": str(e)},
    #                     timestamp=int(time.time() * 1000)
    #                 )
    #                 raise
    #
    #         logger.info("Dev run ENDED.")
    #
    #     finally:
    #         # Flush any remaining commands from the queue
    #         logger.info(f"Flushing dev message queue for task {dev_task.run_id}.")
    #         while not dev_task.queue.empty():
    #             try:
    #                 dev_task.queue.get_nowait()
    #             except Empty:
    #                 break
    #         logger.info("Dev message queue flushed.")

    def launch_dev_run(self, init_state: dict, dev_task: "ManagedTask"):
        """Register and execute a dev run task so pause/resume/step/cancel work via EC_Agent.
        This method is invoked in a background thread from EC_Agent, so it's safe to run synchronously.
        """
        try:
            self._dev_task = dev_task
            # Merge provided initial state
            if isinstance(init_state, dict):
                try:
                    cur = getattr(dev_task, "state", {}) or {}
                    dev_task.state = {**cur, **init_state}
                except Exception:
                    pass
            # Ensure it is runnable
            try:
                dev_task.pause_event.set()
            except Exception:
                pass
            if hasattr(dev_task, "status"):
                try:
                    dev_task.status.state = TaskState.WORKING
                except Exception:
                    pass

            # Execute the dev run synchronously using the sync stream API
            try:
                result = dev_task.stream_run(init_state)
                logger.info("Dev run finished with result:", result)
                return {"success": True, "result": result}
            except Exception as run_exc:
                ex_stat = "ErrorDevRunExecute:" + traceback.format_exc() + " " + str(run_exc)
                logger.error(ex_stat)
                return {"success": False, "error": ex_stat}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def resume_dev_run(self):
        try:
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

            logger.info(f"[resume_dev_run] ctx={ctx}, resume_payload={resume_payload}, thread_id={saved_cfg.get('configurable', {}).get('thread_id')}")
            result = self._dev_task.stream_run(Command(resume=resume_payload), checkpoint=checkpoint, context=ctx, config=saved_cfg)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def pause_dev_run(self):
        try:
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
            return {"success": False, "error": str(e)}

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
            
            logger.info(f"[step_dev_run] ctx={ctx}, resume_payload={resume_payload}, thread_id={saved_cfg.get('configurable', {}).get('thread_id')}")
            result = self._dev_task.stream_run(Command(resume=resume_payload), checkpoint=checkpoint, context=ctx, config=saved_cfg)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_dev_run(self):
        try:
            if self._dev_task is None:
                return {"success": True}
            try:
                if hasattr(self._dev_task, "cancel"):
                    self._dev_task.cancel()
                if hasattr(self._dev_task, "exit"):
                    self._dev_task.exit()
            except Exception:
                pass
            self._dev_task = None
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_serializable_state(self, task, config):
        """Helper: safely extract JSON-serializable state"""
        try:
            clean_state = task.skill.runnable.get_state(config=config)
            if hasattr(clean_state, "values") and isinstance(clean_state.values, dict):
                return clean_state.values
            return {}
        except Exception as e:
            logger.warning(f"Could not get clean state: {e}")
            return {}

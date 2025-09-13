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
from fastapi.responses import JSONResponse
import time
import queue
import threading
from langgraph.types import Command

from datetime import datetime, timedelta
import inspect
import traceback
from datetime import datetime, timedelta
from calendar import monthrange
from langgraph.types import interrupt
from app_context import AppContext
from utils.logger_helper import logger_helper as logger
# from agent.chats.tests.test_notifications import *
from langgraph.types import Interrupt
from agent.ec_skills.dev_defs import BreakpointManager
from utils.logger_helper import get_traceback
from langgraph.errors import NodeInterrupt

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
    id: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resume_from: Optional[str] = None
    trigger: Optional[str] = None
    task: Optional[asyncio.Task] = None
    pause_event: asyncio.Event = asyncio.Event()
    cancellation_event: threading.Event = Field(default_factory=threading.Event)
    schedule: Optional[TaskSchedule] = None
    checkpoint_nodes: Optional[List[str]] = None
    priority: Optional[Priority_Types] = None
    last_run_datetime: Optional[datetime] = None
    already_run_flag: bool = False

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
        
        taskJS = {
            "id": self.id,
            "runId": self.run_id,
            "skill": self.skill.name,
            "metadata": self.metadata,
            "state": self.state,
            "resume_from": self.resume_from,
            "trigger": self.trigger,
            # "pause_event": self.pause_event,
            "schedule": schedule_dict,
            "checkpoint_nodes": self.checkpoint_nodes,
            "priority": self.priority.value if self.priority else None,
            "last_run_datetime": last_run_datetime_str,
            "already_run_flag": self.already_run_flag,
        }
        return taskJS

    def set_priority(self, p):
        self.priority = p

    def add_checkpoint_node(self, cp_name):
        if cp_name not in self.checkpoint_nodes:
            self.checkpoint_nodes.append(cp_name)

    def remove_checkpoint_node(self, cp_name):
        if cp_name in self.checkpoint_nodes:
            self.checkpoint_nodes.remove(cp_name)

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
        print("current langgraph run time state0:", self.skill.runnable.get_state(config=effective_config))

        # Support Command inputs (e.g., Command(resume=...)) and normal state runs
        if isinstance(in_msg, Command):
            # in_args = self.metadata.get("state", {})
            # agen = self.skill.runnable.stream(in_args, config=effective_config, context=context, **kwargs)
            agen = self.skill.runnable.stream(in_msg, config=effective_config, context=context, **kwargs)
        else:
            in_args = self.metadata.get("state", {})
            print("in_args:", in_args)
            agen = self.skill.runnable.stream(in_args, config=effective_config, context=context, **kwargs)
        try:
            print("running skill:", self.skill.name, in_msg)
            print("stream_run config:", effective_config)
            print("current langgraph run time state2:", self.skill.runnable.get_state(config=effective_config))
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

            for step in agen:
                print("synced Step output:", step)

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
                if step.get("require_user_input") or step.get("await_agent") or step.get("__interrupt__"):
                    self.status.state = TaskState.INPUT_REQUIRED
                    print("input required...", step)
                    # yield {"success": False, "step": step}
                    break

            if self.status.state == TaskState.INPUT_REQUIRED:
                success = False
            else:
                success = True
                self.status.state = TaskState.COMPLETED
                print("task completed...")

            run_result = {"success": success, "step": step}
            print("synced stream_run result:", run_result)
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
        if effective_config is None:
            effective_config = {
                "configurable": {
                    "thread_id": str(uuid.uuid4())
                }
            }
            self.metadata["config"] = effective_config

        # Support Command inputs (e.g., Command(resume=...)) and normal state runs
        if isinstance(in_msg, Command):
            agen = self.skill.runnable.astream(in_msg, config=effective_config, **kwargs)
        else:
            in_args = self.metadata.get("state", {})
            print("in_args:", in_args)
            agen = self.skill.runnable.astream(in_args, config=effective_config, **kwargs)
        try:
            print("running skill:", self.skill.name, in_msg)
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

            async for step in agen:
                print("async Step output:", step)
                await self.pause_event.wait()
                self.status.message = Message(
                    role="agent",
                    parts=[TextPart(type="text", text=str(step))]
                )
                if step.get("require_user_input") or step.get("await_agent") or step.get("__interrupt__"):
                    self.status.state = TaskState.INPUT_REQUIRED
                    print("input required...", step)
                    # yield {"success": False, "step": step}
                    break

            if self.status.state == TaskState.INPUT_REQUIRED:
                success = False
            else:
                success = True
                self.status.state = TaskState.COMPLETED
                print("task completed...")

            run_result = {"success": success, "step": step}
            print("astream_run result:", run_result)
            return run_result

        except Exception as e:
            ex_stat = "ErrorAstreamRun:" + traceback.format_exc() + " " + str(e)
            print(f"{ex_stat}")
            return {"success": False, "Error": ex_stat}

        finally:
            # Cleanup code here
            # self.runner = None
            self.status.state = TaskState.CANCELED
            await agen.aclose()


    async def create_scheduler_task(self):
        self.task = asyncio.create_task(self.scheduled_run())

    def exit(self):
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
        # self.a2a_msg_queue = asyncio.Queue()
        # self.chat_msg_queue = asyncio.Queue()
        self.a2a_msg_queue = queue.Queue()
        self.chat_msg_queue = queue.Queue()
        self.dev_msg_queue = queue.Queue()
        self._stop_event = asyncio.Event()
        TaskRunnerRegistry.register(self)

    def stop(self):
        """Signal all while-loops to exit ASAP and drain queues if needed."""
        try:
            self._stop_event.set()
            # Optionally push sentinels to wake loops polling queues quickly
            try:
                self.a2a_msg_queue.put_nowait({"__shutdown__": True})
            except Exception:
                pass
            try:
                self.chat_msg_queue.put_nowait({"__shutdown__": True})
            except Exception:
                pass
        except Exception:
            pass

    def close(self):
        self.stop()
        TaskRunnerRegistry.unregister(self)

    def assign_agent(self, agent):
        self.agent = agent

    async def create_task(self, skill, state: dict, session_id: Optional[str] = None, resume_from: Optional[str] = None, trigger: Optional[str] = None) -> str:
        task_id = str(uuid.uuid4())
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
                await tbr_task.astream()
            else:
                print("WARNING: no running tasks....")


    async def run_all_tasks(self):
        self.running_tasks = []

        for t in self.agent.tasks:
            if t and callable(t.task):
                try:
                    coro = t.task()  # Try calling it with no arguments
                    if inspect.isawaitable(coro):
                        self.running_tasks.append(coro)
                    else:
                        print(f"Task returned non-awaitable: {coro}")
                except TypeError:
                    print(f"Task {t.task} requires arguments — please invoke it properly.")
            elif inspect.isawaitable(t.task):
                self.running_tasks.append(t.task)
            else:
                print(f"Task is not callable or awaitable: {t.task}")

        if self.running_tasks:
            print("# of running tasks: ", len(self.running_tasks))
            await asyncio.gather(*self.running_tasks)
        else:
            print("WARNING: no running tasks....")


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

    async def cancel_task(self, task_id: str):
        task = self.tasks[task_id]
        if task.task:
            task.task.cancel()
        task.status.state = TaskState.CANCELED

    async def schedule_task(self, task_id: str, delay: int):
        await asyncio.sleep(delay)
        await self.run_task(task_id)

    def save_task(self, task_id: str):
        task = self.tasks[task_id]
        with open(os.path.join(self.save_dir, f"{task_id}.json"), "w", encoding="utf-8") as f:
            f.write(task.model_dump_json(indent=2))

    def load_task(self, task_id: str, skill: 'EC_Skill') -> ManagedTask:
        from pydantic import TypeAdapter
        with open(os.path.join(self.save_dir, f"{task_id}.json"), "r", encoding="utf-8") as f:
            raw = f.read()
        base_task = TypeAdapter(Task).validate_json(raw)
        task = ManagedTask(**base_task.model_dump(), skill=skill)
        self.tasks[task_id] = task
        return task

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

            mainwin = AppContext.main_window
            mainwin.chat_service.push_message_to_chat(target_chat_id, msg_data)

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
            mainwin = AppContext.main_window
            mainwin.chat_service.push_message_to_chat(target_chat_id, msg_data)
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
            mainwin.chat_service.push_notification_to_chat(target_chat_id, msg_data)
        except Exception as e:
            ex_stat = "ErrorSendChat2GUI:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")


    def find_chatter_tasks(self):
        # for now, for the simplicity just find the task that's not scheduled.
        found = [task for task in self.agent.tasks if 'chatter' in task.name.lower()]
        if found:
            return found[0]
        else:
            return None

    def find_suitable_tasks(self, msg):
        # for now, for the simplicity just find the task that's not scheduled.
        found = []
        msg_js = json.loads(msg["message"])         # need , encoding='utf-8'?
        if msg_js['metadata']["mtype"] == "send_task":
            found = [task for task in self.agent.tasks if msg_js['metadata']['task']['name'].lower in task.name.lower()]
        elif msg_js['metadata']["mtype"] == "send_chat":
            found = [task for task in self.agent.tasks if "chatter task" in task.name.lower()]
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

    def _build_resume_payload(self, msg) -> dict:
        """Build a resume payload from incoming chat/task message."""
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
            return payload
        except Exception:
            return {"human_text": ""}


    async def async_task_wait_in_line(self, request):
        try:
            print("task waiting in line.....")
            await self.a2a_msg_queue.put(request)
            # self.a2a_msg_queue.put_nowait(request)
            print("task now in line....")
        except Exception as e:
            ex_stat = "ErrorWaitInLine:" + traceback.format_exc() + " " + str(e)
            print(f"{ex_stat}")

    def sync_task_wait_in_line(self, request):
        try:
            logger.debug("task waiting in line.....")
            # await self.a2a_msg_queue.put(request)
            self.a2a_msg_queue.put_nowait(request)

            logger.debug("task now in line....")
        except Exception as e:
            ex_stat = "ErrorWaitInLine:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")

    async def async_chat_wait_in_line(self, request):
        try:
            logger.debug("chat message waiting in line.....")
            await self.chat_msg_queue.put(request)
            # self.chat_msg_queue.put_nowait(request)
            logger.debug("chat now in line....")
        except Exception as e:
            ex_stat = "ErrorWaitInLine:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")

    def sync_chat_wait_in_line(self, request):
        try:
            logger.debug("chat message waiting in line.....")
            # await self.chat_msg_queue.put(request)
            self.chat_msg_queue.put_nowait(request)
            logger.debug("chat now in line....")
        except Exception as e:
            ex_stat = "ErrorWaitInLine:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")

    # this is for chat task
    # async def launch_scheduled_run(self, task=None):
    def launch_scheduled_run(self, task=None):
        while not self._stop_event.is_set():
            try:
                logger.trace("checking agent scheduled task...." + self.agent.card.name)
                # if nothing on queue, do a quick check if any vehicle needs a ping-pong check
                logger.trace("Checking schedule.....")
                task2run = time_to_run(self.agent)
                logger.trace(f"task2run: len task2run, {task2run}, {self.agent.card.name}")
                if task2run:
                    logger.debug("setting up scheduled task to run", task2run.name)
                    logger.debug("scheduled task2run skill name" + task2run.skill.name)
                    task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent)

                    logger.trace("scheduledtask2run init state" + str(task2run.metadata["state"]))
                    logger.trace("ready to run the right task" + task2run.name)
                    # response = await task2run.astream_run()
                    response = task2run.stream_run()
                    if response:
                        self.agent.a2a_server.task_manager.set_result(task2run.id, response)
                    else:
                        self.agent.a2a_server.task_manager.set_exception(task2run.id, RuntimeError("Task failed"))
                else:
                    logger.trace("schedule task not reached scheduled time yet....")
                    logger.debug("nothing 2 run according to schedule....")

            except Exception as e:
                ex_stat = "ErrorLaunchScheduledRun:" + traceback.format_exc() + " " + str(e)
                logger.error(f"{ex_stat}")

            # await asyncio.sleep(1)  # the loop goes on.....
            time.sleep(1)


    # async def launch_reacted_run(self, task=None):
    def launch_reacted_run(self, task=None):
        chatNotDone = True
        justStarted = True
        while not self._stop_event.is_set():
            try:
                logger.trace("checking a2a queue....", self.agent.card.name)

                if not self.a2a_msg_queue.empty():
                    try:
                        msg = self.a2a_msg_queue.get_nowait()
                        logger.trace("A2A message...."+ str(msg))
                        # a message could be handled by different task, so first find
                        # a task that that's suitable to handle this message,
                        matched_tasks = self.find_suitable_tasks(msg.params)
                        logger.trace("matched task...." + len(matched_tasks))
                        # then run this skill's runnable with the msg
                        if matched_tasks:
                            task2run = matched_tasks[0]
                            if task2run:
                                if justStarted:
                                    logger.debug("task2run skill name" + task2run.skill.name)
                                    task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent, None)

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
                                    task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent, task2run.metadata["state"])

                                    logger.trace("task2run init state" + str(task2run.metadata["state"]))
                                    logger.trace("ready to run the right task" + task2run.name + str(msg))
                                    # response = await task2run.astream_run()
                                    response = task2run.stream_run()
                                    logger.debug("NI, resume tick", response)
                                    # Resume with the user's reply using Command(resume=...)
                                    resume_payload = self._build_resume_payload(msg)
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
                        self.a2a_msg_queue.task_done()

                        # process msg here and the msg could be start a task run.
                    except asyncio.QueueEmpty:
                        logger.info("Queue unexpectedly empty when trying to get message.")
                        pass
                    except Exception as e:
                        logger.error(f"Error processing Commander message: {e}")


            except Exception as e:
                ex_stat = "ErrorLaunchReactedRun:" + traceback.format_exc() + " " + str(e)
                logger.error(f"{ex_stat}")

            # await asyncio.sleep(1)  # the loop goes on.....
            time.sleep(1)


    # this is for chat task
    # async def launch_interacted_run(self, task=None):
    def launch_interacted_run(self, task=None):
        cached_human_responses = ["hi!", "rag prompt", "1 rag, 2 none, 3 no, 4 no", "red", "q"]
        cached_response_index = 0
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        justStarted = True
        logger.debug("launch_interacted_run....", self.agent.card.name)
        while not self._stop_event.is_set():
            try:
                logger.debug("checking chat queue...." + self.agent.card.name)
                logger.trace("checking chat queue...." + self.agent.card.name)
                thread_config = {"configurable": {"thread_id": uuid.uuid4()}}
                if not self.chat_msg_queue.empty():
                    try:
                        msg = self.chat_msg_queue.get_nowait()
                        logger.debug("chat queue message....", type(msg), msg)
                        task2run = self.find_chatter_tasks()
                        task2run_details = str(task2run.to_dict())
                        logger.debug("matched chatter task.... %s", (task2run_details[:100] + '...') if len(task2run_details) > 100 else task2run_details)
                        if task2run:
                            if justStarted:
                                logger.debug("chatter task2run skill name", task2run.skill.name)
                                task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent, msg, None)
                                logger.trace("interacted task2run init state", task2run.metadata["state"])
                                logger.debug("ready to run the right task", task2run.name, type(msg), msg)
                                response = task2run.stream_run()
                                logger.debug("ineracted task run response:", response)
                                logger.debug("sending interrupt prompt1")
                                step = response.get('step') or {}
                                if isinstance(step, dict) and '__interrupt__' in step:
                                    logger.debug("sending interrupt prompt2")
                                    interrupt_obj = step["__interrupt__"][0]
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
                                        logger.error("ERROR: lost track of task id....", msg)
                                self.agent.a2a_server.task_manager.resolve_waiter(task_id, response)
                            else:
                                logger.debug(f"interacted {task2run.skill.name} no longer initial run", msg)
                                task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent, msg, task2run.metadata["state"])
                                logger.debug("NI interacted task2run current state", task2run.metadata["state"])
                                resume_payload = self._build_resume_payload(msg)
                                logger.debug("NI resume payload", resume_payload)

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
                                if not isinstance(msg, dict):
                                    task_id = msg.params.id
                                else:
                                    if "id" in msg['params']:
                                        task_id = msg['params']['id']
                                    elif "id" in msg:
                                        task_id = msg['id']
                                    else:
                                        logger.error("ERROR: lost track of task id....", msg)
                                self.agent.a2a_server.task_manager.resolve_waiter(task_id, response)

                        self.chat_msg_queue.task_done()
                    except asyncio.QueueEmpty:
                        logger.info("Queue unexpectedly empty when trying to get message.")
                        pass
                    except Exception as e:
                        logger.error(f"Error launch interacted run: {e}" + traceback.format_exc())
                else:
                    logger.debug("no chat message")
                    time.sleep(1)
            except Exception as e:
                ex_stat = "ErrorLaunchInteractedRun:" + traceback.format_exc() + " " + str(e)
                logger.error(f"{ex_stat}")
            time.sleep(1)

    def launch_dev_run(self, init_state, task: ManagedTask = None):
        """
        Executes a controlled, interactive development run for a given task,
        allowing for pausing, resuming, and single-stepping from the GUI.
        """
        web_gui = AppContext.get_web_gui()
        ipc_api = web_gui.get_ipc_api()
        if not task:
            logger.error("launch_dev_run called without a task.")
            return

        logger.info(f"Launching interactive dev run for task: {task.name} with run_id: {task.run_id}")

        try:
            context = {
                "id": str(uuid.uuid4()),
                "topic": "",
                "summary": "",
                "msg_thread_id": "",
                "tot_context": {},
                "app_context": {},
                "this_node": {"name": ""},
            }

            # Create a unique thread_id for the checkpointer
            thread_id = str(uuid.uuid4())
            config = {
                "configurable": {"thread_id": thread_id}
                # Breakpoints are now handled at the node level using the interrupt() function
            }

            # Start the stream with the correct config, and initial state
            controller = task.skill.runnable.stream(init_state, context=context, config=config)

            # Get the iterator for the stream
            stream_iterator = iter(controller)
            paused_at_node = "start"
            print("about to enter a black hole.........")
            # Initialize the loop state
            run_status = "running"
            current_node = "start"
            event = None
            
            while not task.cancellation_event.is_set():
                try:
                    print("in the task loop now.....")

                    # Only advance the stream if we're running (not paused)
                    if run_status == "running":
                        # Get a clean state that can be JSON serialized
                        try:
                            clean_state = task.skill.runnable.get_state(config=config)
                            if hasattr(clean_state, 'values') and isinstance(clean_state.values, dict):
                                serializable_state = clean_state.values
                            else:
                                serializable_state = {}
                        except Exception as e:
                            logger.warning(f"Could not get clean running state: {e}")
                            serializable_state = {}
                            
                        ipc_api.update_run_stat(
                            agent_task_id=task.run_id,
                            current_node=current_node,
                            status="running",
                            langgraph_state=serializable_state
                        )

                        # Advance the graph by one step
                        try:
                            event = next(stream_iterator, None)
                        except Exception as e:
                            # Handle any interrupt signal from the node-level interrupt() function
                            logger.info(f"Interrupt caught: {type(e).__name__}: {e}")
                            if hasattr(e, 'values'):
                                event = e.values
                            else:
                                # If it's a different type of interrupt, create a pause event
                                event = {"paused_at": "unknown", "interrupt_type": type(e).__name__}
                            logger.info(f"Breakpoint triggered, pausing execution")

                        # Check if the stream has ended
                        if event is None:
                            logger.info(f"Dev run for {task.name} has completed.")
                            # Get a clean state for completion
                            try:
                                clean_state = task.skill.runnable.get_state(config=config)
                                if hasattr(clean_state, 'values') and isinstance(clean_state.values, dict):
                                    serializable_state = clean_state.values
                                else:
                                    serializable_state = {}
                            except Exception as e:
                                logger.warning(f"Could not get clean completion state: {e}")
                                serializable_state = {}
                            
                            ipc_api.update_run_stat(
                                agent_task_id=task.run_id,
                                current_node=None,
                                status="completed",
                                langgraph_state=serializable_state
                            )
                            break

                        # Check if the event contains an interrupt signal
                        if isinstance(event, dict) and '__interrupt__' in event:
                            # Extract the interrupt data
                            interrupt_tuple = event['__interrupt__']
                            if interrupt_tuple and len(interrupt_tuple) > 0:
                                interrupt_obj = interrupt_tuple[0]
                                if hasattr(interrupt_obj, 'value') and isinstance(interrupt_obj.value, dict):
                                    paused_at_node = interrupt_obj.value.get('paused_at', 'unknown')
                                    logger.info(f"Execution paused at node: {paused_at_node}")
                                    run_status = "paused"
                                    current_node = paused_at_node
                                else:
                                    run_status = "paused"
                                    current_node = "unknown"
                            else:
                                run_status = "paused"
                                current_node = "unknown"
                        elif isinstance(event, dict) and 'paused_at' in event:
                            paused_at_node = event.get('paused_at')
                            logger.info(f"Execution paused at node: {paused_at_node}")
                            run_status = "paused"
                            current_node = paused_at_node
                        else:
                            # Continue running to next node
                            run_status = "running"
                            current_node = ""

                    # Get a clean state that can be JSON serialized
                    try:
                        clean_state = task.skill.runnable.get_state(config=config)
                        # Ensure the state is JSON serializable by removing any problematic objects
                        if hasattr(clean_state, 'values') and isinstance(clean_state.values, dict):
                            serializable_state = clean_state.values
                        else:
                            serializable_state = {}
                    except Exception as e:
                        logger.warning(f"Could not get clean state: {e}")
                        serializable_state = {}

                    # Post-run notification: Tell the GUI where we are now
                    print("current event:", event)
                    ipc_api.update_run_stat(
                        agent_task_id=task.run_id,
                        current_node=current_node,
                        status=run_status,
                        langgraph_state=serializable_state
                    )


                    # If we're paused, wait for a command from the GUI
                    if run_status == "paused":
                        try:
                            command = self.dev_msg_queue.get(timeout=0.3)  # Timeout to prevent deadlocks
                            logger.debug(f"Dev run ({task.run_id}) received queue command: {command}")
                        except:
                            # No command received - stay paused and don't advance the stream
                            logger.debug(f"No command received, staying paused at {current_node}")
                            continue
                    else:
                        # If not paused, continue normal execution
                        command = "step"

                    # Process the command
                    if command == "step":
                        logger.info(f"Stepping execution from {current_node}")
                        run_status = "running"  # Will advance stream on next iteration
                        # Resume the graph from its current state
                        logger.info(f"Creating new stream to resume from current state")
                        controller = task.skill.runnable.stream(None, context=context, config=config)
                        stream_iterator = iter(controller)
                        continue
                    elif command == "resume":
                        logger.info(f"Resuming execution from {current_node}")
                        # Use LangGraph's proper Command(resume=...) pattern like the working code
                        resume_payload = {"_resuming_from": current_node}
                        logger.info(f"DEBUG: Resume payload = {resume_payload}")
                        # Ensure we reuse the SAME thread_id/config to truly resume from the interrupt
                        cfg_thread = None
                        try:
                            cfg_thread = config.get("configurable", {}).get("thread_id") if isinstance(config, dict) else None
                        except Exception:
                            cfg_thread = None
                        logger.info(f"DEBUG: Using thread_id for resume: {cfg_thread}")
                        # Also inject a one-shot skip list into the runtime context so the node builder can skip the breakpoint once
                        if context is None:
                            context = {}
                        try:
                            skip_list = context.get("skip_bp_once", [])
                            if current_node not in skip_list:
                                if isinstance(skip_list, list):
                                    skip_list.append(current_node)
                                else:
                                    skip_list = [current_node]
                            context["skip_bp_once"] = skip_list
                            logger.info(f"DEBUG: Updated context.skip_bp_once = {context['skip_bp_once']}")
                        except Exception as _e:
                            logger.warning(f"Failed to update context.skip_bp_once: {_e}")
                        
                        # Use the same pattern as the working code around line 1126, but pass config/context
                        response = task.stream_run(Command(resume=resume_payload), stream_mode="updates", config=config, context=context)
                        logger.info(f"DEBUG: Resume response = {response}")
                        
                        # Check if we got a step back and handle it
                        step = response.get('step') or {}
                        if isinstance(step, dict) and '__interrupt__' in step:
                            # Still interrupted, continue the loop
                            logger.info(f"Still interrupted after resume, continuing loop")
                            event = step
                            current_node = event["__interrupt__"][0].value.get("paused_at", current_node)
                            run_status = "paused"
                        else:
                            # Successfully resumed and completed
                            logger.info(f"Resume completed successfully")
                            run_status = "completed"
                            break
                        continue
                    elif command == "cancel":
                        task.cancel()
                        logger.info(f"Dev run cancelled by user")
                        break
                    elif command == "pause":
                        # Already paused, just continue waiting
                        continue

                except queue.Empty:
                    logger.warning(f"Dev run for {task.name} timed out waiting for GUI command. It might be stuck.")
                    continue
                except StopIteration:
                    logger.debug(f"Dev run for {task.name} has completed.")
                    ipc_api.update_run_stat(
                        agent_task_id=task.run_id,
                        current_node=None,
                        status="completed",
                        langgraph_state={}
                    )
                    break
            print("dev run ENDED...........")
        except Exception as e:
            err_msg = get_traceback(e, "ErrorLaunchDevRun")
            logger.error(f"Exception during launch_dev_run for task {task.name}: {err_msg}")
            ipc_api.update_run_stat(
                agent_task_id=task.run_id,
                current_node=paused_at_node,
                status="failed",
                langgraph_state={"error": str(e)}
            )
            raise
        finally:
            # Flush any remaining commands from the queue to ensure a clean state for the next run
            logger.info(f"Flushing dev message queue for task {task.run_id}.")
            while not self.dev_msg_queue.empty():
                try:
                    self.dev_msg_queue.get_nowait()
                except queue.Empty:
                    break
            logger.info("Dev message queue flushed.")

    def resume_dev_run(self):
        """Sends the 'resume' command to the running dev task."""
        logger.info("Sending 'resume' command to dev run task.")
        try:
            self.dev_msg_queue.put_nowait("resume")
            return {"success": True}
        except queue.Full:
            logger.error("Development message queue is full. Cannot send 'resume' command.")
            return {"success": False, "error": "Queue full"}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorResumeDevRunTask")
            logger.error(err_msg)
            return {"success": False, "error": err_msg}

    def step_dev_run(self):
        """Sends the 'step' command to the running dev task."""
        logger.info("Sending 'step' command to dev run task.")
        try:
            self.dev_msg_queue.put_nowait("step")
            return {"success": True}
        except queue.Full:
            logger.error("Development message queue is full. Cannot send 'step' command.")
            return {"success": False, "error": "Queue full"}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorStepDevRunTask")
            logger.error(err_msg)
            return {"success": False, "error": err_msg}

    def pause_dev_run(self):
        """
        Note: Pausing is the default state. This function is a placeholder
        in case you need to send an explicit 'pause' command for other reasons.
        """
        logger.info("Sending 'pause' command to dev run task.")
        try:
            self.dev_msg_queue.put_nowait("pause")
            return {"success": True}
        except queue.Full:
            logger.error("Development message queue is full. Cannot send 'pause' command.")
            return {"success": False, "error": "Queue full"}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorPauseDevRunTask")
            logger.error(err_msg)
            return {"success": False, "error": err_msg}


    def cancel_dev_run(self):
        """Sends the 'cancel' command to the running dev task."""
        logger.info("Sending 'cancel' command to dev run task.")
        try:
            self.dev_msg_queue.put_nowait("cancel")
            return {"success": True}
        except queue.Full:
            logger.error("Development message queue is full. Cannot send 'cancel' command.")
            return {"success": False, "error": "Queue full"}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorCancelDevRunTask")
            logger.error(err_msg)
            return {"success": False, "error": err_msg}


    def inject_state_dev_run(self, in_state):
        logger.debug("resume dev run")
        # set current langgraph nodeState to be in_state, and then resume run.
        self.bp_manager.resume()

    def get_dev_run_state(self):
        run_state = {}
        return run_state

    def set_bps_dev_skill(self, bps):
        self.bp_manager.set_breakpoints(bps)

    def clear_bps_dev_skill(self, bps):
        self.bp_manager.clear_breakpoints(bps)

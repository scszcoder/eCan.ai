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

from datetime import datetime, timedelta
import inspect
import traceback
from datetime import datetime, timedelta
from calendar import monthrange
from langgraph.types import interrupt, Command
from app_context import AppContext
from utils.logger_helper import logger_helper as logger
# from agent.chats.tests.test_notifications import *
from langgraph.types import Interrupt


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
    resume_from: Optional[str] = None
    trigger: Optional[str] = None
    task: Optional[asyncio.Task] = None
    pause_event: asyncio.Event = asyncio.Event()
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
            "sessionId": self.sessionId,
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

    # from langgraph.types import Command

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
        self.running_tasks = []
        self.save_dir = os.path.join(agent.mainwin.my_ecb_data_homepath, "task_saves")
        os.makedirs(self.save_dir, exist_ok=True)
        # self.a2a_msg_queue = asyncio.Queue()
        # self.chat_msg_queue = asyncio.Queue()
        self.a2a_msg_queue = queue.Queue()
        self.chat_msg_queue = queue.Queue()
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

    def launch_dev_run(self, task=None):
        chatNotDone = True
        justStarted = True
        while not self._stop_event.is_set():
            try:
                logger.trace("checking a2a queue....", self.agent.card.name)

                if not self.a2a_msg_queue.empty():
                    try:
                        msg = self.a2a_msg_queue.get_nowait()
                        logger.trace("A2A message...." + str(msg))
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
                                        interrupt_obj = step["__interrupt__"][
                                            0]  # [0] because it's a tuple with one item
                                        prompt = interrupt_obj.value["prompt_to_human"]
                                        # now return this prompt to GUI to display
                                        chatId = msg.params.metadata['chatId']
                                        self.sendChatMessageToGUI(self.agent, chatId, prompt)
                                        justStarted = False
                                    else:
                                        justStarted = True
                                else:
                                    logger.debug("task2run skill name" + task2run.skill.name)
                                    task2run.metadata["state"] = prep_skills_run(task2run.skill.name, self.agent,
                                                                                 task2run.metadata["state"])

                                    logger.trace("task2run init state" + str(task2run.metadata["state"]))
                                    logger.trace("ready to run the right task" + task2run.name + str(msg))
                                    # response = await task2run.astream_run()
                                    response = task2run.stream_run()
                                    logger.debug("NI, resume tick", response)
                                    # Resume with the user's reply using Command(resume=...)
                                    resume_payload = self._build_resume_payload(msg)
                                    response = task2run.stream_run(Command(resume=resume_payload),
                                                                   stream_mode="updates")
                                    logger.debug("NI reacted task resume response:", response)

                                    step = response.get('step') or {}
                                    if isinstance(step, dict) and '__interrupt__' in step:
                                        logger.trace("sending interrupt prompt2")
                                        interrupt_obj = step["__interrupt__"][
                                            0]  # [0] because it's a tuple with one item
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
                                            self.sendChatFormToGUI(self.agent, chatId,
                                                                   interrupt_obj.value.get["qa_form_to_human"])
                                        elif interrupt_obj.value.get("notification_to_agent", None):
                                            self.sendChatNotificationToGUI(self.agent, chatId, interrupt_obj.value.get[
                                                "notification_to_human"])

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

    def resume_dev_run(self, skill_runnable):
        for event in skill_runnable.stream({"x": 0}):
            if isinstance(event, dict):
                print("State:", event)

            elif isinstance(event, Interrupt):
                print(f"⏸ Paused at node {event.value['at']} with state {event.value['state']}")
                # resume control
                event.resume()

        logger.debug("resume dev run")

    def step_dev_run(self):
        logger.debug("resume dev run")

    def cancel_dev_run(self):
        logger.debug("resume dev run")

    def pause_dev_run(self):
        logger.debug("resume dev run")

    def inject_state_dev_run(self):
        logger.debug("resume dev run")

    def get_dev_run_state(self):
        run_state = {}
        return run_state

# Remaining application code continues here...
# (not repeating routing/app setup for brevity)


# cached_human_responses = ["hi!", "rag prompt", "1 rag, 2 none, 3 no, 4 no", "red", "q"]
# cached_response_index = 0
# config = {"configurable": {"thread_id": str(uuid.uuid4())}}
# while True:
#     try:
#         user = input("User (q/Q to quit): ")
#     except:
#         user = cached_human_responses[cached_response_index]
#         cached_response_index += 1
#     print(f"User (q/Q to quit): {user}")
#     if user in {"q", "Q"}:
#         print("AI: Byebye")
#         break
#     output = None
#     for output in graph.stream(
#         {"messages": [HumanMessage(content=user)]}, config=config, stream_mode="updates"
#     ):
#         last_message = next(iter(output.values()))["messages"][-1]
#         last_message.pretty_print()
#
#     if output and "prompt" in output:
#         print("Done!")
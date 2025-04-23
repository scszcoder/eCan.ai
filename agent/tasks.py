import asyncio
from typing import Any, Dict, List, Literal, Optional, Type, Generic, Tuple, TypeVar, cast
from pydantic import ConfigDict, BaseModel
import uuid
from agent.a2a.common.types import *
from agent.ec_skill import EC_Skill
import os
from datetime import datetime, timedelta
import inspect
import traceback
from datetime import datetime, timedelta
from calendar import monthrange
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
    skill: EC_Skill
    state: dict
    resume_from: Optional[str] = None
    trigger: Optional[str] = None
    task: Optional[asyncio.Task] = None
    pause_event: asyncio.Event = asyncio.Event()
    schedule: Optional[TaskSchedule] = None
    checkpoint_nodes: Optional[List[str]] = None
    priority: Optional[Priority_Types] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pause_event.set()
        self.priority = Priority_Types.LOW
        if self.checkpoint_nodes is None:
            self.checkpoint_nodes = []

    def set_priority(self, p):
        self.priority = p

    def add_checkpoint_node(self, cp_name):
        if cp_name not in self.checkpoint_nodes:
            self.checkpoint_nodes.append(cp_name)

    def remove_checkpoint_node(self, cp_name):
        if cp_name in self.checkpoint_nodes:
            self.checkpoint_nodes.remove(cp_name)

    async def astream_run(self):
        async for step in self.skill.runnable.astream(self.metadata.get("state", {})):
            await self.pause_event.wait()
            self.status.message = Message(role="agent", parts=[Part(type="text", text=str(step))])
            if step.get("require_user_input") or step.get("await_agent"):
                self.status.state = TaskState.INPUT_REQUIRED
                return
        self.status.state = TaskState.COMPLETED


    async def create_scheduler_task(self):
        self.task = asyncio.create_task(self.scheduled_run())

    def exit(self):
        if self.task and not self.task.done():
            self.task.cancel()

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

    start_time = datetime.strptime(schedule.start_date_time, fmt)
    end_time = datetime.strptime(schedule.end_date_time, fmt)
    repeat_number = int(schedule.repeat_number)

    if schedule.repeat_type == Repeat_Types.NONE:
        return start_time, False  # ⛔ Never auto-run
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

# sort t2rs by start time, the earliest will be run first.
def time_to_run(agent):
    t2r = None
    t2rs = []
    for task in agent.tasks:
        next_run_time, should_run = get_next_runtime(task.schedule)
        if should_run:
            t2rs.append({"rt": next_run_time, "task": task})

    if not t2rs:
        return None  # no tasks ready to run

    # ✅ Sort the list by run time (earliest first)
    t2rs.sort(key=lambda x: x["rt"])

    now = datetime.now()
    if now >= t2rs[0]["rt"]:
        return t2rs[0]

    return None

class TaskRunner(Generic[Context]):
    def __init__(self, agent):  # includes persistence methods
        self.agent = agent
        self.tasks: Dict[str, ManagedTask] = {}
        self.running_tasks = []
        self.save_dir = "./task_saves"
        os.makedirs(self.save_dir, exist_ok=True)
        self.msg_queue = asyncio.Queue()
        self._stop_event = asyncio.Event()


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
                        print(f"⚠️ Task returned non-awaitable: {coro}")
                except TypeError:
                    print(f"⚠️ Task {t.task} requires arguments — please invoke it properly.")
            elif inspect.isawaitable(t.task):
                self.running_tasks.append(t.task)
            else:
                print(f"⚠️ Task is not callable or awaitable: {t.task}")

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

    async def wait_in_line(self, request):
        try:
            print("waiting in line.....")
            await self.msg_queue.put(request)
            print("now in line....")
        except Exception as e:
            ex_stat = "ErrorWaitInLine:" + traceback.format_exc() + " " + str(e)
            print(f"{ex_stat}")

    async def launch_scheduled_run(self):
        while not self._stop_event.is_set():
            try:
                print("checking a2a queue....")

                if not self.msg_queue.empty():
                    try:
                        msg = self.msg_queue.get_nowait()
                        print("A2A message....", msg)
                        self.msg_queue.task_done()

                        # process msg here and the msg could be start a task run.
                    except asyncio.QueueEmpty:
                        print("Queue unexpectedly empty when trying to get message.")
                        pass
                    except Exception as e:
                        print(f"Error processing Commander message: {e}")
                else:
                    # if nothing on queue, do a quick check if any vehicle needs a ping-pong check
                    print("Checking schedule.....")
                    task2run = time_to_run(self.agent)
                    print("len task2run", task2run)
                    if task2run:
                        response = await task2run.astream_run()
                        if response:
                            self.agent.a2a_server.task_manager.set_result(task2run.id, response)
                        else:
                            self.agent.a2a_server.task_manager.set_exception(task2run.id, RuntimeError("Task failed"))
                    else:
                        print("nothing 2 run")

            except Exception as e:
                ex_stat = "ErrorWaitInLine:" + traceback.format_exc() + " " + str(e)
                print(f"{ex_stat}")

            await asyncio.sleep(1)  # the loop goes on.....

# Remaining application code continues here...
# (not repeating routing/app setup for brevity)

import asyncio
from typing import Any, Dict, List, Literal, Optional, Type, Generic, Tuple, TypeVar, cast
from pydantic import ConfigDict, BaseModel
import uuid
from agent.a2a.common.types import *
from agent.ec_skill import EC_Skill
import os
from datetime import datetime, timedelta

class TaskSchedule(BaseModel):
    repeat_cycle: int
    repeat_unit: str
    start_date_time: str
    end_date_time: str
    time_out: str


class ManagedTask(Task):
    skill: EC_Skill
    state: dict
    resume_from: Optional[str] = None
    trigger: Optional[str] = None
    task: Optional[asyncio.Task] = None
    pause_event: asyncio.Event = asyncio.Event()
    schedule: Optional[TaskSchedule] = None
    msg_queue: asyncio.Queue = asyncio.Queue()
    checkpoint_nodes: Optional[List[str]] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pause_event.set()
        if self.checkpoint_nodes is None:
            self.checkpoint_nodes = []

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

    async def scheduled_run(self):
        while True:
            print("listening to platoons")

            if not self.msg_queue.empty():
                try:
                    msg = self.msg_queue.get_nowait()
                    print("A2A message....", msg)
                    self.msg_queue.task_done()

                except asyncio.QueueEmpty:
                    print("Queue unexpectedly empty when trying to get message.")
                    pass
                except Exception as e:
                    print(f"Error processing Commander message: {e}")
            else:
                # if nothing on queue, do a quick check if any vehicle needs a ping-pong check
                if self.time_to_run():
                    await self.astream_run()
            await asyncio.sleep(1)  # Short sleep to avoid busy-waiting

    async def create_scheduler_task(self):
        self.task = asyncio.create_task(self.scheduled_run())

    def exit(self):
        if self.task and not self.task.done():
            self.task.cancel()

from agent.a2a.common.types import TaskSendParams, TextPart
Context = TypeVar('Context')

class TaskRunner(Generic[Context]):
    def __init__(self, agent):  # includes persistence methods
        self.agent = agent
        self.tasks: Dict[str, ManagedTask] = {}
        self.running_tasks = []
        self.save_dir = "./task_saves"
        os.makedirs(self.save_dir, exist_ok=True)
        self.agent = None

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


    async def run_all_tasks(self):
        self.running_tasks = [task.task for task in self.agent.tasks]
        await asyncio.gather(*self.running_tasks)


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

# Remaining application code continues here...
# (not repeating routing/app setup for brevity)

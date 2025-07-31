import asyncio
from typing import Any, Dict, List, Literal, Optional, Type, Generic, Tuple, TypeVar, cast
from pydantic import ConfigDict, BaseModel
import uuid
from agent.ec_skill import EC_Skill
import os

from datetime import datetime, timedelta
import inspect
import traceback
from datetime import datetime, timedelta
from calendar import monthrange

Context = TypeVar('Context')
class HumanChatter(Generic[Context]):
    def __init__(self, agent):  # includes persistence methods
        self.agent = agent
        self.history: str="chat_his"
        self.save_dir = os.path.join(agent.mainwin.my_ecb_data_homepath, "task_saves")
        os.makedirs(self.save_dir, exist_ok=True)
        self.human_msg_queue = asyncio.Queue()            # queue for the message from agent to human.


    def assign_agent(self, agent):
        self.agent = agent

    async def launch_human_chatter(self):
        while not self._stop_event.is_set():
            try:
                print("checking a2a queue....", self.agent.card.name)

                if not self.msg_queue.empty():
                    try:
                        msg = self.msg_queue.get_nowait()
                        print("A2A message....", msg)
                        # a message could be handled by different task, so first find
                        # a task that that's suitable to handle this message,
                        matched_tasks = self.find_suitable_tasks(msg)
                        print("matched task....", len(matched_tasks))
                        # then run this skill's runnable with the msg
                        if matched_tasks:
                            task2run = matched_tasks[0]
                            task2run.metadata["state"] = {
                                "messages": [self.agent, msg]
                            }
                            print("ready to run the right task", task2run.name, msg)
                            response = await task2run.astream_run()
                            print("task run response:", response)
                            task_id = msg.params.id
                            self.agent.a2a_server.task_manager.resolve_waiter(task_id, response)
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
                    print(f"len task2run, {task2run}, {self.agent.card.name}")
                    if task2run:
                        task2run.metadata["state"] = {
                            "messages": [self.agent]
                        }
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
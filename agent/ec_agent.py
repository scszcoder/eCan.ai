from __future__ import annotations
import traceback
import asyncio
from typing import Dict, List, Optional
from dotenv import load_dotenv
from queue import Queue

from agent.models import *
from agent.a2a.common.client import A2AClient
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.common.types import Message, TextPart, FilePart, FileContent, TaskSendParams

from browser_use.agent.service import Agent
from agent.ec_skill import EC_Skill
from agent.run_utils import time_execution_sync
from agent.tasks import TaskRunner, ManagedTask
from agent.human_chatter import *
import threading
import concurrent.futures
import base64
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.db.services.db_avatar_service import DBAvatarService


load_dotenv()




class EC_Agent(Agent):
	@time_execution_sync('--init (agent)')
	def __init__(
		self,
		mainwin,  # Add mainwin parameter
		skill_llm,
		tasks: Optional[List[ManagedTask]] = None,
		# Optional parameters
		skills: Optional[List[EC_Skill]] = None,
		card: AgentCard | None = None,
		supervisor_id: Optional[str] = None,
		rank: Optional[str] = None,
		org_id: Optional[str] = None,
		title: Optional[str] = None,
		gender: Optional[str] = None,
		birthday: Optional[str] = None,
		personalities: Optional[List[str]] = None,
		vehicle: Optional[str] = None,
		avatar: Optional[Dict] = None,
		*args,
		**kwargs
	):
		# Core components
		self.tasks = tasks
		self.skill_llm = skill_llm
		self.active_tasks: Dict[str, concurrent.futures.Future] = {}
		self.task_lock = threading.Lock()
		self.skills = skills if skills is not None else []  # Use skills (unified naming)
		self._stop_event = asyncio.Event()
		
		# Save card before calling super().__init__() to ensure it's preserved
		self.card = card

		# Agent properties
		self.supervisor_id = supervisor_id
		self.rank = rank if rank is not None else ""
		# Note: subordinates can be queried via supervisor_id reverse lookup
		# Note: peers relationship not yet implemented
		self.org_id = org_id
		self.title = title if title is not None else ""
		self.gender = gender if gender is not None else "m"
		self.birthday = birthday if birthday is not None else "2000-01-01"
		self.personalities = personalities if personalities is not None else []  # Use personalities (unified naming)
		self.vehicle = vehicle if vehicle is not None else ""
		self.status = "active"
		self.images = [{"image_name":"", "image_source":"","text":""}]
		self.avatar = avatar or (DBAvatarService.generate_default_avatar(card.id) if card else None)

		# Auto-detect model vision support and set use_vision accordingly to avoid warnings
		if 'use_vision' not in kwargs:
			from agent.ec_skills.llm_utils.llm_utils import get_use_vision_from_llm
			llm = kwargs.get('llm')
			kwargs['use_vision'] = get_use_vision_from_llm(llm, context="EC_Agent")

		super().__init__(*args, **kwargs)
		# Configure extraction
		from agent.memory.service import MemoryManager

		self.mem_manager = MemoryManager(agent_id=self.card.id, llm=self.skill_llm)

		# LLM API connection setup: do not enforce environment variables.
		# Provider-specific factories will read keys from secure_store when needed.


		# Start non-blocking LLM connection verification
		# Show first 8 and last 4 characters, mask the middle
		# openai_api_key: str = os.getenv("OPENAI_API_KEY")
		# if openai_api_key and len(openai_api_key) > 12:
		# 	mask_openai_api_key = openai_api_key[:8] + "*" * (len(openai_api_key) - 12) + openai_api_key[-4:]
		# elif openai_api_key:
		# 	mask_openai_api_key = openai_api_key[:2] + "*" * (len(openai_api_key) - 2)
		# else:
		# 	mask_openai_api_key = "Not set"
		# logger.info("OPENAI API KEY IS::::::::", mask_openai_api_key)


		# Extract port from Card URL (already allocated during card creation)
		# This avoids duplicate port allocation
		try:
			a2a_server_port = int(card.url.split(":")[-1].split("/")[0])
		except (ValueError, IndexError):
			logger.error(f"Failed to extract port from card URL: {card.url}")
			return None
		
		self.mainwin = mainwin
		self.card = card
		server_host = "0.0.0.0"  # Bind to all interfaces for both local and remote access
		
		self.a2a_client = A2AClient(self.card)
		notification_sender_auth = PushNotificationSenderAuth()
		notification_sender_auth.generate_jwk()
		self.a2a_server = A2AServer(
			agent_card=self.card,
			task_manager=AgentTaskManager(notification_sender_auth=notification_sender_auth),
			host=server_host,
			port=a2a_server_port,
			endpoint="/a2a/",
		)
		self.a2a_server.attach_agent(self)
		self.a2a_msg_queue = Queue()

		self.runner = TaskRunner(self)
		self.human_chatter = HumanChatter(self)




	def to_dict(self, owner: str = None):
		"""
		Convert agent to dict for frontend/API consumption
		
		Unified serialization that matches DBAgent.to_dict() structure
		to ensure consistency across the application.
		
		Args:
			owner: Optional owner username/email to include in the dict
		
		Returns:
			dict: Agent structure compatible with frontend expectations
		"""
		# Helper function to serialize skills/tasks
		def serialize_items(items):
			result = []
			if items:
				for item in items:
					if hasattr(item, 'to_dict'):
						result.append(item.to_dict())
					elif isinstance(item, dict):
						result.append(item)
					elif isinstance(item, str):
						result.append({'id': item, 'name': item})
			return result
		
		# Build the unified structure
		return {
			# Card information (nested for frontend compatibility)
			'card': self.card_to_dict(self.card) if self.card else {},

			# Agent profile
			'id': self.card.id if self.card else None,
			'name': self.card.name if self.card else '',
			'description': getattr(self, 'description', ''),
			'owner': owner or getattr(self, 'owner', None),
			'gender': getattr(self, 'gender', 'male'),
			'birthday': getattr(self, 'birthday', None),

			# Organization and hierarchy
			'org_id': self.org_id,
			'supervisor_id': self.supervisor_id,
			'rank': self.rank,

			# Agent characteristics
			'title': self.title,
			'personalities': self.personalities or [],
			# Use _db_skills/_db_tasks if available (from database), otherwise serialize runtime skills/tasks
			'skills': getattr(self, '_db_skills', []) or serialize_items(getattr(self, 'skills', [])),
			'tasks': getattr(self, '_db_tasks', []) or serialize_items(getattr(self, 'tasks', [])),

			# Configuration
			'vehicle_id': getattr(self, 'vehicle_id', None),
			'status': getattr(self, 'status', 'active'),
			# Avatar: 确保返回字典格式，如果是字典则直接返回，否则返回 None
			'avatar': self.avatar if isinstance(self.avatar, dict) else None,
			'extra_data': getattr(self, 'extra_data', ''),
		}

	def card_to_dict(self, card):
		cardJS = {
			"name": card.name,
			"id": card.id,
			"description": card.description,
			"url": card.url,
			"provider": card.provider,
			"version": card.version,
			"documentationUrl": card.documentationUrl,
			"capabilities": card.capabilities.dict(),
			"authentication": card.authentication,
			"defaultInputModes": card.defaultInputModes,
			"defaultOutputModes": card.defaultOutputModes,
			# "skills": card.skills
		}
		return cardJS


	def add_tasks(self, tasks):
		self.tasks += tasks  # or: self.tasks.extend(tasks)

	def remove_tasks(self, tasks):
		self.tasks = [t for t in self.tasks if t not in tasks]

	def update_tasks(self, tasks):
		# Replace existing tasks with same ID or append if new
		task_ids = {t.id for t in tasks}
		self.tasks = [t for t in self.tasks if t.id not in task_ids] + tasks

	def get_work_msg_queue(self):
		chat_task = next((task for task in self.tasks if task and "work" in task.name.lower()), None)
		if chat_task:
			return chat_task.queue
		else:
			return None

	def get_chat_msg_queue(self):
		chat_task = next((task for task in self.tasks if task and "chat" in task.name.lower()), None)
		if chat_task:
			return chat_task.queue
		else:
			return None

	def add_skills(self, skills):
		self.skills += skills  # or: self.skills.extend(skills)

	def remove_skills(self, skills):
		self.skills = [s for s in self.skills if s not in skills]

	def update_skills(self, skills):
		skill_ids = {s.id for s in skills}
		self.skills = [s for s in self.skills if s.id not in skill_ids] + skills

	def set_skill_llm(self, llm):
		self.skill_llm = llm

	def set_llm(self, llm):
		self.llm = llm

	def get_card(self):
		return self.card

	def get_a2a_server_port(self):
		"""Get the A2A server port number"""
		return int(self.a2a_server.agent_card.url.split(":")[-1])

	def get_vehicle(self):
		return self.vehicle

	def is_busy(self):
		busy = False
		return busy

	def start_a2a_server_in_thread(self, a2a_server):
		"""Start A2A server in a daemon thread"""
		def run_server():
			try:
				a2a_server.start()
			except Exception as e:
				logger.error(f"[{self.card.name}] A2A server error: {e}")
				import traceback
				logger.error(traceback.format_exc())

		self.a2a_server_thread = threading.Thread(target=run_server, name=f"A2A-{self.card.name}")
		self.a2a_server_thread.daemon = True
		self.a2a_server_thread.start()

	def exit_a2a_server_in_thread(self):
		if self.a2a_server_thread and self.a2a_server_thread.is_alive():
			self.a2a_server_thread.join(timeout=5)

	def new_thread(self,tid):
		task_thread = threading.Thread()
		self.running_tasks.append({'id': tid, 'thread': task_thread})
		return task_thread

	def start(self):
		# Start A2A server in daemon thread
		self.start_a2a_server_in_thread(self.a2a_server)

		# kick off memory manager in background.
		self.mem_manager.start()
		logger.info("A2A server started....", self.card.name)
		# loop = asyncio.get_running_loop()
		# kick off TaskExecutor
		thread_pool_executor = self.mainwin.threadPoolExecutor
		logger.info(f"[AGENT_START] Agent {self.card.name} has {len(self.tasks)} tasks to start")
		for task in self.tasks:
			# new_thread = self.new_thread(task.id)
			qid = id(task.queue) if hasattr(task, 'queue') and task.queue is not None else None
			logger.info(f"[AGENT_START] {self.card.name} Starting task {task.name} with trigger {task.trigger}, has_queue={hasattr(task, 'queue') and task.queue is not None}")
			logger.info(f"[AGENT_START] Task details: task_id={getattr(task,'id',None)}, run_id={getattr(task,'run_id',None)}, queue_id={qid}")

			target_func = None
			if task.trigger == "schedule":
				logger.info(f"[AGENT_START] scheduled task name: {task.name}")
				target_func = self.runner.launch_scheduled_run
			elif task.trigger == "message":
				logger.info(f"[AGENT_START] message task name: {task.name}")
				target_func = self.runner.launch_reacted_run
			elif task.trigger == "interaction":
				logger.info(f"[AGENT_START] interaction task name: {task.name}")
				target_func = self.runner.launch_interacted_run
			else:
				logger.warning(f"[AGENT_START] WARNING: UNRECOGNIZED task trigger type for task {task.name}")
				continue

			# Submit the task and register it using its run_id
			if hasattr(task, 'run_id') and task.run_id:
				future = thread_pool_executor.submit(target_func, task)
				with self.task_lock:
					self.active_tasks[task.run_id] = future
				future.add_done_callback(lambda f, run_id=task.run_id: self._task_done_callback(run_id, f))
				qid_after = id(task.queue) if hasattr(task, 'queue') and task.queue is not None else None
				logger.info(f"[AGENT_START] ✅ Submitted: agent={self.card.name}, task={task.name}, task_id={task.id}, run_id={task.run_id}, queue_id={qid_after}, future={future}")
			else:
				logger.error(f"[AGENT_START] ❌ Task {task.name} is missing a 'run_id' and cannot be tracked.")


		# runnable = self.skills[0].get_runnable()
		# response: dict[str, Any] = await self.runnable.ainvoke(input_messages)
		# runnable.ainvoke()
		logger.info("Ready to A2A chat....", self.card.name)

	async def hone_skills(self):
		logger.info("hone skills...")

	def _task_done_callback(self, run_id: str, future: concurrent.futures.Future):
		"""Callback to remove a task from the registry upon completion."""
		# Keep dev run alive; it manages pause/step/resume explicitly.
		if run_id == "dev_run_singleton":
			try:
				_ = future.result()  # raise if task errored, so we can log it
			except Exception as e:
				logger.error(f"Dev run task failed with an exception: {e}")
			else:
				logger.info("Dev run task callback invoked; preserving registry entry for step/resume.")
			return

		# Non-dev tasks: default behavior
		try:
			_ = future.result()
		except Exception as e:
			logger.error(f"Task with run_id {run_id} failed with an exception: {e}")

		with self.task_lock:
			if run_id in self.active_tasks:
				del self.active_tasks[run_id]
				logger.info(f"Task with run_id {run_id} completed and removed from registry.")




	def is_task_running(self, run_id: str) -> bool:
		"""Check if a task with the given run_id is currently running."""
		with self.task_lock:
			return run_id in self.active_tasks

	def request_local_help(self, recipient_agent=None):
		# this is only available if myself is not a helper agent
		helper = next((ag for ag in self.mainwin.agents if "helper" in self.get_card().name.lower()), None)
		logger.info("client card:", self.get_card().name.lower())
		if helper:
			self.a2a_client.set_recipient(helper.get_card())
			help_msg = Message(role="user", parts=[TextPart(type="text", text="Summarize this report")], metadata={"type": "send_task"})
			payload = {
				"id": "task-001X",
				"sessionId": "sess-abc",
				"message": help_msg,
				"acceptedOutputModes": ["json"],
				"skill": "resolve_rpa_failure"  # Or whatever your agent expects
			}

			logger.info("client payload:", payload["id"])
			response = self.a2a_client.send_task(payload)
			logger.info("A2A RESPONSE:", response)
		else:
			logger.info("client err:", self.get_card().name.lower())

	def a2a_send_chat_message(self, recipient_agent, message):
		# this is only available if myself is not a helper agent
		logger.info("[ec_agent] recipient card:", recipient_agent.get_card().name.lower())
		logger.info("[ec_agent] sending message:", message)
		try:
			a2a_end_point = recipient_agent.get_card().url + "/a2a/"
			logger.info("[ec_agent] a2a end point: ", a2a_end_point)
			self.a2a_client.set_recipient(url=a2a_end_point)
			if isinstance(message["attributes"]['params']['content'], str):
				msg_text = message["attributes"]['params']['content']
			elif isinstance(message["attributes"]['params']['content'], dict):
				msg_text = message["attributes"]['params']['content']['text']
			else:
				msg_text = message['attributes']['params']['content']['text']
			msg_parts = [TextPart(type="text", text=msg_text)]

			if message["attributes"]['params']['attachments']:
				for attachment in message["attributes"]['params']['attachments']:
					file_data = attachment['data']
					if isinstance(file_data, bytes):
						file_data = base64.b64encode(file_data).decode('utf-8')

					fc = FileContent(name=attachment['name'],
								mimeType=attachment['type'],
								bytes= file_data,
								uri = attachment['url'])
					msg_parts.append(FilePart(type="file", file=fc))


			if msg_text.lstrip().startswith("dev>"):
				mtype = "dev_send_chat"
			else:
				mtype = "send_chat"

			chat_msg = Message(role="user", parts=msg_parts, metadata={"mtype": mtype})

			if "id" in message:
				sess_id = message["id"]
			else:
				sess_id = message['messages'][3]

			payload = TaskSendParams(
				id="0001",
				sessionId=sess_id,
				message=chat_msg,
				acceptedOutputModes=["text", "json", "image/png"],
				pushNotification=None,
				historyLength=0,
				metadata={
					"params": message['attributes']["params"]
				}
			)


			logger.info("[ec_agent] client payload:", payload)
			# response = await self.a2a_client.send_task(payload)
			response = self.a2a_client.sync_send_task(payload.model_dump())
			logger.info("[ec_agent] A2A RESPONSE:", response)
			return response
		except Exception as e:
			# Get the traceback information
			traceback_info = traceback.extract_tb(e.__traceback__)
			# Extract the file name and line number from the last entry in the traceback
			if traceback_info:
				ex_stat = "ErrorA2ASend:" + traceback.format_exc() + " " + str(e)
			else:
				ex_stat = "ErrorA2ASend: traceback information not available:" + str(e)
			logger.error(ex_stat)


	def launch_dev_run_task(self, init_state):
		"""Launches a development run, ensuring any previous dev run is cancelled first."""
		logger.info("Attempting to launch dev run task...")
		DEV_RUN_ID = "dev_run_singleton"

		try:
			# Check if a dev run is already active and cancel it
			if self.is_task_running(DEV_RUN_ID):
				logger.info(f"An existing dev run ({DEV_RUN_ID}) is active. Attempting to cancel it.")
				with self.task_lock:
					# Find the ManagedTask object associated with the running future
					old_future = self.active_tasks.get(DEV_RUN_ID)
					dev_task_instance = next((t for t in self.tasks if hasattr(t, 'run_id') and t.run_id == DEV_RUN_ID), None)

					if dev_task_instance:
						dev_task_instance.cancel() # Signal the task to stop
						logger.info(f"Cancellation signal sent to task with run_id {DEV_RUN_ID}.")
					else:
						logger.warning(f"Could not find the ManagedTask object for run_id {DEV_RUN_ID} to send cancel signal.")

					if old_future:
						# Wait for the old task to finish cancelling
						try:
							old_future.result(timeout=5) # Wait for up to 5 seconds
							logger.info(f"Previous dev run task {DEV_RUN_ID} successfully cancelled.")
						except concurrent.futures.TimeoutError:
							logger.error(f"Timeout waiting for previous dev run task {DEV_RUN_ID} to cancel.")
						except Exception as e:
							logger.info(f"Previous dev run task {DEV_RUN_ID} terminated. Exception during cancellation: {e}")

			# Find the template task for development runs
			dev_task_template = next((task for task in self.tasks if "run task for skill under development" in task.name.lower()), None)
			if not dev_task_template:
				logger.error("Could not find the 'run task for skill under development' template task.")
				return {"success": False, "error": "Dev task template not found."}

			# Assign the unique run_id for tracking
			dev_task_template.run_id = DEV_RUN_ID
			dev_task_template.cancellation_event.clear() # Ensure the event is not set from a previous run

			# Launch the new dev run task
			thread_pool_executor = self.mainwin.threadPoolExecutor
			future = thread_pool_executor.submit(self.runner.launch_dev_run, init_state, dev_task_template)
			with self.task_lock:
				self.active_tasks[DEV_RUN_ID] = future
			future.add_done_callback(lambda f: self._task_done_callback(DEV_RUN_ID, f))

			logger.info(f"New dev run task with run_id {DEV_RUN_ID} submitted and registered.")
			return {"success": True, "message": "Dev run launched successfully."}

		except Exception as e:
			err_msg = get_traceback(e, "ErrorLaunchDevRunTask")
			logger.error(err_msg)
			return {"success": False, "error": err_msg}

	def resume_dev_run_task(self):
		logger.info("launching dev run task!")
		try:
			response = self.runner.resume_dev_run()
			logger.info("launching dev run task!", response)
			return response
		except Exception as e:
			# Get the traceback information
			err_msg = get_traceback(e, "ErrorLaunchDevRunTask")
			logger.error(err_msg)

	def step_dev_run_task(self):
		logger.info("launching dev run task!")
		try:
			response = self.runner.step_dev_run()
			logger.info("launching dev run task!", response)
			return response
		except Exception as e:
			# Get the traceback information
			err_msg = get_traceback(e, "ErrorLaunchDevRunTask")
			logger.error(err_msg)

	def pause_dev_run_task(self):
		logger.info("launching dev run task!")
		try:
			response = self.runner.pause_dev_run()
			logger.info("launching dev run task!", response)
			return response
		except Exception as e:
			# Get the traceback information
			err_msg = get_traceback(e, "ErrorLaunchDevRunTask")
			logger.error(err_msg)

	def cancel_dev_run_task(self):
		logger.info("launching dev run task!")
		try:
			response = self.runner.cancel_dev_run()
			logger.info("launching dev run task!", response)
			return response
		except Exception as e:
			# Get the traceback information
			err_msg = get_traceback(e, "ErrorLaunchDevRunTask")
			logger.error(err_msg)


	def set_checkpointer(self, checkpointer):
		"""Sets the checkpointer for the agent's runner."""


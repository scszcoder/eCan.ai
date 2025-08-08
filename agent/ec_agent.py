from __future__ import annotations
import traceback
import asyncio
import gc
import inspect
import json
import logging
import os
import socket
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, TypeVar, Union
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
	BaseMessage,
	HumanMessage,
	SystemMessage,
)
from langchain.embeddings import init_embeddings
from langgraph.store.memory import InMemoryStore

# from lmnr.sdk.decorators import observe
from pydantic import BaseModel, ValidationError
from agent.models import *
from agent.a2a.common.client import A2AClient
# from agent.gif import create_history_gif
from browser_use.agent.prompts import AgentMessagePrompt
from browser_use.agent.views import (
	ActionResult,
	AgentError,
	AgentHistory,
	AgentHistoryList,
	AgentOutput,
	AgentSettings,
	AgentState,
	AgentStepInfo,
	AgentStructuredOutput,
	BrowserStateHistory,
	StepMetadata,
)
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.common.types import Message, TextPart, FilePart, DataPart, FileContent, TaskSendParams

from browser_use.browser.types import Browser, BrowserContext, Page
from browser_use.browser.views import BrowserStateSummary
from browser_use.config import CONFIG
from browser_use.controller.registry.views import ActionModel
from browser_use.controller.service import Controller
from browser_use.agent.service import Agent
from agent.exceptions import LLMException

from agent.run_utils import check_env_variables, time_execution_async, time_execution_sync
from agent.tasks import TaskRunner, ManagedTask
from agent.human_chatter import *
import threading
import concurrent.futures
import base64
from utils.logger_helper import logger_helper as logger


load_dotenv()

class EC_Agent(Agent):
	@time_execution_sync('--init (agent)')
	def __init__(
		self,
		mainwin,
		skill_llm,
		tasks: Optional[List[ManagedTask]] = None,
		# Optional parameters
		skill_set: Optional[List[EC_Skill]] = None,
		card: AgentCard | None = None,
		supervisors: Optional[List[str]] = None,
		subordinates: Optional[List[str]] = None,
		peers: Optional[List[str]] = None,
		rank: Optional[str] = None,
		organizations: Optional[List[str]] = None,
		title: Optional[str] = None,
		gender: Optional[str] = None,
		birthday: Optional[str] = None,
		personalities: Optional[List[str]] = None,
		vehicle: Optional[str] = None,
		*args,
		**kwargs
	):
		# Core components
		self.tasks = tasks
		self.skill_llm = skill_llm
		self.running_tasks = []
		self.skill_set = skill_set
		self._stop_event = asyncio.Event()
		self.supervisors = supervisors if supervisors is not None else []
		self.subordinates = subordinates if subordinates is not None else []
		self.peers = peers if peers is not None else []
		self.rank = rank if rank is not None else ""
		self.organizations = organizations if organizations is not None else []
		self.title = title if title is not None else ""
		self.gender = gender if gender is not None else "m"
		self.birthday = birthday if birthday is not None else "2000-01-01"
		self.personalities = personalities if personalities is not None else []
		self.vehicle = vehicle if vehicle is not None else ""
		self.status = "active"

		# 在打包环境中安全初始化embeddings
		try:
			self.embeddings = init_embeddings("openai:text-embedding-3-small")
			self.store = InMemoryStore(
				index={
					"embed": self.embeddings,
					"dims": 1536,
				}
			)
		except Exception as e:
			logger.warning(f"Failed to initialize embeddings in packaged environment: {e}")
		# keep the old inits
		super().__init__(*args, **kwargs)

		# LLM API connection setup
		llm_api_env_vars = REQUIRED_LLM_API_ENV_VARS.get(self.llm.__class__.__name__, [])
		if llm_api_env_vars and not check_env_variables(llm_api_env_vars):
			logger.error(f'Environment variables not set for {self.llm.__class__.__name__}')
			raise ValueError('Environment variables not set')


		# Start non-blocking LLM connection verification
		logger.info("OPENAI API KEY IS::::::::", os.getenv("OPENAI_API_KEY"))

		capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
		def get_lan_ip():
			try:
				# Connect to an external address, but don't actually send anything
				s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				s.connect(("8.8.8.8", 80))  # Google's DNS IP
				ip = s.getsockname()[0]
				s.close()
				return ip
			except Exception:
				return "127.0.0.1"  # fallback

		host = get_lan_ip()
		self.mainwin = mainwin
		free_ports = mainwin.get_free_agent_ports(1)
		if not free_ports:
			return None
		a2a_server_port = free_ports[0]
		self.card = card
		self.a2a_client = A2AClient(self.card)
		notification_sender_auth = PushNotificationSenderAuth()
		notification_sender_auth.generate_jwk()
		self.a2a_server = A2AServer(
			agent_card=self.card,
			task_manager=AgentTaskManager(notification_sender_auth=notification_sender_auth),
			host=host,
			port=a2a_server_port,
			endpoint="/a2a/",
		)
		logger.info("host:", host, "a2a server port:", a2a_server_port)
		self.a2a_server.attach_agent(self)

		self.runner = TaskRunner(self)
		self.human_chatter = HumanChatter(self)



	def to_dict(self):
		agentJS = {
			"card": self.card_to_dict(self.card),
			"supervisors": self.supervisors,
			"subordinates": self.subordinates,
			"peers": self.peers,
			"rank": self.rank,
			"organizations": self.organizations,
			"title": self.title,
			"personalities": self.personalities
		}
		return agentJS

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

	def add_skills(self, skills):
		self.skill_set += skills  # or: self.skill_set.extend(skills)

	def remove_skills(self, skills):
		self.skill_set = [s for s in self.skill_set if s not in skills]

	def update_skills(self, skills):
		skill_ids = {s.id for s in skills}
		self.skill_set = [s for s in self.skill_set if s.id not in skill_ids] + skills

	def set_skill_llm(self, llm):
		self.skill_llm = llm

	def set_llm(self, llm):
		self.llm = llm

	def get_card(self):
		return self.card

	def get_a2a_server_port(self):
		logger.info(f"get a2a server port: {self.a2a_server.agent_card.url.split(':')[-1]}")
		return int(self.a2a_server.agent_card.url.split(":")[-1])

	def is_busy(self):
		busy = False
		return busy

	def start_a2a_server_in_thread(self, a2a_server):
		def run_server():
			a2a_server.start()  # this is the uvicorn.run(...) call

		self.a2a_server_thread = threading.Thread(target=run_server)
		self.a2a_server_thread.daemon = True
		self.a2a_server_thread.start()

	def exit_a2a_server_in_thread(self):
		if self.a2a_server_thread and self.a2a_server_thread.is_alive():
			self.a2a_server_thread.join(timeout=5)

	def new_thread(self,tid):
		task_thread = threading.Thread()
		self.running_tasks.append({'id': tid, 'thread': task_thread})
		return task_thread

	# async def start(self):
	def start(self):
		# kick off a2a server:
		self.start_a2a_server_in_thread(self.a2a_server)
		logger.info("A2A server started....")
		# loop = asyncio.get_running_loop()
		# kick off TaskExecutor
		self.running_tasks = self.mainwin.threadPoolExecutor
		for task in self.tasks:
			# new_thread = self.new_thread(task.id)
			logger.info(f"{self.card.name} Starting task {task.name} with trigger {task.trigger}")
			if task.trigger == "schedule":
				logger.info(" scheduled task name:", task.name)
				self.running_tasks.submit(self.runner.launch_scheduled_run,task)
				# await self.runner.launch_scheduled_run(task)
				# await loop.run_in_executor(threading.Thread(), await self.runner.launch_scheduled_run(task), True)
			elif task.trigger == "message":
				logger.info(" message task name:", task.name)
				self.running_tasks.submit(self.runner.launch_reacted_run,task)

				# await self.runner.launch_reacted_run(task)
				# await loop.run_in_executor(threading.Thread(), await self.runner.launch_reacted_run(task), True)
			elif task.trigger == "interaction":
				logger.info(" interaction task name:", task.name)
				self.running_tasks.submit(self.runner.launch_interacted_run,task)

				# await self.runner.launch_interacted_run(task)
				# await loop.run_in_executor(threading.Thread(), await self.runner.launch_interacted_run(task), True)
			else:
				logger.info("WARNING: UNRECOGNIZED task trigger type....")

		# runnable = self.skill_set[0].get_runnable()
		# response: dict[str, Any] = await self.runnable.ainvoke(input_messages)
		# runnable.ainvoke()
		logger.info("Ready to A2A chat....")

	async def hone_skills(self):
		logger.info("hone skills...")

	def get_task_id_from_request(self, req):
		task_id = req.params.id
		logger.info(f"TASK ID IN QUERY:{task_id}.")
		return task_id

	@time_execution_async('--request_local_help (agent)')
	async def request_local_help(self, recipient_agent=None):
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
			response = await self.a2a_client.send_task(payload)
			logger.info("A2A RESPONSE:", response)
		else:
			logger.info("client err:", self.get_card().name.lower())

	# class Message(BaseModel):
	# 	role: Literal["user", "agent"]
	# 	parts: List[Part]
	# 	metadata: dict[str, Any] | None = None
	# @time_execution_async('--a2a_send_message (agent, message)')
	# async def a2a_send_chat_message(self, recipient_agent, message):
	@time_execution_sync('--a2a_send_chat_message (agent, message)')
	def a2a_send_chat_message(self, recipient_agent, message):
		# this is only available if myself is not a helper agent
		logger.info("recipient card:", recipient_agent.get_card().name.lower())
		logger.info("sending message:", message)
		try:
			a2a_end_point = recipient_agent.get_card().url + "/a2a/"
			logger.info("a2a end point: ", a2a_end_point)
			self.a2a_client.set_recipient(url=a2a_end_point)
			msg_parts = [TextPart(type="text", text=message['chat']['input'])]
			if message['chat']['attachments']:
				for attachment in message['chat']['attachments']:
					file_data = attachment['data']
					if isinstance(file_data, bytes):
						file_data = base64.b64encode(file_data).decode('utf-8')

					fc = FileContent(name=attachment['name'],
								mimeType=attachment['type'],
								bytes= file_data,
								uri = attachment['url'])
					msg_parts.append(FilePart(type="file", file=fc))

			chat_msg = Message(role="user", parts=msg_parts, metadata={"type": "send_chat"})

			payload = TaskSendParams(
				id="0001",
				sessionId= message['chat']['messages'][3],
				message =chat_msg,
				acceptedOutputModes = ["text", "json", "image/png"],
				pushNotification = None,
				historyLength = None,
				metadata = {
					"type": "send_chat",
					"msgId": message['chat']['messages'][2],
					"chatId": message['chat']['messages'][1],
				}
			)

			logger.info("client payload:", payload)
			# response = await self.a2a_client.send_task(payload)
			response = self.a2a_client.sync_send_task(payload.model_dump())
			logger.info("A2A RESPONSE:", response)
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

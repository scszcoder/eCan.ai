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

# from lmnr.sdk.decorators import observe
from pydantic import BaseModel, ValidationError

from agent.a2a.common.client import A2AClient
# from agent.gif import create_history_gif
from agent.message_manager.service import MessageManager
from agent.message_manager.utils import convert_input_messages, extract_json_from_model_output, save_conversation
from agent.prompts import AgentMessagePrompt, PlannerPrompt
from agent.models import (
	REQUIRED_LLM_API_ENV_VARS,
	ActionResult,
	AgentError,
	AgentHistory,
	AgentHistoryList,
	AgentOutput,
	AgentSettings,
	AgentState,
	AgentStepInfo,
	StepMetadata,
	ToolCallingMethod,
)
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.common.types import Message, TextPart

from agent.ec_skills.browser.browser import Browser
from agent.ec_skills.browser.context import BrowserContext
from agent.runner.context import RunnerContext

from agent.base import GlobalContext, Personality
from agent.ec_skill import EC_Skill
from agent.ec_skills.browser.views import BrowserState, BrowserStateHistory
from agent.ec_skills.dom.history_tree_processor.service import (
	DOMHistoryElement,
	HistoryTreeProcessor,
)
from agent.exceptions import LLMException
from telemetry.service import ProductTelemetry
from telemetry.views import (
	AgentEndTelemetryEvent,
	AgentRunTelemetryEvent,
	AgentStepTelemetryEvent,
)
from agent.run_utils import check_env_variables, time_execution_async, time_execution_sync
from agent.tasks import TaskRunner, ManagedTask
from agent.human_chatter import *
import threading


load_dotenv()
logger = logging.getLogger(__name__)

SKIP_LLM_API_KEY_VERIFICATION = os.environ.get('SKIP_LLM_API_KEY_VERIFICATION', 'false').lower()[0] in 'ty1'


def log_response(response: AgentOutput) -> None:
	"""Utility function to log the model's response."""

	if 'Success' in response.current_state.evaluation_previous_goal:
		emoji = '👍'
	elif 'Failed' in response.current_state.evaluation_previous_goal:
		emoji = '⚠'
	else:
		emoji = '🤷'

	logger.info(f'{emoji} Eval: {response.current_state.evaluation_previous_goal}')
	logger.info(f'🧠 Memory: {response.current_state.memory}')
	logger.info(f'🎯 Next goal: {response.current_state.next_goal}')
	for i, action in enumerate(response.action):
		logger.info(f'🛠️  Action {i + 1}/{len(response.action)}: {action.model_dump_json(exclude_unset=True)}')


Context = TypeVar('Context')

AgentHookFunc = Callable[['Agent'], None]


class EC_Agent(Generic[Context]):
	@time_execution_sync('--init (agent)')
	def __init__(
		self,
		mainwin,
		llm: BaseChatModel,
		tasks: Optional[List[ManagedTask]] = None,
		# Optional parameters
		browser: Browser | None = None,
		browser_context: BrowserContext | None = None,
		global_context: GlobalContext | None = None,
		runner_context: RunnerContext | None = None,
		skill_set: Optional[List[EC_Skill]] = None,
		card: AgentCard | None = None,
		supervisors: Optional[List[str]] = None,
		subordinates: Optional[List[str]] = None,
		peers: Optional[List[str]] = None,
		orgnizations: Optional[List[str]] = None,
		job_descriptsion: Optional[List[str]] = None,
		personality: Personality | None = None,
		# runner: Runner[Context] = Runner(),
		# Initial agent run parameters
		sensitive_data: Optional[Dict[str, str]] = None,
		initial_actions: Optional[List[Dict[str, Dict[str, Any]]]] = None,
		# Cloud Callbacks
		register_new_step_callback: Union[
			Callable[['BrowserState', 'AgentOutput', int], None],  # Sync callback
			Callable[['BrowserState', 'AgentOutput', int], Awaitable[None]],  # Async callback
			None,
		] = None,
		register_done_callback: Union[
			Callable[['AgentHistoryList'], Awaitable[None]],  # Async Callback
			Callable[['AgentHistoryList'], None],  # Sync Callback
			None,
		] = None,
		register_external_agent_status_raise_error_callback: Callable[[], Awaitable[bool]] | None = None,
		# Agent settings
		use_vision: bool = True,
		use_vision_for_planner: bool = False,
		save_conversation_path: Optional[str] = None,
		save_conversation_path_encoding: Optional[str] = 'utf-8',
		max_failures: int = 3,
		retry_delay: int = 10,
		override_system_message: Optional[str] = None,
		extend_system_message: Optional[str] = None,
		max_input_tokens: int = 128000,
		validate_output: bool = False,
		message_context: Optional[str] = None,
		generate_gif: bool | str = False,
		available_file_paths: Optional[list[str]] = None,
		include_attributes: list[str] = [
			'title',
			'type',
			'name',
			'role',
			'aria-label',
			'placeholder',
			'value',
			'alt',
			'aria-expanded',
			'data-date-format',
		],
		max_actions_per_step: int = 10,
		tool_calling_method: Optional[ToolCallingMethod] = 'auto',
		page_extraction_llm: Optional[BaseChatModel] = None,
		planner_llm: Optional[BaseChatModel] = None,
		planner_interval: int = 1,  # Run planner every N steps
		is_planner_reasoning: bool = False,
		# Inject state
		injected_agent_state: Optional[AgentState] = None,
		#
		context: Context | None = None,
		# Memory settings
		enable_memory: bool = True,
		memory_interval: int = 10,
		memory_config: Optional[dict] = None,
	):
		if page_extraction_llm is None:
			page_extraction_llm = llm

		# Core components
		self.tasks = tasks
		self.running_tasks = []
		self.llm = llm
		self.sensitive_data = sensitive_data
		self.skill_set = skill_set
		self._stop_event = asyncio.Event()
		self.supervisors = supervisors if supervisors is not None else []
		self.subordinates = subordinates if subordinates is not None else []
		self.peers = peers if peers is not None else []

		self.settings = AgentSettings(
			use_vision=use_vision,
			use_vision_for_planner=use_vision_for_planner,
			save_conversation_path=save_conversation_path,
			save_conversation_path_encoding=save_conversation_path_encoding,
			max_failures=max_failures,
			retry_delay=retry_delay,
			override_system_message=override_system_message,
			extend_system_message=extend_system_message,
			max_input_tokens=max_input_tokens,
			validate_output=validate_output,
			message_context=message_context,
			generate_gif=generate_gif,
			available_file_paths=available_file_paths,
			include_attributes=include_attributes,
			max_actions_per_step=max_actions_per_step,
			tool_calling_method=tool_calling_method,
			page_extraction_llm=page_extraction_llm,
			planner_llm=planner_llm,
			planner_interval=planner_interval,
			is_planner_reasoning=is_planner_reasoning,
			enable_memory=enable_memory,
			memory_interval=memory_interval,
			memory_config=memory_config,
		)

		# Initialize state
		self.state = injected_agent_state or AgentState()

		# Action setup
		# self._setup_action_models()
		# self._set_browser_use_version_and_source()
		# self.initial_actions = self._convert_initial_actions(initial_actions) if initial_actions else None

		# Model setup
		# self._set_model_names()
		# logger.info(
		# 	f'🧠 Starting an agent with main_model={self.model_name}, planner_model={self.planner_model_name}, '
		# 	f'extraction_model={self.settings.page_extraction_llm.model_name if hasattr(self.settings.page_extraction_llm, "model_name") else None}'
		# )

		# LLM API connection setup
		llm_api_env_vars = REQUIRED_LLM_API_ENV_VARS.get(self.llm.__class__.__name__, [])
		if llm_api_env_vars and not check_env_variables(llm_api_env_vars):
			logger.error(f'Environment variables not set for {self.llm.__class__.__name__}')
			raise ValueError('Environment variables not set')


		# Start non-blocking LLM connection verification
		print("OPENAI API KEY IS::::::::", os.getenv("OPENAI_API_KEY"))
		# self.llm._verified_api_keys = self._verify_llm_connection(self.llm)
		self.llm._verified_api_keys = asyncio.create_task(self._verify_llm_connection(self.llm))
		print("VERIFIED OPENAI API KEY IS::::::::", self.llm._verified_api_keys)

		# self.mcp_agent = create_react_agent(self.llm, self.mcp_client.get_tools())

		# Initialize available actions for system prompt (only non-filtered actions)
		# These will be used for the system prompt to maintain caching
		# self.unfiltered_actions = self.runner.registry.get_prompt_description()

		# self.tool_calling_method = self._set_tool_calling_method()
		# self.settings.message_context = self._set_message_context()

		# Initialize message manager with state
		# Initial system prompt with all actions - will be updated during each step
		# self._message_manager = MessageManager(
		# 	task=task,
		# 	system_message=SystemPrompt(
		# 		action_description=self.unfiltered_actions,
		# 		max_actions_per_step=self.settings.max_actions_per_step,
		# 		override_system_message=override_system_message,
		# 		extend_system_message=extend_system_message,
		# 	).get_system_message(),
		# 	settings=MessageManagerSettings(
		# 		max_input_tokens=self.settings.max_input_tokens,
		# 		include_attributes=self.settings.include_attributes,
		# 		message_context=self.settings.message_context,
		# 		sensitive_data=sensitive_data,
		# 		available_file_paths=self.settings.available_file_paths,
		# 	),
		# 	state=self.state.message_manager_state,
		# )
		#
		# if self.settings.enable_memory:
		# 	memory_settings = MemorySettings(
		# 		agent_id=self.state.agent_id,
		# 		interval=self.settings.memory_interval,
		# 		config=self.settings.memory_config,
		# 	)
		#
		# 	# Initialize memory
		# 	self.memory = Memory(
		# 		message_manager=self._message_manager,
		# 		llm=self.llm,
		# 		settings=memory_settings,
		# 	)
		# else:
		# 	self.memory = None

		# Browser setup
		self.injected_browser = browser is not None
		self.injected_browser_context = browser_context is not None
		self.browser = browser or Browser()
		# self.browser_context = browser_context or BrowserContext(
		# 	browser=self.browser, config=self.browser.config.new_context_config
		# )
		self.global_context = global_context or GlobalContext()

		# =====================a2a client+server setup ==================================
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
		print("host:", host, "a2a server port:", a2a_server_port)
		self.a2a_server.attach_agent(self)

		self.runner = TaskRunner(self)
		self.human_chatter = HumanChatter(self)


		# Callbacks
		self.register_new_step_callback = register_new_step_callback
		self.register_done_callback = register_done_callback
		self.register_external_agent_status_raise_error_callback = register_external_agent_status_raise_error_callback

		# Context
		self.context = context

		# Telemetry
		self.telemetry = ProductTelemetry()

		if self.settings.save_conversation_path:
			logger.info(f'Saving conversation to {self.settings.save_conversation_path}')

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

	def set_llm(self, llm):
		self.llm = llm

	def _set_message_context(self) -> str | None:
		if self.tool_calling_method == 'raw':
			# For raw tool calling, only include actions with no filters initially
			if self.settings.message_context:
				self.settings.message_context += f'\n\nAvailable actions: {self.unfiltered_actions}'
			else:
				self.settings.message_context = f'Available actions: {self.unfiltered_actions}'
		return self.settings.message_context

	def _set_browser_use_version_and_source(self) -> None:
		"""Get the version and source of the browser-use package (git or pip in a nutshell)"""
		try:
			# First check for repository-specific files
			repo_files = ['.git', 'README.md', 'docs', 'examples']
			package_root = Path(__file__).parent.parent.parent

			# If all of these files/dirs exist, it's likely from git
			if all(Path(package_root / file).exists() for file in repo_files):
				try:
					import subprocess

					version = subprocess.check_output(['git', 'describe', '--tags']).decode('utf-8').strip()
				except Exception:
					version = 'unknown'
				source = 'git'
			else:
				# If no repo files found, try getting version from pip
				import pkg_resources

				version = pkg_resources.get_distribution('browser-use').version
				source = 'pip'
		except Exception:
			version = 'unknown'
			source = 'unknown'

		logger.debug(f'Version: {version}, Source: {source}')
		self.version = version
		self.source = source

	def _set_model_names(self) -> None:
		self.chat_model_library = self.llm.__class__.__name__
		self.model_name = 'Unknown'
		if hasattr(self.llm, 'model_name'):
			model = self.llm.model_name  # type: ignore
			self.model_name = model if model is not None else 'Unknown'
		elif hasattr(self.llm, 'model'):
			model = self.llm.model  # type: ignore
			self.model_name = model if model is not None else 'Unknown'

		if self.settings.planner_llm:
			if hasattr(self.settings.planner_llm, 'model_name'):
				self.planner_model_name = self.settings.planner_llm.model_name  # type: ignore
			elif hasattr(self.settings.planner_llm, 'model'):
				self.planner_model_name = self.settings.planner_llm.model  # type: ignore
			else:
				self.planner_model_name = 'Unknown'
		else:
			self.planner_model_name = None

	def _setup_action_models(self) -> None:
		"""Setup dynamic action models from controller's registry"""
		# Initially only include actions with no filters
		self.ActionModel = self.runner.registry.create_action_model()
		# Create output model with the dynamic actions
		self.AgentOutput = AgentOutput.type_with_custom_actions(self.ActionModel)

		# used to force the done action when max_steps is reached
		self.DoneActionModel = self.runner.registry.create_action_model(include_actions=['done'])
		self.DoneAgentOutput = AgentOutput.type_with_custom_actions(self.DoneActionModel)

	def _set_tool_calling_method(self) -> Optional[ToolCallingMethod]:
		tool_calling_method = self.settings.tool_calling_method
		if tool_calling_method == 'auto':
			if 'deepseek-reasoner' in self.model_name or 'deepseek-r1' in self.model_name:
				return 'raw'
			elif self.chat_model_library == 'ChatGoogleGenerativeAI':
				return None
			elif self.chat_model_library == 'ChatOpenAI':
				return 'function_calling'
			elif self.chat_model_library == 'AzureChatOpenAI':
				return 'function_calling'
			else:
				return None
		else:
			return tool_calling_method

	def add_new_task(self, new_task: str) -> None:
		self._message_manager.add_new_task(new_task)

	async def _raise_if_stopped_or_paused(self) -> None:
		"""Utility function that raises an InterruptedError if the agent is stopped or paused."""

		if self.register_external_agent_status_raise_error_callback:
			if await self.register_external_agent_status_raise_error_callback():
				raise InterruptedError

		if self.state.stopped or self.state.paused:
			# logger.debug('Agent paused after getting state')
			raise InterruptedError

	@time_execution_async('--step (agent)')
	async def step(self, step_info: Optional[AgentStepInfo] = None) -> None:
		"""Execute one step of the task"""
		logger.info(f'📍 Step {self.state.n_steps}')
		state = None
		model_output = None
		result: list[ActionResult] = []
		step_start_time = time.time()
		tokens = 0

		try:
			if step_info.in_browser:
				await self.browser_step(step_info)
			else:
				global_context = self.global_context
				state = await self.global_context.get_state()
				active_page = await self.global_context.get_current_page()
				# generate procedural memory if needed
				if self.settings.enable_memory and self.memory and self.state.n_steps % self.settings.memory_interval == 0:
					self.memory.create_procedural_memory(self.state.n_steps)

				await self._raise_if_stopped_or_paused()

				# Update action models with page-specific actions
				await self._update_action_models_for_page(active_page, global_context)

				# Get page-specific filtered actions
				page_filtered_actions = self.runner.registry.get_prompt_description(active_page, global_context)

				# If there are page-specific actions, add them as a special message for this step only
				if page_filtered_actions:
					page_action_message = f'For this page, these additional actions are available:\n{page_filtered_actions}'
					self._message_manager._add_message_with_tokens(HumanMessage(content=page_action_message))

				# If using raw tool calling method, we need to update the message context with new actions
				if self.tool_calling_method == 'raw':
					# For raw tool calling, get all non-filtered actions plus the page-filtered ones
					all_unfiltered_actions = self.runner.registry.get_prompt_description()
					all_actions = all_unfiltered_actions
					if page_filtered_actions:
						all_actions += '\n' + page_filtered_actions

					context_lines = self._message_manager.settings.message_context.split('\n')
					non_action_lines = [line for line in context_lines if not line.startswith('Available actions:')]
					updated_context = '\n'.join(non_action_lines)
					if updated_context:
						updated_context += f'\n\nAvailable actions: {all_actions}'
					else:
						updated_context = f'Available actions: {all_actions}'
					self._message_manager.settings.message_context = updated_context

				print("add state message:", state)
				self._message_manager.add_state_message(state, self.state.last_result, step_info, self.settings.use_vision)

				# Run planner at specified intervals if planner is configured
				if self.settings.planner_llm and self.state.n_steps % self.settings.planner_interval == 0:
					plan = await self._run_planner()
					# add plan before last state message
					self._message_manager.add_plan(plan, position=-1)

				if step_info and step_info.is_last_step():
					# Add last step warning if needed
					msg = 'Now comes your last step. Use only the "done" action now. No other actions - so here your action sequence must have length 1.'
					msg += '\nIf the task is not yet fully finished as requested by the user, set success in "done" to false! E.g. if not all steps are fully completed.'
					msg += '\nIf the task is fully finished, set success in "done" to true.'
					msg += '\nInclude everything you found out for the ultimate task in the done text.'
					logger.info('Last step finishing up')
					self._message_manager._add_message_with_tokens(HumanMessage(content=msg))
					self.AgentOutput = self.DoneAgentOutput

				input_messages = self._message_manager.get_messages()
				tokens = self._message_manager.state.history.current_tokens

				try:
					model_output = await self.get_next_action(input_messages)

					# Check again for paused/stopped state after getting model output
					# This is needed in case Ctrl+C was pressed during the get_next_action call
					await self._raise_if_stopped_or_paused()

					self.state.n_steps += 1

					if self.register_new_step_callback:
						if inspect.iscoroutinefunction(self.register_new_step_callback):
							await self.register_new_step_callback(state, model_output, self.state.n_steps)
						else:
							self.register_new_step_callback(state, model_output, self.state.n_steps)
					if self.settings.save_conversation_path:
						target = self.settings.save_conversation_path + f'_{self.state.n_steps}.txt'
						save_conversation(input_messages, model_output, target,
										  self.settings.save_conversation_path_encoding)

					self._message_manager._remove_last_state_message()  # we dont want the whole state in the chat history

					# check again if Ctrl+C was pressed before we commit the output to history
					await self._raise_if_stopped_or_paused()

					self._message_manager.add_model_output(model_output)
				except asyncio.CancelledError:
					# Task was cancelled due to Ctrl+C
					self._message_manager._remove_last_state_message()
					raise InterruptedError('Model query cancelled by user')
				except InterruptedError:
					# Agent was paused during get_next_action
					self._message_manager._remove_last_state_message()
					raise  # Re-raise to be caught by the outer try/except
				except Exception as e:
					# model call failed, remove last state message from history
					self._message_manager._remove_last_state_message()
					raise e

				result: list[ActionResult] = await self.multi_act(model_output.action)

				self.state.last_result = result

				if len(result) > 0 and result[-1].is_done:
					logger.info(f'📄 Result: {result[-1].extracted_content}')

				self.state.consecutive_failures = 0

		except InterruptedError:
			# logger.debug('Agent paused')
			self.state.last_result = [
				ActionResult(
					error='The agent was paused mid-step - the last action might need to be repeated',
					include_in_memory=False
				)
			]
			return
		except asyncio.CancelledError:
			# Directly handle the case where the step is cancelled at a higher level
			# logger.debug('Task cancelled - agent was paused with Ctrl+C')
			self.state.last_result = [ActionResult(error='The agent was paused with Ctrl+C', include_in_memory=False)]
			raise InterruptedError('Step cancelled by user')
		except Exception as e:
			traceback_info = traceback.extract_tb(e.__traceback__)
			# Extract the file name and line number from the last entry in the traceback
			if traceback_info:
				ex_stat = "ErrorFetchSchedule:" + traceback.format_exc() + " " + str(e)
				logger.error(f'❌  Failed to step: {ex_stat}')

			result = await self._handle_step_error(e)
			self.state.last_result = result

		finally:
			step_end_time = time.time()
			actions = [a.model_dump(exclude_unset=True) for a in model_output.action] if model_output else []
			self.telemetry.capture(
				AgentStepTelemetryEvent(
					agent_id=self.state.agent_id,
					step=self.state.n_steps,
					actions=actions,
					consecutive_failures=self.state.consecutive_failures,
					step_error=[r.error for r in result if r.error] if result else ['No result'],
				)
			)
			if not result:
				return

			if state:
				metadata = StepMetadata(
					step_number=self.state.n_steps,
					step_start_time=step_start_time,
					step_end_time=step_end_time,
					input_tokens=tokens,
				)
				self._make_history_item(model_output, state, result, metadata)


	@time_execution_async('--handle_step_error (agent)')
	async def _handle_step_error(self, error: Exception) -> list[ActionResult]:
		"""Handle all types of errors that can occur during a step"""
		include_trace = logger.isEnabledFor(logging.DEBUG)
		error_msg = AgentError.format_error(error, include_trace=include_trace)
		prefix = f'❌ Result failed {self.state.consecutive_failures + 1}/{self.settings.max_failures} times:\n '
		self.state.consecutive_failures += 1

		if 'Browser closed' in error_msg:
			logger.error('❌  Browser is closed or disconnected, unable to proceed')
			return [ActionResult(error='Browser closed or disconnected, unable to proceed', include_in_memory=False)]

		if isinstance(error, (ValidationError, ValueError)):
			logger.error(f'{prefix}{error_msg}')
			if 'Max token limit reached' in error_msg:
				# cut tokens from history
				self._message_manager.settings.max_input_tokens = self.settings.max_input_tokens - 500
				logger.info(
					f'Cutting tokens from history - new max input tokens: {self._message_manager.settings.max_input_tokens}'
				)
				self._message_manager.cut_messages()
			elif 'Could not parse response' in error_msg:
				# give model a hint how output should look like
				error_msg += '\n\nReturn a valid JSON object with the required fields.'

		else:
			from anthropic import RateLimitError as AnthropicRateLimitError
			from google.api_core.exceptions import ResourceExhausted
			from openai import RateLimitError

			# Define a tuple of rate limit error types for easier maintenance
			RATE_LIMIT_ERRORS = (
				RateLimitError,  # OpenAI
				ResourceExhausted,  # Google
				AnthropicRateLimitError,  # Anthropic
			)

			if isinstance(error, RATE_LIMIT_ERRORS):
				logger.warning(f'{prefix}{error_msg}')
				await asyncio.sleep(self.settings.retry_delay)
			else:
				logger.error(f'{prefix}{error_msg}')

		return [ActionResult(error=error_msg, include_in_memory=True)]

	def _make_history_item(
		self,
		model_output: AgentOutput | None,
		state: BrowserState,
		result: list[ActionResult],
		metadata: Optional[StepMetadata] = None,
	) -> None:
		"""Create and store history item"""

		if model_output:
			interacted_elements = AgentHistory.get_interacted_element(model_output, state.selector_map)
		else:
			interacted_elements = [None]

		state_history = BrowserStateHistory(
			url=state.url,
			title=state.title,
			tabs=state.tabs,
			interacted_element=interacted_elements,
			screenshot=state.screenshot,
		)

		history_item = AgentHistory(model_output=model_output, result=result, state=state_history, metadata=metadata)

		self.state.history.history.append(history_item)

	THINK_TAGS = re.compile(r'<think>.*?</think>', re.DOTALL)
	STRAY_CLOSE_TAG = re.compile(r'.*?</think>', re.DOTALL)

	def _remove_think_tags(self, text: str) -> str:
		# Step 1: Remove well-formed <think>...</think>
		text = re.sub(self.THINK_TAGS, '', text)
		# Step 2: If there's an unmatched closing tag </think>,
		#         remove everything up to and including that.
		text = re.sub(self.STRAY_CLOSE_TAG, '', text)
		return text.strip()

	def _convert_input_messages(self, input_messages: list[BaseMessage]) -> list[BaseMessage]:
		"""Convert input messages to the correct format"""
		if self.model_name == 'deepseek-reasoner' or 'deepseek-r1' in self.model_name:
			return convert_input_messages(input_messages, self.model_name)
		else:
			return input_messages

	@time_execution_async('--get_next_action (agent)')
	async def get_next_action(self, input_messages: list[BaseMessage]) -> AgentOutput:
		"""Get next action from LLM based on current state"""
		input_messages = self._convert_input_messages(input_messages)

		if self.tool_calling_method == 'raw':
			logger.debug(f'Using {self.tool_calling_method} for {self.chat_model_library}')
			try:
				output = self.llm.invoke(input_messages)
				response = {'raw': output, 'parsed': None}
			except Exception as e:
				logger.error(f'Failed to invoke model: {str(e)}')
				raise LLMException(401, 'LLM API call failed') from e
			# 2do: currently invoke does not return reasoning_content, we should override invoke
			output.content = self._remove_think_tags(str(output.content))
			try:
				parsed_json = extract_json_from_model_output(output.content)
				parsed = self.AgentOutput(**parsed_json)
				response['parsed'] = parsed
			except (ValueError, ValidationError) as e:
				logger.warning(f'Failed to parse model output: {output} {str(e)}')
				raise ValueError('Could not parse response.')

		elif self.tool_calling_method is None:
			structured_llm = self.llm.with_structured_output(self.AgentOutput, include_raw=True)
			try:
				# response: dict[str, Any] = await structured_llm.ainvoke(input_messages)  # type: ignore
				# MCP client

					response: dict[str, Any] = await self.mcp_agent.ainvoke(input_messages)  # type: ignore

					parsed: AgentOutput | None = response['parsed']

			except Exception as e:
				logger.error(f'Failed to invoke model: {str(e)}')
				raise LLMException(401, 'LLM API call failed') from e

		else:
			logger.debug(f'Using {self.tool_calling_method} for {self.chat_model_library}')
			structured_llm = self.llm.with_structured_output(self.AgentOutput, include_raw=True, method=self.tool_calling_method)
			print("ACTUAL API KEY>>>>>>>>:", self.llm.openai_api_key.get_secret_value())
			print("LLM prompt>>>>>>>:", input_messages)
			response: dict[str, Any] = await structured_llm.ainvoke(input_messages)  # type: ignore

		# Handle tool call responses
		if response.get('parsing_error') and 'raw' in response:
			raw_msg = response['raw']
			if hasattr(raw_msg, 'tool_calls') and raw_msg.tool_calls:
				# Convert tool calls to AgentOutput format

				tool_call = raw_msg.tool_calls[0]  # Take first tool call

				# Create current state
				tool_call_name = tool_call['name']
				tool_call_args = tool_call['args']

				current_state = {
					'page_summary': 'Processing tool call',
					'evaluation_previous_goal': 'Executing action',
					'memory': 'Using tool call',
					'next_goal': f'Execute {tool_call_name}',
				}

				# Create action from tool call
				action = {tool_call_name: tool_call_args}

				parsed = self.AgentOutput(current_state=current_state, action=[self.ActionModel(**action)])
			else:
				parsed = None
		else:
			parsed = response['parsed']

		if not parsed:
			try:
				parsed_json = extract_json_from_model_output(response['raw'].content)
				parsed = self.AgentOutput(**parsed_json)
			except Exception as e:
				logger.warning(f'Failed to parse model output: {response["raw"].content} {str(e)}')
				raise ValueError('Could not parse response.')

		# cut the number of actions to max_actions_per_step if needed
		if len(parsed.action) > self.settings.max_actions_per_step:
			parsed.action = parsed.action[: self.settings.max_actions_per_step]

		if not (hasattr(self.state, 'paused') and (self.state.paused or self.state.stopped)):
			log_response(parsed)

		return parsed

	def _log_agent_run(self) -> None:
		"""Log the agent run"""
		logger.info(f'🚀 Starting task: {self.task}')

		logger.debug(f'Version: {self.version}, Source: {self.source}')
		self.telemetry.capture(
			AgentRunTelemetryEvent(
				agent_id=self.state.agent_id,
				use_vision=self.settings.use_vision,
				task=self.task,
				model_name=self.model_name,
				chat_model_library=self.chat_model_library,
				version=self.version,
				source=self.source,
			)
		)

	async def take_step(self) -> tuple[bool, bool]:
		"""Take a step

		Returns:
			Tuple[bool, bool]: (is_done, is_valid)
		"""
		await self.step()

		if self.state.history.is_done():
			if self.settings.validate_output:
				if not await self._validate_output():
					return True, False

			await self.log_completion()
			if self.register_done_callback:
				if inspect.iscoroutinefunction(self.register_done_callback):
					await self.register_done_callback(self.state.history)
				else:
					self.register_done_callback(self.state.history)
			return True, True

		return False, False

	# @observe(name='agent.run', ignore_output=True)
	@time_execution_async('--run (agent)')
	async def run(
		self, max_steps: int = 100, on_step_start: AgentHookFunc | None = None, on_step_end: AgentHookFunc | None = None
	) -> AgentHistoryList:
		"""Execute the task with maximum number of steps"""

		loop = asyncio.get_event_loop()

		# Set up the Ctrl+C signal handler with callbacks specific to this agent
		from agent.run_utils import SignalHandler

		signal_handler = SignalHandler(
			loop=loop,
			pause_callback=self.pause,
			resume_callback=self.resume,
			custom_exit_callback=None,  # No special cleanup needed on forced exit
			exit_on_second_int=True,
		)
		signal_handler.register()

		# Start non-blocking LLM connection verification
		assert self.llm._verified_api_keys, 'Failed to verify LLM API keys'

		try:
			self._log_agent_run()

			# Execute initial actions if provided
			if self.initial_actions:
				result = await self.multi_act(self.initial_actions, check_for_new_elements=False)
				self.state.last_result = result

			for step in range(max_steps):
				# Check if waiting for user input after Ctrl+C
				if self.state.paused:
					signal_handler.wait_for_resume()
					signal_handler.reset()

				# Check if we should stop due to too many failures
				if self.state.consecutive_failures >= self.settings.max_failures:
					logger.error(f'❌ Stopping due to {self.settings.max_failures} consecutive failures')
					break

				# Check control flags before each step
				if self.state.stopped:
					logger.info('Agent stopped')
					break

				while self.state.paused:
					await asyncio.sleep(0.2)  # Small delay to prevent CPU spinning
					if self.state.stopped:  # Allow stopping while paused
						break

				if on_step_start is not None:
					await on_step_start(self)

				step_info = AgentStepInfo(step_number=step, max_steps=max_steps, in_browser=False)
				await self.step(step_info)

				if on_step_end is not None:
					await on_step_end(self)

				if self.state.history.is_done():
					if self.settings.validate_output and step < max_steps - 1:
						if not await self._validate_output():
							continue

					await self.log_completion()
					break
			else:
				logger.info('❌ Failed to complete task in maximum steps')

			return self.state.history

		except KeyboardInterrupt:
			# Already handled by our signal handler, but catch any direct KeyboardInterrupt as well
			logger.info('Got KeyboardInterrupt during execution, returning current history')
			return self.state.history

		finally:
			# Unregister signal handlers before cleanup
			signal_handler.unregister()

			self.telemetry.capture(
				AgentEndTelemetryEvent(
					agent_id=self.state.agent_id,
					is_done=self.state.history.is_done(),
					success=self.state.history.is_successful(),
					steps=self.state.n_steps,
					max_steps_reached=self.state.n_steps >= max_steps,
					errors=self.state.history.errors(),
					total_input_tokens=self.state.history.total_input_tokens(),
					total_duration_seconds=self.state.history.total_duration_seconds(),
				)
			)

			await self.close()

			if self.settings.generate_gif:
				output_path: str = 'agent_history.gif'
				if isinstance(self.settings.generate_gif, str):
					output_path = self.settings.generate_gif

				# create_history_gif(task=self.task, history=self.state.history, output_path=output_path)

	# @observe(name='runner.multi_act')
	@time_execution_async('--multi-act (agent)')
	async def multi_act(
		self,
		actions: list[ActionModel],
		check_for_new_elements: bool = True,
	) -> list[ActionResult]:
		"""Execute multiple actions"""
		results = []

		cached_selector_map = await self.browser_context.get_selector_map()
		cached_path_hashes = set(e.hash.branch_path_hash for e in cached_selector_map.values())

		await self.browser_context.remove_highlights()

		for i, action in enumerate(actions):
			if action.get_index() is not None and i != 0:
				new_state = await self.browser_context.get_state()
				new_selector_map = new_state.selector_map

				# Detect index change after previous action
				orig_target = cached_selector_map.get(action.get_index())  # type: ignore
				orig_target_hash = orig_target.hash.branch_path_hash if orig_target else None
				new_target = new_selector_map.get(action.get_index())  # type: ignore
				new_target_hash = new_target.hash.branch_path_hash if new_target else None
				if orig_target_hash != new_target_hash:
					msg = f'Element index changed after action {i} / {len(actions)}, because page changed.'
					logger.info(msg)
					results.append(ActionResult(extracted_content=msg, include_in_memory=True))
					break

				new_path_hashes = set(e.hash.branch_path_hash for e in new_selector_map.values())
				if check_for_new_elements and not new_path_hashes.issubset(cached_path_hashes):
					# next action requires index but there are new elements on the page
					msg = f'Something new appeared after action {i} / {len(actions)}'
					logger.info(msg)
					results.append(ActionResult(extracted_content=msg, include_in_memory=True))
					break

			try:
				await self._raise_if_stopped_or_paused()

				result = await self.runner.act(
					action,
					self.browser_context,
					self.settings.page_extraction_llm,
					self.sensitive_data,
					self.settings.available_file_paths,
					context=self.context,
				)

				results.append(result)

				logger.debug(f'Executed action {i + 1} / {len(actions)}')
				if results[-1].is_done or results[-1].error or i == len(actions) - 1:
					break

				await asyncio.sleep(self.browser_context.config.wait_between_actions)
				# hash all elements. if it is a subset of cached_state its fine - else break (new elements on page)

			except asyncio.CancelledError:
				# Gracefully handle task cancellation
				logger.info(f'Action {i + 1} was cancelled due to Ctrl+C')
				if not results:
					# Add a result for the cancelled action
					results.append(ActionResult(error='The action was cancelled due to Ctrl+C', include_in_memory=True))
				raise InterruptedError('Action cancelled by user')

		return results

	async def _validate_output(self) -> bool:
		"""Validate the output of the last action is what the user wanted"""
		system_msg = (
			f'You are a validator of an agent who interacts with a browser. '
			f'Validate if the output of last action is what the user wanted and if the task is completed. '
			f'If the task is unclear defined, you can let it pass. But if something is missing or the image does not show what was requested dont let it pass. '
			f'Try to understand the page and help the model with suggestions like scroll, do x, ... to get the solution right. '
			f'Task to validate: {self.task}. Return a JSON object with 2 keys: is_valid and reason. '
			f'is_valid is a boolean that indicates if the output is correct. '
			f'reason is a string that explains why it is valid or not.'
			f' example: {{"is_valid": false, "reason": "The user wanted to search for "cat photos", but the agent searched for "dog photos" instead."}}'
		)

		if self.browser_context.session:
			state = await self.browser_context.get_state()
			content = AgentMessagePrompt(
				state=state,
				result=self.state.last_result,
				include_attributes=self.settings.include_attributes,
			)
			msg = [SystemMessage(content=system_msg), content.get_user_message(self.settings.use_vision)]
		else:
			# if no browser session, we can't validate the output
			return True

		class ValidationResult(BaseModel):
			"""
			Validation results.
			"""

			is_valid: bool
			reason: str

		validator = self.llm.with_structured_output(ValidationResult, include_raw=True)
		response: dict[str, Any] = await validator.ainvoke(msg)  # type: ignore
		parsed: ValidationResult = response['parsed']
		is_valid = parsed.is_valid
		if not is_valid:
			logger.info(f'❌ Validator decision: {parsed.reason}')
			msg = f'The output is not yet correct. {parsed.reason}.'
			self.state.last_result = [ActionResult(extracted_content=msg, include_in_memory=True)]
		else:
			logger.info(f'✅ Validator decision: {parsed.reason}')
		return is_valid

	async def log_completion(self) -> None:
		"""Log the completion of the task"""
		logger.info('✅ Task completed')
		if self.state.history.is_successful():
			logger.info('✅ Successfully')
		else:
			logger.info('❌ Unfinished')

		if self.register_done_callback:
			if inspect.iscoroutinefunction(self.register_done_callback):
				await self.register_done_callback(self.state.history)
			else:
				self.register_done_callback(self.state.history)

	async def rerun_history(
		self,
		history: AgentHistoryList,
		max_retries: int = 3,
		skip_failures: bool = True,
		delay_between_actions: float = 2.0,
	) -> list[ActionResult]:
		"""
		Rerun a saved history of actions with error handling and retry logic.

		Args:
				history: The history to replay
				max_retries: Maximum number of retries per action
				skip_failures: Whether to skip failed actions or stop execution
				delay_between_actions: Delay between actions in seconds

		Returns:
				List of action results
		"""
		# Execute initial actions if provided
		if self.initial_actions:
			result = await self.multi_act(self.initial_actions)
			self.state.last_result = result

		results = []

		for i, history_item in enumerate(history.history):
			goal = history_item.model_output.current_state.next_goal if history_item.model_output else ''
			logger.info(f'Replaying step {i + 1}/{len(history.history)}: goal: {goal}')

			if (
				not history_item.model_output
				or not history_item.model_output.action
				or history_item.model_output.action == [None]
			):
				logger.warning(f'Step {i + 1}: No action to replay, skipping')
				results.append(ActionResult(error='No action to replay'))
				continue

			retry_count = 0
			while retry_count < max_retries:
				try:
					result = await self._execute_history_step(history_item, delay_between_actions)
					results.extend(result)
					break

				except Exception as e:
					retry_count += 1
					if retry_count == max_retries:
						error_msg = f'Step {i + 1} failed after {max_retries} attempts: {str(e)}'
						logger.error(error_msg)
						if not skip_failures:
							results.append(ActionResult(error=error_msg))
							raise RuntimeError(error_msg)
					else:
						logger.warning(f'Step {i + 1} failed (attempt {retry_count}/{max_retries}), retrying...')
						await asyncio.sleep(delay_between_actions)

		return results

	async def _execute_history_step(self, history_item: AgentHistory, delay: float) -> list[ActionResult]:
		"""Execute a single step from history with element validation"""
		state = await self.browser_context.get_state()
		if not state or not history_item.model_output:
			raise ValueError('Invalid state or model output')
		updated_actions = []
		for i, action in enumerate(history_item.model_output.action):
			updated_action = await self._update_action_indices(
				history_item.state.interacted_element[i],
				action,
				state,
			)
			updated_actions.append(updated_action)

			if updated_action is None:
				raise ValueError(f'Could not find matching element {i} in current page')

		result = await self.multi_act(updated_actions)

		await asyncio.sleep(delay)
		return result

	async def _update_action_indices(
		self,
		historical_element: Optional[DOMHistoryElement],
		action: ActionModel,  # Type this properly based on your action model
		current_state: BrowserState,
	) -> Optional[ActionModel]:
		"""
		Update action indices based on current page state.
		Returns updated action or None if element cannot be found.
		"""
		if not historical_element or not current_state.element_tree:
			return action

		current_element = HistoryTreeProcessor.find_history_element_in_tree(historical_element, current_state.element_tree)

		if not current_element or current_element.highlight_index is None:
			return None

		old_index = action.get_index()
		if old_index != current_element.highlight_index:
			action.set_index(current_element.highlight_index)
			logger.info(f'Element moved in DOM, updated index from {old_index} to {current_element.highlight_index}')

		return action

	async def load_and_rerun(self, history_file: Optional[str | Path] = None, **kwargs) -> list[ActionResult]:
		"""
		Load history from file and rerun it.

		Args:
				history_file: Path to the history file
				**kwargs: Additional arguments passed to rerun_history
		"""
		if not history_file:
			history_file = 'AgentHistory.json'
		history = AgentHistoryList.load_from_file(history_file, self.AgentOutput)
		return await self.rerun_history(history, **kwargs)

	def save_history(self, file_path: Optional[str | Path] = None) -> None:
		"""Save the history to a file"""
		if not file_path:
			file_path = 'AgentHistory.json'
		self.state.history.save_to_file(file_path)

	def pause(self) -> None:
		"""Pause the agent before the next step"""
		print('\n\n⏸️  Got Ctrl+C, paused the agent and left the browser open.')
		self.state.paused = True

		# The signal handler will handle the asyncio pause logic for us
		# No need to duplicate the code here

	def resume(self) -> None:
		"""Resume the agent"""
		print('----------------------------------------------------------------------')
		print('▶️  Got Enter, resuming agent execution where it left off...\n')
		self.state.paused = False

		# The signal handler should have already reset the flags
		# through its reset() method when called from run()

		# playwright browser is always immediately killed by the first Ctrl+C (no way to stop that)
		# so we need to restart the browser if user wants to continue
		if self.browser:
			logger.info('🌎 Restarting/reconnecting to browser...')
			loop = asyncio.get_event_loop()
			loop.create_task(self.browser._init())
			loop.create_task(asyncio.sleep(5))

	def stop(self) -> None:
		"""Stop the agent"""
		logger.info('⏹️ Agent stopping')
		self.state.stopped = True

	def _convert_initial_actions(self, actions: List[Dict[str, Dict[str, Any]]]) -> List[ActionModel]:
		"""Convert dictionary-based actions to ActionModel instances"""
		converted_actions = []
		action_model = self.ActionModel
		for action_dict in actions:
			# Each action_dict should have a single key-value pair
			action_name = next(iter(action_dict))
			params = action_dict[action_name]

			# Get the parameter model for this action from registry
			action_info = self.runner.registry.registry.actions[action_name]
			param_model = action_info.param_model

			# Create validated parameters using the appropriate param model
			validated_params = param_model(**params)

			# Create ActionModel instance with the validated parameters
			action_model = self.ActionModel(**{action_name: validated_params})
			converted_actions.append(action_model)

		return converted_actions

	async def _verify_llm_connection(self, llm: BaseChatModel) -> bool:
		"""
		Verify that the LLM API keys are working properly by sending a simple test prompt
		and checking that the response contains the expected answer.
		"""
		if getattr(llm, '_verified_api_keys', None) is True or SKIP_LLM_API_KEY_VERIFICATION:
			# If the LLM API keys have already been verified during a previous run, skip the test
			return True

		test_prompt = 'What is the capital of France? Respond with a single word.'
		test_answer = 'paris'
		required_keys = REQUIRED_LLM_API_ENV_VARS.get(llm.__class__.__name__, ['OPENAI_API_KEY'])
		try:
			response = await llm.ainvoke([HumanMessage(content=test_prompt)])
			response_text = str(response.content).lower()

			if test_answer in response_text:
				logger.debug(
					f'🧠 LLM API keys {", ".join(required_keys)} verified, {llm.__class__.__name__} model is connected and responding correctly.'
				)
				llm._verified_api_keys = True
				return True
			else:
				logger.debug(
					'❌  Got bad LLM response to basic sanity check question: %s  EXPECTING: %s  GOT: %s',
					test_prompt,
					test_answer,
					response,
				)
				raise Exception('LLM responded to a simple test question incorrectly')
		except Exception as e:
			logger.error(
				f'\n\n❌  LLM {llm.__class__.__name__} connection test failed. Check that {", ".join(required_keys)} is set correctly in .env and that the LLM API account has sufficient funding.\n'
			)
			raise Exception(f'LLM API connection test failed: {e}') from e
		return False

	async def _run_planner(self) -> Optional[str]:
		"""Run the planner to analyze state and suggest next steps"""
		# Skip planning if no planner_llm is set
		if not self.settings.planner_llm:
			return None

		# Get current state to filter actions by page
		page = await self.browser_context.get_current_page()

		# Get all standard actions (no filter) and page-specific actions
		standard_actions = self.runner.registry.get_prompt_description()  # No page = system prompt actions
		page_actions = self.runner.registry.get_prompt_description(page)  # Page-specific actions

		# Combine both for the planner
		all_actions = standard_actions
		if page_actions:
			all_actions += '\n' + page_actions

		# Create planner message history using full message history with all available actions
		planner_messages = [
			PlannerPrompt(all_actions).get_system_message(self.settings.is_planner_reasoning),
			*self._message_manager.get_messages()[1:],  # Use full message history except the first
		]

		if not self.settings.use_vision_for_planner and self.settings.use_vision:
			last_state_message: HumanMessage = planner_messages[-1]
			# remove image from last state message
			new_msg = ''
			if isinstance(last_state_message.content, list):
				for msg in last_state_message.content:
					if msg['type'] == 'text':  # type: ignore
						new_msg += msg['text']  # type: ignore
					elif msg['type'] == 'image_url':  # type: ignore
						continue  # type: ignore
			else:
				new_msg = last_state_message.content

			planner_messages[-1] = HumanMessage(content=new_msg)

		planner_messages = convert_input_messages(planner_messages, self.planner_model_name)

		# Get planner output
		try:
			response = await self.settings.planner_llm.ainvoke(planner_messages)
		except Exception as e:
			logger.error(f'Failed to invoke planner: {str(e)}')
			raise LLMException(401, 'LLM API call failed') from e

		plan = str(response.content)
		# if deepseek-reasoner, remove think tags
		if self.planner_model_name and (
			'deepseek-r1' in self.planner_model_name or 'deepseek-reasoner' in self.planner_model_name
		):
			plan = self._remove_think_tags(plan)
		try:
			plan_json = json.loads(plan)
			logger.info(f'Planning Analysis:\n{json.dumps(plan_json, indent=4)}')
		except json.JSONDecodeError:
			logger.info(f'Planning Analysis:\n{plan}')
		except Exception as e:
			logger.debug(f'Error parsing planning analysis: {e}')
			logger.info(f'Plan: {plan}')

		return plan

	@property
	def message_manager(self) -> MessageManager:
		return self._message_manager

	async def close(self):
		"""Close all resources"""
		try:
			# First close browser resources
			if self.browser_context and not self.injected_browser_context:
				await self.browser_context.close()
			if self.browser and not self.injected_browser:
				await self.browser.close()

			# Force garbage collection
			gc.collect()

		except Exception as e:
			logger.error(f'Error during cleanup: {e}')

	async def _update_action_models_for_page(self, page, global_context=None) -> None:
		"""Update action models with page-specific actions"""
		# Create new action model with current page's filtered actions
		# general purpose code
		self.ActionModel = self.runner.registry.create_action_model(page=page, global_context=global_context)
		# Update output model with the new actions
		self.AgentOutput = AgentOutput.type_with_custom_actions(self.ActionModel)

		# Update done action model too
		self.DoneActionModel = self.runner.registry.create_action_model(include_actions=['done'], page=page)
		self.DoneAgentOutput = AgentOutput.type_with_custom_actions(self.DoneActionModel)

	def get_card(self):
		return self.card

	def get_a2a_server_port(self):
		print(f"a2a server port: {self.a2a_server.agent_card.url.split(':')[-1]}")
		return int(self.a2a_server.agent_card.url.split(":")[-1])

	def is_busy(self):
		busy = False
		return busy

	@time_execution_async('--resolve (agent)')
	async def resolve(
			self, runner_context, max_steps=8
	) -> bool:
		"""Execute the task with maximum number of steps"""
		resolved = False
		loop = asyncio.get_event_loop()

		# Set up the Ctrl+C signal handler with callbacks specific to this agent
		from agent.run_utils import SignalHandler

		signal_handler = SignalHandler(
			loop=loop,
			pause_callback=self.pause,
			resume_callback=self.resume,
			custom_exit_callback=None,  # No special cleanup needed on forced exit
			exit_on_second_int=True,
		)
		signal_handler.register()

		# Start non-blocking LLM connection verification
		assert self.llm._verified_api_keys, 'Failed to verify LLM API keys'

		try:
			self._log_agent_run()

			# Execute initial actions if provided
			if self.initial_actions:
				result = await self.multi_act(self.initial_actions, check_for_new_elements=False)
				self.state.last_result = result

			for step in range(max_steps):
				# Check if waiting for user input after Ctrl+C
				if self.state.paused:
					signal_handler.wait_for_resume()
					signal_handler.reset()

				# Check if we should stop due to too many failures
				if self.state.consecutive_failures >= self.settings.max_failures:
					logger.error(f'❌ Stopping due to {self.settings.max_failures} consecutive failures')
					break

				# Check control flags before each step
				if self.state.stopped:
					logger.info('Agent stopped')
					break

				while self.state.paused:
					await asyncio.sleep(0.2)  # Small delay to prevent CPU spinning
					if self.state.stopped:  # Allow stopping while paused
						break


				step_info = AgentStepInfo(step_number=step, max_steps=max_steps)
				await self.step(step_info)


				if self.state.history.is_done():
					if self.settings.validate_output and step < max_steps - 1:
						if not await self._validate_output():
							continue

					await self.log_completion()
					break
			else:
				logger.info('❌ Failed to complete task in maximum steps')

			return result, resolved

		except KeyboardInterrupt:
			# Already handled by our signal handler, but catch any direct KeyboardInterrupt as well
			logger.info('Got KeyboardInterrupt during execution, returning current history')
			return self.state.history

		finally:
			# Unregister signal handlers before cleanup
			signal_handler.unregister()

			self.telemetry.capture(
				AgentEndTelemetryEvent(
					agent_id=self.state.agent_id,
					is_done=self.state.history.is_done(),
					success=self.state.history.is_successful(),
					steps=self.state.n_steps,
					max_steps_reached=self.state.n_steps >= max_steps,
					errors=self.state.history.errors(),
					total_input_tokens=self.state.history.total_input_tokens(),
					total_duration_seconds=self.state.history.total_duration_seconds(),
				)
			)

			await self.close()

			if self.settings.generate_gif:
				output_path: str = 'agent_history.gif'
				if isinstance(self.settings.generate_gif, str):
					output_path = self.settings.generate_gif

		# create_history_gif(task=self.task, history=self.state.history, output_path=output_path)

	def start_a2a_server_in_thread(self, a2a_server):
		def run_server():
			a2a_server.start()  # this is the uvicorn.run(...) call

		self.a2a_server_thread = threading.Thread(target=run_server)
		self.a2a_server_thread.daemon = True
		self.a2a_server_thread.start()

	def exit_a2a_server_in_thread(self):
		if self.a2a_server_thread and self.a2a_server_thread.is_alive():
			self.a2a_server_thread.join(timeout=5)

	async def start(self):
		# kick off a2a server:
		self.start_a2a_server_in_thread(self.a2a_server)
		print("A2A server started....")
		# kick off TaskExecutor
		for task in self.tasks:
			if task.trigger == "schedule":
				self.running_tasks.append(asyncio.create_task(self.runner.launch_scheduled_run(task)))
			elif task.trigger == "message":
				self.running_tasks.append(asyncio.create_task(self.runner.launch_reacted_run(task)))
			elif task.trigger == "interaction":
				self.running_tasks.append(asyncio.create_task(self.runner.launch_interacted_run(task)))
			else:
				print("WARNING: UNRECOGNIZED task trigger type....")

		# runnable = self.skill_set[0].get_runnable()
		# response: dict[str, Any] = await self.runnable.ainvoke(input_messages)
		# runnable.ainvoke()
		print("Ready to A2A chat....")

	async def hone_skills(self):
		print("hone skills...")

	def get_task_id_from_request(self, req):
		task_id = req.params.id
		print(f"TASK ID IN QUERY:{task_id}.")
		return task_id

	@time_execution_async('--request_local_help (agent)')
	async def request_local_help(self, recipient_agent=None):
		# this is only available if myself is not a helper agent
		helper = next((ag for ag in self.mainwin.agents if "helper" in self.get_card().name.lower()), None)
		print("client card:", self.get_card().name.lower())
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

			print("client payload:", payload["id"])
			response = await self.a2a_client.send_task(payload)
			print("A2A RESPONSE:", response)
		else:
			print("client err:", self.get_card().name.lower())

	# class Message(BaseModel):
	# 	role: Literal["user", "agent"]
	# 	parts: List[Part]
	# 	metadata: dict[str, Any] | None = None
	@time_execution_async('--a2a_send_message (agent, message)')
	async def a2a_send_chat_message(self, recipient_agent, message):
		# this is only available if myself is not a helper agent
		print("recipient card:", recipient_agent.get_card().name.lower())

		try:
			a2a_end_point = recipient_agent.get_card().url + "/a2a/"
			print("a2a end point: ", a2a_end_point)
			self.a2a_client.set_recipient(url=a2a_end_point)
			chat_msg = Message(role="user", parts=[TextPart(type="text", text="Summarize this report")], metadata={"type": "send_chat"})

			payload = {
				"id": "task-001X",
				"sessionId": "sess-abc",
				"message": chat_msg,
				"acceptedOutputModes": ["json"],
				"skill": "resolve_rpa_failure"  # Or whatever your agent expects
			}

			print("client payload:", payload)
			response = await self.a2a_client.send_task(payload)
			print("A2A RESPONSE:", response)
			return response
		except Exception as e:
			# Get the traceback information
			traceback_info = traceback.extract_tb(e.__traceback__)
			# Extract the file name and line number from the last entry in the traceback
			if traceback_info:
				ex_stat = "ErrorA2ASend:" + traceback.format_exc() + " " + str(e)
			else:
				ex_stat = "ErrorA2ASend: traceback information not available:" + str(e)
			print(ex_stat)

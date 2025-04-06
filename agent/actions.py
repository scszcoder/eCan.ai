from inspect import iscoroutinefunction, signature
from typing import Any, Callable, Dict, Generic, Optional, Type, TypeVar
from selenium import webdriver


from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, create_model, ConfigDict

from browser.context import BrowserContext

from telemetry.service import ProductTelemetry
from telemetry.views import (
	ControllerRegisteredFunctionsTelemetryEvent,
	RegisteredFunction,
)

from agent.run_utils import time_execution_async, time_execution_sync

class RegisteredAction(BaseModel):
	"""Model for a registered action"""

	name: str
	description: str
	function: Callable
	param_model: Type[BaseModel]

	# filters: provide specific domains or a function to determine whether the action should be available on the given page or not
	domains: list[str] | None = None  # e.g. ['*.google.com', 'www.bing.com', 'yahoo.*]
	page_filter: Callable[[webdriver], bool] | None = None

	model_config = ConfigDict(arbitrary_types_allowed=True)

	def prompt_description(self) -> str:
		"""Get a description of the action for the prompt"""
		skip_keys = ['title']
		s = f'{self.description}: \n'
		s += '{' + str(self.name) + ': '
		s += str(
			{
				k: {sub_k: sub_v for sub_k, sub_v in v.items() if sub_k not in skip_keys}
				for k, v in self.param_model.model_json_schema()['properties'].items()
			}
		)
		s += '}'
		return s


class ActionModel(BaseModel):
	"""Base model for dynamically created action models"""

	# this will have all the registered actions, e.g.
	# click_element = param_model = ClickElementParams
	# done = param_model = None
	#
	model_config = ConfigDict(arbitrary_types_allowed=True)

	def get_index(self) -> int | None:
		"""Get the index of the action"""
		# {'clicked_element': {'index':5}}
		params = self.model_dump(exclude_unset=True).values()
		if not params:
			return None
		for param in params:
			if param is not None and 'index' in param:
				return param['index']
		return None

	def set_index(self, index: int):
		"""Overwrite the index of the action"""
		# Get the action name and params
		action_data = self.model_dump(exclude_unset=True)
		action_name = next(iter(action_data.keys()))
		action_params = getattr(self, action_name)

		# Update the index directly on the model
		if hasattr(action_params, 'index'):
			action_params.index = index


class ActionRegistry(BaseModel):
	"""Model representing the action registry"""

	actions: Dict[str, RegisteredAction] = {}

	@staticmethod
	def _match_domains(domains: list[str] | None, url: str) -> bool:
		"""
		Match a list of domain glob patterns against a URL.

		Args:
			domain_patterns: A list of domain patterns that can include glob patterns (* wildcard)
			url: The URL to match against

		Returns:
			True if the URL's domain matches the pattern, False otherwise
		"""

		if domains is None or not url:
			return True

		import fnmatch
		from urllib.parse import urlparse

		# Parse the URL to get the domain
		try:
			parsed_url = urlparse(url)
			if not parsed_url.netloc:
				return False

			domain = parsed_url.netloc
			# Remove port if present
			if ':' in domain:
				domain = domain.split(':')[0]

			for domain_pattern in domains:
				if fnmatch.fnmatch(domain, domain_pattern):  # Perform glob *.matching.*
					return True
			return False
		except Exception:
			return False

	@staticmethod
	def _match_page_filter(page_filter: Callable[[webdriver], bool] | None, page: webdriver) -> bool:
		"""Match a page filter against a page"""
		if page_filter is None:
			return True
		return page_filter(page)

	def get_prompt_description(self, page: Page | None = None) -> str:
		"""Get a description of all actions for the prompt

		Args:
			page: If provided, filter actions by page using page_filter and domains.

		Returns:
			A string description of available actions.
			- If page is None: return only actions with no page_filter and no domains (for system prompt)
			- If page is provided: return only filtered actions that match the current page (excluding unfiltered actions)
		"""
		if page is None:
			# For system prompt (no page provided), include only actions with no filters
			return '\n'.join(
				action.prompt_description()
				for action in self.actions.values()
				if action.page_filter is None and action.domains is None
			)

		# only include filtered actions for the current page
		filtered_actions = []
		for action in self.actions.values():
			if not (action.domains or action.page_filter):
				# skip actions with no filters, they are already included in the system prompt
				continue

			domain_is_allowed = self._match_domains(action.domains, page.url)
			page_is_allowed = self._match_page_filter(action.page_filter, page)

			if domain_is_allowed and page_is_allowed:
				filtered_actions.append(action)

		return '\n'.join(action.prompt_description() for action in filtered_actions)


Context = TypeVar('Context')


class Registry(Generic[Context]):
	"""Service for registering and managing actions"""

	def __init__(self, exclude_actions: list[str] | None = None):
		self.registry = ActionRegistry()
		# self.telemetry = ProductTelemetry()
		self.exclude_actions = exclude_actions if exclude_actions is not None else []

	@time_execution_sync('--create_param_model')
	def _create_param_model(self, function: Callable) -> Type[BaseModel]:
		"""Creates a Pydantic model from function signature"""
		sig = signature(function)
		params = {
			name: (param.annotation, ... if param.default == param.empty else param.default)
			for name, param in sig.parameters.items()
			if name != 'browser' and name != 'page_extraction_llm' and name != 'available_file_paths'
		}

		# 2do: make the types here work
		return create_model(
			f'{function.__name__}_parameters',
			__base__=ActionModel,
			**params,  # type: ignore
		)

	def action(
		self,
		description: str,
		param_model: Optional[Type[BaseModel]] = None,
		domains: Optional[list[str]] = None,
		page_filter: Optional[Callable[[Any], bool]] = None,
	):
		"""Decorator for registering actions"""

		def decorator(func: Callable):
			# Skip registration if action is in exclude_actions
			if func.__name__ in self.exclude_actions:
				return func

			# Create param model from function if not provided
			actual_param_model = param_model or self._create_param_model(func)

			# Wrap sync functions to make them async
			if not iscoroutinefunction(func):

				async def async_wrapper(*args, **kwargs):
					return await asyncio.to_thread(func, *args, **kwargs)

				# Copy the signature and other metadata from the original function
				async_wrapper.__signature__ = signature(func)
				async_wrapper.__name__ = func.__name__
				async_wrapper.__annotations__ = func.__annotations__
				wrapped_func = async_wrapper
			else:
				wrapped_func = func

			action = RegisteredAction(
				name=func.__name__,
				description=description,
				function=wrapped_func,
				param_model=actual_param_model,
				domains=domains,
				page_filter=page_filter,
			)
			self.registry.actions[func.__name__] = action
			return func

		return decorator

	@time_execution_async('--execute_action')
	async def execute_action(
		self,
		action_name: str,
		params: dict,
		browser: Optional[BrowserContext] = None,
		page_extraction_llm: Optional[BaseChatModel] = None,
		sensitive_data: Optional[Dict[str, str]] = None,
		available_file_paths: Optional[list[str]] = None,
		#
		context: Context | None = None,
	) -> Any:
		"""Execute a registered action"""
		if action_name not in self.registry.actions:
			raise ValueError(f'Action {action_name} not found')

		action = self.registry.actions[action_name]
		try:
			# Create the validated Pydantic model
			validated_params = action.param_model(**params)

			# Check if the first parameter is a Pydantic model
			sig = signature(action.function)
			parameters = list(sig.parameters.values())
			is_pydantic = parameters and issubclass(parameters[0].annotation, BaseModel)
			parameter_names = [param.name for param in parameters]

			if sensitive_data:
				validated_params = self._replace_sensitive_data(validated_params, sensitive_data)

			# Check if the action requires browser
			if 'browser' in parameter_names and not browser:
				raise ValueError(f'Action {action_name} requires browser but none provided.')
			if 'page_extraction_llm' in parameter_names and not page_extraction_llm:
				raise ValueError(f'Action {action_name} requires page_extraction_llm but none provided.')
			if 'available_file_paths' in parameter_names and not available_file_paths:
				raise ValueError(f'Action {action_name} requires available_file_paths but none provided.')

			if 'context' in parameter_names and not context:
				raise ValueError(f'Action {action_name} requires context but none provided.')

			# Prepare arguments based on parameter type
			extra_args = {}
			if 'context' in parameter_names:
				extra_args['context'] = context
			if 'browser' in parameter_names:
				extra_args['browser'] = browser
			if 'page_extraction_llm' in parameter_names:
				extra_args['page_extraction_llm'] = page_extraction_llm
			if 'available_file_paths' in parameter_names:
				extra_args['available_file_paths'] = available_file_paths
			if action_name == 'input_text' and sensitive_data:
				extra_args['has_sensitive_data'] = True
			if is_pydantic:
				return await action.function(validated_params, **extra_args)
			return await action.function(**validated_params.model_dump(), **extra_args)

		except Exception as e:
			raise RuntimeError(f'Error executing action {action_name}: {str(e)}') from e

	def _replace_sensitive_data(self, params: BaseModel, sensitive_data: Dict[str, str]) -> BaseModel:
		"""Replaces the sensitive data in the params"""
		# if there are any str with <secret>placeholder</secret> in the params, replace them with the actual value from sensitive_data

		import re

		secret_pattern = re.compile(r'<secret>(.*?)</secret>')

		def replace_secrets(value):
			if isinstance(value, str):
				matches = secret_pattern.findall(value)
				for placeholder in matches:
					if placeholder in sensitive_data:
						value = value.replace(f'<secret>{placeholder}</secret>', sensitive_data[placeholder])
				return value
			elif isinstance(value, dict):
				return {k: replace_secrets(v) for k, v in value.items()}
			elif isinstance(value, list):
				return [replace_secrets(v) for v in value]
			return value

		for key, value in params.model_dump().items():
			params.__dict__[key] = replace_secrets(value)
		return params

	@time_execution_sync('--create_action_model')
	def create_action_model(self, include_actions: Optional[list[str]] = None, page=None) -> Type[ActionModel]:
		"""Creates a Pydantic model from registered actions, used by LLM APIs that support tool calling & enforce a schema"""

		# Filter actions based on page if provided:
		#   if page is None, only include actions with no filters
		#   if page is provided, only include actions that match the page

		available_actions = {}
		for name, action in self.registry.actions.items():
			if include_actions is not None and name not in include_actions:
				continue

			# If no page provided, only include actions with no filters
			if page is None:
				if action.page_filter is None and action.domains is None:
					available_actions[name] = action
				continue

			# Check page_filter if present
			domain_is_allowed = self.registry._match_domains(action.domains, page.url)
			page_is_allowed = self.registry._match_page_filter(action.page_filter, page)

			# Include action if both filters match (or if either is not present)
			if domain_is_allowed and page_is_allowed:
				available_actions[name] = action

		fields = {
			name: (
				Optional[action.param_model],
				Field(default=None, description=action.description),
			)
			for name, action in available_actions.items()
		}

		# self.telemetry.capture(
		# 	ControllerRegisteredFunctionsTelemetryEvent(
		# 		registered_functions=[
		# 			RegisteredFunction(name=name, params=action.param_model.model_json_schema())
		# 			for name, action in available_actions.items()
		# 		]
		# 	)
		# )

		return create_model('ActionModel', __base__=ActionModel, **fields)  # type:ignore

	def get_prompt_description(self, page=None) -> str:
		"""Get a description of all actions for the prompt

		If page is provided, only include actions that are available for that page
		based on their filter_func
		"""
		return self.registry.get_prompt_description(page=page)
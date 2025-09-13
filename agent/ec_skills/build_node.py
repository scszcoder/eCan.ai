import re
import os
import importlib.util
import httpx
import asyncio
from agent.mcp.local_client import mcp_call_tool
from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
from agent.ec_skills.dev_defs import BreakpointManager
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from agent.ec_skill import node_builder
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

def get_default_node_schemas():
    schemas = {
        "llm" : {

        }
    }
    return schemas

def build_llm_node(config_metadata: dict, node_name, skill_name, owner, bp_manager):
    """
    Builds a callable function for a LangGraph node that interacts with an LLM.

    Args:
        config_metadata: A dictionary containing the configuration for the LLM node,
                         including provider, model, temperature, and prompt templates.

    Returns:
        A callable function that takes a state dictionary and returns the updated state.
    """
    # Extract configuration from metadata with sensible defaults
    model_name = config_metadata.get("model_name", "gpt-3.5-turbo")
    temperature = float(config_metadata.get("temperature", 0.7))
    llm_provider = config_metadata.get("llm_provider", "openai").lower()
    system_prompt_template = config_metadata.get("system_prompt", "")
    user_prompt_template = config_metadata.get("user_prompt", "{input}")

    # Factory function to get the correct LLM client
    def get_llm_client(provider, model, temp):
        if provider == "openai":
            return ChatOpenAI(model=model, temperature=temp)
        elif provider == "anthropic":
            return ChatAnthropic(model=model, temperature=temp)
        elif provider == "google":
            return ChatGoogleGenerativeAI(model=model, temperature=temp)
        else:
            # Default to OpenAI if provider is unknown
            print(f"Warning: Unknown LLM provider '{provider}'. Defaulting to OpenAI.")
            return ChatOpenAI(model=model, temperature=temp)

    # This is the actual function that will be executed as the node in the graph
    def llm_node_callable(state: dict) -> dict:
        """
        The runtime callable for the LLM node. It formats prompts, invokes the LLM,
        and updates the state with the response.
        """
        print(f"Executing LLM node with state: {state}")

        # Find all variable placeholders (e.g., {var_name}) in the prompts
        variables = re.findall(r'\{(\w+)\}', system_prompt_template + user_prompt_template)

        # Get attributes from state, default to an empty dict if not present
        attributes = state.get("attributes", {})

        # Prepare the context for formatting the prompts by pulling values from the state
        format_context = {}
        for var in variables:
            if var in attributes:
                format_context[var] = attributes[var]
            else:
                print(f"Warning: Variable '{{{var}}}' not found in state attributes. Using empty string.")
                format_context[var] = ""

        # Format the final prompts with values from the state
        try:
            final_system_prompt = system_prompt_template.format(**format_context)
            final_user_prompt = user_prompt_template.format(**format_context)
        except KeyError as e:
            error_message = f"Error formatting prompt: Missing key {e} in state attributes."
            print(error_message)
            state['error'] = error_message
            return state

        # Build the message list for the LLM
        messages = []
        if final_system_prompt:
            messages.append(SystemMessage(content=final_system_prompt))
        messages.append(HumanMessage(content=final_user_prompt))

        # Instantiate the LLM client
        llm = get_llm_client(llm_provider, model_name, temperature)

        # Invoke the LLM and update the state
        try:
            response = llm.invoke(messages)
            # It's good practice to put results in specific keys
            if 'llm_responses' not in state:
                state['llm_responses'] = []
            state['llm_responses'].append(response.content)
            
            # Also update attributes for easy access by downstream nodes
            attributes['last_llm_response'] = response.content
            state['attributes'] = attributes

        except Exception as e:
            error_message = f"LLM invocation failed: {e}"
            print(error_message)
            state['error'] = error_message

        return state

    full_node_callable = node_builder(llm_node_callable, node_name, skill_name, owner, bp_manager)
    return full_node_callable


def build_basic_node(config_metadata: dict, node_id: str, skill_name: str, owner: str, bp_manager) -> callable:
    """
    Builds a basic node from a code source, which can be either a file path or an inline string.
    This function is responsible for dynamically loading or executing the code and returning
    a callable that can be used as a node in the graph.
    """
    print("building basic node", config_metadata)
    code_source = config_metadata.get('script').get('content')
    print("code_source:", code_source)
    if not code_source or not isinstance(code_source, str):
        print("Error: 'code' key is missing or invalid in config_metadata for basic_node.")
        # Return a no-op function that just passes the state through
        return lambda state: state

    node_callable = None
    node_name = node_id

    # Scenario 1: Code is a file path
    if False and (code_source.endswith('.py') and os.path.exists(code_source)):
        try:
            # Use a unique module name to avoid conflicts
            module_name = f"dynamic_basic_node_{os.path.basename(code_source)[:-3]}"
            spec = importlib.util.spec_from_file_location(module_name, code_source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Convention: the file must have a 'run' function
            if hasattr(module, 'run'):
                node_callable = getattr(module, 'run')
            else:
                print(f"Warning: Basic node file {code_source} is missing a 'run(state)' function.")

        except Exception as e:
            print(f"Error loading module from {code_source}: {e}")

    # Scenario 2: Code is an inline script
    else:
        try:
            # Define a scope for the exec to run in, so imports are captured
            local_scope = {}
            exec(code_source, local_scope, local_scope)

            # Find the 'main' function within the executed code's scope
            main_func = local_scope.get('main')
            if callable(main_func):
                node_callable = main_func
                print("callable obtained.....")
            else:
                 print(f"Warning: No function definition found in inline code for basic node.")

        except Exception as e:
            err_msg = get_traceback(e, "ErrorExecutingInlineCodeForBasicNode")
            print(f"{err_msg}")
            node_callable = None

    # If callable creation failed, return a no-op function
    if node_callable is None:
        return lambda state: state

    print("done building basic node", node_name)
    full_node_callable = node_builder(node_callable, node_name, skill_name, owner, bp_manager)

    return full_node_callable


def build_api_node(config_metadata: dict, node_name, skill_name, owner, bp_manager):
    """
    Builds a callable function for a node that makes an API call.

    Args:
        config_metadata: A dictionary containing the API call configuration:
                         - api_endpoint: URL for the request.
                         - method: HTTP method (GET, POST, etc.).
                         - headers: Request headers.
                         - params: Request parameters (for query string or body).
                         - sync: Boolean indicating if the call is synchronous.

    Returns:
        A sync or async callable function that takes a state dictionary.
    """
    # Extract configuration
    endpoint_template = config_metadata.get('api_endpoint')
    method = config_metadata.get('method', 'GET').upper()
    headers_template = config_metadata.get('headers', {})
    params_template = config_metadata.get('params', {})
    is_sync = config_metadata.get('sync', True)

    if not endpoint_template:
        print("Error: 'api_endpoint' is missing in config_metadata for api_node.")
        return lambda state: {**state, 'error': 'API endpoint not configured'}

    def _format_from_state(template, attributes):
        """Recursively format strings in a template dict/list with state attributes."""
        if isinstance(template, str):
            return template.format(**attributes)
        if isinstance(template, dict):
            return {k: _format_from_state(v, attributes) for k, v in template.items()}
        if isinstance(template, list):
            return [_format_from_state(i, attributes) for i in template]
        return template

    def _prepare_request_args(state):
        """Prepare final request arguments by formatting templates with state."""
        attributes = state.get("attributes", {})
        final_url = endpoint_template.format(**attributes)
        final_headers = _format_from_state(headers_template, attributes)
        final_params = _format_from_state(params_template, attributes)

        request_args = {'method': method, 'url': final_url, 'headers': final_headers}
        if method in ['GET', 'DELETE']:
            request_args['params'] = final_params
        else: # POST, PUT, PATCH
            request_args['json'] = final_params
        
        return request_args

    # Define the synchronous version of the callable
    def sync_api_callable(state: dict) -> dict:
        print(f"Executing sync API node for endpoint: {endpoint_template}")
        request_args = _prepare_request_args(state)
        try:
            with httpx.Client() as client:
                response = client.request(**request_args)
                response.raise_for_status() # Raise an exception for bad status codes
                state.setdefault('results', []).append(response.json())
        except httpx.HTTPStatusError as e:
            error_msg = f"API call failed with status {e.response.status_code}: {e.response.text}"
            print(error_msg)
            state['error'] = error_msg
        except Exception as e:
            error_msg = f"API call failed: {e}"
            print(error_msg)
            state['error'] = error_msg
        return state

    # Define the asynchronous version of the callable
    async def async_api_callable(state: dict) -> dict:
        print(f"Executing async API node for endpoint: {endpoint_template}")
        request_args = _prepare_request_args(state)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(**request_args)
                response.raise_for_status()
                state.setdefault('results', []).append(response.json())
        except httpx.HTTPStatusError as e:
            error_msg = f"API call failed with status {e.response.status_code}: {e.response.text}"
            print(error_msg)
            state['error'] = error_msg
        except Exception as e:
            error_msg = f"API call failed: {e}"
            print(error_msg)
            state['error'] = error_msg
        return state

    # return sync_api_callable if is_sync else async_api_callable

    # Return the correct function based on the 'sync' flag
    full_node_callable = node_builder(sync_api_callable, node_name, skill_name, owner, bp_manager)

    return full_node_callable


def build_mcp_tool_calling_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """
    Builds a callable function for a node that calls an MCP tool.

    Args:
        config_metadata: A dictionary containing the tool configuration:
                         - tool_name: The name of the MCP tool to call.

    Returns:
        A callable function that takes a state dictionary.
    """
    tool_name = config_metadata.get('tool_name')

    if not tool_name:
        print("Error: 'tool_name' is missing in config_metadata for mcp_tool_calling_node.")
        return lambda state: {**state, 'error': 'MCP tool_name not configured'}

    def mcp_tool_callable(state: dict) -> dict:
        print(f"Executing MCP tool node for tool: {tool_name}")

        # By convention, the input for the tool is expected in state['tool_input']
        tool_input = state.get('tool_input', {})

        async def run_tool_call():
            """A local async function to perform the actual tool call."""
            print(f"Calling MCP tool '{tool_name}' with input: {tool_input}")
            return await mcp_call_tool(tool_name, tool_input)

        try:
            # Use the utility to run the async function from a sync context
            tool_result = run_async_in_sync(run_tool_call())
            
            # Add the result to the state
            state.setdefault('results', []).append(tool_result)

            # Also update attributes for easier access by subsequent nodes
            attributes = state.get('attributes', {})
            attributes[f'{tool_name}_result'] = tool_result
            state['attributes'] = attributes

        except Exception as e:
            error_msg = f"MCP tool call '{tool_name}' failed: {e}"
            print(error_msg)
            state['error'] = error_msg

        return state

    # graph.add_node("step1", breakpoint_wrapper(step1, "step1", bp_manager))

    node_callable = node_builder(mcp_tool_callable, node_name, skill_name, owner, bp_manager)
    return node_callable


def build_condition_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    node_callable = None

    return node_callable


def build_loop_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    node_callable = None

    return node_callable

def build_debug_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    node_callable = None

    return node_callable
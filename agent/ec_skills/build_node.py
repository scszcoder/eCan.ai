import re
import os
import importlib.util
import httpx
import asyncio
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
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
from langgraph.types import interrupt
from app_context import AppContext

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
    # Extract configuration from metadata with sensible defaults (tolerant to missing keys)
    logger.debug("building llm node:", config_metadata)
    inputs = (config_metadata or {}).get("inputsValues", {}) or {}
    # Prefer explicit provider; infer from apiHost if absent
    raw_provider = None
    try:
        raw_provider = ((inputs.get("modelProvider") or {}).get("content")
                        or (inputs.get("provider") or {}).get("content"))
    except Exception:
        raw_provider = None
    model_name = ((inputs.get("modelName") or {}).get("content")
                  or (inputs.get("model") or {}).get("content")
                  or "gpt-3.5-turbo")
    api_key = ((inputs.get("apiKey") or {}).get("content") or "")
    api_host = ((inputs.get("apiHost") or {}).get("content") or "")
    try:
        temperature = float(((inputs.get("temperature") or {}).get("content") or 0.5))
    except Exception:
        temperature = 0.5
    system_prompt_template = ((inputs.get("systemPrompt") or {}).get("content")
                              or "You are an AI assistant.")
    user_prompt_template = ((inputs.get("prompt") or {}).get("content")
                            or "You are an AI assistant.")

    # Infer provider when not explicitly set
    def _infer_provider(host: str, model: str) -> str:
        try:
            h = (host or "").lower()
            m = (model or "").lower()
            if "anthropic" in h or m.startswith("claude"):
                return "anthropic"
            if "google" in h or "generativeai" in h or m.startswith("gemini"):
                return "google"
            return "openai"
        except Exception:
            return "openai"

    model_provider = raw_provider or _infer_provider(api_host, model_name)
    llm_provider = (model_provider or "openai").lower()

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
    def llm_node_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        """
        The runtime callable for the LLM node. It formats prompts, invokes the LLM,
        and updates the state with the response.
        """
        print(f"Executing LLM node with state: {state}")

        # Find all variable placeholders (e.g., {var_name}) in the prompts
        variables = re.findall(r'\{(\w+)\}', system_prompt_template + user_prompt_template)

        # Get attributes from state, default to an empty dict if not present
        prompt_refs = state.get("prompt_refs", {})

        # Prepare the context for formatting the prompts by pulling values from the state
        format_context = {}
        for var in variables:
            if var in prompt_refs:
                format_context[var] = prompt_refs[var]
            else:
                print(f"Warning: Variable '{{{var}}}' not found in state prompt_refs. Using empty string.")
                format_context[var] = ""

        # Format the final prompts with values from the state
        try:
            final_system_prompt = system_prompt_template.format(**format_context)
            final_user_prompt = user_prompt_template.format(**format_context)
        except KeyError as e:
            error_message = f"Error formatting prompt: Missing key {e} in state prompt_refs."
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
            state['llm_responses'].append({'provider': llm_provider, 'model': model_name, 'content': response.content})
            # Ensure messages list exists before appending
            if 'messages' not in state or not isinstance(state.get('messages'), list):
                state['messages'] = []
            state['messages'].append(response.content)


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
    logger.debug("building basic node", config_metadata)
    # Safely extract inline script content; tolerate missing keys and fall back to no-op
    try:
        code_source = (config_metadata or {}).get('script', {}).get('content')
    except Exception:
        code_source = None
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
    # Extract configuration (support legacy `{http: {...}}` and new flowgram schema)
    logger.debug("building api node...", config_metadata)
    cfg_http = config_metadata.get("http") if isinstance(config_metadata, dict) else None
    if isinstance(cfg_http, dict):
        api_endpoint = cfg_http.get('apiUrl') or cfg_http.get('url') or ""
        method = (cfg_http.get('apiMethod') or cfg_http.get('method') or "GET").upper()
        timeout = int(cfg_http.get('timeout', 30))
        retries = int(cfg_http.get('retry', 3))
        headers_template = cfg_http.get('requestHeadersValues', {'Content-Type': {'type': 'constant', 'content': 'application/json'}})
        params_template = cfg_http.get('requestParams', {})
        api_key = cfg_http.get('apiKey', "")
        attachments = cfg_http.get('attachments', [])
    else:
        api = (config_metadata.get('api') or {}) if isinstance(config_metadata, dict) else {}
        url_field = api.get('url')
        if isinstance(url_field, dict):
            api_endpoint = url_field.get('content') or ""
        else:
            api_endpoint = str(url_field or "")
        method = (api.get('method') or "GET").upper()
        to = (config_metadata.get('timeout') or {}) if isinstance(config_metadata, dict) else {}
        # incoming timeout in ms; convert to seconds, fallback 10s
        timeout = int(max(1, int((to.get('timeout') or 10000) / 1000)))
        retries = int((to.get('retryTimes') or 1))
        headers_template = (config_metadata.get('headers') or {})
        params_template = (config_metadata.get('params') or {})
        body_cfg = (config_metadata.get('body') or {})
        attachments = body_cfg.get('attachments', []) if isinstance(body_cfg, dict) else []
        api_key = (config_metadata.get('apiKey') or "")

    is_sync = bool((config_metadata or {}).get('sync', True))

    if not api_endpoint:
        print("Error: 'api_endpoint' is missing in config_metadata for api_node.")
        return lambda state: {**state, 'error': 'API endpoint not configured'}

    def _format_from_state(template, attributes):
        """Recursively format strings in a template dict/list with state attributes."""
        if isinstance(template, str):
            return template.format(**attributes)
        if isinstance(template, dict):
            out = {}
            for k, v in template.items():
                if isinstance(v, dict):
                    # Prefer 'content' if present
                    val = v.get('content', None)
                    if val is None:
                        # If no 'content', try formatting the entire dict recursively
                        val = _format_from_state(v, attributes)
                    out[k] = val
                else:
                    out[k] = _format_from_state(v, attributes)
            return out
        if isinstance(template, list):
            return [_format_from_state(i, attributes) for i in template]
        return template

    def _flatten_kv(template):
        """Recursively flatten {key: {type, content}} -> {key: formatted_content}"""
        out = {}
        if not isinstance(template, dict):
            return out
        for k, v in template.items():
            if isinstance(v, dict):
                # Prefer 'content' if present
                content = v.get('content')
                if content is None:
                    # If no 'content', try formatting the entire dict recursively
                    content = _format_from_state(v, {})
                if isinstance(content, str):
                    try:
                        content = content.format(**{})
                    except Exception:
                        pass
                out[k] = content
            elif isinstance(v, str):
                try:
                    out[k] = v.format(**{})
                except Exception:
                    out[k] = v
            else:
                out[k] = v
        return out

    def _prepare_request_args(state):
        """Prepare final request arguments by formatting templates with state.

        - headers_template follows requestHeadersValues shape: {name: {type, content, ...}}
        - params_template may be {values: {name: {type, content}}} or a flat dict.
        """
        attributes = state.get("attributes", {})
        try:
            final_url = (api_endpoint or "").format(**attributes)
        except Exception:
            final_url = api_endpoint or ""

        # Helper to flatten {key: {type, content}} -> {key: formatted_content}
        def _flatten_kv(template):
            out = {}
            if not isinstance(template, dict):
                return out
            for k, v in template.items():
                if isinstance(v, dict):
                    # Prefer 'content' if present
                    content = v.get('content')
                    if content is None:
                        # If no 'content', try formatting the entire dict recursively
                        content = _format_from_state(v, attributes)
                    out[k] = content
                elif isinstance(v, str):
                    try:
                        out[k] = v.format(**attributes)
                    except Exception:
                        out[k] = v
                else:
                    out[k] = v
            return out

        # Build headers from requestHeadersValues
        final_headers = {}
        if isinstance(headers_template, dict):
            final_headers.update(_flatten_kv(headers_template))

        # Build params from requestParams (support both flat and values-schema form)
        if isinstance(params_template, dict):
            values = params_template.get('values') if 'values' in params_template else params_template
            final_params = _flatten_kv(values if isinstance(values, dict) else {})
        else:
            final_params = {}

        print("final_params:", final_params)
        # Convenience: if GET/DELETE and no explicit params provided, promote non-standard headers to query params
        # This supports simple GUI inputs where users add foo1/bar1 in headers area.
        if method in ['GET', 'DELETE'] and not final_params and isinstance(headers_template, dict):
            common_headers = {
                'content-type','authorization','accept','user-agent','cache-control','connection','pragma',
                'referer','origin','host','accept-encoding','accept-language'
            }
            promoted = {}
            for k, v in headers_template.items():
                key_l = k.lower()
                if key_l in common_headers:
                    continue
                if isinstance(v, dict):
                    content = v.get('content')
                    if content is None:
                        continue
                    if isinstance(content, str):
                        try:
                            content = content.format(**attributes)
                        except Exception:
                            pass
                    promoted[k] = content
                elif isinstance(v, str):
                    promoted[k] = v
            if promoted:
                final_params.update(promoted)

        # Always merge primitive attributes into params/body (explicit params override attributes)
        if isinstance(attributes, dict):
            reserved_keys = {"__this_node__"}
            attr_params = {}
            for k, v in attributes.items():
                if k in reserved_keys:
                    continue
                if isinstance(v, (str, int, float, bool)):
                    attr_params[k] = v
            if attr_params:
                # attributes first, then explicit params so explicit wins on key conflicts
                final_params = {**attr_params, **final_params}

        # Merge any query string already present in apiUrl with final_params
        request_args = {'method': method, 'headers': final_headers}
        if method in ['GET', 'DELETE']:
            try:
                parsed = urlparse(final_url)
                existing_qs = dict(parse_qsl(parsed.query))
                # final_params take precedence
                merged_params = {**existing_qs, **final_params}
                # rebuild URL without query; pass params separately
                cleaned_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, '', parsed.fragment))
                request_args['url'] = cleaned_url
                request_args['params'] = merged_params
            except Exception:
                request_args['url'] = final_url
                request_args['params'] = final_params
        else: # POST, PUT, PATCH
            request_args['url'] = final_url
            request_args['json'] = final_params
        
        # Inject API key if configured
        try:
            if api_key:
                # Case 1: simple string -> default to Authorization: Bearer <token>
                if isinstance(api_key, str):
                    token = api_key.format(**attributes)
                    request_args['headers'] = request_args.get('headers', {})
                    # Do not overwrite if already provided
                    request_args['headers'].setdefault('Authorization', f"Bearer {token}")
                # Case 2: dict configuration
                elif isinstance(api_key, dict):
                    # Support nested style: {'header': {...}} or {'query': {...}}
                    if 'header' in api_key or 'query' in api_key:
                        for place in ['header', 'query']:
                            if place in api_key and isinstance(api_key[place], dict):
                                spec = api_key[place]
                                name = spec.get('name', 'Authorization' if place == 'header' else 'api_key')
                                value = spec.get('value')
                                if value is None and spec.get('env_var'):
                                    value = os.getenv(spec.get('env_var'), '')
                                if isinstance(value, str):
                                    value = value.format(**attributes)
                                prefix = spec.get('prefix', '')
                                full_value = f"{prefix}{value}" if prefix else value
                                if place == 'header':
                                    request_args['headers'] = request_args.get('headers', {})
                                    request_args['headers'][name] = full_value
                                else:  # query
                                    if method in ['GET', 'DELETE']:
                                        params = request_args.get('params') or {}
                                        if not isinstance(params, dict):
                                            params = {}
                                        params[name] = full_value
                                        request_args['params'] = params
                                    else:
                                        body = request_args.get('json') or {}
                                        if not isinstance(body, dict):
                                            body = {}
                                        body[name] = full_value
                                        request_args['json'] = body
                    else:
                        # Flat dict: {'in': 'header'|'query', 'name': 'Authorization', 'value': '...', 'env_var': '...', 'prefix': 'Bearer '}
                        place = api_key.get('in', 'header')
                        name = api_key.get('name', 'Authorization' if place == 'header' else 'api_key')
                        value = api_key.get('value')
                        if value is None and api_key.get('env_var'):
                            value = os.getenv(api_key.get('env_var'), '')
                        if isinstance(value, str):
                            value = value.format(**attributes)
                        prefix = api_key.get('prefix', '')
                        full_value = f"{prefix}{value}" if prefix else value
                        if place == 'header':
                            request_args['headers'] = request_args.get('headers', {})
                            request_args['headers'][name] = full_value
                        else:
                            if method in ['GET', 'DELETE']:
                                params = request_args.get('params') or {}
                                if not isinstance(params, dict):
                                    params = {}
                                params[name] = full_value
                                request_args['params'] = params
                            else:
                                body = request_args.get('json') or {}
                                if not isinstance(body, dict):
                                    body = {}
                                body[name] = full_value
                                request_args['json'] = body
        except Exception as e:
            logger.debug(f"build_api_node api_key injection skipped due to error: {e}")

        # Handle file attachments for multipart/form-data
        opened_files = []
        try:
            files_arg = []
            if attachments:
                for att in attachments:
                    if not isinstance(att, dict):
                        continue
                    field = att.get('field', 'file')
                    path_tmpl = att.get('path') or att.get('filepath')
                    if not path_tmpl:
                        continue
                    # Format path with attributes if templated
                    path = path_tmpl.format(**attributes)
                    filename = att.get('filename') or os.path.basename(path)
                    content_type = att.get('content_type', 'application/octet-stream')
                    f = open(path, 'rb')
                    opened_files.append(f)
                    files_arg.append((field, (filename, f, content_type)))

            if files_arg:
                request_args['files'] = files_arg
                # When sending files, use form fields for params instead of JSON body
                if 'json' in request_args:
                    body = request_args.pop('json')
                    request_args['data'] = body
        except Exception as e:
            # If attachments setup fails, close any opened files and continue without files
            logger.debug(f"build_api_node attachments setup error: {e}")
            for fh in opened_files:
                try:
                    fh.close()
                except Exception:
                    pass
            opened_files = []

        return request_args, opened_files

    # Define the synchronous version of the callable
    def sync_api_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        print(f"Executing sync API node for endpoint: {api_endpoint}, current state is:", state)
        request_args, file_handles = _prepare_request_args(state)
        print(f"prepared request args::", request_args)

        try:
            with httpx.Client() as client:
                # follow redirects to avoid 302 on some endpoints
                response = client.request(**request_args, follow_redirects=True)
                print("HTTP API response received:", response)
                response.raise_for_status() # Raise an exception for bad status codes
                # Prefer JSON; fall back to text for non-JSON endpoints
                payload = None
                ct = (response.headers.get('content-type') or '').lower()
                if 'application/json' in ct:
                    payload = response.json()
                else:
                    try:
                        payload = response.json()
                    except Exception:
                        payload = response.text
                state.setdefault('results', []).append({
                    'status': response.status_code,
                    'url': str(response.url),
                    'headers': dict(response.headers),
                    'body': payload,
                })
                print("recevied response payload is:", payload)
        except httpx.HTTPStatusError as e:
            error_msg = f"API call failed with status {e.response.status_code}: {e.response.text}"
            print(error_msg)
            state['error'] = error_msg
        except Exception as e:
            error_msg = f"API call failed: {e}"
            print(error_msg)
            state['error'] = error_msg
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass
        return state

    # Define the asynchronous version of the callable
    async def async_api_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        print(f"Executing async API node for endpoint: {api_endpoint}")
        request_args, file_handles = _prepare_request_args(state)
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
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass
        return state

    # return sync_api_callable if is_sync else async_api_callable

    # Return the correct function based on the 'sync' flag
    full_node_callable = node_builder(sync_api_callable, node_name, skill_name, owner, bp_manager)

    return full_node_callable

# pre-requisite: tool_name is in config_metadata, tool_input is in state and conform the tool input schema (strictly, it will be type checked)
def build_mcp_tool_calling_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """
    Builds a callable function for a node that calls an MCP tool.

    Args:
        config_metadata: A dictionary containing the tool configuration:
                         - tool_name: The name of the MCP tool to call.

    Returns:
        A callable function that takes a state dictionary.
    """
    # Accept multiple shapes from GUI/legacy formats
    logger.debug("building mcp tool node", config_metadata)
    tool_name = None
    try:
        tool_name = (config_metadata.get('tool_name')
                     or config_metadata.get('toolName')
                     or ((config_metadata.get('inputsValues') or {}).get('tool_name') or {}).get('content')
                     or ((config_metadata.get('inputsValues') or {}).get('toolName') or {}).get('content')
                     or (config_metadata.get('inputs') or {}).get('tool_name')
                     or (config_metadata.get('inputs') or {}).get('toolName'))
    except Exception:
        tool_name = None

    if not tool_name:
        print("Error: 'tool_name' is missing in config_metadata for mcp_tool_calling_node.")
        return lambda state: {**state, 'error': 'MCP tool_name not configured'}

    def mcp_tool_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
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
    """Conditions are handled by graph's conditional edges.
    Return a no-op callable to keep the graph executable when visited.
    """
    logger.debug("building condition node", config_metadata)
    def _noop(state: dict, *, runtime=None, store=None, **kwargs):
        return state
    # Wrap to inherit common context/retry behavior
    return node_builder(_noop, node_name, skill_name, owner, bp_manager)


def build_loop_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Loops are translated structurally by the compiler; runtime callable is a no-op."""
    logger.debug("building loop node", config_metadata)
    def _noop(state: dict, *, runtime=None, store=None, **kwargs):
        return state
    return node_builder(_noop, node_name, skill_name, owner, bp_manager)


def build_pend_event_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Interrupt the graph and wait for an external event or human input.

    Config (best-effort):
      - prompt: optional string to present to human/agent
      - tag: optional business tag; defaults to node_name
    """
    logger.debug("building pend event node:", config_metadata)
    prompt = (config_metadata or {}).get("prompt") or "Action required to continue."
    tag = (config_metadata or {}).get("tag") or node_name

    def _pend(state: dict, *, runtime=None, store=None, **kwargs):
        info = {
            "i_tag": tag,
            "paused_at": node_name,
            "prompt_to_human": prompt,
        }
        interrupt(info)
        return state

    return node_builder(_pend, node_name, skill_name, owner, bp_manager)


def build_chat_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Chat node sends messages via TaskRunner GUI methods."""
    logger.debug("building chat node:", config_metadata)
    role = ((config_metadata or {}).get("role") or "assistant").lower()
    msg_tpl = (config_metadata or {}).get("message") or ""
    wait_for_reply = bool((config_metadata or {}).get("wait_for_reply", False))
    def _chat(state: dict, *, runtime=None, store=None, **kwargs):
        attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
        try:
            message = msg_tpl.format(**attrs) if isinstance(msg_tpl, str) else str(msg_tpl)
        except Exception:
            message = str(msg_tpl)

        if not isinstance(state.get("messages"), list):
            state["messages"] = []
        state["messages"].append({"role": role, "content": message})

        # Try to deliver to GUI via TaskRunner helpers
        try:
            mainwin = AppContext.get_main_window()
            # choose the first available agent/runner for now
            agent = next((ag for ag in getattr(mainwin, 'agents', []) or []), None)
            runner = getattr(agent, 'runner', None) if agent else None
            # locate chatId from state metadata/attributes
            chat_id = None
            try:
                chat_id = (state.get('metadata') or {}).get('chatId')
                if not chat_id:
                    chat_id = (state.get('attributes') or {}).get('chatId')
            except Exception:
                chat_id = None
            chat_id = chat_id or 'default_chat'

            if role == 'assistant':
                runner and runner.sendChatMessageToGUI(agent, chat_id, message)
            elif role == 'system':
                runner and runner.sendChatNotificationToGUI(agent, chat_id, {"title": "system", "text": message})
            else:  # user role -> treat as message
                runner and runner.sendChatMessageToGUI(agent, chat_id, message)
        except Exception as e:
            logger.debug(f"chat_node GUI send failed: {e}")

        if wait_for_reply:
            interrupt({"i_tag": node_name, "paused_at": node_name, "prompt_to_human": message})
        return state

    return node_builder(_chat, node_name, skill_name, owner, bp_manager)


def build_rag_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """RAG node with optional LIGHTRAG API."""
    logger.debug("building rag node:", config_metadata)
    query_path = (config_metadata or {}).get("query_path") or "attributes.query"
    def _rag(state: dict, *, runtime=None, store=None, **kwargs):
        # Resolve dotted path from state
        cur = state
        for part in query_path.split("."):
            try:
                cur = cur.get(part)
            except Exception:
                cur = None
                break
        query = cur if isinstance(cur, (str, int, float)) else None
        # Try LIGHTRAG backend if configured, otherwise fallback to empty
        results = []
        try:
            rag_url = os.getenv('LIGHTRAG_API_URL') or os.getenv('LIGHTRAG_URL')
            if rag_url and query:
                url = rag_url.rstrip('/') + '/query'
                payload = {"query": str(query)}
                with httpx.Client(timeout=20.0) as client:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        # best-effort normalize
                        results = data.get('documents') or data.get('results') or data.get('hits') or []
        except Exception as e:
            logger.debug(f"RAG backend error: {e}")
        state.setdefault("tool_result", {})
        state["tool_result"][node_name] = {"query": query, "documents": results}
        return state

    return node_builder(_rag, node_name, skill_name, owner, bp_manager)


def build_browser_automation_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Browser automation scaffold.

    Config keys (best-effort):
      - provider: 'browser-use' | 'browsebase' | 'crawl4ai' (default 'browser-use')
      - task: high-level instruction text for the agent
      - action/params: legacy fields folded into task when present
      - wait_for_done: whether to interrupt when external completion is needed
      - model: optional LLM model for browser-use (env fallback supported)
    """
    logger.debug("building browser automation node:", config_metadata)
    provider = ((config_metadata or {}).get("provider") or "browser-use").lower()
    action = (config_metadata or {}).get("action") or "open_page"
    params = (config_metadata or {}).get("params") or {}
    wait_for_done = bool((config_metadata or {}).get("wait_for_done", False))
    task_text = (config_metadata or {}).get("task") or f"{action} {params}".strip()

    async def _run_browser_use(task: str, model_name: str | None) -> dict:
        try:
            from browser_use import Agent as BUAgent, Controller as BUController
            from browser_use.llm import ChatOpenAI as BUChatOpenAI
            from browser_use.browser.profile import BrowserProfile as BUBrowserProfile

            controller = BUController()
            model_name = model_name or os.getenv('BROWSER_USE_MODEL') or 'gpt-4o-mini'
            model = BUChatOpenAI(model=model_name)
            profile = BUBrowserProfile()
            agent = BUAgent(task=task, llm=model, controller=controller, browser_profile=profile)
            history = await agent.run()
            final = history.final_result() if hasattr(history, 'final_result') else None
            return {"final": final, "history": str(history)}
        except Exception as e:
            return {"error": str(e)}

    def _auto(state: dict, *, runtime=None, store=None, **kwargs):
        if provider == 'browser-use':
            model_name = (config_metadata or {}).get('model')
            info = {}
            try:
                info = run_async_in_sync(_run_browser_use(task_text, model_name)) or {}
            except Exception as e:
                info = {"error": f"browser-use run failed: {e}"}
            state.setdefault("tool_result", {})
            state["tool_result"][node_name] = {"provider": provider, "task": task_text, **info}
            # Optionally interrupt if downstream needs human check
            if wait_for_done and info.get("error"):
                interrupt({"i_tag": node_name, "paused_at": node_name, "prompt_to_human": f"Automation pending: {action}"})
            return state
        # Fallback: record intent for other providers
        intents = state.setdefault("metadata", {}).setdefault("automation_intents", [])
        intents.append({"node": node_name, "provider": provider, "action": action, "params": params, "task": task_text})
        if wait_for_done:
            interrupt({"i_tag": node_name, "paused_at": node_name, "prompt_to_human": f"Please perform automation: {action}"})
        return state

    return node_builder(_auto, node_name, skill_name, owner, bp_manager)
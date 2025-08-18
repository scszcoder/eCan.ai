import re

from selenium.webdriver.support.expected_conditions import element_selection_state_to_be

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_agent_by_id, get_traceback
import json
import base64
from agent.ec_skills.llm_hooks.llm_hooks import *

def rough_token_count(text: str) -> int:
    # Split on whitespace and common punctuations (roughly approximates token count)
    tokens = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return len(tokens)


def parse_json_from_response(response_text):
    # Find JSON content between ```json and ``` or [ and ]
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Fallback: look for array pattern
        json_match = re.search(r'(\[[\s\S]*?\])', response_text)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            return []

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return []


def prep_multi_modal_content(state, runtime):
    try:
        attachments = state.get("attachments", [])
        user_content = []
        print("node running:", runtime)
        user_input = state.get("input", "")
        print("LLM input text:", user_input)
        # Add user text
        user_content.append({"type": "text", "text": user_input})

        # Add all attachments in supported format
        for att in attachments:
            fname = att["filename"].lower()

            mime_type = att.get("mime_type", "").lower()
            print(f"Processing file: {fname} (MIME: {mime_type})")

            # Skip if no file data
            if not att.get("file_data"):
                print(f"Skipping empty file: {fname}")
                continue

            data = att["file_data"]

            # file_text = extract_file_text(data, fname)

            # Handle image files (PNG, JPG, etc.)
            if mime_type.startswith('image/'):
                print(f"Processing image file: {fname}")
                file_data = data if isinstance(data, str) else base64.b64encode(data).decode('utf-8')
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{file_data}"
                        # "detail": "auto"
                    }
                })

            # Handle PDF files
            elif mime_type == 'application/pdf':
                print(f"Processing PDF file: {fname}")
                # For PDFs, we'll just note its existence since we can't process it directly
                user_content.append({
                    "type": "text",
                    "text": f"[PDF file: {fname} - PDF content cannot be processed directly]"
                })

            # Handle audio files
            elif mime_type.startswith('audio/'):
                print(f"Processing audio file: {fname}")
                # For audio files, we'll just note its existence
                user_content.append({
                    "type": "text",
                    "text": f"[Audio file: {fname} - Audio content cannot be processed directly]"
                })

            # Handle other file types
            else:
                logger.warning(f"Unsupported file type: {fname} ({mime_type})")
                # user_content.append({
                #     "type": "text",
                #     "text": f"[File: {fname} - This file type is not supported for direct analysis]"
                # })

        return user_content

    except Exception as e:
        err_trace = get_traceback(e, "ErrorPrepMultiModalContent")
        logger.debug(err_trace)



import requests
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatAnthropic
from langchain_deepseek import ChatDeepSeek
from langchain_qwq import ChatQwQ


def get_country_by_ip() -> str | None:
    """Return country code of current public IP, e.g., 'CN' for China."""
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=5)
        if resp.status_code == 200:
            logger.debug(f"This host IP lookup result: {resp.json()}")
            return resp.json().get("country")
    except Exception as e:
        print(f"IP lookup failed: {e}")
    return None


def pick_llm(settings):
    """Return appropriate LLM instance depending on IP location."""
    country = get_country_by_ip()
    print(f"Detected country: {country}")

    if country == "CN":
        # Prefer DeepSeek, fallback to Qwen
        try:
            if settings.get("cn_llm_provider", False):
                if settings.get("cn_llm_model") == "deepseek":
                    if settings.get("cn_llm_model", False):
                        cn_llm = ChatDeepSeek(model=settings.get("cn_llm_model"), temperature=0)
                    else:
                        cn_llm = ChatDeepSeek(model="deepseek-chat", temperature=0)
                elif settings.get("cn_llm_model") == "qwen":
                    if settings.get("cn_llm_model", False):
                        cn_llm = ChatQwQ(model=settings.get("cn_llm_model"), temperature=0)
                    else:
                        cn_llm = ChatQwQ(model="qwq-plus", temperature=0)
            else:
                cn_llm = ChatDeepSeek(model="deepseek-chat", temperature=0)
            return cn_llm
        except Exception:
            return ChatQwQ(model="qwq-plus", temperature=0)
    elif country == "US":
        try:
            if settings.get("us_llm_provider", False):
                if settings.get("us_llm_model") == "openai":
                    if settings.get("us_llm_model", False):
                        us_llm = ChatOpenAI(model=settings.get("us_llm_model"), temperature=0)
                    else:
                        us_llm = ChatOpenAI(model="gpt-4o", temperature=0)
                elif settings.get("us_llm_model") == "claude":
                    if settings.get("us_llm_model", False):
                        us_llm = ChatAnthropic(model=settings.get("us_llm_model"), temperature=0)
                    else:
                        us_llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
            else:
                us_llm = ChatOpenAI(model="gpt-4o", temperature=0)

            return us_llm
        except Exception:
            us_llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
            return us_llm
    else:
        return ChatOpenAI(model="gpt-4o", temperature=0)



def get_standard_prompt(state:NodeState) -> NodeState:
    boss = "Guest User"
    standard_prompt_template = [
                ("system", """
                    You're a e-commerce business expert helping your human boss {boss_name} to run best performance e-commerce business. 
                    Given the latest human boss message,  try your best to understand it and respond to it.
                """),
                ("human", "{input}")
            ]
    langchain_prompt = ChatPromptTemplate.from_messages(standard_prompt_template)
    formatted_prompt = langchain_prompt.format_messages(boss_name=boss, input=state["input"])
    return formatted_prompt


def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore, skill_name) -> NodeState:
    print("in llm_node_with_raw_files....")
    user_input = state.get("input", "")
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    print("run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")
    # print("current node:", current_node)
    nodes = [{"askid": "skid0", "name": current_node_name}]
    full_node_name = f"{skill_name}:{current_node_name}"
    nodes_prompts = run_pre_llm_hook(current_node_name, agent, state)

    print("networked prompts:", nodes_prompts)
    node_prompt = nodes_prompts[0]

    mm_content = prep_multi_modal_content(state, runtime)
    langchain_prompt = ChatPromptTemplate.from_messages(node_prompt)
    formatted_prompt = langchain_prompt.format_messages(component_info=state["input"], categories=state["attributes"]["categories"])


    llm = ChatOpenAI(model="gpt-4.1-2025-04-14")


    print("chat node: llm prompt ready:", formatted_prompt)
    response = llm.invoke(formatted_prompt)
    print("chat node: LLM response:", response)
    # Parse the response
    run_post_llm_hook(current_node_name, agent, state, response)




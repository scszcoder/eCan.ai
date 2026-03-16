"""
Self Tools - MCP tools for agent self-introspection and management.

Tools:
- describe_self: Returns structured description of agent (agents, skills, tasks, tools, knowledge_base, prompts)
- create_agent: Create a new agent with given configuration
- delete_agent: Delete an existing agent by ID
- find_skill: Search for skills in own skillset and skill market
- open_channel: Open a communication channel (telegram, slack, discord, etc.)
- close_channel: Close an active communication channel

Task management tools have been moved to agent/ec_tasks/task_mcp_tools.py.
Naming convention follows server.py and tool_schemas.py patterns.
"""

import json
import time
import traceback
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from agent.agent_service import get_agent_by_id
from app_context import AppContext
from utils.logger_helper import logger_helper as logger, get_traceback

# Valid sections for describe_self
_VALID_SECTIONS = {"agents", "skills", "tasks", "tools", "knowledge_base", "prompts", "llm", "network", "diagnostics"}


def _mask_key(key: str) -> str:
    """Mask an API key showing only first 6 and last 6 chars.
    Returns '(not set)' for empty/None keys."""
    if not key or not key.strip():
        return "(not set)"
    key = key.strip()
    if len(key) <= 12:
        return key[:2] + "***" + key[-2:]
    return key[:6] + "***" + key[-6:]


# ==================== Tool Implementations ====================

# ---------- describe_self ----------

def describe_self(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a structured description of the agent system.

    Supports selective sections and output format.

    Args:
        mainwin: Main window instance
        config: {
            "agent_id": optional agent ID (default: first agent),
            "sections": "all" | list of section names
                        (agents, skills, tasks, tools, knowledge_base, prompts),
            "format": "json" | "txt" | "md"  (default: "json")
        }

    Returns:
        dict (json format) or {"text": str} for txt/md formats.
    """
    try:
        agent_id = config.get("agent_id", "")
        sections_param = config.get("sections", "all")
        out_format = config.get("format", "json").lower()

        # Resolve which sections to include
        if sections_param == "all" or not sections_param:
            sections = _VALID_SECTIONS
        elif isinstance(sections_param, str):
            sections = {s.strip() for s in sections_param.split(",")} & _VALID_SECTIONS
        elif isinstance(sections_param, list):
            sections = set(sections_param) & _VALID_SECTIONS
        else:
            sections = _VALID_SECTIONS

        if not sections:
            sections = _VALID_SECTIONS

        # Get agent by ID or use first available agent
        agent = None
        if agent_id:
            agent = get_agent_by_id(agent_id)
        else:
            if hasattr(mainwin, 'agents') and mainwin.agents:
                agent = mainwin.agents[0]
                agent_id = getattr(getattr(agent, 'card', None), 'id', 'unknown')

        if not agent:
            return {
                "error": f"Agent not found: {agent_id}",
                "timestamp": int(time.time() * 1000)
            }

        result: Dict[str, Any] = {
            "agent_id": agent_id,
            "timestamp": int(time.time() * 1000)
        }

        # -- agents section --
        if "agents" in sections:
            result["agent_info"] = _collect_agents_info(mainwin, agent, agent_id)

        # -- skills section --
        if "skills" in sections:
            result["skills"] = _collect_skills_info(agent)

        # -- tasks section --
        if "tasks" in sections:
            result["tasks"] = _collect_tasks_info(agent)

        # -- tools section --
        if "tools" in sections:
            result["tools"] = _collect_tools_info()

        # -- knowledge_base section --
        if "knowledge_base" in sections:
            result["knowledge_base"] = _collect_knowledge_base_info(mainwin)

        # -- prompts section --
        if "prompts" in sections:
            result["prompts"] = _collect_prompts_info(mainwin)

        # -- llm section --
        if "llm" in sections:
            result["llm"] = _collect_llm_info(mainwin)

        # -- network section --
        if "network" in sections:
            result["network"] = _collect_network_info(mainwin)

        # -- diagnostics section --
        if "diagnostics" in sections:
            result["diagnostics"] = diagnose_llm(mainwin, {})

        logger.info(f"[describe_self] Agent {agent_id}: sections={list(sections)}, format={out_format}")

        # Format output
        if out_format == "json":
            return result
        elif out_format == "md":
            return {"text": _format_as_markdown(result, sections)}
        elif out_format == "txt":
            return {"text": _format_as_text(result, sections)}
        else:
            return result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorDescribeSelf")
        logger.error(err_trace)
        return {
            "error": err_trace,
            "timestamp": int(time.time() * 1000)
        }


def _collect_agents_info(mainwin, current_agent, current_agent_id: str) -> Dict[str, Any]:
    """Collect information about all agents in the system."""
    agents_list = []
    all_agents = getattr(mainwin, 'agents', []) or []
    for ag in all_agents:
        card = getattr(ag, 'card', None)
        agents_list.append({
            "id": getattr(card, 'id', 'unknown'),
            "name": getattr(card, 'name', 'Unknown'),
            "description": getattr(card, 'description', ''),
            "status": getattr(ag, 'status', 'unknown'),
            "rank": getattr(ag, 'rank', ''),
            "title": getattr(ag, 'title', ''),
            "cloud_based": getattr(ag, 'cloud_based', False),
            "is_current": (getattr(card, 'id', '') == current_agent_id),
        })
    return {
        "total": len(agents_list),
        "agents": agents_list
    }


def _collect_skills_info(agent) -> List[Dict[str, Any]]:
    """Collect skills information for an agent."""
    skills_list = []
    skills = getattr(agent, 'skills', []) or []
    for skill in skills:
        skill_info = {
            "id": getattr(skill, 'id', '') or getattr(skill, 'name', 'unknown'),
            "name": getattr(skill, 'name', 'Unknown'),
            "description": getattr(skill, 'description', ''),
            "type": getattr(skill, 'type', 'unknown'),
            "enabled": getattr(skill, 'enabled', True)
        }
        if hasattr(skill, 'tags') and skill.tags:
            skill_info["tags"] = skill.tags
        skills_list.append(skill_info)
    return skills_list


def _collect_tasks_info(agent) -> Dict[str, List]:
    """Collect tasks information categorized by state."""
    categorized = {"running": [], "pending": [], "completed": [], "failed": []}
    tasks = getattr(agent, 'tasks', []) or []
    for task in tasks:
        task_info = {
            "id": getattr(task, 'id', 'unknown'),
            "name": getattr(task, 'name', 'Unknown'),
            "skill_name": getattr(getattr(task, 'skill', None), 'name', 'unknown'),
            "state": "unknown",
            "created_at": None,
            "run_id": getattr(task, 'run_id', None)
        }
        task_status = getattr(task, 'status', None)
        if task_status:
            state = getattr(task_status, 'state', None)
            if state:
                task_info["state"] = state.value if hasattr(state, 'value') else str(state)
        schedule = getattr(task, 'schedule', None)
        if schedule:
            task_info["schedule"] = {
                "next_run": getattr(schedule, 'next_run', None),
                "repeat_type": getattr(schedule, 'repeat_type', None)
            }
        state_str = task_info["state"].lower() if task_info["state"] else "unknown"
        if state_str in ("working", "running", "in_progress"):
            categorized["running"].append(task_info)
        elif state_str in ("completed", "done", "success"):
            categorized["completed"].append(task_info)
        elif state_str in ("failed", "error", "canceled"):
            categorized["failed"].append(task_info)
        else:
            categorized["pending"].append(task_info)
    return categorized


def _collect_tools_info() -> List[Dict[str, str]]:
    """Collect registered MCP tools summary."""
    tools_list = []
    try:
        from agent.mcp.server.tool_schemas import get_tool_schemas
        for tool in get_tool_schemas():
            tools_list.append({
                "name": getattr(tool, 'name', 'unknown'),
                "description": getattr(tool, 'description', '')[:200],
            })
    except Exception as e:
        logger.debug(f"[describe_self] Could not collect tools: {e}")
    return tools_list


def _collect_knowledge_base_info(mainwin) -> Dict[str, Any]:
    """Collect knowledge base / RAG index information."""
    kb_info: Dict[str, Any] = {"indices": []}
    try:
        # Try to get RAG indices from the mainwin or config
        rag_manager = getattr(mainwin, 'rag_manager', None)
        if rag_manager:
            indices = getattr(rag_manager, 'list_indices', lambda: [])() or []
            for idx in indices:
                kb_info["indices"].append({
                    "name": getattr(idx, 'name', str(idx)),
                    "doc_count": getattr(idx, 'doc_count', None),
                    "status": getattr(idx, 'status', 'unknown'),
                })
        # Fallback: check if there's a data directory with RAG files
        if not kb_info["indices"]:
            import os
            data_home = getattr(mainwin, 'ecb_data_homepath', None) or os.getcwd()
            rag_dir = os.path.join(data_home, 'rag_data')
            if os.path.isdir(rag_dir):
                dirs = [d for d in os.listdir(rag_dir) if os.path.isdir(os.path.join(rag_dir, d))]
                for d in dirs:
                    kb_info["indices"].append({"name": d, "status": "on_disk"})
    except Exception as e:
        logger.debug(f"[describe_self] Could not collect knowledge base info: {e}")
    kb_info["total"] = len(kb_info["indices"])
    return kb_info


def _collect_prompts_info(mainwin) -> Dict[str, Any]:
    """Collect prompts information."""
    prompts_info: Dict[str, Any] = {"prompts": []}
    try:
        # Try prompt_store
        from agent.skill_editor.prompt_store import PromptStore
        store = PromptStore.get_instance() if hasattr(PromptStore, 'get_instance') else None
        if store:
            all_prompts = getattr(store, 'list_prompts', lambda: [])() or []
            for p in all_prompts:
                prompts_info["prompts"].append({
                    "id": getattr(p, 'id', '') or str(p.get('id', '')) if isinstance(p, dict) else getattr(p, 'id', ''),
                    "name": getattr(p, 'name', '') or (p.get('name', '') if isinstance(p, dict) else ''),
                    "category": getattr(p, 'category', '') or (p.get('category', '') if isinstance(p, dict) else ''),
                })
    except Exception as e:
        logger.debug(f"[describe_self] Could not collect prompts info: {e}")
    prompts_info["total"] = len(prompts_info["prompts"])
    return prompts_info


def _collect_llm_info(mainwin) -> Dict[str, Any]:
    """Collect LLM provider/model settings: default LLM, embedding, reranking, and available providers."""
    llm_info: Dict[str, Any] = {}
    try:
        config_manager = getattr(mainwin, 'config_manager', None)
        if not config_manager:
            return {"error": "config_manager not available"}

        gs = getattr(config_manager, 'general_settings', None)
        if not gs:
            return {"error": "general_settings not available"}

        # --- Default LLM ---
        llm_info["default_llm"] = {
            "provider": gs.default_llm or "(not set)",
            "model": gs.default_llm_model or "(not set)",
        }

        # --- Default Embedding ---
        llm_info["default_embedding"] = {
            "provider": gs.default_embedding or "(not set)",
            "model": gs.default_embedding_model or "(not set)",
        }

        # --- Default Reranking ---
        llm_info["default_rerank"] = {
            "provider": gs.default_rerank or "(not set)",
            "model": gs.default_rerank_model or "(not set)",
        }

        # --- Available LLM providers ---
        llm_manager = getattr(config_manager, 'llm_manager', None)
        if llm_manager:
            try:
                all_providers = llm_manager.get_all_providers()
                providers_summary = []
                for p in all_providers:
                    prov = {
                        "name": p.get("display_name") or p.get("name", ""),
                        "provider_id": p.get("provider", ""),
                        "is_local": p.get("is_local", False),
                        "api_key_configured": p.get("api_key_configured", False),
                        "is_preferred": p.get("is_preferred", False),
                        "preferred_model": p.get("preferred_model", ""),
                        "default_model": p.get("default_model", ""),
                    }
                    # Show masked API key status per env var
                    env_vars = p.get("api_key_env_vars", [])
                    if env_vars and not p.get("is_local"):
                        masked_keys = {}
                        for ev in env_vars:
                            raw_key = llm_manager.retrieve_api_key(ev)
                            masked_keys[ev] = _mask_key(raw_key)
                        prov["api_keys"] = masked_keys
                    # Base URL for local providers
                    if p.get("is_local") and p.get("base_url"):
                        prov["base_url"] = p["base_url"]
                    # Supported models (names only)
                    models = p.get("supported_models", [])
                    prov["supported_models"] = [
                        m.get("name", str(m)) if isinstance(m, dict) else str(m)
                        for m in models
                    ]
                    providers_summary.append(prov)
                llm_info["available_providers"] = providers_summary
            except Exception as e:
                logger.debug(f"[describe_self] Could not list LLM providers: {e}")
                llm_info["available_providers_error"] = str(e)

        # --- Available Embedding providers ---
        embedding_manager = getattr(config_manager, 'embedding_manager', None)
        if embedding_manager and hasattr(embedding_manager, 'get_all_providers'):
            try:
                emb_providers = embedding_manager.get_all_providers()
                emb_summary = []
                for p in emb_providers:
                    emb_summary.append({
                        "name": p.get("display_name") or p.get("name", ""),
                        "provider_id": p.get("provider", ""),
                        "is_local": p.get("is_local", False),
                        "api_key_configured": p.get("api_key_configured", False),
                        "is_preferred": p.get("is_preferred", False),
                        "default_model": p.get("default_model", ""),
                    })
                llm_info["available_embedding_providers"] = emb_summary
            except Exception as e:
                logger.debug(f"[describe_self] Could not list embedding providers: {e}")

        # --- Available Rerank providers ---
        rerank_manager = getattr(config_manager, 'rerank_manager', None)
        if rerank_manager and hasattr(rerank_manager, 'get_all_providers'):
            try:
                rrk_providers = rerank_manager.get_all_providers()
                rrk_summary = []
                for p in rrk_providers:
                    rrk_summary.append({
                        "name": p.get("display_name") or p.get("name", ""),
                        "provider_id": p.get("provider", ""),
                        "is_local": p.get("is_local", False),
                        "api_key_configured": p.get("api_key_configured", False),
                        "is_preferred": p.get("is_preferred", False),
                        "default_model": p.get("default_model", ""),
                    })
                llm_info["available_rerank_providers"] = rrk_summary
            except Exception as e:
                logger.debug(f"[describe_self] Could not list rerank providers: {e}")

    except Exception as e:
        logger.debug(f"[describe_self] Could not collect LLM info: {e}")
        llm_info["error"] = str(e)
    return llm_info


def _collect_network_info(mainwin) -> Dict[str, Any]:
    """Collect network endpoint and connectivity settings."""
    net_info: Dict[str, Any] = {}
    try:
        config_manager = getattr(mainwin, 'config_manager', None)
        gs = getattr(config_manager, 'general_settings', None) if config_manager else None
        if not gs:
            return {"error": "general_settings not available"}

        net_info["network_api_engine"] = gs.network_api_engine
        net_info["schedule_engine"] = gs.schedule_engine
        net_info["endpoints"] = {
            "lan_api_endpoint": gs.lan_api_endpoint or "(not set)",
            "wan_api_endpoint": gs.wan_api_endpoint or "(not set)",
            "ws_api_endpoint": gs.ws_api_endpoint or "(not set)",
            "ws_api_host": gs.ws_api_host or "(not set)",
            "ecan_cloud_searcher_url": gs.ecan_cloud_searcher_url or "(not set)",
            "ocr_api_endpoint": gs.ocr_api_endpoint or "(not set)",
        }
        net_info["database"] = {
            "local_user_db_host": gs.local_user_db_host,
            "local_user_db_port": gs.local_user_db_port,
            "local_agent_db_host": gs.local_agent_db_host,
            "local_agent_db_port": gs.local_agent_db_port,
        }
        net_info["ports"] = {
            "local_server_port": gs.local_server_port,
            "local_agent_ports": gs.local_agent_ports,
        }
        # Mask sensitive keys
        net_info["api_keys"] = {
            "wan_api_key": _mask_key(gs.wan_api_key),
            "ocr_api_key": _mask_key(gs.ocr_api_key),
        }
    except Exception as e:
        logger.debug(f"[describe_self] Could not collect network info: {e}")
        net_info["error"] = str(e)
    return net_info


def diagnose_llm(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run a quick diagnostic test against the current default LLM.

    Sends a ~1 000-token translation prompt and expects ~1 000 tokens back.
    Measures wall-clock response time, token counts, and throughput.

    Args:
        mainwin: Main window instance
        config: {} (no required params — always tests the default LLM)

    Returns:
        dict with provider, model, status, response_time_ms, input_tokens,
        output_tokens, tokens_per_second, and a snippet of the reply.
    """
    diag: Dict[str, Any] = {"status": "error"}
    try:
        config_manager = getattr(mainwin, 'config_manager', None)
        if not config_manager:
            diag["message"] = "config_manager not available"
            return diag

        llm_manager = getattr(config_manager, 'llm_manager', None)
        if not llm_manager:
            diag["message"] = "llm_manager not available"
            return diag

        # Get default LLM config
        llm_cfg = llm_manager.get_default_llm_config()
        if not llm_cfg:
            diag["message"] = "No default LLM configured"
            return diag

        provider_id = llm_cfg.get('provider_id', 'unknown')
        model_name = llm_cfg.get('model_name', 'unknown')
        provider_dict = llm_cfg.get('provider_dict', {})
        diag["provider"] = provider_id
        diag["model"] = model_name

        # Create an LLM instance
        from agent.ec_skills.llm_utils.llm_utils import _create_llm_instance
        llm_instance = _create_llm_instance(provider_dict, config_manager=config_manager)
        if not llm_instance:
            diag["message"] = "Failed to create LLM instance"
            return diag

        # Build a ~1k-token prompt (translation task to also produce ~1k tokens back)
        prompt_text = (
            "You are a professional translator. Translate the following English passage "
            "into formal Simplified Chinese. Produce a complete, accurate translation "
            "that preserves the original meaning, tone, and structure.\n\n"
            "--- BEGIN PASSAGE ---\n"
            "Artificial intelligence has undergone remarkable transformation over the past decade. "
            "From early rule-based expert systems to modern deep learning architectures, the field "
            "has expanded at an unprecedented pace. Large language models, trained on vast corpora "
            "of text data, now demonstrate capabilities that were once considered exclusive to human "
            "cognition — including nuanced reasoning, creative writing, code generation, and "
            "multilingual translation.\n\n"
            "The emergence of transformer architectures in 2017 marked a pivotal turning point. "
            "By leveraging self-attention mechanisms, transformers enabled models to capture "
            "long-range dependencies in sequential data far more effectively than their recurrent "
            "predecessors. This architectural innovation paved the way for scaling language models "
            "to hundreds of billions of parameters, unlocking emergent abilities that smaller "
            "models simply could not exhibit.\n\n"
            "Today, AI systems are being deployed across virtually every industry — healthcare, "
            "finance, education, manufacturing, legal services, and creative arts. In healthcare, "
            "AI assists with diagnostic imaging, drug discovery, and personalized treatment plans. "
            "In finance, algorithmic trading systems and fraud detection tools rely heavily on "
            "machine learning pipelines. Educational platforms use adaptive learning algorithms "
            "to tailor content to individual student needs.\n\n"
            "However, the rapid proliferation of AI technology also raises significant ethical "
            "and societal concerns. Issues of bias in training data, lack of interpretability "
            "in deep neural networks, potential job displacement, and the concentration of AI "
            "capabilities among a handful of large technology companies have sparked intense "
            "debate among policymakers, researchers, and the general public. The development "
            "of robust AI governance frameworks, transparent model documentation practices, "
            "and inclusive stakeholder engagement processes will be essential to ensuring that "
            "the benefits of artificial intelligence are broadly shared while its risks are "
            "carefully managed and mitigated.\n\n"
            "Looking ahead, the next frontier of AI research includes multimodal models that "
            "seamlessly integrate text, images, audio, and video understanding; agentic systems "
            "capable of autonomous planning and tool use; and breakthroughs in reasoning and "
            "mathematical problem-solving. As these capabilities mature, the boundary between "
            "human and machine intelligence will continue to blur, presenting both extraordinary "
            "opportunities and profound challenges for civilization.\n"
            "--- END PASSAGE ---\n\n"
            "Please translate the entire passage above into Simplified Chinese now."
        )

        # Invoke with timing
        import time as _time
        t0 = _time.perf_counter()
        response = llm_instance.invoke(prompt_text)
        t1 = _time.perf_counter()

        elapsed_ms = round((t1 - t0) * 1000, 1)

        # Extract response text
        reply_text = ""
        if hasattr(response, 'content'):
            reply_text = response.content
        elif isinstance(response, str):
            reply_text = response
        else:
            reply_text = str(response)

        # Rough token estimates (1 token ≈ 4 chars EN, ≈ 1.5 chars ZH)
        input_tokens_est = len(prompt_text) // 4
        output_tokens_est = len(reply_text) // 2  # Chinese characters
        tokens_per_sec = round(output_tokens_est / max((t1 - t0), 0.001), 1)

        # Try to get real usage if available
        usage = getattr(response, 'usage_metadata', None) or getattr(response, 'response_metadata', {}).get('token_usage')
        if usage:
            if isinstance(usage, dict):
                input_tokens_est = usage.get('input_tokens', usage.get('prompt_tokens', input_tokens_est))
                output_tokens_est = usage.get('output_tokens', usage.get('completion_tokens', output_tokens_est))
            elif hasattr(usage, 'input_tokens'):
                input_tokens_est = usage.input_tokens
                output_tokens_est = usage.output_tokens
            tokens_per_sec = round(output_tokens_est / max((t1 - t0), 0.001), 1)

        diag["status"] = "ok"
        diag["response_time_ms"] = elapsed_ms
        diag["input_tokens"] = input_tokens_est
        diag["output_tokens"] = output_tokens_est
        diag["tokens_per_second"] = tokens_per_sec
        diag["reply_snippet"] = reply_text[:500] + ("..." if len(reply_text) > 500 else "")
        diag["reply_length_chars"] = len(reply_text)

        logger.info(f"[diagnose_llm] {provider_id}/{model_name}: {elapsed_ms}ms, "
                    f"~{input_tokens_est}in/{output_tokens_est}out tokens, {tokens_per_sec} tok/s")

    except Exception as e:
        diag["status"] = "error"
        diag["message"] = str(e)
        logger.error(f"[diagnose_llm] Error: {e}")
    return diag


# ---------- Output formatters ----------

def _format_as_markdown(data: Dict[str, Any], sections: set) -> str:
    """Format describe_self result as Markdown."""
    lines = [f"# Agent Self-Description"]
    lines.append(f"**Agent ID:** {data.get('agent_id', 'N/A')}")
    lines.append(f"**Timestamp:** {data.get('timestamp', '')}")
    lines.append("")

    if "agents" in sections and "agent_info" in data:
        info = data["agent_info"]
        lines.append(f"## Agents ({info.get('total', 0)})")
        for ag in info.get("agents", []):
            current = " *(current)*" if ag.get("is_current") else ""
            lines.append(f"- **{ag['name']}** (`{ag['id']}`){current} — status: {ag['status']}")
            if ag.get("description"):
                lines.append(f"  {ag['description']}")
        lines.append("")

    if "skills" in sections and "skills" in data:
        skills = data["skills"]
        lines.append(f"## Skills ({len(skills)})")
        for s in skills:
            tags = f" [{', '.join(s['tags'])}]" if s.get('tags') else ""
            lines.append(f"- **{s['name']}** (`{s['id']}`) — {s['type']}{tags}")
            if s.get("description"):
                lines.append(f"  {s['description'][:120]}")
        lines.append("")

    if "tasks" in sections and "tasks" in data:
        tasks = data["tasks"]
        total = sum(len(v) for v in tasks.values())
        lines.append(f"## Tasks ({total})")
        for category in ("running", "pending", "completed", "failed"):
            items = tasks.get(category, [])
            if items:
                lines.append(f"### {category.capitalize()} ({len(items)})")
                for t in items:
                    lines.append(f"- **{t['name']}** — skill: {t['skill_name']}, state: {t['state']}")
        lines.append("")

    if "tools" in sections and "tools" in data:
        tools = data["tools"]
        lines.append(f"## Tools ({len(tools)})")
        for t in tools:
            lines.append(f"- **{t['name']}**")
        lines.append("")

    if "knowledge_base" in sections and "knowledge_base" in data:
        kb = data["knowledge_base"]
        lines.append(f"## Knowledge Base ({kb.get('total', 0)} indices)")
        for idx in kb.get("indices", []):
            lines.append(f"- **{idx['name']}** — status: {idx.get('status', 'N/A')}")
        lines.append("")

    if "prompts" in sections and "prompts" in data:
        pr = data["prompts"]
        lines.append(f"## Prompts ({pr.get('total', 0)})")
        for p in pr.get("prompts", []):
            lines.append(f"- **{p.get('name', 'unnamed')}** (`{p.get('id', '')}`) — {p.get('category', '')}")
        lines.append("")

    if "llm" in sections and "llm" in data:
        llm = data["llm"]
        lines.append("## LLM Configuration")
        dl = llm.get("default_llm", {})
        lines.append(f"- **Default LLM:** {dl.get('provider', 'N/A')} / {dl.get('model', 'N/A')}")
        de = llm.get("default_embedding", {})
        lines.append(f"- **Default Embedding:** {de.get('provider', 'N/A')} / {de.get('model', 'N/A')}")
        dr = llm.get("default_rerank", {})
        lines.append(f"- **Default Rerank:** {dr.get('provider', 'N/A')} / {dr.get('model', 'N/A')}")
        providers = llm.get("available_providers", [])
        if providers:
            lines.append(f"\n### Available LLM Providers ({len(providers)})")
            for p in providers:
                star = " ⭐" if p.get("is_preferred") else ""
                key_status = "✅" if p.get("api_key_configured") else "❌"
                lines.append(f"- **{p['name']}** (`{p['provider_id']}`) — keys: {key_status}{star}")
                if p.get("api_keys"):
                    for ev, mv in p["api_keys"].items():
                        lines.append(f"  - `{ev}`: {mv}")
        emb_providers = llm.get("available_embedding_providers", [])
        if emb_providers:
            lines.append(f"\n### Available Embedding Providers ({len(emb_providers)})")
            for p in emb_providers:
                lines.append(f"- **{p['name']}** (`{p['provider_id']}`)")
        rrk_providers = llm.get("available_rerank_providers", [])
        if rrk_providers:
            lines.append(f"\n### Available Rerank Providers ({len(rrk_providers)})")
            for p in rrk_providers:
                lines.append(f"- **{p['name']}** (`{p['provider_id']}`)")
        lines.append("")

    if "network" in sections and "network" in data:
        net = data["network"]
        lines.append("## Network Configuration")
        lines.append(f"- **Network API Engine:** {net.get('network_api_engine', 'N/A')}")
        lines.append(f"- **Schedule Engine:** {net.get('schedule_engine', 'N/A')}")
        eps = net.get("endpoints", {})
        if eps:
            lines.append("\n### Endpoints")
            for k, v in eps.items():
                lines.append(f"- **{k}:** {v}")
        db = net.get("database", {})
        if db:
            lines.append("\n### Database")
            for k, v in db.items():
                lines.append(f"- **{k}:** {v}")
        ports = net.get("ports", {})
        if ports:
            lines.append("\n### Ports")
            for k, v in ports.items():
                lines.append(f"- **{k}:** {v}")
        api_keys = net.get("api_keys", {})
        if api_keys:
            lines.append("\n### API Keys")
            for k, v in api_keys.items():
                lines.append(f"- **{k}:** {v}")
        lines.append("")

    if "diagnostics" in sections and "diagnostics" in data:
        diag = data["diagnostics"]
        lines.append("## LLM Diagnostics")
        lines.append(f"- **Status:** {diag.get('status', 'N/A')}")
        if diag.get("provider"):
            lines.append(f"- **Provider:** {diag.get('provider')} / {diag.get('model', '')}")
        if diag.get("response_time_ms") is not None:
            lines.append(f"- **Response Time:** {diag['response_time_ms']}ms")
            lines.append(f"- **Input Tokens:** ~{diag.get('input_tokens', '?')}")
            lines.append(f"- **Output Tokens:** ~{diag.get('output_tokens', '?')}")
            lines.append(f"- **Throughput:** {diag.get('tokens_per_second', '?')} tok/s")
        if diag.get("message"):
            lines.append(f"- **Error:** {diag['message']}")
        lines.append("")

    return "\n".join(lines)


def _format_as_text(data: Dict[str, Any], sections: set) -> str:
    """Format describe_self result as plain text."""
    lines = [f"Agent Self-Description"]
    lines.append(f"Agent ID: {data.get('agent_id', 'N/A')}")
    lines.append(f"Timestamp: {data.get('timestamp', '')}")
    lines.append("")

    if "agents" in sections and "agent_info" in data:
        info = data["agent_info"]
        lines.append(f"=== Agents ({info.get('total', 0)}) ===")
        for ag in info.get("agents", []):
            current = " (current)" if ag.get("is_current") else ""
            lines.append(f"  {ag['name']} [{ag['id']}]{current} - status: {ag['status']}")
        lines.append("")

    if "skills" in sections and "skills" in data:
        skills = data["skills"]
        lines.append(f"=== Skills ({len(skills)}) ===")
        for s in skills:
            lines.append(f"  {s['name']} [{s['id']}] - {s['type']}")
        lines.append("")

    if "tasks" in sections and "tasks" in data:
        tasks = data["tasks"]
        total = sum(len(v) for v in tasks.values())
        lines.append(f"=== Tasks ({total}) ===")
        for category in ("running", "pending", "completed", "failed"):
            items = tasks.get(category, [])
            if items:
                lines.append(f"  [{category.upper()}]")
                for t in items:
                    lines.append(f"    {t['name']} - skill: {t['skill_name']}, state: {t['state']}")
        lines.append("")

    if "tools" in sections and "tools" in data:
        tools = data["tools"]
        lines.append(f"=== Tools ({len(tools)}) ===")
        for t in tools:
            lines.append(f"  {t['name']}")
        lines.append("")

    if "knowledge_base" in sections and "knowledge_base" in data:
        kb = data["knowledge_base"]
        lines.append(f"=== Knowledge Base ({kb.get('total', 0)} indices) ===")
        for idx in kb.get("indices", []):
            lines.append(f"  {idx['name']} - {idx.get('status', 'N/A')}")
        lines.append("")

    if "prompts" in sections and "prompts" in data:
        pr = data["prompts"]
        lines.append(f"=== Prompts ({pr.get('total', 0)}) ===")
        for p in pr.get("prompts", []):
            lines.append(f"  {p.get('name', 'unnamed')} [{p.get('id', '')}] - {p.get('category', '')}")
        lines.append("")

    if "llm" in sections and "llm" in data:
        llm = data["llm"]
        lines.append("=== LLM Configuration ===")
        dl = llm.get("default_llm", {})
        lines.append(f"  Default LLM: {dl.get('provider', 'N/A')} / {dl.get('model', 'N/A')}")
        de = llm.get("default_embedding", {})
        lines.append(f"  Default Embedding: {de.get('provider', 'N/A')} / {de.get('model', 'N/A')}")
        dr = llm.get("default_rerank", {})
        lines.append(f"  Default Rerank: {dr.get('provider', 'N/A')} / {dr.get('model', 'N/A')}")
        providers = llm.get("available_providers", [])
        if providers:
            lines.append(f"  --- Available LLM Providers ({len(providers)}) ---")
            for p in providers:
                star = " *" if p.get("is_preferred") else ""
                key_status = "yes" if p.get("api_key_configured") else "no"
                lines.append(f"    {p['name']} ({p['provider_id']}) - keys: {key_status}{star}")
                if p.get("api_keys"):
                    for ev, mv in p["api_keys"].items():
                        lines.append(f"      {ev}: {mv}")
        lines.append("")

    if "network" in sections and "network" in data:
        net = data["network"]
        lines.append("=== Network Configuration ===")
        lines.append(f"  Network API Engine: {net.get('network_api_engine', 'N/A')}")
        lines.append(f"  Schedule Engine: {net.get('schedule_engine', 'N/A')}")
        eps = net.get("endpoints", {})
        if eps:
            lines.append("  --- Endpoints ---")
            for k, v in eps.items():
                lines.append(f"    {k}: {v}")
        db = net.get("database", {})
        if db:
            lines.append("  --- Database ---")
            for k, v in db.items():
                lines.append(f"    {k}: {v}")
        ports = net.get("ports", {})
        if ports:
            lines.append("  --- Ports ---")
            for k, v in ports.items():
                lines.append(f"    {k}: {v}")
        api_keys = net.get("api_keys", {})
        if api_keys:
            lines.append("  --- API Keys ---")
            for k, v in api_keys.items():
                lines.append(f"    {k}: {v}")
        lines.append("")

    if "diagnostics" in sections and "diagnostics" in data:
        diag = data["diagnostics"]
        lines.append("=== LLM Diagnostics ===")
        lines.append(f"  Status: {diag.get('status', 'N/A')}")
        if diag.get("provider"):
            lines.append(f"  Provider: {diag.get('provider')} / {diag.get('model', '')}")
        if diag.get("response_time_ms") is not None:
            lines.append(f"  Response Time: {diag['response_time_ms']}ms")
            lines.append(f"  Input Tokens: ~{diag.get('input_tokens', '?')}")
            lines.append(f"  Output Tokens: ~{diag.get('output_tokens', '?')}")
            lines.append(f"  Throughput: {diag.get('tokens_per_second', '?')} tok/s")
        if diag.get("message"):
            lines.append(f"  Error: {diag['message']}")
        lines.append("")

    return "\n".join(lines)


# ---------- create_agent ----------

def create_agent(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new agent.

    Args:
        mainwin: Main window instance
        config: {
            "name": str (required),
            "description": str,
            "skills": list of skill IDs to assign,
            "role": str (default "Platoon"),
            "title": str,
            "personality": list[str],
        }
    """
    try:
        name = config.get("name")
        if not name:
            return {"error": "Agent name is required", "timestamp": int(time.time() * 1000)}

        description = config.get("description", "")
        role = config.get("role", "Platoon")
        title = config.get("title", "")
        skill_ids = config.get("skills", [])
        personality = config.get("personality", [])

        # Delegate to mainwin agent creation if available
        if hasattr(mainwin, 'create_agent'):
            result = mainwin.create_agent(
                name=name, description=description, role=role,
                title=title, skill_ids=skill_ids, personality=personality
            )
            logger.info(f"[create_agent] Created agent '{name}' via mainwin")
            return result if isinstance(result, dict) else {"success": True, "agent": result}

        # Fallback: create via DB service
        try:
            from agent.db.services.db_agent_service import DBAgentService
            import uuid
            agent_id = str(uuid.uuid4())
            db_result = DBAgentService.create_agent({
                "id": agent_id,
                "name": name,
                "description": description,
                "role": role,
                "title": title,
                "skills": skill_ids,
                "personality": personality,
            })
            logger.info(f"[create_agent] Created agent '{name}' (id={agent_id}) via DB")
            return {"success": True, "agent_id": agent_id, "name": name, "db_result": db_result}
        except ImportError:
            return {"error": "Agent creation not supported — no create_agent handler or DBAgentService available",
                    "timestamp": int(time.time() * 1000)}

    except Exception as e:
        err_trace = get_traceback(e, "ErrorCreateAgent")
        logger.error(err_trace)
        return {"error": err_trace, "timestamp": int(time.time() * 1000)}


# ---------- delete_agent ----------

def delete_agent(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete an existing agent by ID.

    Args:
        mainwin: Main window instance
        config: {"agent_id": str (required)}
    """
    try:
        agent_id = config.get("agent_id")
        if not agent_id:
            return {"error": "agent_id is required", "timestamp": int(time.time() * 1000)}

        # Check agent exists
        agent = get_agent_by_id(agent_id)
        if not agent:
            return {"error": f"Agent not found: {agent_id}", "timestamp": int(time.time() * 1000)}

        agent_name = getattr(getattr(agent, 'card', None), 'name', 'Unknown')

        # Delegate to mainwin if available
        if hasattr(mainwin, 'delete_agent'):
            result = mainwin.delete_agent(agent_id)
            logger.info(f"[delete_agent] Deleted agent '{agent_name}' ({agent_id}) via mainwin")
            return result if isinstance(result, dict) else {"success": True, "agent_id": agent_id}

        # Fallback: DB deletion
        try:
            from agent.db.services.db_agent_service import DBAgentService
            DBAgentService.delete_agent(agent_id)
            # Remove from in-memory list
            if hasattr(mainwin, 'agents'):
                mainwin.agents = [a for a in mainwin.agents
                                  if getattr(getattr(a, 'card', None), 'id', None) != agent_id]
            logger.info(f"[delete_agent] Deleted agent '{agent_name}' ({agent_id}) via DB")
            return {"success": True, "agent_id": agent_id, "name": agent_name}
        except ImportError:
            return {"error": "Agent deletion not supported — no handler available",
                    "timestamp": int(time.time() * 1000)}

    except Exception as e:
        err_trace = get_traceback(e, "ErrorDeleteAgent")
        logger.error(err_trace)
        return {"error": err_trace, "timestamp": int(time.time() * 1000)}


# ---------- find_skill ----------

def find_skill(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for skills in own skillset and skill market.

    Args:
        mainwin: Main window instance
        config: {
            "query": str — search term (name, tag, keyword),
            "source": "local" | "market" | "all" (default "all"),
            "agent_id": optional — scope local search to specific agent,
        }
    """
    try:
        query = (config.get("query") or "").lower().strip()
        source = config.get("source", "all").lower()
        agent_id = config.get("agent_id", "")
        results: Dict[str, Any] = {"local": [], "market": []}

        # --- Local skills ---
        if source in ("local", "all"):
            # Agent-specific skills
            if agent_id:
                agent = get_agent_by_id(agent_id)
                if agent:
                    for s in (getattr(agent, 'skills', []) or []):
                        if _skill_matches(s, query):
                            results["local"].append(_skill_to_dict(s, source_label="agent"))

            # Global compiled skills
            all_skills = getattr(mainwin, 'agent_skills', []) or []
            seen_ids = {s["id"] for s in results["local"]}
            for s in all_skills:
                sid = getattr(s, 'id', '') or getattr(s, 'name', '')
                if sid not in seen_ids and _skill_matches(s, query):
                    results["local"].append(_skill_to_dict(s, source_label="global"))

        # --- Skill market (cloud) ---
        if source in ("market", "all"):
            try:
                from agent.cloud_api.cloud_api import CloudAPI
                cloud_api = CloudAPI.get_instance() if hasattr(CloudAPI, 'get_instance') else None
                if cloud_api and hasattr(cloud_api, 'search_skill_market'):
                    market_results = cloud_api.search_skill_market(query) or []
                    for item in market_results:
                        results["market"].append({
                            "id": item.get("id", ""),
                            "name": item.get("name", ""),
                            "description": item.get("description", ""),
                            "author": item.get("author", ""),
                            "rating": item.get("rating"),
                            "source": "market",
                        })
            except Exception as e:
                logger.debug(f"[find_skill] Skill market search failed: {e}")
                results["market_error"] = str(e)

        results["total_local"] = len(results["local"])
        results["total_market"] = len(results["market"])
        logger.info(f"[find_skill] query='{query}' source={source} => "
                    f"{results['total_local']} local, {results['total_market']} market")
        return results

    except Exception as e:
        err_trace = get_traceback(e, "ErrorFindSkill")
        logger.error(err_trace)
        return {"error": err_trace, "timestamp": int(time.time() * 1000)}


def _skill_matches(skill, query: str) -> bool:
    """Check if a skill matches the search query."""
    if not query:
        return True
    name = (getattr(skill, 'name', '') or '').lower()
    desc = (getattr(skill, 'description', '') or '').lower()
    tags = [t.lower() for t in (getattr(skill, 'tags', []) or [])]
    return query in name or query in desc or any(query in t for t in tags)


def _skill_to_dict(skill, source_label: str = "") -> Dict[str, Any]:
    """Convert a skill object to a dict."""
    info = {
        "id": getattr(skill, 'id', '') or getattr(skill, 'name', 'unknown'),
        "name": getattr(skill, 'name', 'Unknown'),
        "description": getattr(skill, 'description', ''),
        "type": getattr(skill, 'type', 'unknown'),
        "enabled": getattr(skill, 'enabled', True),
        "source": source_label,
    }
    if hasattr(skill, 'tags') and skill.tags:
        info["tags"] = skill.tags
    return info


# ---------- open_channel ----------

def open_channel(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Open (start) a communication channel.

    Args:
        mainwin: Main window instance
        config: {
            "channel_id": str (required) — e.g. "telegram", "slack", "discord",
                          "whatsapp", "webchat", "dingtalk", "messenger", "twitter",
            "channel_config": dict (optional) — override channel configuration,
        }
    """
    try:
        channel_id = config.get("channel_id", "").strip()
        if not channel_id:
            return {"error": "channel_id is required", "timestamp": int(time.time() * 1000)}

        channel_config = config.get("channel_config", {})

        # Get channel manager from agent
        channel_mgr = _get_channel_manager(mainwin)
        if not channel_mgr:
            return {"error": "Channel manager not available", "timestamp": int(time.time() * 1000)}

        # Check current status
        current_status = channel_mgr.get_status(channel_id)
        if current_status and current_status.value == "running":
            return {
                "success": True,
                "channel_id": channel_id,
                "status": "already_running",
                "message": f"Channel '{channel_id}' is already running."
            }

        # If channel_config provided, re-register with new config
        if channel_config:
            channel_config.setdefault("enabled", True)
            channel_mgr._register_channel(channel_id, channel_config)

        # Start the channel
        channel_mgr.start_channel(channel_id)

        # Verify
        new_status = channel_mgr.get_status(channel_id)
        status_str = new_status.value if new_status else "unknown"

        logger.info(f"[open_channel] Channel '{channel_id}' started, status={status_str}")
        return {
            "success": True,
            "channel_id": channel_id,
            "status": status_str,
        }

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOpenChannel")
        logger.error(err_trace)
        return {"error": err_trace, "timestamp": int(time.time() * 1000)}


# ---------- close_channel ----------

def close_channel(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Close (stop) an active communication channel.

    Args:
        mainwin: Main window instance
        config: {"channel_id": str (required)}
    """
    try:
        channel_id = config.get("channel_id", "").strip()
        if not channel_id:
            return {"error": "channel_id is required", "timestamp": int(time.time() * 1000)}

        channel_mgr = _get_channel_manager(mainwin)
        if not channel_mgr:
            return {"error": "Channel manager not available", "timestamp": int(time.time() * 1000)}

        current_status = channel_mgr.get_status(channel_id)
        if not current_status:
            return {
                "error": f"Channel '{channel_id}' not found.",
                "available_channels": list(channel_mgr.get_all_status().keys()),
                "timestamp": int(time.time() * 1000)
            }

        if current_status.value in ("stopped", "idle"):
            return {
                "success": True,
                "channel_id": channel_id,
                "status": current_status.value,
                "message": f"Channel '{channel_id}' is already stopped."
            }

        channel_mgr.stop_channel(channel_id)

        new_status = channel_mgr.get_status(channel_id)
        status_str = new_status.value if new_status else "stopped"

        logger.info(f"[close_channel] Channel '{channel_id}' stopped, status={status_str}")
        return {
            "success": True,
            "channel_id": channel_id,
            "status": status_str,
        }

    except Exception as e:
        err_trace = get_traceback(e, "ErrorCloseChannel")
        logger.error(err_trace)
        return {"error": err_trace, "timestamp": int(time.time() * 1000)}


def _get_channel_manager(mainwin):
    """Try to locate the ChannelManager from mainwin or agents."""
    # Direct attribute on mainwin
    mgr = getattr(mainwin, 'channel_manager', None)
    if mgr:
        return mgr
    # From first agent
    agents = getattr(mainwin, 'agents', []) or []
    for ag in agents:
        mgr = getattr(ag, 'channel_manager', None)
        if mgr:
            return mgr
    return None


# ==================== Tool Schema Functions ====================

def add_describe_self_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add describe_self tool schema to the tool schemas list."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="describe_self",
        description=(
            "<category>Agent</category><sub-category>Self</sub-category>"
            "Get a structured description of the agent system including any combination of: "
            "agents, skills, tasks, tools, knowledge_base, prompts. "
            "Supports 'all' to show everything. Output in json, txt, or md format. "
            "Useful for agent self-introspection and capability discovery."
        ),
        inputSchema={
            "type": "object",
            "required": [],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID to describe. If not provided, uses the first available agent."
                        },
                        "sections": {
                            "description": (
                                "Which sections to include. Use 'all' for everything, "
                                "or a comma-separated string or array from: "
                                "agents, skills, tasks, tools, knowledge_base, prompts, llm, network, diagnostics. "
                                "The 'llm' section shows default LLM/embedding/reranking providers and available providers with masked API keys. "
                                "The 'network' section shows endpoint URLs, DB hosts, ports. "
                                "The 'diagnostics' section runs a live LLM connection test (~1k tokens in/out) and reports latency and throughput."
                            ),
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}}
                            ],
                            "default": "all"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["json", "txt", "md"],
                            "default": "json",
                            "description": "Output format: 'json' (structured), 'txt' (plain text), 'md' (markdown)."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_create_agent_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add create_agent tool schema."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="create_agent",
        description=(
            "<category>Agent</category><sub-category>Management</sub-category>"
            "Create a new agent with the given name, description, role, skills, and personality."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the new agent."
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of the agent's purpose."
                        },
                        "role": {
                            "type": "string",
                            "enum": ["Commander", "Platoon"],
                            "default": "Platoon",
                            "description": "Agent role in the hierarchy."
                        },
                        "title": {
                            "type": "string",
                            "description": "Job title for the agent."
                        },
                        "skills": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of skill IDs to assign to the agent."
                        },
                        "personality": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Personality traits (e.g. ['friendly', 'professional'])."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_delete_agent_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add delete_agent tool schema."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="delete_agent",
        description=(
            "<category>Agent</category><sub-category>Management</sub-category>"
            "Delete an existing agent by its agent ID. The agent will be stopped and removed."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["agent_id"],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "The ID of the agent to delete."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_find_skill_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add find_skill tool schema."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="find_skill",
        description=(
            "<category>Agent</category><sub-category>Skills</sub-category>"
            "Search for skills by name, tag, or keyword. "
            "Searches the agent's own skillset and optionally the skill market (cloud). "
            "Useful for discovering available capabilities before assigning them to agents or tasks."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search term (name, tag, keyword). Empty string returns all skills."
                        },
                        "source": {
                            "type": "string",
                            "enum": ["local", "market", "all"],
                            "default": "all",
                            "description": "Where to search: 'local' (own skillset), 'market' (skill market), 'all' (both)."
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Scope local search to a specific agent's skills."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_open_channel_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add open_channel tool schema."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="open_channel",
        description=(
            "<category>Agent</category><sub-category>Channels</sub-category>"
            "Open (start) a communication channel so the agent can send and receive messages through it. "
            "Supported channels: telegram, slack, discord, whatsapp, webchat, dingtalk, messenger, twitter."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["channel_id"],
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "enum": ["telegram", "slack", "discord", "whatsapp",
                                     "webchat", "dingtalk", "messenger", "twitter"],
                            "description": "The communication channel to open."
                        },
                        "channel_config": {
                            "type": "object",
                            "description": (
                                "Optional channel-specific configuration overrides "
                                "(e.g. bot_token, webhook_url). If omitted, uses saved config from channels.json."
                            )
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_diagnose_llm_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add diagnose_llm tool schema."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="diagnose_llm",
        description=(
            "<category>Agent</category><sub-category>Diagnostics</sub-category>"
            "Run a self-diagnostic test against the current default LLM. "
            "Sends a ~1k-token translation prompt and measures response time, "
            "token throughput (tok/s), and returns a snippet of the reply. "
            "Use this to verify LLM connectivity and performance."
        ),
        inputSchema={
            "type": "object",
            "required": [],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {}
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_close_channel_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add close_channel tool schema."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="close_channel",
        description=(
            "<category>Agent</category><sub-category>Channels</sub-category>"
            "Close (stop) an active communication channel. "
            "The channel will stop receiving messages and release resources."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["channel_id"],
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "enum": ["telegram", "slack", "discord", "whatsapp",
                                     "webchat", "dingtalk", "messenger", "twitter"],
                            "description": "The communication channel to close."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


# ==================== Async Wrappers for Server ====================

async def async_describe_self(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for describe_self tool."""
    try:
        input_config = args.get('input', {})
        result = describe_self(mainwin, input_config)

        # If format is txt/md, result has a "text" key
        if "text" in result:
            return [TextContent(type="text", text=result["text"])]

        msg = "Agent description retrieved successfully"
        if "error" in result:
            msg = f"Error: {result['error']}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"agent_description": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncDescribeSelf")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_create_agent(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for create_agent tool."""
    try:
        input_config = args.get('input', {})
        result = create_agent(mainwin, input_config)
        msg = json.dumps(result, ensure_ascii=False, default=str)
        return [TextContent(type="text", text=msg)]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncCreateAgent")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_delete_agent(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for delete_agent tool."""
    try:
        input_config = args.get('input', {})
        result = delete_agent(mainwin, input_config)
        msg = json.dumps(result, ensure_ascii=False, default=str)
        return [TextContent(type="text", text=msg)]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncDeleteAgent")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_find_skill(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for find_skill tool."""
    try:
        input_config = args.get('input', {})
        result = find_skill(mainwin, input_config)
        msg = json.dumps(result, ensure_ascii=False, default=str)
        return [TextContent(type="text", text=msg)]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncFindSkill")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_open_channel(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for open_channel tool."""
    try:
        input_config = args.get('input', {})
        result = open_channel(mainwin, input_config)
        msg = json.dumps(result, ensure_ascii=False, default=str)
        return [TextContent(type="text", text=msg)]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncOpenChannel")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_diagnose_llm(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for diagnose_llm tool."""
    try:
        input_config = args.get('input', {})
        result = diagnose_llm(mainwin, input_config)
        msg = json.dumps(result, ensure_ascii=False, default=str)
        return [TextContent(type="text", text=msg)]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncDiagnoseLLM")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_close_channel(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for close_channel tool."""
    try:
        input_config = args.get('input', {})
        result = close_channel(mainwin, input_config)
        msg = json.dumps(result, ensure_ascii=False, default=str)
        return [TextContent(type="text", text=msg)]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncCloseChannel")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

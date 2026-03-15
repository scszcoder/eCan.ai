"""
Internationalization (i18n) module for the Skill Editor Agent.

Provides:
- Language detection from user messages
- Bilingual message catalog (English + Chinese)
- `t(key, lang, **kwargs)` translation function
- `detect_language(text)` helper

Usage:
    from .i18n import t, detect_language

    lang = detect_language(user_message)
    response = t("casual_chat_default", lang)
    response = t("save_success", lang, name=skill_name)
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

# CJK Unicode blocks — covers Chinese, Japanese, Korean
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff"       # CJK Unified Ideographs
    r"\u3400-\u4dbf"        # CJK Extension A
    r"\u2e80-\u2eff"        # CJK Radicals
    r"\u3000-\u303f"        # CJK Symbols/Punctuation
    r"\uff00-\uffef"        # Halfwidth/Fullwidth Forms
    r"\u3040-\u309f"        # Hiragana (Japanese)
    r"\u30a0-\u30ff]"       # Katakana (Japanese)
)


def detect_language(text: str) -> str:
    """Detect language from user input. Returns 'zh' or 'en'.

    Simple heuristic: if ≥20% of non-whitespace characters are CJK, treat as
    Chinese. This covers mixed messages like '创建一个LED Neon Sign工作流'.
    """
    if not text:
        return "en"
    stripped = text.replace(" ", "")
    if not stripped:
        return "en"
    cjk_count = len(_CJK_RE.findall(stripped))
    ratio = cjk_count / len(stripped)
    return "zh" if ratio >= 0.20 else "en"


# ---------------------------------------------------------------------------
# Message catalog
# ---------------------------------------------------------------------------

_MESSAGES = {
    # ===================== Casual Chat =====================
    "casual_chat_default": {
        "en": "Got it. When you're ready, tell me what workflow you want to build (or what you want to change on the canvas).",
        "zh": "收到。准备好后，告诉我你想创建什么工作流，或者想对画布上的内容做什么修改。",
    },
    "casual_chat_redirect": {
        "en": "Happy to chat, but let's keep moving in the Skill Editor. What do you want to do next: create a new workflow, load an existing skill, or modify the current canvas?",
        "zh": "很高兴聊天，但让我们继续在技能编辑器中工作。接下来你想做什么：创建新工作流、加载已有技能，还是修改当前画布？",
    },

    # ===================== Intent / Routing =====================
    "vague_edit_request": {
        "en": "What specific change do you want me to make to the currently loaded workflow? For example: 'wrap node X in a loop', 'connect A -> B', or 'change the LLM prompt in node Y'.",
        "zh": "你想对当前工作流做什么具体修改？例如：'把节点X放进循环'、'连接A到B'、'修改节点Y的LLM提示词'。",
    },
    "edit_confirmation": {
        "en": "I'm ready to apply this edit to the currently loaded workflow:\n\n{plan_text}\n\nProceed?",
        "zh": "我准备对当前工作流执行以下修改：\n\n{plan_text}\n\n确认执行？",
    },

    # ===================== Load / Save =====================
    "load_skill_no_name": {
        "en": "I couldn't determine which skill to load. Please specify the skill name, e.g., 'load ebay000 skill'.",
        "zh": "无法确定要加载哪个技能。请指定技能名称，例如：'加载 ebay000 技能'。",
    },
    "save_no_workflow": {
        "en": "No workflow to save. Please create or load a skill first.",
        "zh": "没有可保存的工作流。请先创建或加载一个技能。",
    },
    "save_failed": {
        "en": "Failed to save the skill. Please try again.",
        "zh": "保存技能失败，请重试。",
    },

    # ===================== Node Config =====================
    "node_config_select_first": {
        "en": "Please select a node on the canvas first, then tell me how you'd like to configure it.",
        "zh": "请先在画布上选择一个节点，然后告诉我你想如何配置它。",
    },
    "node_config_lost_track": {
        "en": "I lost track of which node we were configuring. Please select the node again.",
        "zh": "我丢失了正在配置的节点信息，请重新选择该节点。",
    },

    # ===================== Log Analysis =====================
    "log_empty_paste": {
        "en": "The pasted content appears to be empty — nothing to analyze.",
        "zh": "粘贴的内容似乎为空——没有可分析的内容。",
    },
    "log_no_analysis_for_fix": {
        "en": "No log analysis available to apply fixes from. Please analyze a log first.",
        "zh": "没有可用的日志分析结果来应用修复。请先分析一份日志。",
    },

    # ===================== Test / Deploy =====================
    "no_skill_loaded": {
        "en": "No skill is currently loaded. Please load or create a skill first.",
        "zh": "当前没有加载任何技能。请先加载或创建一个技能。",
    },
    "no_skill_for_deploy": {
        "en": "No skill is currently loaded. Please load or create a skill first before deploying.",
        "zh": "当前没有加载任何技能。请先加载或创建一个技能再进行部署。",
    },

    # ===================== Workflow Description / Planning =====================
    "plan_rejected_start_over": {
        "en": "Understood. Please describe what you'd like to build and we'll start over.",
        "zh": "明白了。请描述你想构建什么，我们重新开始。",
    },
    "validated_connections": {
        "en": "Validated and fixed the current flowgram's connections.",
        "zh": "已验证并修复了当前工作流的连接。",
    },

    # ===================== Progress Messages =====================
    "progress_thinking": {
        "en": "Thinking...",
        "zh": "思考中...",
    },
    "progress_classifying": {
        "en": "Classifying intent...",
        "zh": "识别意图...",
    },
    "progress_reading_log": {
        "en": "Reading log file...",
        "zh": "正在读取日志文件...",
    },
    "progress_pre_filtering": {
        "en": "Pre-filtering {size} bytes of log data...",
        "zh": "正在预过滤 {size} 字节的日志数据...",
    },
    "progress_analyzing": {
        "en": "Analyzing with {provider} / {model}...",
        "zh": "正在使用 {provider} / {model} 分析...",
    },
    "progress_applying_fixes": {
        "en": "Applying fixes based on log analysis...",
        "zh": "正在根据日志分析结果应用修复...",
    },
    "progress_answering": {
        "en": "Answering...",
        "zh": "正在回答...",
    },
    "progress_answering_followup": {
        "en": "Answering follow-up about {filename}...",
        "zh": "正在回答关于 {filename} 的后续问题...",
    },
    "progress_preparing_modify": {
        "en": "Preparing to modify the current workflow...",
        "zh": "正在准备修改当前工作流...",
    },
    "progress_waiting_confirmation": {
        "en": "Waiting for confirmation...",
        "zh": "等待确认...",
    },
    "progress_gathering_requirements": {
        "en": "Gathering domain requirements ({domain})…",
        "zh": "正在收集领域需求（{domain}）...",
    },
    "progress_asking_domain_questions": {
        "en": "Asking domain-specific questions ({domain})…",
        "zh": "正在提问领域相关问题（{domain}）...",
    },
    "progress_drafting_description": {
        "en": "Drafting workflow description…",
        "zh": "正在起草工作流描述...",
    },
    "progress_approved_planning": {
        "en": "Workflow design approved — planning implementation…",
        "zh": "工作流设计已通过——正在规划实施方案...",
    },
    "progress_updating_description": {
        "en": "Updating workflow description with your feedback…",
        "zh": "正在根据你的反馈更新工作流描述...",
    },
    "progress_plan_approved_codegen": {
        "en": "Plan approved — starting code generation…",
        "zh": "方案已通过——正在开始生成代码...",
    },
    "progress_saving": {
        "en": "Saving workflow…",
        "zh": "正在保存工作流...",
    },
    "progress_working": {
        "en": "Working on your request ({intent})…",
        "zh": "正在处理你的请求（{intent}）...",
    },


    # ===================== Log Analysis Messages =====================
    "log_no_file_path": {
        "en": (
            "I couldn't find a file path in your answers. "
            "Please provide the full path to the log file you want me to analyze.\n\n"
            "Example: *please analyze my run log in C:\\Users\\me\\logs\\run.log*"
        ),
        "zh": (
            "我无法从你的回答中找到文件路径。"
            "请提供你想分析的日志文件的完整路径。\n\n"
            "示例：*请分析我的运行日志 C:\\Users\\me\\logs\\run.log*"
        ),
    },
    "log_uploading": {
        "en": "Uploading your log file to cloud storage for analysis...\n\nFile: `{file_path}`",
        "zh": "正在将你的日志文件上传到云存储进行分析...\n\n文件：`{file_path}`",
    },
    "log_cloud_paste_request": {
        "en": (
            "I'm running in **cloud mode** and cannot directly access "
            "files on your local machine.\n\n"
            "The path you provided: `{file_path}`\n\n"
            "\U0001f4cb **Please paste the log content directly in the chat** "
            "(or the relevant sections — first ~50 lines, the error section, "
            "and ~50 lines after the error), and I'll analyze it for you."
        ),
        "zh": (
            "我运行在**云端模式**，无法直接访问你本地机器上的文件。\n\n"
            "你提供的路径：`{file_path}`\n\n"
            "\U0001f4cb **请直接在聊天中粘贴日志内容**"
            "（或相关部分——错误前约50行、错误段落、错误后约50行），我来帮你分析。"
        ),
    },
    "log_file_not_found": {
        "en": "File not found: **{file_path}**\n\nPlease double-check the path and try again.",
        "zh": "文件未找到：**{file_path}**\n\n请检查路径后重试。",
    },
    "log_dir_no_logs": {
        "en": (
            "**{file_path}** is a directory but contains no log files "
            "(.log, .txt, .out, .err).\n\n"
            "Please provide the full path to a specific file."
        ),
        "zh": (
            "**{file_path}** 是一个目录，但其中没有日志文件"
            "（.log、.txt、.out、.err）。\n\n"
            "请提供具体文件的完整路径。"
        ),
    },
    "log_dir_using_recent": {
        "en": "Directory provided — using most recent file: {filename}",
        "zh": "已提供目录——使用最近的文件：{filename}",
    },
    "log_read_error": {
        "en": "Error accessing path **{file_path}**: {error}",
        "zh": "访问路径 **{file_path}** 时出错：{error}",
    },
    "log_read_failed": {
        "en": "Failed to read **{file_path}**: {error}",
        "zh": "读取 **{file_path}** 失败：{error}",
    },
    "log_file_empty": {
        "en": "The file **{file_path}** is empty — nothing to analyze.",
        "zh": "文件 **{file_path}** 为空——没有可分析的内容。",
    },
    "log_no_workflow_for_fix": {
        "en": (
            "I can't apply fixes because there is no workflow loaded on the canvas. "
            "Please load the affected skill first, then say **\"fix it\"** again."
        ),
        "zh": (
            "无法应用修复，因为画布上没有加载工作流。"
            "请先加载相关技能，然后再说**\"修复\"**。"
        ),
    },
    "log_fix_error": {
        "en": (
            "I encountered an error while trying to apply fixes: {error}\n\n"
            "You can try again, or apply the recommended fixes manually from the analysis above."
        ),
        "zh": (
            "尝试应用修复时遇到错误：{error}\n\n"
            "你可以重试，或根据上面的分析手动应用修复建议。"
        ),
    },
    "log_cloud_read_failed": {
        "en": "Failed to read the uploaded log file from cloud storage: {error}",
        "zh": "从云存储读取上传的日志文件失败：{error}",
    },

    # ===================== Casual Chat (awaiting state) =====================
    "casual_chat_awaiting_answers": {
        "en": "Got it. When you're ready, please answer the questions above (or cancel), so I can continue.",
        "zh": "收到。准备好后，请回答上面的问题（或取消），这样我可以继续。",
    },
    "casual_chat_awaiting_approval": {
        "en": "Got it. If you want me to proceed with the plan, reply 'yes' (or click Approve). If you want to stop, reply 'cancel'.",
        "zh": "收到。如果你想让我执行这个方案，请回复'是'（或点击批准）。如果想取消，请回复'取消'。",
    },

    # ===================== Plan Approval =====================
    "plan_rejected_edit": {
        "en": "Understood. Please describe what you'd like to change.",
        "zh": "明白了。请描述你想做什么修改。",
    },
    "plan_rejected_create": {
        "en": "Understood. Please describe what you'd like to change about the plan.",
        "zh": "明白了。请描述你想对方案做什么修改。",
    },

    # ===================== Load / Save (detailed) =====================
    "load_skill_not_found": {
        "en": "Skill '{skill_name}' not found. Available skills: {skills_list}",
        "zh": "未找到技能 '{skill_name}'。可用技能：{skills_list}",
    },
    "load_skill_corrupted": {
        "en": "Failed to load skill '{skill_name}'. The skill file may be corrupted.",
        "zh": "加载技能 '{skill_name}' 失败。技能文件可能已损坏。",
    },
    "load_skill_success": {
        "en": "Loaded skill **{skill_name}** with {node_count} nodes and {edge_count} edges. You can now edit this workflow.",
        "zh": "已加载技能 **{skill_name}**，包含 {node_count} 个节点和 {edge_count} 条连接。你现在可以编辑这个工作流了。",
    },
    "save_skill_success": {
        "en": "Saved skill **{skill_name}** with {node_count} nodes and {edge_count} edges to `{skill_path}`.",
        "zh": "已保存技能 **{skill_name}**（{node_count} 个节点，{edge_count} 条连接）到 `{skill_path}`。",
    },

    # ===================== Planning / Description =====================
    "plan_present": {
        "en": "{plan_message}\n\n{plan_text}\n\nWould you like me to proceed with this plan?",
        "zh": "{plan_message}\n\n{plan_text}\n\n你想让我执行这个方案吗？",
    },
    "plan_present_default_header": {
        "en": "Here is my implementation plan:",
        "zh": "以下是我的实施方案：",
    },
    "plan_from_answers": {
        "en": "Based on your answers, here's my plan:\n\n{plan_text}\n\nShall I proceed?",
        "zh": "根据你的回答，以下是我的方案：\n\n{plan_text}\n\n要我执行吗？",
    },
    "requirement_collection_intro": {
        "en": "Before I design the workflow, I need a few details about your requirements:\n",
        "zh": "在设计工作流之前，我需要了解一些需求细节：\n",
    },
    "domain_qa_intro": {
        "en": "Great — now a few **{domain}**-specific questions to refine the design:\n",
        "zh": "好的——现在有几个 **{domain}** 相关的问题来完善设计：\n",
    },
    "workflow_description_review": {
        "en": (
            "Here is the workflow I'm planning to build:\n\n"
            "{description}\n\n"
            "---\n"
            "Would you like me to **proceed** with this design, or do you have any **changes**?"
        ),
        "zh": (
            "以下是我计划构建的工作流：\n\n"
            "{description}\n\n"
            "---\n"
            "你想让我**继续**这个设计，还是有什么**修改意见**？"
        ),
    },

    # ===================== Code Generation =====================
    "codegen_failed": {
        "en": (
            "I wasn't able to generate the workflow from the plan. "
            "This can happen when the model returns an incomplete response. "
            "Please try again — you can start a new session or re-describe your workflow."
        ),
        "zh": (
            "我无法从方案生成工作流。"
            "这可能是因为模型返回了不完整的响应。"
            "请重试——你可以开始新会话或重新描述你的工作流。"
        ),
    },
    "edit_refused_node_loss": {
        "en": (
            "I refused to apply this update because it would remove existing nodes from your canvas. "
            "This usually happens when the LLM returns a partial flowgram. "
            "Please retry, or use the validate/repair request which runs deterministically."
        ),
        "zh": (
            "我拒绝应用此更新，因为它会删除画布上的现有节点。"
            "这通常是因为LLM返回了不完整的工作流。"
            "请重试，或使用确定性运行的验证/修复请求。"
        ),
    },
    "error_editing": {
        "en": "I encountered an error editing the workflow: {error}",
        "zh": "编辑工作流时遇到错误：{error}",
    },
    "error_configuring_node": {
        "en": "I encountered an error configuring the node: {error}",
        "zh": "配置节点时遇到错误：{error}",
    },
    # ===================== Error Messages =====================
    "error_processing": {
        "en": "I encountered an error processing your request: {error}",
        "zh": "处理你的请求时遇到错误：{error}",
    },

    # ===================== System Prompt Language Instruction =====================
    "system_language_instruction_zh": {
        "en": "",  # not used for English
        "zh": (
            "\n\n**LANGUAGE REQUIREMENT**: The user is communicating in Chinese (中文). "
            "You MUST respond entirely in Chinese. All explanations, clarification questions, "
            "plan summaries, status messages, and conversational responses must be in Chinese. "
            "Technical terms (node types like 'browser_automation', 'mcp', 'pend_event_node'; "
            "JSON keys; tool names) should remain in English but explanatory text around them "
            "must be in Chinese. When generating node prompts/instructions inside the flowgram, "
            "write them in Chinese so the runtime sub-agents also operate in Chinese.\n"
        ),
    },
}


# ---------------------------------------------------------------------------
# Translation function
# ---------------------------------------------------------------------------

def t(key: str, lang: str = "en", **kwargs) -> str:
    """Look up a translated message.

    Args:
        key: Message key from the catalog.
        lang: 'zh' or 'en'.
        **kwargs: Format arguments (e.g. name=..., error=...).

    Returns:
        Translated string. Falls back to English if key or lang missing.
    """
    entry = _MESSAGES.get(key)
    if not entry:
        return key  # return key as-is if not found (safe fallback)
    text = entry.get(lang) or entry.get("en", key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass  # return unformatted if args don't match
    return text


def get_language_instruction(lang: str) -> str:
    """Return a language instruction block to append to system prompts.

    For Chinese users, this instructs the LLM to respond in Chinese.
    For English users, returns empty string (no extra instruction needed).
    """
    if lang == "zh":
        return t("system_language_instruction_zh", "zh")
    return ""

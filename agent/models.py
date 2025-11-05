from __future__ import annotations


from typing import Any, Dict, List, Literal, Optional, Type


ToolCallingMethod = Literal['function_calling', 'json_mode', 'raw', 'auto']
REQUIRED_LLM_API_ENV_VARS = {
	'ChatOpenAI': ['OPENAI_API_KEY'],
	'AzureOpenAI': ['AZURE_ENDPOINT', 'AZURE_OPENAI_API_KEY'],
	'ChatBedrockConverse': ['ANTHROPIC_API_KEY'],
	'ChatAnthropic': ['ANTHROPIC_API_KEY'],
	'ChatGoogleGenerativeAI': ['GEMINI_API_KEY'],
	'ChatDeepSeek': ['DEEPSEEK_API_KEY'],
	'ChatQwQ': ['DASHSCOPE_API_KEY'],
	'ChatDoubao': ['ARK_API_KEY'],
	'ChatOllama': [],
}



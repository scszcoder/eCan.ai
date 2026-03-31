"""
Lambda Proxy LLM for browser-use — implements browser-use's BaseChatModel protocol.

Routes LLM calls through an AWS Lambda Function URL. The Lambda holds the real
API keys and does per-user token accounting. Supports streaming responses to
avoid Lambda's 30s synchronous timeout.

Usage:
    llm = ChatLambdaProxy(
        provider="openai",
        model="gpt-4o",
        user_id="user@example.com",
        lambda_endpoint="https://xxx.lambda-url.us-east-1.on.aws",
        auth_token="cognito-id-token",
    )
    agent = Agent(task="...", llm=llm)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from browser_use.llm.base import BaseChatModel
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import BaseMessage
from browser_use.llm.views import ChatInvokeCompletion, ChatInvokeUsage
from browser_use.llm.openai.serializer import OpenAIMessageSerializer

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

# Default Lambda Function URL endpoint path
_CHAT_PATH = '/v1/chat/completions'


@dataclass
class ChatLambdaProxy(BaseChatModel):
    """Browser-use compatible LLM that proxies calls through an AWS Lambda.

    Implements the browser_use.llm.base.BaseChatModel protocol:
      - model: str
      - provider: str (property)
      - name: str (property)
      - ainvoke(messages, output_format, **kwargs)
    """

    # --- Required by BaseChatModel protocol ---
    model: str = ''
    _verified_api_keys: bool = True

    # --- Proxy-specific fields ---
    provider_name: str = ''  # "openai", "anthropic", etc.
    user_id: str = ''
    lambda_endpoint: str = ''  # Lambda Function URL base (no trailing slash)
    auth_token: str = ''  # Cognito ID token
    timeout: float = 300.0  # generous timeout for streaming responses
    max_retries: int = 2

    # Optional: callback to refresh an expired auth token
    _token_refresh_fn: Any = field(default=None, repr=False)

    @property
    def provider(self) -> str:
        return self.provider_name or 'lambda-proxy'

    @property
    def name(self) -> str:
        return f"lambda-proxy/{self.provider_name}/{self.model}"

    @property
    def model_name(self) -> str:
        """Legacy support property."""
        return self.model

    def _get_auth_token(self) -> str:
        """Get the current auth token, refreshing if a callback is set."""
        if self._token_refresh_fn:
            try:
                fresh = self._token_refresh_fn()
                if fresh:
                    self.auth_token = fresh
            except Exception as e:
                logger.warning(f"[ChatLambdaProxy] Token refresh failed: {e}")
        return self.auth_token

    def _build_headers(self) -> dict:
        token = self._get_auth_token()
        headers = {
            'Content-Type': 'application/json',
            'X-User-Id': self.user_id,
        }
        if token:
            headers['Authorization'] = f'Bearer {token}'
        return headers

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        output_format: type[T] | None = None,
        **kwargs: Any,
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:

        serialized_messages = OpenAIMessageSerializer.serialize_messages(messages)

        payload: dict[str, Any] = {
            'provider': self.provider_name,
            'model': self.model,
            'messages': serialized_messages,
            'user_id': self.user_id,
            'stream': False,
        }
        if output_format:
            payload['output_schema'] = output_format.model_json_schema()

        url = self.lambda_endpoint.rstrip('/') + _CHAT_PATH
        headers = self._build_headers()

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self._do_request(url, headers, payload, output_format)
            except httpx.TimeoutError as e:
                last_error = e
                logger.warning(
                    f"[ChatLambdaProxy] Timeout on attempt {attempt}/{self.max_retries}: {e}"
                )
            except httpx.HTTPStatusError as e:
                # Retry on 5xx, fail fast on 4xx
                if e.response.status_code >= 500 and attempt < self.max_retries:
                    last_error = e
                    logger.warning(
                        f"[ChatLambdaProxy] Server error {e.response.status_code} on attempt "
                        f"{attempt}/{self.max_retries}, retrying..."
                    )
                else:
                    raise ModelProviderError(
                        message=f"Lambda proxy error {e.response.status_code}: {e.response.text[:500]}",
                        model=self.name,
                    ) from e
            except Exception as e:
                raise ModelProviderError(message=str(e), model=self.name) from e

        raise ModelProviderError(
            message=f"Lambda proxy failed after {self.max_retries} attempts: {last_error}",
            model=self.name,
        )

    async def _do_request(
        self,
        url: str,
        headers: dict,
        payload: dict,
        output_format: type[T] | None,
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
        """Execute a single HTTP request to the Lambda proxy."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()

            # The Lambda returns OpenAI-compatible format:
            # { choices: [{ message: { content: "..." } }], usage: {...} }
            # OR a simplified format:
            # { completion: "...", usage: {...} }
            completion_text = self._extract_completion(data)

            # Parse structured output if requested
            completion: Any = completion_text
            if output_format and isinstance(completion_text, str):
                try:
                    completion = output_format.model_validate_json(completion_text)
                except Exception:
                    # Try parsing as dict first
                    try:
                        parsed = json.loads(completion_text)
                        completion = output_format.model_validate(parsed)
                    except Exception as e:
                        logger.warning(
                            f"[ChatLambdaProxy] Failed to parse output as {output_format.__name__}: {e}"
                        )
                        # Return raw text — let browser-use handle the fallback
                        completion = completion_text

            usage = self._extract_usage(data)

            return ChatInvokeCompletion(
                completion=completion,
                usage=usage,
                stop_reason=self._extract_stop_reason(data),
            )

    @staticmethod
    def _extract_completion(data: dict) -> str:
        """Extract completion text from OpenAI-compatible or simplified response."""
        # OpenAI format
        choices = data.get('choices')
        if choices and isinstance(choices, list) and len(choices) > 0:
            message = choices[0].get('message', {})
            return message.get('content', '')
        # Simplified format
        if 'completion' in data:
            return data['completion']
        raise ValueError(f"Unexpected response format: {list(data.keys())}")

    @staticmethod
    def _extract_usage(data: dict) -> ChatInvokeUsage | None:
        """Extract usage from OpenAI-compatible or simplified response."""
        usage_data = data.get('usage')
        if not usage_data:
            return None
        return ChatInvokeUsage(
            prompt_tokens=usage_data.get('prompt_tokens', 0),
            prompt_cached_tokens=usage_data.get('prompt_tokens_details', {}).get('cached_tokens'),
            prompt_cache_creation_tokens=None,
            prompt_image_tokens=None,
            completion_tokens=usage_data.get('completion_tokens', 0),
            total_tokens=usage_data.get('total_tokens', 0),
        )

    @staticmethod
    def _extract_stop_reason(data: dict) -> str:
        """Extract stop reason from response."""
        choices = data.get('choices')
        if choices and isinstance(choices, list) and len(choices) > 0:
            return choices[0].get('finish_reason', 'stop')
        return data.get('stop_reason', 'stop')

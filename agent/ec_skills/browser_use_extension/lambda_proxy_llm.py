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
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from browser_use.llm.base import BaseChatModel
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import BaseMessage
from browser_use.llm.views import ChatInvokeCompletion, ChatInvokeUsage
from browser_use.llm.openai.serializer import OpenAIMessageSerializer

# The app's file handler is bound to the "eCan"/"eCan.cn" logger tree, so a
# module-name logger here writes to nothing the user (or a customer log)
# ever sees — every [ChatLambdaProxy] diagnostic was silently discarded.
from utils.logger_helper import logger_helper as logger

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
        # ws197: per-request token attribution (agent/task/skill/vehicle) from the
        # active run scope. Read HERE, at request time, not off the (cached,
        # shared) LLM instance — concurrent runs would otherwise cross-attribute.
        try:
            from utils.log_scope import attribution_headers
            headers.update(attribution_headers())
        except Exception:
            pass
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
            _schema = output_format.model_json_schema()
            payload['output_schema'] = _schema
            # Diagnostic: log action count so we can detect when tools vanish.
            try:
                _defs = _schema.get('$defs', _schema.get('definitions', {}))
                _action_names = [k for k in _defs if k.endswith('ActionModel')]
                _action_count = len(_action_names)
                _has_bu = any('BuSelectAgents' in n or 'bu_select' in n.lower() for n in _action_names)
                # The live-chat bundle's tool family is recognised by the
                # brand prefix of its send tool (resolved via the runner
                # bridge so this module stays site-agnostic).  No bundle
                # loaded -> empty marker -> counts as "missing", same as a
                # schema without the site's tools.
                _site_marker = ""
                try:
                    from agent.ec_skills import live_chat_dispatch as _lcd
                    _site_tool = str(_lcd.runner_bridge().send_message_tool_name or "")
                    _site_marker = (_site_tool.split("_", 1)[0] or "").lower()
                except Exception:
                    _site_marker = ""
                _has_site = bool(_site_marker) and any(
                    _site_marker in n.lower() for n in _action_names
                )
                if _action_count < 10 or not _has_bu or not _has_site:
                    logger.warning(
                        f"[ChatLambdaProxy] TOOL SCHEMA ISSUE: {_action_count} ActionModels, "
                        f"has_bu={_has_bu}, has_site={_has_site}, "
                        f"output_format={output_format.__name__}, "
                        f"actions={_action_names}"
                    )
                else:
                    logger.debug(
                        f"[ChatLambdaProxy] Schema OK: {_action_count} ActionModels "
                        f"(bu={_has_bu}, site={_has_site})"
                    )
            except Exception as _diag_err:
                logger.debug(f"[ChatLambdaProxy] Schema diagnostic failed: {_diag_err}")

        url = self.lambda_endpoint.rstrip('/') + _CHAT_PATH
        headers = self._build_headers()
        # One line that answers "did the call even go out, and to where".
        # Payload BYTES, not just message count: CloudBase's gateway rejects an
        # oversized body with 413 EXCEED_MAX_PAYLOAD_SIZE before llm_proxy ever
        # runs, and "messages=2" says nothing about how close we are to that
        # ceiling. A real eBay Seller Hub page (3343 DOM nodes) tripped it on
        # 2026-09-16 while a 107-node splash page sailed through; without a
        # measurement there is no way to size domLimit except by guessing.
        try:
            _payload_bytes = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        except Exception:
            _payload_bytes = -1
        logger.info(
            f"[ChatLambdaProxy] POST {url} provider={self.provider_name} model={self.model} "
            f"messages={len(serialized_messages)} payload={_payload_bytes / 1024:.1f}KB "
            f"structured={bool(output_format)} "
            f"timeout={self.timeout}s auth={'yes' if headers.get('Authorization') else 'NO'}"
        )
        # Per-message breakdown when the body is big enough to matter. Capping
        # the DOM (domLimit 25000 -> 8000) did not move a 107KB payload by a
        # single byte on 2026-09-16, which means the clickable-element list was
        # never the bulk of it. Naming the actual offender beats guessing at
        # another knob.
        if _payload_bytes > 64 * 1024:
            try:
                # Schema first: on 2026-09-16 a 107KB body split as ~1KB of
                # messages and the rest output_schema (the browser-use action
                # model). structured=True was 107KB and 413'd; structured=False
                # was 1KB and passed, every single time. Capping the DOM moved
                # the number by zero bytes, because the DOM was never the bulk.
                _schema_kb = 0.0
                if payload.get('output_schema') is not None:
                    _schema_kb = len(json.dumps(
                        payload['output_schema'], ensure_ascii=False).encode('utf-8')) / 1024
                _msgs_kb = len(json.dumps(
                    serialized_messages, ensure_ascii=False).encode('utf-8')) / 1024
                logger.info(
                    f"[ChatLambdaProxy] payload split: output_schema={_schema_kb:.1f}KB "
                    f"messages={_msgs_kb:.1f}KB"
                )
                # Which actions actually cost the bytes. 56 ActionModels ->
                # 66.4KB means ~1.2KB each, so the question is which families
                # are attached that this node will never call.
                _sch = payload.get('output_schema') or {}
                _dd = _sch.get('$defs', _sch.get('definitions', {})) or {}
                _sizes = sorted(
                    ((len(json.dumps(v, ensure_ascii=False)), k) for k, v in _dd.items()),
                    reverse=True,
                )
                _top = ' '.join(f"{k}={n / 1024:.1f}KB" for n, k in _sizes[:12])
                logger.info(
                    f"[ChatLambdaProxy] schema defs={len(_dd)} "
                    f"total={sum(n for n, _ in _sizes) / 1024:.1f}KB top: {_top}"
                )
                _parts = []
                for _i, _m in enumerate(serialized_messages):
                    _c = _m.get('content') if isinstance(_m, dict) else None
                    if isinstance(_c, list):  # multimodal parts
                        _n = sum(len(json.dumps(_p, ensure_ascii=False)) for _p in _c)
                    else:
                        _n = len(_c or '') if isinstance(_c, str) else len(
                            json.dumps(_c, ensure_ascii=False))
                    _parts.append(
                        f"[{_i}]{(_m.get('role') if isinstance(_m, dict) else '?')}"
                        f"={_n / 1024:.1f}KB"
                    )
                logger.info(f"[ChatLambdaProxy] payload breakdown: {' '.join(_parts)}")
            except Exception as _bd_exc:
                logger.debug(f"[ChatLambdaProxy] breakdown failed: {_bd_exc}")

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self._do_request(url, headers, payload, output_format)
            # httpx has no TimeoutError — it is TimeoutException. Evaluating a
            # missing attribute in an except clause raises AttributeError AT
            # HANDLING TIME, which replaced the real error and skipped every
            # handler below, including the retry. That is why a failed call
            # produced no usable message and never retried.
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    f"[ChatLambdaProxy] Timeout on attempt {attempt}/{self.max_retries}: "
                    f"type={type(e).__name__} str={str(e)!r} url={url} timeout={self.timeout}s",
                    exc_info=True,
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
                    from agent.ec_skills.llm_utils.proxy_errors import friendly_proxy_error_message
                    _friendly = friendly_proxy_error_message(e.response.text)
                    raise ModelProviderError(
                        message=_friendly or
                        f"Lambda proxy error {e.response.status_code}: {e.response.text[:500]}",
                        model=self.name,
                    ) from e
            except Exception as e:
                # str(e) is EMPTY for a bare TimeoutError / CancelledError /
                # ConnectError, and browser-use reports failures as
                # f'❌ Result failed N/M times: {str(error)}' — so the cause
                # vanished and six identical failures looked like silence
                # (2026-09-16: cost a full afternoon of bisecting providers).
                # Name the type, and log the frame before it is flattened.
                logger.error(
                    f"[ChatLambdaProxy] request failed on attempt {attempt}/{self.max_retries}: "
                    f"type={type(e).__name__} str={str(e)!r} url={url} "
                    f"provider={self.provider_name} model={self.model}",
                    exc_info=True,
                )
                raise ModelProviderError(
                    message=f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__} (no message)",
                    model=self.name,
                ) from e

        raise ModelProviderError(
            message=(
                f"Lambda proxy failed after {self.max_retries} attempts: "
                f"{type(last_error).__name__}: {last_error}"
            ),
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
            # Log error responses for diagnostics
            if 'error' in data and 'choices' not in data:
                logger.error(
                    f"[ChatLambdaProxy] Error response from {url}: "
                    f"status={response.status_code}, body={response.text[:500]}"
                )

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
        # Check for error response first
        if 'error' in data and 'choices' not in data and 'completion' not in data:
            error_detail = data['error']
            if isinstance(error_detail, dict):
                error_msg = error_detail.get('message', str(error_detail))
            else:
                error_msg = str(error_detail)
            logger.error(f"[ChatLambdaProxy] Lambda proxy returned error: {error_msg}")
            from agent.ec_skills.llm_utils.proxy_errors import friendly_proxy_error_message
            _friendly = friendly_proxy_error_message(str(error_detail))
            raise ValueError(_friendly or f"Lambda proxy error: {error_msg}")
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

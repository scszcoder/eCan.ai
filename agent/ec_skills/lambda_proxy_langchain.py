"""
Lambda Proxy LLM for LangChain — extends ChatOpenAI to route through Lambda.

Since the Lambda exposes an OpenAI-compatible /v1/chat/completions endpoint,
we simply extend ChatOpenAI and override the base_url + headers to route
through the proxy. This gives us full LangChain compatibility (streaming,
tool calling, structured output, etc.) for free.

Usage:
    llm = create_lambda_proxy_langchain(
        provider="openai",
        model="gpt-4o",
        user_id="user@example.com",
        lambda_endpoint="https://xxx.lambda-url.us-east-1.on.aws",
        auth_token="cognito-id-token",
    )
"""

import logging
from typing import Optional, Callable

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def create_lambda_proxy_langchain(
    *,
    provider: str,
    model: str,
    user_id: str,
    lambda_endpoint: str,
    auth_token: str = '',
    temperature: float = 0.5,
    token_refresh_fn: Optional[Callable[[], str]] = None,
    timeout: float = 300.0,
    max_retries: int = 2,
    **kwargs,
) -> ChatOpenAI:
    """Create a LangChain ChatOpenAI instance routed through the Lambda proxy.

    The Lambda Function URL exposes an OpenAI-compatible API, so we can
    use ChatOpenAI directly with a custom base_url. The Lambda dispatches
    to the correct provider (OpenAI, Anthropic, etc.) based on the model name
    and X-Provider / X-User-Id headers.

    Args:
        provider: LLM provider name ("openai", "anthropic", "deepseek", etc.)
        model: Model name ("gpt-4o", "claude-sonnet-4-20250514", etc.)
        user_id: User identifier for billing/accounting
        lambda_endpoint: Lambda Function URL (no trailing slash)
        auth_token: Cognito ID token for authentication
        temperature: Sampling temperature
        token_refresh_fn: Optional callback to refresh expired auth tokens
        timeout: Request timeout in seconds
        max_retries: Number of retry attempts
        **kwargs: Additional kwargs passed to ChatOpenAI
    """
    # Refresh token if callback provided
    if token_refresh_fn:
        try:
            fresh = token_refresh_fn()
            if fresh:
                auth_token = fresh
        except Exception as e:
            logger.warning(f"[LambdaProxyLangChain] Token refresh failed: {e}")

    # The Lambda expects:
    # - Authorization: Bearer <cognito-token>
    # - X-Provider: <provider-name> (so Lambda knows which backend to use)
    # - X-User-Id: <user-id> (for token accounting)
    default_headers = {
        'X-Provider': provider,
        'X-User-Id': user_id,
    }

    # Build base_url — Lambda Function URL serves /v1/chat/completions
    base_url = lambda_endpoint.rstrip('/') + '/v1'

    llm = ChatOpenAI(
        model=model,
        api_key=auth_token or 'lambda-proxy',  # OpenAI SDK requires non-empty api_key
        base_url=base_url,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        default_headers=default_headers,
        **kwargs,
    )

    logger.info(
        f"[LambdaProxyLangChain] Created proxy LLM: provider={provider}, "
        f"model={model}, user={user_id}, endpoint={base_url}"
    )
    return llm

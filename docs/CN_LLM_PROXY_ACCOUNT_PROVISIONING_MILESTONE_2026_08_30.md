# CN LLM Proxy And Account Provisioning Milestone

**Date:** 2026-08-30
**Status:** Verified in production

## Outcome

CN desktop skill execution can now route cloud chat LLM requests through the
Tencent `llm_proxy` while using a server-owned account record for access
control, trial eligibility, and usage logging.

## Account Provisioning

After a successful CN email/password or phone login, the shared login finalizer
calls `ecbAccountManager` action `ensure_account`. The function verifies the
fresh CloudBase access token with CloudBase `/auth/v1/user/me`; it does not
trust a caller-provided identity, email, or phone number.

The operation finds or creates an active row in `public.accounts`, populating
the verified email or phone when available and persisting the verified identity
in both `subid` and `subs`. This is the identity form that `llm_proxy` accepts
for its account gate. WeChat uses the server-owned OAuth callback and follows
the same account-upsert semantics with raw OpenID as its canonical identity.

## Mainland Provider Fallback

The CN client routes cloud LLM calls through `llm_proxy` by default, excluding
Ollama, local/LAN endpoints, and explicit per-node proxy choices. The proxy
verifies the caller, checks that an `accounts` row is active and funded or
within trial, then forwards to the selected provider and records usage.

OpenAI and Gemini upstream domains timed out from the mainland deployment. For
chat requests resolved as either provider, `llm_proxy` now replaces both the
provider and model with the configured CN fallback before forwarding. The live
fallback is:

```text
provider: deepseek
model: deepseek-v4-flash
```

Explicit DeepSeek, Qwen, Kimi, GLM, MiniMax, and ByteDance selections remain
unchanged. Embedding and reranking routes are not affected by this chat-only
fallback.

## RAG Model Distinction

CN RAG indexing is independent of the chat proxy fallback. It uses DashScope
Qwen `text-embedding-v3` with 1024-dimensional vectors, and Qwen `qwen-plus`
to synthesize grounded retrieval responses from the top cosine-ranked chunks.

## Validation

- A CN email login created an active `accounts` row with the verified email and
  identity stored in `subid` and `subs`.
- Client skill workflow reached `llm_proxy`, passed authentication/account
  gating, and identified the previous upstream timeout/model mismatch.
- `llm_proxy` focused contract tests pass, including provider/model fallback
  substitution.
- The deployed proxy is active with a configured DeepSeek credential and
  `DEFAULT_PROVIDER=deepseek`, `DEFAULT_MODEL=deepseek-v4-flash`.
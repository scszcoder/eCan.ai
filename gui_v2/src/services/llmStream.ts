/**
 * SSE display-streaming client for the LLM proxy gateway.
 *
 * Opens a fetch()-based SSE request to the Lambda proxy's OpenAI-compatible
 * `POST /v1/chat/completions` endpoint and emits token deltas as they arrive.
 *
 * This is DISPLAY-PROGRESS transport only: the canonical assistant message is
 * still written by chatter and delivered through the existing WebSocket
 * subscription (onA2AMessageReceived). Callers should render deltas in a
 * temporary bubble and replace it with the persisted message when it arrives.
 *
 * Native EventSource is not used because it only supports GET and cannot
 * attach an Authorization header — we read response.body as a ReadableStream
 * and parse SSE frames manually.
 */

import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';

export interface LlmStreamConfig {
    enabled: boolean;
    endpoint?: string;   // Lambda Function URL base, no trailing slash
    auth_token?: string; // eCan session token
    user_id?: string;
    provider?: string;
    model?: string;
    reason?: string;     // populated when enabled=false
}

export interface StreamChatParams {
    config: LlmStreamConfig;
    messages: Array<{ role: string; content: string }>;
    model?: string;      // overrides config.model
    requestId?: string;  // correlates with a future WS llm.delta shape
    signal?: AbortSignal;
    onDelta: (text: string) => void;
    onDone: () => void;
    onError: (err: unknown) => void;
}

const CHAT_PATH = '/v1/chat/completions';

/**
 * SSE display streaming is a CN-only feature. Mirrors the isCNBuild()
 * check in services/web/appSyncSubscriptions.ts; the backend enforces the
 * same gate in llm_proxy.get_stream_config — this just skips the IPC call
 * entirely on intl builds.
 */
const isCNBuild = (): boolean => {
    const env = (typeof import.meta !== 'undefined' && import.meta.env) || ({} as Record<string, string | undefined>);
    return env.VITE_APP_ID === 'cn' || env.VITE_CLOUDBASE_ENV_ID !== undefined;
};

// Config cache: avoid one IPC roundtrip per chat message. Short TTL so a
// token refresh or settings change is picked up quickly.
const CONFIG_TTL_MS = 60_000;
let cachedConfig: LlmStreamConfig | null = null;
let cachedAt = 0;

/**
 * Fetch (and briefly cache) the SSE streaming config from the backend.
 * Never throws: returns { enabled: false } when streaming is unavailable
 * (endpoint unset, not signed in, web platform without IPC, ...).
 */
export async function fetchLlmStreamConfig(): Promise<LlmStreamConfig> {
    if (!isCNBuild()) return { enabled: false, reason: 'intl build' };
    const now = Date.now();
    if (cachedConfig && now - cachedAt < CONFIG_TTL_MS) return cachedConfig;
    try {
        const resp = await get_ipc_api().getLlmStreamConfig<LlmStreamConfig>();
        const cfg: LlmStreamConfig = (resp?.success && resp.data)
            ? resp.data
            : { enabled: false, reason: resp?.error ? JSON.stringify(resp.error) : 'no config' };
        cachedConfig = cfg;
        cachedAt = now;
        return cfg;
    } catch (err) {
        logger.warn(`[llmStream] Stream config fetch failed: ${err}`);
        return { enabled: false, reason: String(err) };
    }
}

/** Extract the delta text from one parsed SSE data payload. */
const extractDelta = (payload: any): string => {
    // OpenAI-compatible streaming shape: choices[0].delta.content
    const openAiDelta = payload?.choices?.[0]?.delta?.content;
    if (typeof openAiDelta === 'string') return openAiDelta;
    // Forward-compatible request-scoped event shape: { type: 'llm.delta', requestId, delta }
    if (payload?.type === 'llm.delta' && typeof payload?.delta === 'string') return payload.delta;
    return '';
};

/**
 * Stream one chat completion. Resolves after the stream ends ([DONE], EOF,
 * abort, or error). All UI updates flow through the callbacks.
 */
export async function streamChatCompletion(params: StreamChatParams): Promise<void> {
    const { config, messages, model, requestId, signal, onDelta, onDone, onError } = params;

    if (!config.enabled || !config.endpoint || !config.auth_token) {
        onError(new Error(config.reason || 'LLM streaming not configured'));
        return;
    }

    try {
        const resp = await fetch(`${config.endpoint}${CHAT_PATH}`, {
            method: 'POST',
            signal,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${config.auth_token}`,
                'Accept': 'text/event-stream',
            },
            body: JSON.stringify({
                model: model || config.model,
                messages,
                stream: true,
                user: config.user_id || undefined,
                ...(requestId ? { request_id: requestId } : {}),
            }),
        });

        if (!resp.ok || !resp.body) {
            const bodyText = resp.body ? await resp.text().catch(() => '') : '';
            throw new Error(`SSE request failed: HTTP ${resp.status} ${bodyText.slice(0, 200)}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let done = false;

        while (!done) {
            const { value, done: eof } = await reader.read();
            if (eof) break;
            buffer += decoder.decode(value, { stream: true });

            // SSE frames are separated by a blank line; tolerate \r\n servers.
            const frames = buffer.split(/\r?\n\r?\n/);
            buffer = frames.pop() ?? ''; // keep the trailing partial frame

            for (const frame of frames) {
                for (const line of frame.split(/\r?\n/)) {
                    if (!line.startsWith('data:')) continue; // ignore event:/id:/comments
                    const data = line.slice(5).trim();
                    if (data === '[DONE]') {
                        done = true;
                        break;
                    }
                    if (!data) continue;
                    try {
                        const delta = extractDelta(JSON.parse(data));
                        if (delta) onDelta(delta);
                    } catch {
                        logger.warn(`[llmStream] Unparseable SSE data frame: ${data.slice(0, 120)}`);
                    }
                }
                if (done) break;
            }
        }

        try { reader.cancel(); } catch { /* already closed */ }
        onDone();
    } catch (err: unknown) {
        if ((err as Error)?.name === 'AbortError') {
            // Caller aborted (e.g. final A2A message arrived first) — not an error.
            onDone();
            return;
        }
        logger.error(`[llmStream] Stream failed: ${err}`);
        onError(err);
    }
}

import React from 'react';
import { Button, Input, Typography, message as antdMessage } from 'antd';
import { CustomerServiceOutlined, CloseOutlined, SendOutlined } from '@ant-design/icons';
import { appSyncRequest } from '@/services/web/appSyncClient';
import { GRAPHQL_MUTATIONS, GRAPHQL_QUERIES } from '@/services/api/api-config';
import type { A2AMessage, A2AMessageConnection } from '@/services/api/cloudChatApi';
import { cloudChatApi } from '@/services/api/cloudChatApi';
import { webAuthSession } from '@/services/auth/webAuthSession';
import { useUserStore } from '@/stores/userStore';

const { Text } = Typography;

type ChatLine = {
  id: string;
  role: 'user' | 'agent';
  text: string;
  ts: number;
};

const SUPPORT_AGENT_ID = 'customer_support';

const API_KEY_TTL_MS = 24 * 60 * 60 * 1000;

type CachedApiKey = {
  apiKey: string;
  obtainedAt: number;
  user: string;
};

function cacheKeyForUser(user: string): string {
  const safe = (user || 'anonymous').replace(/[^a-zA-Z0-9_@.\-]/g, '_');
  return `chat_test:reqApiKey:${safe}`;
}

function readCachedApiKey(user: string): string | null {
  try {
    const raw = localStorage.getItem(cacheKeyForUser(user));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedApiKey;
    if (!parsed?.apiKey || !parsed?.obtainedAt) return null;
    const age = Date.now() - Number(parsed.obtainedAt);
    if (age < 0) return null;
    if (age <= API_KEY_TTL_MS) return String(parsed.apiKey);
    return null;
  } catch {
    return null;
  }
}

function writeCachedApiKey(user: string, apiKey: string): void {
  try {
    const payload: CachedApiKey = { apiKey, obtainedAt: Date.now(), user };
    localStorage.setItem(cacheKeyForUser(user), JSON.stringify(payload));
  } catch {
    // ignore (no storage / quota)
  }
}

function pickSenderId(): string {
  const webUser = webAuthSession.getUserInfo();
  const email = (webUser?.email || '').trim();
  if (email) return email;
  const username = (webUser?.username || '').trim();
  if (username) return username;
  const storeUsername = (useUserStore.getState().username || '').trim();
  return storeUsername || 'anonymous';
}

function toLine(msg: A2AMessage): ChatLine | null {
  const part = msg?.message?.parts?.find((p) => p?.type === 'text');
  const text = (part?.text ?? '').toString();
  if (!text) return null;
  const roleRaw = (msg?.message?.role || '').toString().toLowerCase();
  const role: ChatLine['role'] = roleRaw === 'user' ? 'user' : 'agent';
  const ts = msg?.timestamp ? Date.parse(msg.timestamp) : Date.now();
  return { id: msg.id || `${ts}`, role, text, ts };
}

async function fetchWanApiKey(): Promise<string> {
  // Requirement: request an API key from backend before sending.
  // Use reqApiKey(input: CustomerInput) which is Cognito-authenticated.
  const sender = pickSenderId();

  // Reuse for at least 24 hours.
  const cached = readCachedApiKey(sender);
  if (cached) return cached;

  const result = await appSyncRequest<{ reqApiKey: { apiKey?: string; message?: string } }>(
    GRAPHQL_MUTATIONS.REQ_API_KEY,
    { input: { user: sender } },
    { authMode: 'bearer' },
    'chat_test.req_api_key'
  );
  const key = (result as any)?.reqApiKey?.apiKey;
  if (!key) {
    const msg = (result as any)?.reqApiKey?.message;
    throw new Error(msg || 'API key missing: reqApiKey returned empty apiKey');
  }

  writeCachedApiKey(sender, String(key));
  return String(key);
}

async function sendA2AWithApiKey(params: {
  apiKey: string;
  channelId: string;
  sessionId: string;
  senderId: string;
  recipientId: string;
  text: string;
}): Promise<A2AMessage> {
  const graphqlInput = {
    channelId: params.channelId,
    sessionId: params.sessionId,
    senderId: params.senderId,
    recipientId: params.recipientId,
    message: {
      role: 'user',
      parts: [{ type: 'text', text: params.text }],
    },
    metadata: JSON.stringify({ senderName: params.senderId }),
    acceptedOutputModes: ['text'],
  };

  const result = await appSyncRequest<{ sendA2AMessage: A2AMessage }>(
    GRAPHQL_MUTATIONS.SEND_A2A_MESSAGE,
    { input: graphqlInput },
    {
      authMode: 'lambda',
      headers: {
        'x-custom-api-key': params.apiKey,
        // If this doesn't match the stored user, myAuthorizer falls back when only 1 item exists.
        'x-api-caller': params.senderId,
      },
    },
    'chat_test.send_cloud_a2a_message'
  );

  return result.sendA2AMessage;
}

async function getA2AMessagesWithApiKey(params: {
  apiKey: string;
  channelId: string;
  limit?: number;
  senderId: string;
}): Promise<A2AMessageConnection> {
  const result = await appSyncRequest<{ getA2AMessages: A2AMessageConnection }>(
    GRAPHQL_QUERIES.GET_A2A_MESSAGES,
    { channelId: params.channelId, limit: params.limit ?? 50, nextToken: undefined },
    {
      authMode: 'lambda',
      headers: {
        'x-custom-api-key': params.apiKey,
        'x-api-caller': params.senderId,
      },
    },
    'chat_test.get_a2a_messages'
  );
  return result.getA2AMessages;
}

const ChatTest: React.FC = () => {
  const [open, setOpen] = React.useState(false);
  const [lines, setLines] = React.useState<ChatLine[]>([]);
  const [text, setText] = React.useState('');
  const [sending, setSending] = React.useState(false);

  const senderId = React.useMemo(() => pickSenderId(), []);
  const recipientId = SUPPORT_AGENT_ID;
  const channelId = React.useMemo(() => cloudChatApi.getChannelId(senderId, recipientId), [senderId, recipientId]);
  const [sessionId] = React.useState(() => cloudChatApi.generateSessionId());

  const refreshFromBackend = React.useCallback(async () => {
    try {
      const apiKey = await fetchWanApiKey();
      const connection = await getA2AMessagesWithApiKey({ apiKey, channelId, limit: 50, senderId });
      const next = (connection.items || [])
        .map(toLine)
        .filter(Boolean) as ChatLine[];
      next.sort((a, b) => a.ts - b.ts);
      setLines(next);
    } catch {
      // ignore (blank page + popup should still render)
    }
  }, [channelId]);

  React.useEffect(() => {
    if (open) {
      void refreshFromBackend();
    }
  }, [open, refreshFromBackend]);

  const handleSend = React.useCallback(async () => {
    const content = text.trim();
    if (!content || sending) return;

    setSending(true);
    try {
      // 1) Request API key from backend
      const apiKey = await fetchWanApiKey();

      // 2) Optimistically append user line
      const now = Date.now();
      setLines((prev) => [...prev, { id: `local_${now}`, role: 'user', text: content, ts: now }]);
      setText('');

      // 3) Send A2A message using API-key auth
      await sendA2AWithApiKey({
        apiKey,
        channelId,
        sessionId,
        senderId,
        recipientId,
        text: content,
      });

      // 4) Refresh thread (agent reply may arrive async; this is a best-effort update)
      setTimeout(() => {
        void refreshFromBackend();
      }, 800);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      antdMessage.error(msg);
    } finally {
      setSending(false);
    }
  }, [text, sending, channelId, sessionId, senderId, recipientId, refreshFromBackend]);

  return (
    <div style={{ height: '100%', width: '100%' }}>
      {/* Blank page by design */}

      {/* Floating chat icon hanging on right edge */}
      <Button
        type="primary"
        shape="circle"
        icon={<CustomerServiceOutlined />}
        onClick={() => setOpen(true)}
        style={{
          position: 'fixed',
          right: 0,
          top: '50%',
          transform: 'translate(50%, -50%)',
          zIndex: 1000,
        }}
      />

      {open && (
        <div
          style={{
            position: 'fixed',
            right: 16,
            bottom: 24,
            width: 360,
            height: 480,
            zIndex: 1001,
            background: 'rgba(15, 23, 42, 0.98)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 12,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '10px 12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            <Text style={{ color: 'rgba(255,255,255,0.92)', fontWeight: 600 }}>
              Chat Test (Support Agent)
            </Text>
            <Button
              type="text"
              icon={<CloseOutlined />}
              onClick={() => setOpen(false)}
              style={{ color: 'rgba(255,255,255,0.8)' }}
            />
          </div>

          <div style={{ flex: 1, overflow: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {lines.map((l) => (
              <div
                key={l.id}
                style={{
                  alignSelf: l.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  padding: '8px 10px',
                  borderRadius: 10,
                  background: l.role === 'user' ? 'rgba(59, 130, 246, 0.35)' : 'rgba(148, 163, 184, 0.18)',
                  color: 'rgba(255,255,255,0.92)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {l.text}
              </div>
            ))}
            {lines.length === 0 && (
              <Text style={{ color: 'rgba(255,255,255,0.55)' }}>
                Send a message to start testing.
              </Text>
            )}
          </div>

          <div style={{ padding: 12, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <Input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onPressEnter={(e) => {
                // prevent newline in input
                e.preventDefault();
                void handleSend();
              }}
              placeholder="Type a message…"
              suffix={
                <Button
                  type="text"
                  icon={<SendOutlined />}
                  onClick={() => void handleSend()}
                  disabled={!text.trim() || sending}
                  style={{ color: 'rgba(255,255,255,0.8)' }}
                />
              }
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default ChatTest;

/**
 * Fleet feed (web): the account's desktop machines (Commander / Platoon) publish
 * what their agents do on the WAN chat channel `fleet.feed`; this listens to it
 * over the cloud WebSocket and sends commands back on `fleet.cmd`.
 *
 * Wire protocol = the desktop's (agent/fleet/activity_feed.py): AppSync-compatible
 * graphql-ws, auth in the URL (`?header=<b64 {host, Authorization}>&payload=e30=`)
 * and in the subscription's extensions. The server scopes both channels to the
 * signed-in account, so nothing here names a user.
 */
import { useFleetFeedStore } from '@/stores/fleetFeedStore';
import { getCachedAppConfig } from '@/contexts/AppConfigContext';
import { userStorageManager } from '@/services/storage/UserStorageManager';
import { appSyncRequest } from '@/services/web/appSyncClient';

export const FEED_CHANNEL = 'fleet.feed';
export const CMD_CHANNEL = 'fleet.cmd';

const SUBSCRIPTION = `subscription onMessageReceived($chatID: String!) {
  onMessageReceived(chatID: $chatID) { id chatID sender receiver type contents parameters timestamp }
}`;

const SEND = `mutation sendWanMessage($input: WanChatMessageInput!) {
  sendWanMessage(input: $input) { id chatID timestamp }
}`;

const env = (): Record<string, string> => ((import.meta as any).env || {}) as Record<string, string>;

/** The cloud WebSocket endpoint: runtime config first, then build-time env. */
export function fleetWsEndpoint(): string {
  const cloud = getCachedAppConfig()?.cloud;
  return (cloud?.ws_endpoint || env().VITE_WS_URL || env().VITE_APPSYNC_WS_ENDPOINT || '').trim();
}

function bareToken(): string {
  let t = (userStorageManager.getToken() || '').trim();
  if (t.includes('/@@/')) t = t.split('/@@/').pop() || '';
  if (t.toLowerCase().startsWith('bearer ')) t = t.slice(7).trim();
  return t;
}

function b64(obj: unknown): string {
  return btoa(unescape(encodeURIComponent(JSON.stringify(obj))));
}

let socket: WebSocket | null = null;
let retry = 0;
let stopped = true;
let retryTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleReconnect() {
  if (stopped) return;
  const wait = Math.min(60_000, 2_000 * 2 ** Math.min(retry, 5));
  retry += 1;
  retryTimer = setTimeout(connect, wait);
}

function connect() {
  const store = useFleetFeedStore.getState();
  const endpoint = fleetWsEndpoint();
  const token = bareToken();
  if (!endpoint || !token) {
    store.setConnection('unconfigured', !endpoint ? 'no cloud WebSocket endpoint configured' : 'not signed in');
    return;
  }
  let host = '';
  try { host = new URL(endpoint).host; } catch { /* keep empty */ }
  const auth = { host, Authorization: token };
  const url = `${endpoint}${endpoint.includes('?') ? '&' : '?'}header=${encodeURIComponent(b64(auth))}&payload=e30=`;
  store.setConnection('connecting');
  const ws = new WebSocket(url, 'graphql-ws');
  socket = ws;
  ws.onopen = () => ws.send(JSON.stringify({ type: 'connection_init', payload: {} }));
  ws.onmessage = (ev) => {
    let f: any;
    try { f = JSON.parse(String(ev.data)); } catch { return; }
    if (f.type === 'connection_ack') {
      ws.send(JSON.stringify({
        id: 'fleet-feed', type: 'start',
        payload: {
          data: JSON.stringify({ query: SUBSCRIPTION, variables: { chatID: FEED_CHANNEL } }),
          extensions: { authorization: auth },
        },
      }));
    } else if (f.type === 'start_ack') {
      retry = 0;
      useFleetFeedStore.getState().setConnection('live');
      void sendFleetCommand('snapshot');           // ask every machine for its state now
    } else if (f.type === 'data') {
      const msg = f.payload?.data?.onMessageReceived;
      if (msg?.type === 'fleet_feed') {
        try {
          const body = typeof msg.contents === 'string' ? JSON.parse(msg.contents) : msg.contents;
          useFleetFeedStore.getState().ingest(body);
        } catch { /* a malformed message is skipped */ }
      }
    } else if (f.type === 'error' || f.type === 'connection_error') {
      useFleetFeedStore.getState().setConnection('error', JSON.stringify(f.payload || f).slice(0, 200));
    }
  };
  ws.onclose = () => {
    if (socket === ws) socket = null;
    if (!stopped) {
      useFleetFeedStore.getState().setConnection('reconnecting');
      scheduleReconnect();
    }
  };
  ws.onerror = () => { try { ws.close(); } catch { /* closing anyway */ } };
}

export function startFleetFeed() {
  if (!stopped) return;
  stopped = false;
  retry = 0;
  connect();
}

export function stopFleetFeed() {
  stopped = true;
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = null;
  try { socket?.close(); } catch { /* ignore */ }
  socket = null;
  useFleetFeedStore.getState().setConnection('idle');
}

/** Send a command to one machine (its id) or all ('*'). */
export async function sendFleetCommand(
  cmd: 'snapshot' | 'ping' | 'log_start' | 'log_stop',
  machine: string = '*',
  extra: { ttl_s?: number; level?: string } = {},
): Promise<boolean> {
  try {
    await appSyncRequest(SEND, {
      input: {
        chatID: CMD_CHANNEL, sender: 'web', receiver: machine, type: 'fleet_cmd',
        contents: JSON.stringify({ cmd, machine, ...extra }), parameters: '{}',
      },
    }, { authMode: 'bearer' });
    return true;
  } catch (e) {
    console.warn('[FleetFeed] command not sent', e);
    return false;
  }
}

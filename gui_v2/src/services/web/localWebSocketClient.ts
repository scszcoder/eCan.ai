/**
 * Local WebSocket Client for Skill Editor Streaming
 * 
 * Connects to the local Python backend WebSocket server for receiving
 * streaming events (chat chunks, canvas commands, etc.) when running
 * in desktop mode with VITE_IPC_MODE OFF.
 */

import { getSettings } from '../../stores/settingsStore';
import { eventBus } from '@/utils/eventBus';
import { unifiedEventHandler, createStandardizedEvent } from '@/services/events/unifiedEventHandler';
import { detectPlatform } from '@/config/platform';
import { useAdStore } from '@/stores/adStore';

type MessageHandler = (data: any) => void;

interface LocalWebSocketClientOptions {
  autoReconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

const getEnv = () => {
  try {
    if (typeof import.meta !== 'undefined' && (import.meta as any).env) {
      return (import.meta as any).env as Record<string, any>;
    }
  } catch {}
  return {} as Record<string, any>;
};

const isTruthyEnvValue = (value: unknown): boolean => {
  const normalized = String(value ?? '').trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
};

class LocalWebSocketClient {
  private static instance: LocalWebSocketClient | null = null;
  private ws: WebSocket | null = null;
  private messageHandlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private options: Required<LocalWebSocketClientOptions>;
  private subscribedChannels: Set<string> = new Set();
  private isConnecting = false;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  // Consecutive-failure counter used to decide log level + backoff.
  // Tracked separately from `reconnectAttempts` so we can grow the backoff
  // even after the max-attempts "fast retry" phase ends.
  private consecutiveFailures = 0;
  // Set true when the user / logout explicitly tore down the link.
  // In this state we MUST NOT auto-reconnect — the backend is gone on
  // purpose.  Only `connect({ force: true })` should restart us.
  private userInitiatedDisconnect = false;

  private constructor(options: LocalWebSocketClientOptions = {}) {
    this.options = {
      autoReconnect: options.autoReconnect ?? true,
      reconnectInterval: options.reconnectInterval ?? 3000,
      maxReconnectAttempts: options.maxReconnectAttempts ?? 10,
    };
  }

  static getInstance(): LocalWebSocketClient {
    if (!LocalWebSocketClient.instance) {
      LocalWebSocketClient.instance = new LocalWebSocketClient();
    }
    return LocalWebSocketClient.instance;
  }

  /**
   * Check if we should use local WebSocket (desktop + VITE_IPC_MODE OFF)
   * Also returns true in dev mode when IPC is OFF (desktop development without Qt WebChannel)
   */
  shouldUseLocalWebSocket(): boolean {
    const env = getEnv();
    const ipcModeOn = isTruthyEnvValue(env.VITE_IPC_MODE);
    
    // If IPC mode is ON, we don't need local WebSocket (using IPC directly)
    if (ipcModeOn) return false;
    
    const platform = detectPlatform();
    
    // Desktop mode (Qt WebChannel available)
    if (platform === 'desktop') return true;
    
    // Dev mode with IPC OFF - this is desktop development without Qt WebChannel
    // In this case, we use local WebSocket for real-time push events
    const isDev = (typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV) || false;
    if (isDev && !ipcModeOn) {
      console.log('[LocalWS] Dev mode with IPC OFF - using local WebSocket');
      return true;
    }
    
    return false;
  }

  /**
   * Get the WebSocket URL for the local server
   */
  private getWebSocketUrl(): string {
    // Always use the backend server port, not the Vite dev server port
    // In dev mode, Vite runs on 3000 but backend runs on 4668
    const settings = getSettings();
    const port = settings?.local_server_port || '4668';
    return `ws://localhost:${port}/ws/skill-editor`;
  }

  /**
   * Connect to the local WebSocket server
   * @param force - If true, bypasses the shouldUseLocalWebSocket check (for testing)
   */
  async connect(force: boolean = false): Promise<boolean> {
    if (!force && !this.shouldUseLocalWebSocket()) {
      console.log('[LocalWS] Not using local WebSocket (not desktop or IPC mode is ON)');
      return false;
    }

    // A user-initiated disconnect (e.g. logout) must not be overridden by an
    // unrelated reconnect timer.  Only an explicit `connect({ force: true })`
    // can bring it back (used by `resetAndConnect()` after a clean restart).
    if (this.userInitiatedDisconnect && !force) {
      console.log('[LocalWS] Skipping connect: user-initiated disconnect is in effect');
      return false;
    }

    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('[LocalWS] Already connected');
      return true;
    }

    if (this.isConnecting) {
      console.log('[LocalWS] Connection already in progress');
      return false;
    }

    this.isConnecting = true;
    const url = this.getWebSocketUrl();
    console.log('[LocalWS] Connecting to:', url);

    return new Promise((resolve) => {
      try {
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('[LocalWS] ✅ Connected successfully to:', url);
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          this.consecutiveFailures = 0;

          // Re-subscribe to previously subscribed channels
          this.subscribedChannels.forEach(channel => {
            this.subscribe(channel);
          });

          // Start keepalive ping to prevent idle disconnections
          this.startPing();

          resolve(true);
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          // Don't spam console.error: a closed backend (e.g. after user
          // ran `python3 main.py` once and quit) is expected, not an
          // application-level error.  First failure warns; subsequent
          // failures are debug-level until the link comes back up.
          this.consecutiveFailures++;
          if (this.consecutiveFailures === 1) {
            console.warn(
              '[LocalWS] WebSocket error (will retry with backoff):',
              error,
            );
          } else {
            console.debug(
              '[LocalWS] WebSocket error (attempt %d):',
              this.consecutiveFailures,
              error,
            );
          }
          this.isConnecting = false;
        };

        this.ws.onclose = (event) => {
          // Code 1006 (abnormal closure) is what the browser reports when
          // the OS refuses the TCP connection (backend not listening).
          // Code 1005 is "no status received".  Anything else means the
          // backend explicitly closed — likely a server restart.
          const expectedClose = event.code === 1006 || event.code === 1005;
          if (expectedClose && this.consecutiveFailures > 1) {
            console.debug('[LocalWS] Connection closed:', event.code, event.reason);
          } else {
            console.log('[LocalWS] Connection closed:', event.code, event.reason);
          }
          this.isConnecting = false;
          this.ws = null;
          this.stopPing();

          if (
            this.options.autoReconnect &&
            this.reconnectAttempts < this.options.maxReconnectAttempts
          ) {
            this.scheduleReconnect();
          } else if (this.options.autoReconnect) {
            // Past the "fast retry" window — schedule a slow keepalive
            // reconnect (every 30s) so we still recover when the user
            // restarts `python3 main.py`.  Use a distinct log line so
            // it doesn't pile up in the same channel as the fast retries.
            this.scheduleKeepaliveReconnect();
          }

          resolve(false);
        };

      } catch (error) {
        console.error('[LocalWS] Failed to create WebSocket:', error);
        this.isConnecting = false;
        resolve(false);
      }
    });
  }

  /**
   * Disconnect from the WebSocket server
   *
   * Sets `userInitiatedDisconnect` so the auto-reconnect loop stops until
   * the next explicit `connect({ force: true })` (e.g. after a logout /
   * backend restart).  Pass `{ keepAutoReconnect: true }` to drop the
   * current socket without blocking future auto-reconnect attempts.
   */
  disconnect(options: { keepAutoReconnect?: boolean } = {}): void {
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.reconnectAttempts = 0;
    this.consecutiveFailures = 0;
    if (!options.keepAutoReconnect) {
      this.userInitiatedDisconnect = true;
    }
    console.log('[LocalWS] Disconnected (userInitiated=%s)', this.userInitiatedDisconnect);
  }

  /**
   * Re-arm auto-reconnect after a previous `disconnect()` call.  Used by
   * LoginCN mount (after logout) and by LogoutManager-aware flows that want
   * to silently come back once the backend is reachable again.
   */
  enableAutoReconnect(): void {
    this.userInitiatedDisconnect = false;
    this.consecutiveFailures = 0;
    this.reconnectAttempts = 0;
  }

  /**
   * Subscribe to a specific channel (e.g., session:xxx)
   */
  subscribe(channel: string): void {
    this.subscribedChannels.add(channel);
    
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'subscribe',
        channel
      }));
      console.log('[LocalWS] Subscribed to channel:', channel);
    }
  }

  /**
   * Unsubscribe from a channel
   */
  unsubscribe(channel: string): void {
    this.subscribedChannels.delete(channel);
    
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'unsubscribe',
        channel
      }));
      console.log('[LocalWS] Unsubscribed from channel:', channel);
    }
  }

  /**
   * Subscribe to a session's events
   */
  subscribeToSession(sessionId: string): void {
    this.subscribe(`session:${sessionId}`);
  }

  /**
   * Unsubscribe from a session's events
   */
  unsubscribeFromSession(sessionId: string): void {
    this.unsubscribe(`session:${sessionId}`);
  }

  /**
   * Register a handler for a specific message type
   */
  on(messageType: string, handler: MessageHandler): void {
    if (!this.messageHandlers.has(messageType)) {
      this.messageHandlers.set(messageType, new Set());
    }
    this.messageHandlers.get(messageType)!.add(handler);
  }

  /**
   * Remove a handler for a specific message type
   */
  off(messageType: string, handler: MessageHandler): void {
    this.messageHandlers.get(messageType)?.delete(handler);
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Handle push_ad event from local backend
   */
  private handlePushAd(payload: { bannerText?: string; popupHtml?: string; durationMs?: number }): void {
    const store = useAdStore.getState();
    const durationMs = payload.durationMs || 60000;
    const expiresAt = Date.now() + durationMs;

    if (payload.bannerText) {
      store.setBannerAd({
        id: `ad-banner-${Date.now()}`,
        text: payload.bannerText,
        expiresAt,
      });
      console.log('[LocalWS] 📢 Set banner ad:', payload.bannerText.substring(0, 50));
    }

    if (payload.popupHtml) {
      store.setPopupAd({
        id: `ad-popup-${Date.now()}`,
        htmlContent: payload.popupHtml,
        expiresAt,
      });
      console.log('[LocalWS] 📢 Set popup ad');
    }
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleMessage(data: string): void {
    try {
      const message = JSON.parse(data);
      const messageType = message.type;
      
      // Filter out routine/noisy events from logging
      // IMPORTANT: 'pong' and 'ping' are WebSocket heartbeat events - always silent
      const routineEvents = ['skill_editor_log', 'push_account_info', 'update_skill_run_stat', 'subscribed', 'pong', 'ping'];
      const shouldLog = !routineEvents.includes(messageType);
      
      if (shouldLog) {
        console.log('[LocalWS] 📥 Received message:', {
          type: messageType,
          sessionId: message.sessionId,
          messageId: message.messageId,
          chunkIndex: message.chunkIndex,
          hasChunk: !!message.chunk,
          chunkLength: message.chunk?.length,
          timestamp: new Date().toISOString()
        });
      }
      
      // Dispatch to registered handlers
      const handlers = this.messageHandlers.get(messageType);
      if (handlers) {
        handlers.forEach(handler => {
          try {
            handler(message);
          } catch (error) {
            console.error('[LocalWS] Handler error:', error);
          }
        });
      }
      
      // Also emit via eventBus for global listeners
      eventBus.emit(`localws:${messageType}`, message);
      
      // Map to IPC-style events for compatibility with existing handlers
      if (shouldLog) {
        console.log('[LocalWS] 🔄 Mapping to IPC events:', messageType);
      }
      this.mapToIpcEvents(message, shouldLog);
      
    } catch (error) {
      console.error('[LocalWS] Failed to parse message:', error, data);
    }
  }

  /**
   * Map WebSocket messages to unified event handler
   * Now uses centralized event processing instead of duplicate switch-case logic
   */
  private mapToIpcEvents(message: any, shouldLog = true): void {
    const { type, sessionId } = message;
    
    // Use same event types as AppSync subscriptions for compatibility
    // AppSync uses eventType field, local WS uses type field - handle both
    const eventType = message.eventType || type;
    const eventPayload = message.payload || {};
    
    // Merge top-level fields into payload for backward compatibility
    // Exclude structural fields that are not part of the payload
    const { type: _type, eventType: _eventType, sessionId: _sessionId, payload: _payload, ...topLevelFields } = message;
    const mergedPayload = {
      ...topLevelFields,
      ...eventPayload,
      ...(message.messageId && { messageId: message.messageId }),
      ...(message.chunk && { chunk: message.chunk }),
      ...(message.chunkIndex !== undefined && { chunkIndex: message.chunkIndex }),
      ...(message.fullContent && { fullContent: message.fullContent }),
    };
    
    if (shouldLog) {
      console.log(`[LocalWS] Processing event: ${eventType}`, { sessionId });
    }
    
    // Handle WebSocket heartbeat ping/pong - consume silently without logging
    if (eventType === 'pong' || eventType === 'ping') {
      return;
    }
    
    // Handle special cases that don't go through unified handler
    if (eventType === 'push_ad') {
      console.log('[LocalWS] 📢 Handling push_ad directly');
      this.handlePushAd(mergedPayload);
      return;
    }
    
    if (eventType === 'update_org_agents') {
      console.log('[LocalWS] 🏢 Emitting org-agents-update');
      eventBus.emit('org-agents-update', {
        timestamp: Date.now(),
        source: 'local_websocket',
        data: mergedPayload
      });
      return;
    }
    
    // Use unified event handler for all other events
    const standardizedEvent = createStandardizedEvent(
      eventType,
      mergedPayload,
      'local-ws',
      sessionId
    );
    
    unifiedEventHandler.handle(standardizedEvent);
  }

  /**
   * Start keepalive ping to prevent idle WebSocket disconnections
   */
  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30_000);
  }

  /**
   * Stop keepalive ping
   */
  private stopPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  /**
   * Schedule a reconnection attempt with exponential backoff.
   *
   * The interval grows: 3s → 6s → 12s → capped at 30s.  This dramatically
   * reduces the console-spam footprint when the backend is unreachable
   * for a long time (e.g. user quit `python3 main.py` while leaving the
   * Vite dev server running).  See terminals/7.txt for the original
   * pre-fix behavior (every 3s for 60+ seconds).
   */
  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    if (this.userInitiatedDisconnect) return;

    this.reconnectAttempts++;
    const baseInterval = this.options.reconnectInterval;
    // Exponential backoff: 3s, 6s, 12s, 24s, 30s (cap)
    const backoff = Math.min(
      baseInterval * Math.pow(2, this.reconnectAttempts - 1),
      30_000,
    );
    console.log(
      `[LocalWS] Scheduling reconnect attempt ${this.reconnectAttempts}/${this.options.maxReconnectAttempts} in ${(backoff / 1000).toFixed(1)}s`,
    );

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, backoff);
  }

  /**
   * Slow keepalive reconnect (60s) used after the fast-retry window
   * (``maxReconnectAttempts``) has been exhausted.  Keeps the client
   * ready to silently recover if the user restarts the backend (e.g.
   * `python3 main.py` again) without producing 1-retry-per-second noise.
   * Logged at debug level only so the user isn't bombarded after a
   * normal backend exit.
   */
  private scheduleKeepaliveReconnect(): void {
    if (this.reconnectTimer) return;
    if (this.userInitiatedDisconnect) return;

    console.debug(
      '[LocalWS] Fast retries exhausted — falling back to 60s keepalive reconnect',
    );
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      // Force-reset the attempt counter so a single successful connect
      // returns us to the "fast retry" cadence for the next outage.
      this.reconnectAttempts = 0;
      this.connect();
    }, 60_000);
  }
}

// Export singleton instance
export const localWebSocketClient = LocalWebSocketClient.getInstance();

// Auto-connect when module loads if conditions are met
if (typeof window !== 'undefined') {
  // Delay connection to allow settings to load
  setTimeout(async () => {
    if (localWebSocketClient.shouldUseLocalWebSocket()) {
      // Initialize WebSocket event listeners first
      const { initWebSocketEventListeners } = await import('./wsEventListeners');
      initWebSocketEventListeners();
      
      localWebSocketClient.connect().then(connected => {
        if (connected) {
          console.log('[LocalWS] Auto-connected to local WebSocket server');
        }
      });
    }
  }, 2000);
}

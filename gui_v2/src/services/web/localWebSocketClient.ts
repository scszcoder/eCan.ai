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
          console.error('[LocalWS] WebSocket error:', error);
          this.isConnecting = false;
        };

        this.ws.onclose = (event) => {
          console.log('[LocalWS] Connection closed:', event.code, event.reason);
          this.isConnecting = false;
          this.ws = null;
          this.stopPing();
          
          if (this.options.autoReconnect && this.reconnectAttempts < this.options.maxReconnectAttempts) {
            this.scheduleReconnect();
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
   */
  disconnect(): void {
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
    console.log('[LocalWS] Disconnected');
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
   * Schedule a reconnection attempt
   */
  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    
    this.reconnectAttempts++;
    console.log(`[LocalWS] Scheduling reconnect attempt ${this.reconnectAttempts}/${this.options.maxReconnectAttempts}`);
    
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.options.reconnectInterval);
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

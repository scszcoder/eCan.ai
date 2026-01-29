/**
 * Local WebSocket Client for Skill Editor Streaming
 * 
 * Connects to the local Python backend WebSocket server for receiving
 * streaming events (chat chunks, canvas commands, etc.) when running
 * in desktop mode with VITE_IPC_MODE OFF.
 */

import { getSettings } from '../../stores/settingsStore';
import { detectPlatform } from '../../config/platform';
import { eventBus } from '../../utils/eventBus';
import { useAdStore } from '../../stores/adStore';

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
   */
  shouldUseLocalWebSocket(): boolean {
    const platform = detectPlatform();
    if (platform !== 'desktop') return false;
    
    const env = getEnv();
    const ipcModeOn = isTruthyEnvValue(env.VITE_IPC_MODE);
    return !ipcModeOn;
  }

  /**
   * Get the WebSocket URL for the local server
   */
  private getWebSocketUrl(): string {
    try {
      if (typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/skill-editor`;
      }
    } catch {}
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
      
      // Detailed logging for observability
      console.log('[LocalWS] 📥 Received message:', {
        type: messageType,
        sessionId: message.sessionId,
        messageId: message.messageId,
        chunkIndex: message.chunkIndex,
        hasChunk: !!message.chunk,
        chunkLength: message.chunk?.length,
        timestamp: new Date().toISOString()
      });
      
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
      console.log('[LocalWS] 🔄 Mapping to IPC events:', messageType);
      this.mapToIpcEvents(message);
      
    } catch (error) {
      console.error('[LocalWS] Failed to parse message:', error, data);
    }
  }

  /**
   * Map WebSocket messages to IPC-style events for compatibility
   */
  private mapToIpcEvents(message: any): void {
    const { type, sessionId, messageId, chunk, chunkIndex, fullContent, commandType, payload } = message;
    
    // Use same event types as AppSync subscriptions for compatibility
    // AppSync uses eventType field, local WS uses type field - handle both
    const eventType = message.eventType || type;
    const eventPayload = message.payload || {};
    
    switch (eventType) {
      case 'skill_editor.chat.stream_chunk':
        const chunkData = eventPayload.chunk || chunk;
        const chunkIdx = eventPayload.chunkIndex ?? chunkIndex;
        console.log('[LocalWS] 📝 Emitting stream chunk:', { sessionId, chunkIndex: chunkIdx, chunkLength: chunkData?.length });
        // Emit in same format as AppSync subscription handler
        eventBus.emit('skill_editor:chat:stream_chunk', {
          sessionId,
          messageId: messageId || eventPayload.messageId,
          chunk: chunkData,
          chunkIndex: chunkIdx
        });
        break;
        
      case 'skill_editor.chat.stream_end':
        const fullMsg = eventPayload.fullContent || fullContent;
        console.log('[LocalWS] ✅ Emitting stream end:', { sessionId, contentLength: fullMsg?.length });
        // Emit in same format as AppSync subscription handler
        eventBus.emit('skill_editor:chat:stream_end', {
          sessionId,
          messageId: messageId || eventPayload.messageId,
          fullContent: fullMsg
        });
        break;
        
      case 'skill_editor.chat.error':
        console.log('[LocalWS] ❌ Emitting stream error:', { sessionId });
        eventBus.emit('skill_editor:chat:error', {
          sessionId,
          ...eventPayload
        });
        break;
        
      case 'skill_editor.event':
        console.log('[LocalWS] 🎨 Emitting skill editor event:', { sessionId, commandType: eventPayload.commandType, type: eventPayload.type, hasFlowgram: !!eventPayload.flowgram });
        console.log('[LocalWS] 🎨 Full eventPayload:', JSON.stringify(eventPayload).substring(0, 500));
        eventBus.emit('skill_editor:event', {
          sessionId,
          ...eventPayload
        });
        break;
      
      // ==================== Data Update Events ====================
      case 'update_agents':
        console.log('[LocalWS] 👥 Emitting update_agents');
        eventBus.emit('ws:update_agents', eventPayload);
        break;
        
      case 'update_skills':
        console.log('[LocalWS] 🛠️ Emitting update_skills');
        eventBus.emit('ws:update_skills', eventPayload);
        break;
        
      case 'update_tasks':
        console.log('[LocalWS] 📋 Emitting update_tasks');
        eventBus.emit('ws:update_tasks', eventPayload);
        break;
        
      case 'update_tools':
        console.log('[LocalWS] 🔧 Emitting update_tools');
        eventBus.emit('ws:update_tools', eventPayload);
        break;
        
      case 'update_settings':
        console.log('[LocalWS] ⚙️ Emitting update_settings');
        eventBus.emit('ws:update_settings', eventPayload);
        break;
        
      case 'update_vehicles':
        console.log('[LocalWS] 🚗 Emitting update_vehicles');
        eventBus.emit('ws:update_vehicles', eventPayload);
        break;
        
      case 'update_knowledge':
        console.log('[LocalWS] 📚 Emitting update_knowledge');
        eventBus.emit('ws:update_knowledge', eventPayload);
        break;
        
      case 'update_chats':
        console.log('[LocalWS] 💬 Emitting update_chats');
        eventBus.emit('ws:update_chats', eventPayload);
        break;
        
      case 'update_all':
        console.log('[LocalWS] 🔄 Emitting update_all');
        eventBus.emit('ws:update_all', eventPayload);
        break;
      
      // ==================== Chat Events ====================
      case 'push_chat_message':
        console.log('[LocalWS] 💬 Emitting push_chat_message');
        eventBus.emit('ws:push_chat_message', eventPayload);
        break;
        
      case 'push_chat_notification':
        console.log('[LocalWS] 🔔 Emitting push_chat_notification');
        eventBus.emit('ws:push_chat_notification', eventPayload);
        break;
      
      // ==================== Ad Banner Events ====================
      case 'push_ad':
        console.log('[LocalWS] 📢 Emitting push_ad:', { bannerText: eventPayload.bannerText?.substring(0, 50), hasPopup: !!eventPayload.popupHtml });
        // Directly update ad store for local desktop mode
        this.handlePushAd(eventPayload);
        break;
      
      // ==================== Skill Run Events ====================
      case 'update_skill_run_stat':
        console.log('[LocalWS] 📊 Emitting update_skill_run_stat:', { agentTaskId: eventPayload.agentTaskId, currentNode: eventPayload.currentNode });
        eventBus.emit('ws:update_skill_run_stat', eventPayload);
        break;
        
      case 'update_tasks_stat':
        console.log('[LocalWS] 📈 Emitting update_tasks_stat');
        eventBus.emit('ws:update_tasks_stat', eventPayload);
        break;
      
      // ==================== LightRAG Events ====================
      case 'lightrag.queryStream.chunk':
        console.log('[LocalWS] 💡 Emitting lightrag chunk');
        eventBus.emit('ws:lightrag:chunk', eventPayload);
        break;
        
      case 'lightrag.queryStream.done':
        console.log('[LocalWS] ✅ Emitting lightrag done');
        eventBus.emit('ws:lightrag:done', eventPayload);
        break;
        
      case 'lightrag.queryStream.error':
        console.log('[LocalWS] ❌ Emitting lightrag error');
        eventBus.emit('ws:lightrag:error', eventPayload);
        break;
      
      // ==================== UI Events ====================
      case 'refresh_dashboard':
        console.log('[LocalWS] 🔄 Emitting refresh_dashboard');
        eventBus.emit('ws:refresh_dashboard', eventPayload);
        break;
        
      case 'update_screens':
        console.log('[LocalWS] 🖥️ Emitting update_screens');
        eventBus.emit('ws:update_screens', eventPayload);
        break;
        
      default:
        console.log('[LocalWS] ⚠️ Unknown event type:', eventType);
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

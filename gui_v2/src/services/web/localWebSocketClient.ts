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
    const settings = getSettings();
    const port = settings?.local_server_port || '4668';
    return `ws://localhost:${port}/ws/skill-editor`;
  }

  /**
   * Connect to the local WebSocket server
   */
  async connect(): Promise<boolean> {
    if (!this.shouldUseLocalWebSocket()) {
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
  setTimeout(() => {
    if (localWebSocketClient.shouldUseLocalWebSocket()) {
      localWebSocketClient.connect().then(connected => {
        if (connected) {
          console.log('[LocalWS] Auto-connected to local WebSocket server');
        }
      });
    }
  }, 2000);
}

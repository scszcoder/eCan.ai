/**
 * WebSocket IPC Client
 * 
 * Provides WebSocket-based transport for web deployment mode.
 * This allows the React frontend to communicate with the Python backend
 * over a network connection instead of Qt WebChannel.
 * 
 * Usage:
 *   import { IPCWSClient } from './ipcWSClient';
 *   
 *   const client = IPCWSClient.getInstance();
 *   await client.connect('ws://localhost:8765');
 *   const response = await client.invoke('get_all', { username: 'test' });
 */

import {
    IPCRequest,
    IPCResponse,
    IPCRequestHandler,
    createRequest,
    createErrorResponse,
    generateRequestId,
    isIPCResponse
} from './types';
import { getHandlers } from './handlers';
import { logger } from '../../utils/logger';

// Connection state enum
export enum WSConnectionState {
    DISCONNECTED = 'disconnected',
    CONNECTING = 'connecting',
    CONNECTED = 'connected',
    RECONNECTING = 'reconnecting',
    FAILED = 'failed'
}

// WebSocket client configuration
export interface WSClientConfig {
    url: string;
    reconnectAttempts?: number;
    reconnectDelay?: number;
    reconnectBackoff?: number;
    pingInterval?: number;
    requestTimeout?: number;
}

const DEFAULT_CONFIG: Partial<WSClientConfig> = {
    reconnectAttempts: 5,
    reconnectDelay: 1000,
    reconnectBackoff: 1.5,
    pingInterval: 30000,
    requestTimeout: 60000
};

/**
 * WebSocket IPC Client
 * Implements the same interface as IPCWCClient but uses WebSocket transport
 */
export class IPCWSClient {
    private static instance: IPCWSClient;
    
    private ws: WebSocket | null = null;
    private config: WSClientConfig | null = null;
    private connectionState: WSConnectionState = WSConnectionState.DISCONNECTED;
    private reconnectCount: number = 0;
    private pingIntervalId: number | null = null;
    
    // Session management
    private sessionId: string | null = null;
    
    // Request handling
    private pendingRequests: Map<string, {
        resolve: (value: IPCResponse) => void;
        reject: (reason?: any) => void;
        timeout: number;
    }> = new Map();
    private requestHandlers: Record<string, IPCRequestHandler>;
    
    // Event callbacks
    private onConnectionChange?: (state: WSConnectionState) => void;
    private onSessionChange?: (sessionId: string | null) => void;
    
    // Limits
    private readonly MAX_PENDING_REQUESTS = 1000;
    
    private constructor() {
        this.requestHandlers = getHandlers();
    }
    
    /**
     * Get singleton instance
     */
    public static getInstance(): IPCWSClient {
        if (!IPCWSClient.instance) {
            IPCWSClient.instance = new IPCWSClient();
        }
        return IPCWSClient.instance;
    }
    
    /**
     * Connect to WebSocket server
     */
    public async connect(url: string, config?: Partial<WSClientConfig>): Promise<void> {
        if (this.connectionState === WSConnectionState.CONNECTED) {
            logger.warn('[IPCWSClient] Already connected');
            return;
        }
        
        this.config = { url, ...DEFAULT_CONFIG, ...config };
        this.connectionState = WSConnectionState.CONNECTING;
        this.notifyConnectionChange();
        
        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(url);
                
                this.ws.onopen = () => {
                    logger.info('[IPCWSClient] Connected to', url);
                    this.connectionState = WSConnectionState.CONNECTED;
                    this.reconnectCount = 0;
                    this.startPingInterval();
                    this.notifyConnectionChange();
                    resolve();
                };
                
                this.ws.onclose = (event) => {
                    logger.info('[IPCWSClient] Connection closed:', event.code, event.reason);
                    this.handleDisconnect();
                };
                
                this.ws.onerror = (error) => {
                    logger.error('[IPCWSClient] WebSocket error:', error);
                    if (this.connectionState === WSConnectionState.CONNECTING) {
                        reject(new Error('Failed to connect to WebSocket server'));
                    }
                };
                
                this.ws.onmessage = (event) => {
                    this.handleMessage(event.data);
                };
                
            } catch (error) {
                this.connectionState = WSConnectionState.FAILED;
                this.notifyConnectionChange();
                reject(error);
            }
        });
    }
    
    /**
     * Disconnect from server
     */
    public disconnect(): void {
        this.stopPingInterval();
        
        if (this.ws) {
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }
        
        this.connectionState = WSConnectionState.DISCONNECTED;
        this.sessionId = null;
        this.notifyConnectionChange();
        
        // Reject all pending requests
        this.pendingRequests.forEach((pending, id) => {
            pending.reject(createErrorResponse(id, 'DISCONNECTED', 'WebSocket disconnected'));
        });
        this.pendingRequests.clear();
    }
    
    /**
     * Check if connected
     */
    public isConnected(): boolean {
        return this.connectionState === WSConnectionState.CONNECTED && this.ws?.readyState === WebSocket.OPEN;
    }
    
    /**
     * Get current connection state
     */
    public getConnectionState(): WSConnectionState {
        return this.connectionState;
    }
    
    /**
     * Get current session ID
     */
    public getSessionId(): string | null {
        return this.sessionId;
    }
    
    /**
     * Set session ID (called after login)
     */
    public setSessionId(sessionId: string): void {
        this.sessionId = sessionId;
        logger.info('[IPCWSClient] Session ID set:', sessionId);
        this.onSessionChange?.(sessionId);
    }
    
    /**
     * Clear session (called on logout)
     */
    public clearSession(): void {
        this.sessionId = null;
        this.onSessionChange?.(null);
    }
    
    /**
     * Set connection state change callback
     */
    public setOnConnectionChange(callback: (state: WSConnectionState) => void): void {
        this.onConnectionChange = callback;
    }
    
    /**
     * Set session change callback
     */
    public setOnSessionChange(callback: (sessionId: string | null) => void): void {
        this.onSessionChange = callback;
    }
    
    /**
     * Send request to backend (main API)
     */
    public async invoke(method: string, params?: unknown, timeout?: number): Promise<IPCResponse> {
        if (!this.isConnected()) {
            throw createErrorResponse(
                generateRequestId(),
                'NOT_CONNECTED',
                'WebSocket not connected. Call connect() first.'
            );
        }
        
        if (this.pendingRequests.size >= this.MAX_PENDING_REQUESTS) {
            throw createErrorResponse(
                generateRequestId(),
                'QUEUE_FULL',
                `Too many pending requests (${this.MAX_PENDING_REQUESTS})`
            );
        }
        
        const requestTimeout = timeout ?? this.config?.requestTimeout ?? DEFAULT_CONFIG.requestTimeout!;
        
        // Add session_id to params if available
        const paramsWithSession = this.addSessionToParams(params);
        
        const request = createRequest(method, paramsWithSession);
        
        // Add session_id to meta as well
        if (this.sessionId) {
            request.meta = { ...request.meta, session_id: this.sessionId };
        }
        
        return new Promise((resolve, reject) => {
            // Set up timeout
            const timeoutId = window.setTimeout(() => {
                this.pendingRequests.delete(request.id);
                reject(createErrorResponse(
                    request.id,
                    'TIMEOUT_ERROR',
                    `Request timed out after ${requestTimeout / 1000} seconds`
                ));
            }, requestTimeout);
            
            // Store pending request
            this.pendingRequests.set(request.id, {
                resolve,
                reject,
                timeout: timeoutId
            });
            
            // Send request
            try {
                const message = JSON.stringify(request);
                logger.debug('[IPCWSClient] Sending:', method, request.id);
                this.ws!.send(message);
            } catch (error) {
                clearTimeout(timeoutId);
                this.pendingRequests.delete(request.id);
                reject(createErrorResponse(
                    request.id,
                    'SEND_ERROR',
                    error instanceof Error ? error.message : 'Failed to send request'
                ));
            }
        });
    }
    
    /**
     * Handle incoming WebSocket message
     */
    private handleMessage(data: string): void {
        try {
            const message = JSON.parse(data);
            
            // Check if this is a response to a pending request
            if (isIPCResponse(message) && this.pendingRequests.has(message.id)) {
                const pending = this.pendingRequests.get(message.id)!;
                clearTimeout(pending.timeout);
                this.pendingRequests.delete(message.id);
                
                logger.debug('[IPCWSClient] Response received:', message.id, message.status);
                pending.resolve(message as IPCResponse);
                return;
            }
            
            // Check if this is a request from the server
            if (message.type === 'request') {
                this.handleServerRequest(message as IPCRequest);
                return;
            }
            
            logger.warn('[IPCWSClient] Unhandled message:', message);
            
        } catch (error) {
            logger.error('[IPCWSClient] Failed to parse message:', error);
        }
    }
    
    /**
     * Handle request from server (push notifications, etc.)
     */
    private async handleServerRequest(request: IPCRequest): Promise<void> {
        const handler = this.requestHandlers[request.method];
        
        if (!handler) {
            logger.warn('[IPCWSClient] No handler for method:', request.method);
            this.sendResponse(request.id, {
                status: 'error',
                error: {
                    code: 'HANDLER_NOT_FOUND',
                    message: `No handler for method: ${request.method}`
                }
            });
            return;
        }
        
        try {
            const result = await handler(request);
            this.sendResponse(request.id, { status: 'success', result });
        } catch (error) {
            this.sendResponse(request.id, {
                status: 'error',
                error: {
                    code: 'HANDLER_ERROR',
                    message: error instanceof Error ? error.message : 'Handler error'
                }
            });
        }
    }
    
    /**
     * Send response to server
     */
    private sendResponse(requestId: string, data: { status: string; result?: unknown; error?: any }): void {
        if (!this.isConnected()) return;
        
        const response: IPCResponse = {
            id: requestId,
            type: 'response',
            status: data.status as 'success' | 'error',
            result: data.result,
            error: data.error,
            timestamp: Date.now()
        };
        
        try {
            this.ws!.send(JSON.stringify(response));
        } catch (error) {
            logger.error('[IPCWSClient] Failed to send response:', error);
        }
    }
    
    /**
     * Add session ID to params
     */
    private addSessionToParams(params: unknown): unknown {
        if (!this.sessionId) return params;
        
        if (params && typeof params === 'object' && !Array.isArray(params)) {
            return { ...params, session_id: this.sessionId };
        }
        
        return params;
    }
    
    /**
     * Handle disconnect and attempt reconnection
     */
    private handleDisconnect(): void {
        this.stopPingInterval();
        
        const wasConnected = this.connectionState === WSConnectionState.CONNECTED;
        this.connectionState = WSConnectionState.DISCONNECTED;
        
        // Reject all pending requests
        this.pendingRequests.forEach((pending, id) => {
            clearTimeout(pending.timeout);
            pending.reject(createErrorResponse(id, 'DISCONNECTED', 'WebSocket disconnected'));
        });
        this.pendingRequests.clear();
        
        // Attempt reconnection if was connected
        if (wasConnected && this.config) {
            this.attemptReconnect();
        } else {
            this.notifyConnectionChange();
        }
    }
    
    /**
     * Attempt to reconnect
     */
    private async attemptReconnect(): Promise<void> {
        if (!this.config) return;
        
        const maxAttempts = this.config.reconnectAttempts ?? DEFAULT_CONFIG.reconnectAttempts!;
        
        if (this.reconnectCount >= maxAttempts) {
            logger.error('[IPCWSClient] Max reconnection attempts reached');
            this.connectionState = WSConnectionState.FAILED;
            this.notifyConnectionChange();
            return;
        }
        
        this.connectionState = WSConnectionState.RECONNECTING;
        this.notifyConnectionChange();
        
        const delay = (this.config.reconnectDelay ?? DEFAULT_CONFIG.reconnectDelay!) *
            Math.pow(this.config.reconnectBackoff ?? DEFAULT_CONFIG.reconnectBackoff!, this.reconnectCount);
        
        logger.info(`[IPCWSClient] Reconnecting in ${delay}ms (attempt ${this.reconnectCount + 1}/${maxAttempts})`);
        
        await new Promise(resolve => setTimeout(resolve, delay));
        this.reconnectCount++;
        
        try {
            await this.connect(this.config.url, this.config);
        } catch (error) {
            logger.error('[IPCWSClient] Reconnection failed:', error);
            this.attemptReconnect();
        }
    }
    
    /**
     * Start ping interval to keep connection alive
     */
    private startPingInterval(): void {
        if (this.pingIntervalId) return;
        
        const interval = this.config?.pingInterval ?? DEFAULT_CONFIG.pingInterval!;
        
        this.pingIntervalId = window.setInterval(() => {
            if (this.isConnected()) {
                // Send a ping request
                this.invoke('ping', { timestamp: Date.now() }).catch(() => {
                    // Ping failed, connection might be dead
                    logger.warn('[IPCWSClient] Ping failed');
                });
            }
        }, interval);
    }
    
    /**
     * Stop ping interval
     */
    private stopPingInterval(): void {
        if (this.pingIntervalId) {
            clearInterval(this.pingIntervalId);
            this.pingIntervalId = null;
        }
    }
    
    /**
     * Notify connection state change
     */
    private notifyConnectionChange(): void {
        this.onConnectionChange?.(this.connectionState);
    }
}

// Export singleton getter for convenience
export const getWSClient = () => IPCWSClient.getInstance();

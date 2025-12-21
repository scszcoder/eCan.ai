/**
 * Unified IPC Client
 * 
 * Provides a unified interface for IPC communication that works in both:
 * - Desktop mode: Uses Qt WebChannel (IPCWCClient)
 * - Web mode: Uses WebSocket (IPCWSClient)
 * 
 * The client automatically detects the deployment mode and uses the appropriate transport.
 * 
 * Usage:
 *   import { ipcClient } from './ipcClient';
 *   
 *   // Initialize (call once at app startup)
 *   await ipcClient.initialize();
 *   
 *   // Use the same API regardless of mode
 *   const response = await ipcClient.invoke('get_all', { username: 'test' });
 */

import { IPCResponse } from './types';
import { IPCWCClient, IPCRequestOptions } from './ipcWCClient';
import { IPCWSClient, WSConnectionState, WSClientConfig } from './ipcWSClient';
import { logger } from '../../utils/logger';

// Deployment mode
export type DeploymentMode = 'desktop' | 'web' | 'auto';

// Client configuration
export interface IPCClientConfig {
    mode?: DeploymentMode;
    wsUrl?: string;
    wsConfig?: Partial<WSClientConfig>;
}

// Default WebSocket URL (can be overridden by environment variable)
// @ts-ignore - import.meta.env is available in Vite
const DEFAULT_WS_URL = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_WS_URL) || 'ws://localhost:8765';

/**
 * Detect deployment mode based on environment
 */
function detectDeploymentMode(): 'desktop' | 'web' {
    // Check if Qt WebChannel is available (desktop mode)
    if (typeof window !== 'undefined' && (window as any).ipc) {
        logger.info('[IPCClient] Detected desktop mode (window.ipc present)');
        return 'desktop';
    }
    
    // Check for webchannel-ready event listener (Qt might inject later)
    // Give it a short timeout to see if we're in desktop mode
    // For now, if no window.ipc, assume web mode
    logger.info('[IPCClient] Detected web mode (no window.ipc)');
    return 'web';
}

/**
 * Unified IPC Client
 */
class UnifiedIPCClient {
    private mode: 'desktop' | 'web' | null = null;
    private wcClient: IPCWCClient | null = null;
    private wsClient: IPCWSClient | null = null;
    private initialized: boolean = false;
    private initPromise: Promise<void> | null = null;
    
    // Session management
    private sessionId: string | null = null;
    
    // Callbacks
    private onModeDetected?: (mode: 'desktop' | 'web') => void;
    private onConnectionChange?: (connected: boolean) => void;
    
    /**
     * Initialize the IPC client
     * Call this once at app startup
     */
    public async initialize(config?: IPCClientConfig): Promise<void> {
        if (this.initialized) {
            logger.warn('[IPCClient] Already initialized');
            return;
        }
        
        if (this.initPromise) {
            return this.initPromise;
        }
        
        this.initPromise = this._initialize(config);
        return this.initPromise;
    }
    
    private async _initialize(config?: IPCClientConfig): Promise<void> {
        const requestedMode = config?.mode ?? 'auto';
        
        if (requestedMode === 'auto') {
            // Try desktop mode first, fall back to web mode
            this.mode = await this.detectModeWithTimeout();
        } else {
            this.mode = requestedMode;
        }
        
        logger.info('[IPCClient] Initializing in', this.mode, 'mode');
        this.onModeDetected?.(this.mode);
        
        if (this.mode === 'desktop') {
            this.wcClient = IPCWCClient.getInstance();
            // WCClient initializes itself via constructor
            this.initialized = true;
        } else {
            this.wsClient = IPCWSClient.getInstance();
            
            // Set up connection state callback
            this.wsClient.setOnConnectionChange((state) => {
                const connected = state === WSConnectionState.CONNECTED;
                this.onConnectionChange?.(connected);
            });
            
            // Connect to WebSocket server
            const wsUrl = config?.wsUrl ?? DEFAULT_WS_URL;
            try {
                await this.wsClient.connect(wsUrl, config?.wsConfig);
                this.initialized = true;
                
                // Restore session ID from storage if available (for page refresh)
                this.restoreSessionFromStorage();
            } catch (error) {
                logger.error('[IPCClient] Failed to connect to WebSocket server:', error);
                throw error;
            }
        }
    }
    
    /**
     * Detect mode with timeout for Qt WebChannel injection
     */
    private async detectModeWithTimeout(): Promise<'desktop' | 'web'> {
        // If window.ipc already exists, we're in desktop mode
        if (typeof window !== 'undefined' && (window as any).ipc) {
            return 'desktop';
        }
        
        // Wait a short time for Qt to inject window.ipc
        return new Promise((resolve) => {
            const timeout = 2000; // 2 seconds
            let resolved = false;
            
            const handleWebChannelReady = () => {
                if (!resolved) {
                    resolved = true;
                    window.removeEventListener('webchannel-ready', handleWebChannelReady);
                    resolve('desktop');
                }
            };
            
            window.addEventListener('webchannel-ready', handleWebChannelReady);
            
            // Check again after a short delay
            setTimeout(() => {
                if (!resolved) {
                    if ((window as any).ipc) {
                        resolved = true;
                        window.removeEventListener('webchannel-ready', handleWebChannelReady);
                        resolve('desktop');
                    }
                }
            }, 500);
            
            // Final timeout - assume web mode
            setTimeout(() => {
                if (!resolved) {
                    resolved = true;
                    window.removeEventListener('webchannel-ready', handleWebChannelReady);
                    resolve('web');
                }
            }, timeout);
        });
    }
    
    /**
     * Check if initialized
     */
    public isInitialized(): boolean {
        return this.initialized;
    }
    
    /**
     * Get current deployment mode
     */
    public getMode(): 'desktop' | 'web' | null {
        return this.mode;
    }
    
    /**
     * Check if connected (always true for desktop, checks WebSocket for web)
     */
    public isConnected(): boolean {
        if (this.mode === 'desktop') {
            return this.initialized;
        }
        return this.wsClient?.isConnected() ?? false;
    }
    
    /**
     * Send request to backend
     */
    public async invoke(method: string, params?: unknown, options?: IPCRequestOptions): Promise<IPCResponse> {
        if (!this.initialized) {
            // Try to initialize with defaults
            await this.initialize();
        }
        
        if (this.mode === 'desktop' && this.wcClient) {
            return this.wcClient.invoke(method, params, options) as Promise<IPCResponse>;
        } else if (this.mode === 'web' && this.wsClient) {
            return this.wsClient.invoke(method, params, options?.timeout);
        }
        
        throw new Error('IPC client not initialized');
    }
    
    /**
     * Set session ID (for web mode)
     */
    public setSessionId(sessionId: string): void {
        this.sessionId = sessionId;
        if (this.wsClient) {
            this.wsClient.setSessionId(sessionId);
        }
    }
    
    /**
     * Get session ID
     */
    public getSessionId(): string | null {
        if (this.wsClient) {
            return this.wsClient.getSessionId();
        }
        return this.sessionId;
    }
    
    /**
     * Clear session (on logout)
     */
    public clearSession(): void {
        this.sessionId = null;
        if (this.wsClient) {
            this.wsClient.clearSession();
        }
    }
    
    /**
     * Restore session ID from storage (for page refresh in web mode)
     */
    private restoreSessionFromStorage(): void {
        try {
            // Dynamic import to avoid circular dependency
            const sessionId = localStorage.getItem('session_id');
            if (sessionId && this.wsClient) {
                this.wsClient.setSessionId(sessionId);
                this.sessionId = sessionId;
                logger.info('[IPCClient] Restored session ID from storage:', sessionId);
            }
        } catch (error) {
            logger.debug('[IPCClient] Could not restore session from storage:', error);
        }
    }
    
    /**
     * Set mode detection callback
     */
    public setOnModeDetected(callback: (mode: 'desktop' | 'web') => void): void {
        this.onModeDetected = callback;
    }
    
    /**
     * Set connection change callback
     */
    public setOnConnectionChange(callback: (connected: boolean) => void): void {
        this.onConnectionChange = callback;
        
        // Also set on WS client if available
        if (this.wsClient) {
            this.wsClient.setOnConnectionChange((state) => {
                callback(state === WSConnectionState.CONNECTED);
            });
        }
    }
    
    /**
     * Disconnect (web mode only)
     */
    public disconnect(): void {
        if (this.wsClient) {
            this.wsClient.disconnect();
        }
        this.initialized = false;
    }
    
    /**
     * Reconnect (web mode only)
     */
    public async reconnect(): Promise<void> {
        if (this.mode === 'web' && this.wsClient) {
            const wsUrl = DEFAULT_WS_URL;
            await this.wsClient.connect(wsUrl);
        }
    }
}

// Export singleton instance
export const ipcClient = new UnifiedIPCClient();

// Export for direct access if needed
export { UnifiedIPCClient };

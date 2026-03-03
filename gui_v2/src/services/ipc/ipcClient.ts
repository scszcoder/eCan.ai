/**
 * Unified IPC Client (Compatibility Layer)
 * 
 * WebChannel and WebSocket IPC removed.
 * Frontend now uses HTTP GraphQL for all requests (via apiRouter).
 * WebSocket is only used for receiving backend push events (handled in localWebSocketClient).
 * 
 * This file provides a compatibility layer for existing code.
 * New code should use apiRouter.execute() directly from @/services/api/api-router.
 */

import { logger } from '../../utils/logger';

/**
 * Simple IPC Client - compatibility wrapper
 * All methods now throw errors directing to use apiRouter instead
 */
class UnifiedIPCClient {
    private initialized: boolean = false;
    
    /**
     * Initialize - no-op for compatibility
     */
    public async initialize(): Promise<void> {
        if (this.initialized) {
            return;
        }
        this.initialized = true;
        logger.info('[IPCClient] Initialized (compatibility mode - use apiRouter for requests)');
    }
    
    /**
     * Invoke method - throws error directing to apiRouter
     */
    public async invoke(method: string, params?: unknown): Promise<any> {
        throw new Error(
            `[IPCClient] invoke() is deprecated. Use apiRouter.execute() instead.\n` +
            `Example: import { apiRouter } from '@/services/api/api-router';\n` +
            `Then: await apiRouter.execute({ method: '${method}' }, params);`
        );
    }
    
    /**
     * Check if connected - always returns false (no WebSocket in this layer)
     */
    public isConnected(): boolean {
        return false;
    }
    
    /**
     * Clear queue - no-op
     */
    public clearQueue(): void {
        // No-op
    }
    
    /**
     * Reconnect - no-op
     */
    public async reconnect(): Promise<void> {
        logger.warn('[IPCClient] reconnect() called but WebSocket is handled separately');
    }
    
    /**
     * Set callbacks - no-op
     */
    public setOnModeDetected(callback: (mode: 'desktop' | 'web') => void): void {
        // No-op
    }
    
    public setOnConnectionChange(callback: (connected: boolean) => void): void {
        // No-op
    }
}

// Export singleton instance
export const ipcClient = new UnifiedIPCClient();

// Export types for compatibility
export type DeploymentMode = 'desktop' | 'web' | 'auto';
export interface IPCClientConfig {
    mode?: DeploymentMode;
}
export { UnifiedIPCClient };

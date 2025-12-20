/**
 * Context-related IPC handlers
 * Handles context panel data from backend
 */
import { IPCRequest } from './types';
import { useContextStore } from '../../stores/contextStore';
import { logger } from '@/utils/logger';
import type { ChatContext } from '@/pages/Chat/types/context';

/**
 * Handle send_all_contexts from backend
 * Backend pushes all contexts on init
 */
export async function handleSendAllContexts(request: IPCRequest): Promise<{ success: boolean }> {
  logger.info('Received send_all_contexts request:', request.params);
  
  try {
    const contexts = request.params as ChatContext[];
    
    if (Array.isArray(contexts)) {
      useContextStore.getState().setContexts(contexts);
      logger.info('[IPC] Updated contexts from backend:', contexts.length);
    }
    
    return { success: true };
  } catch (error) {
    logger.error('[IPC] Error handling send_all_contexts:', error);
    throw error;
  }
}

/**
 * Handle update_contexts from backend
 * Backend pushes new/updated context
 */
export async function handleUpdateContexts(request: IPCRequest): Promise<{ success: boolean }> {
  logger.info('Received update_contexts request:', request.params);
  
  try {
    const context = request.params as ChatContext;
    
    if (context && context.uid) {
      const store = useContextStore.getState();
      const existing = store.contexts.find(c => c.uid === context.uid);
      
      if (existing) {
        store.updateContext(context.uid, context);
        logger.info('[IPC] Updated existing context:', context.uid);
      } else {
        store.addContext(context);
        logger.info('[IPC] Added new context:', context.uid);
      }
    }
    
    return { success: true };
  } catch (error) {
    logger.error('[IPC] Error handling update_contexts:', error);
    throw error;
  }
}

/**
 * Register context handlers with the IPC system
 * Call this function to add context handlers to the handlers map
 */
export function registerContextHandlers(handlers: Record<string, any>) {
  handlers['send_all_contexts'] = handleSendAllContexts;
  handlers['update_contexts'] = handleUpdateContexts;
  logger.info('[IPC] Registered context handlers');
}

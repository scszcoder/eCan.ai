/**
 * Ollama Configuration Utilities
 * Common functions for saving Ollama configuration across LLM, Embedding, and Rerank
 */

import { message } from 'antd';
import { get_ipc_api } from '../../../services/ipc_api';

export interface SaveOllamaConfigParams {
  providerType: 'llm' | 'embedding' | 'rerank';
  host: string;
  apiKey?: string;
  onSuccess?: () => void;
  onError?: (error: string) => void;
}

/**
 * Save Ollama configuration (base_url and API key) to backend
 * 
 * @param params Configuration parameters
 * @returns Promise<boolean> - true if successful, false otherwise
 */
export async function saveOllamaConfig(params: SaveOllamaConfigParams): Promise<boolean> {
  const { providerType, host, apiKey, onSuccess, onError } = params;
  
  try {
    // 1. Prepare update parameters
    const updateParams: any = {
      name: 'ollama',
      base_url: host
    };
    
    // Only include API key if provided
    if (apiKey && apiKey.trim()) {
      updateParams.api_key = apiKey;
    }
    
    // 2. Determine the correct API endpoint
    const apiEndpoint = `update_${providerType}_provider`;
    
    // 3. Call backend API
    const response = await get_ipc_api().executeRequest(apiEndpoint, updateParams);
    
    // 4. Handle response
    if (response.success) {
      onSuccess?.();
      return true;
    } else {
      const errorMsg = response.error?.message || 'Failed to save Ollama configuration';
      onError?.(errorMsg);
      return false;
    }
  } catch (error: any) {
    const errorMsg = error.message || 'Failed to save Ollama configuration';
    onError?.(errorMsg);
    return false;
  }
}

/**
 * Save Ollama configuration with default UI feedback (message.success/error)
 * 
 * @param params Configuration parameters
 * @param successMessage Success message to display
 * @returns Promise<boolean> - true if successful, false otherwise
 */
export async function saveOllamaConfigWithFeedback(
  params: Omit<SaveOllamaConfigParams, 'onSuccess' | 'onError'>,
  successMessage: string = 'Ollama configuration saved successfully'
): Promise<boolean> {
  return saveOllamaConfig({
    ...params,
    onSuccess: () => message.success(successMessage),
    onError: (error) => message.error(error)
  });
}

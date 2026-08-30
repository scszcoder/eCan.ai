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
    const submittedApiKey = apiKey ?? '';
    let response;
    
    // Call the appropriate API method based on provider type
    if (providerType === 'llm') {
      response = await get_ipc_api().updateLLMProvider<{ message: string }>(
        'ollama',
        submittedApiKey,
        undefined, // azureEndpoint
        undefined, // awsAccessKeyId
        undefined, // awsSecretAccessKey
        host       // baseUrl
      );
    } else if (providerType === 'embedding') {
      response = await get_ipc_api().updateEmbeddingProvider<{ message: string }>(
        'ollama',
        submittedApiKey,
        undefined, // azureEndpoint
        host       // baseUrl
      );
    } else if (providerType === 'rerank') {
      response = await get_ipc_api().updateRerankProvider<{ message: string }>(
        'ollama',
        submittedApiKey,
        undefined, // azureEndpoint
        host       // baseUrl
      );
    } else {
      const errorMsg = `Unknown provider type: ${providerType}`;
      onError?.(errorMsg);
      return false;
    }
    
    // Handle response
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

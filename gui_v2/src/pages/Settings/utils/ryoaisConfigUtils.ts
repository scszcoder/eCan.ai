/**
 * RyoAIS configuration utilities
 * Handles saving RyoAIS host and API key configuration
 */

import { get_ipc_api } from '../../../services/ipc_api';

export interface SaveRyoAISConfigParams {
  providerType: 'llm' | 'embedding' | 'rerank';
  host: string;
  apiKey?: string;
  onSuccess?: () => void;
  onError?: (error: string) => void;
}

/**
 * Save RyoAIS configuration (host and optional API key)
 * Unified implementation with Ollama using api.ts methods
 * 
 * @param params - Configuration parameters
 */
export const saveRyoAISConfig = async (params: SaveRyoAISConfigParams): Promise<void> => {
  const { providerType, host, apiKey, onSuccess, onError } = params;

  try {
    // Validate host format
    if (!host || (!host.startsWith('http://') && !host.startsWith('https://'))) {
      onError?.('Invalid host URL. Must start with http:// or https://');
      return;
    }

    const dummyApiKey = apiKey && apiKey.trim() ? apiKey : 'ryoais';
    let response;
    
    // Call the appropriate API method based on provider type
    if (providerType === 'llm') {
      response = await get_ipc_api().updateLLMProvider<{ message: string }>(
        'ryoais',
        dummyApiKey,
        undefined, // azureEndpoint
        undefined, // awsAccessKeyId
        undefined, // awsSecretAccessKey
        host       // baseUrl
      );
    } else if (providerType === 'embedding') {
      response = await get_ipc_api().updateEmbeddingProvider<{ message: string }>(
        'ryoais',
        dummyApiKey,
        undefined, // azureEndpoint
        host       // baseUrl
      );
    } else if (providerType === 'rerank') {
      response = await get_ipc_api().updateRerankProvider<{ message: string }>(
        'ryoais',
        dummyApiKey,
        undefined, // azureEndpoint
        host       // baseUrl
      );
    } else {
      onError?.(`Unknown provider type: ${providerType}`);
      return;
    }

    if (response.success) {
      onSuccess?.();
    } else {
      onError?.(response.error?.message || 'Failed to save RyoAIS configuration');
    }
  } catch (error: any) {
    onError?.(error.message || 'Failed to save RyoAIS configuration');
  }
};

/**
 * Ollama provider validation utilities
 * Shared validation logic for LLM, Embedding, and Rerank management components
 */

import { TFunction } from 'i18next';

export interface OllamaProvider {
  name?: string;
  provider?: string;
  class_name?: string;
  base_url?: string | null;
  supported_models?: Array<{ name: string; [key: string]: any }>;
  [key: string]: any;
}

export interface OllamaValidationResult {
  valid: boolean;
  errorKey?: string;
  errorMessage?: string;
}

/**
 * Check if a provider is Ollama
 */
export const isOllamaProvider = (provider: OllamaProvider): boolean => {
  const name = (provider.name || '').toLowerCase();
  const providerId = (provider.provider || '').toLowerCase();
  const className = (provider.class_name || '').toLowerCase();
  
  return name.includes('ollama') || providerId.includes('ollama') || className.includes('ollama');
};

/**
 * Validate Ollama provider configuration before setting as default
 * 
 * @param provider - The provider object to validate
 * @param selectedModel - The currently selected model (if any)
 * @param t - i18n translation function
 * @returns Validation result with error message if invalid
 */
export const validateOllamaProvider = (
  provider: OllamaProvider,
  selectedModel: string | undefined,
  t: TFunction
): OllamaValidationResult => {
  // Only validate Ollama providers
  if (!isOllamaProvider(provider)) {
    return { valid: true };
  }

  // 1. Check if models are available
  const supportedModels = provider.supported_models || [];
  if (supportedModels.length === 0) {
    return {
      valid: false,
      errorKey: 'ollama_no_models',
      errorMessage: t('pages.settings.ollama_no_models')
    };
  }

  // 2. Check if a model is selected
  if (!selectedModel) {
    return {
      valid: false,
      errorKey: 'ollama_select_model',
      errorMessage: t('pages.settings.ollama_select_model')
    };
  }

  // 3. Check if host is configured
  const baseUrl = provider.base_url || '';
  if (!baseUrl || (!baseUrl.startsWith('http://') && !baseUrl.startsWith('https://'))) {
    return {
      valid: false,
      errorKey: 'ollama_invalid_host',
      errorMessage: t('pages.settings.ollama_invalid_host')
    };
  }

  return { valid: true };
};

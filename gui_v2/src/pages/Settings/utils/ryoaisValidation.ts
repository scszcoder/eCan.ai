/**
 * RyoAIS provider validation utilities
 * Shared validation logic for LLM, Embedding, and Rerank management components
 */

import { TFunction } from 'i18next';

export interface RyoAISProvider {
  name?: string;
  provider?: string;
  class_name?: string;
  base_url?: string | null;
  supported_models?: Array<{ name: string; [key: string]: any }>;
  [key: string]: any;
}

export interface RyoAISValidationResult {
  valid: boolean;
  errorKey?: string;
  errorMessage?: string;
}

/**
 * Check if a provider is RyoAIS
 */
export const isRyoAISProvider = (provider: RyoAISProvider): boolean => {
  const name = (provider.name || '').toLowerCase();
  const providerId = (provider.provider || '').toLowerCase();
  const className = (provider.class_name || '').toLowerCase();
  
  return name.includes('ryoais') || providerId.includes('ryoais') || className.includes('ryoais');
};

/**
 * Validate RyoAIS provider configuration before setting as default
 * 
 * @param provider - The provider object to validate
 * @param selectedModel - The currently selected model (if any)
 * @param t - i18n translation function
 * @returns Validation result with error message if invalid
 */
export const validateRyoAISProvider = (
  provider: RyoAISProvider,
  selectedModel: string | undefined,
  t: TFunction
): RyoAISValidationResult => {
  // Only validate RyoAIS providers
  if (!isRyoAISProvider(provider)) {
    return { valid: true };
  }

  // 1. Check if models are available
  const supportedModels = provider.supported_models || [];
  if (supportedModels.length === 0) {
    return {
      valid: false,
      errorKey: 'ryoais_no_models',
      errorMessage: t('pages.settings.ryoais_no_models')
    };
  }

  // 2. Check if a model is selected
  if (!selectedModel) {
    return {
      valid: false,
      errorKey: 'ryoais_select_model',
      errorMessage: t('pages.settings.ryoais_select_model')
    };
  }

  // 3. Check if host is configured
  const baseUrl = provider.base_url || '';
  if (!baseUrl || (!baseUrl.startsWith('http://') && !baseUrl.startsWith('https://'))) {
    return {
      valid: false,
      errorKey: 'ryoais_invalid_host',
      errorMessage: t('pages.settings.ryoais_invalid_host')
    };
  }

  return { valid: true };
};

/**
 * LightRAG Configuration Validator
 * Validates that required LLM and Embedding configurations are set
 */

export interface ValidationIssue {
  key: string;
  translationKey: string;
}

export interface ValidationResult {
  isValid: boolean;
  issues: ValidationIssue[];
}

/**
 * Check if a provider requires API key
 * Ollama and lollms don't require API keys for local usage
 */
function providerRequiresApiKey(provider: string): boolean {
  if (!provider) return false;
  const normalizedProvider = provider.toLowerCase().trim();
  // Providers that don't require API keys
  const noApiKeyProviders = ['ollama', 'lollms'];
  return !noApiKeyProviders.includes(normalizedProvider);
}

/**
 * Check if an API key is valid (not empty or placeholder)
 */
function isValidApiKey(apiKey: string | undefined): boolean {
  if (!apiKey) return false;
  const trimmedKey = apiKey.trim();
  if (trimmedKey === '') return false;
  
  // Check for common placeholder values
  const placeholders = ['your_api_key', 'your-api-key', 'sk-xxx', 'xxx', 'placeholder'];
  if (placeholders.includes(trimmedKey.toLowerCase())) return false;
  
  return true;
}

/**
 * Check if a host/endpoint is configured
 */
function hasValidHost(host: string | undefined): boolean {
  if (!host) return false;
  const trimmedHost = host.trim();
  if (trimmedHost === '') return false;
  
  // Only reject obvious placeholders (localhost is valid)
  const invalidPlaceholders = ['your_host', 'your-host', 'example.com', 'your_endpoint'];
  
  return !invalidPlaceholders.includes(trimmedHost.toLowerCase());
}

/**
 * Validates LightRAG configuration settings
 * @param settings - The LightRAG settings object
 * @returns ValidationResult with isValid flag and list of issues
 */
export function validateLightRAGConfig(settings: Record<string, any>): ValidationResult {
  const issues: ValidationIssue[] = [];

  // Check LLM Provider
  const llmProvider = settings.LLM_BINDING || settings.LLM_PROVIDER;
  if (!llmProvider || llmProvider === 'null' || llmProvider.trim() === '') {
    issues.push({
      key: 'llm_provider',
      translationKey: 'pages.knowledge.missingLlmProvider'
    });
  }

  // Check LLM configuration based on provider type
  if (llmProvider && llmProvider !== 'null' && llmProvider.trim() !== '') {
    const llmHost = settings.LLM_BINDING_HOST || settings.LLM_HOST;
    const llmApiKey = settings.LLM_BINDING_API_KEY || settings.LLM_API_KEY;
    const isSystemManaged = settings._SYSTEM_LLM_KEY_SOURCE === true;
    const requiresApiKey = providerRequiresApiKey(llmProvider);
    
    // For Ollama and lollms: only check if host is configured
    if (!requiresApiKey) {
      if (!hasValidHost(llmHost)) {
        issues.push({
          key: 'llm_host',
          translationKey: 'pages.knowledge.missingLlmProvider'
        });
      }
    } else {
      // For cloud providers: check API key
      if (!isSystemManaged && !isValidApiKey(llmApiKey)) {
        issues.push({
          key: 'llm_api_key',
          translationKey: 'pages.knowledge.missingLlmApiKey'
        });
      }
    }
  }

  // Check Embedding Provider
  const embeddingProvider = settings.EMBEDDING_BINDING || settings.EMBEDDING_PROVIDER;
  if (!embeddingProvider || embeddingProvider === 'null' || embeddingProvider.trim() === '') {
    issues.push({
      key: 'embedding_provider',
      translationKey: 'pages.knowledge.missingEmbeddingProvider'
    });
  }

  // Check Embedding configuration based on provider type
  if (embeddingProvider && embeddingProvider !== 'null' && embeddingProvider.trim() !== '') {
    const embeddingHost = settings.EMBEDDING_BINDING_HOST || settings.EMBEDDING_HOST;
    const embeddingApiKey = settings.EMBEDDING_BINDING_API_KEY;
    const isSystemManaged = settings._SYSTEM_EMBED_KEY_SOURCE === true;
    const requiresApiKey = providerRequiresApiKey(embeddingProvider);
    
    // For Ollama and lollms: only check if host is configured
    if (!requiresApiKey) {
      if (!hasValidHost(embeddingHost)) {
        issues.push({
          key: 'embedding_host',
          translationKey: 'pages.knowledge.missingEmbeddingProvider'
        });
      }
    } else {
      // For cloud providers: check API key
      if (!isSystemManaged && !isValidApiKey(embeddingApiKey)) {
        issues.push({
          key: 'embedding_api_key',
          translationKey: 'pages.knowledge.missingEmbeddingApiKey'
        });
      }
    }
  }

  return {
    isValid: issues.length === 0,
    issues
  };
}

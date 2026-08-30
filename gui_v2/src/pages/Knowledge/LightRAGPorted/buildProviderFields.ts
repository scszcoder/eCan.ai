/**
 * Derive ProviderFieldConfig[] from raw backend provider data.
 * This replaces the need for a static providerConfig.ts with hardcoded field definitions.
 */
import type { ProviderConfig, ProviderFieldConfig } from './providerConfig';

export interface RawProvider {
  provider: string;
  display_name: string;
  description?: string;
  regions?: string[];
  is_local?: boolean;
  base_url?: string | null;
  default_model?: string | null;
  supported_models?: Array<{
    name: string;
    display_name: string;
    model_id: string;
    default_temperature?: number;
    max_tokens?: number;
    dimensions?: number;
    max_chunks_per_doc?: number;
    supports_streaming?: boolean;
    supports_function_calling?: boolean;
    supports_vision?: boolean;
    cost_per_1k_tokens?: number;
    description?: string;
  }>;
  api_key_env_vars?: string[];
  runtime_kind?: string;
  param_mapping?: Record<string, string>;
  special_features?: Record<string, unknown>;
  default_params?: Record<string, unknown>;
  custom_parameters?: Record<string, unknown>;
}

function buildLLMFields(raw: RawProvider): ProviderFieldConfig[] {
  const fields: ProviderFieldConfig[] = [];
  const runtime = raw.runtime_kind || '';

  // Model field
  if (raw.supported_models?.length) {
    fields.push({
      key: 'LLM_MODEL',
      label: 'fields.model',
      type: 'select',
      defaultValue: raw.default_model || '',
      required: true,
      options: raw.supported_models.map(m => ({
        value: m.model_id,
        label: m.display_name || m.name,
      })),
    });
  } else {
    const isOllama = raw.provider === 'ollama';
    fields.push({
      key: 'LLM_MODEL',
      label: 'fields.model',
      type: 'text',
      defaultValue: raw.default_model || '',
      required: true,
      isDynamicOllamaModel: isOllama,
      isDynamicProviderModel: raw.special_features?.dynamic_models === true,
    });
  }

  // Host field
  if (raw.base_url && runtime !== 'azure_openai') {
    fields.push({
      key: 'LLM_BINDING_HOST',
      label: 'fields.apiHost',
      type: 'text',
      defaultValue: raw.base_url,
    });
  }

  // Temperature (most providers support it)
  const paramMap = raw.param_mapping || {};
  if (paramMap.temperature) {
    fields.push({
      key: 'LLM_TEMPERATURE',
      label: 'fields.temperature',
      type: 'number',
      placeholder: '0.7',
      defaultValue: '0.7',
    });
  }

  // Max completion tokens (OpenAI-compatible)
  if (runtime === 'openai_compatible' && raw.provider === 'openai') {
    fields.push({
      key: 'LLM_MAX_COMPLETION_TOKENS',
      label: 'fields.maxCompletionTokens',
      type: 'number',
      placeholder: '9000',
    });
  }

  // Max output tokens (Anthropic, Google)
  if (paramMap.temperature === 'anthropic_temperature') {
    fields.push({
      key: 'LLM_MAX_OUTPUT_TOKENS',
      label: 'fields.maxOutputTokens',
      type: 'number',
      placeholder: '128000',
    });
  }

  // Azure OpenAI specific fields
  if (runtime === 'azure_openai') {
    fields.push(
      { key: 'AZURE_OPENAI_ENDPOINT', label: 'fields.azureEndpoint', type: 'text', defaultValue: raw.base_url || 'https://your-resource.openai.azure.com', required: true },
      { key: 'AZURE_OPENAI_API_KEY', label: 'fields.apiKey', type: 'password', required: true },
      { key: 'AZURE_OPENAI_API_VERSION', label: 'fields.apiVersion', type: 'text', defaultValue: '2024-02-15-preview' }
    );
  }

  // AWS Bedrock specific fields
  if (runtime === 'bedrock_converse') {
    fields.push(
      { key: 'AWS_ACCESS_KEY_ID', label: 'fields.awsAccessKey', type: 'text', placeholder: 'AKIA...' },
      { key: 'AWS_SECRET_ACCESS_KEY', label: 'fields.awsSecretKey', type: 'password' },
      { key: 'AWS_REGION', label: 'fields.awsRegion', type: 'text', defaultValue: 'us-east-1' }
    );
  }

  // API key (for non-local, non-Azure providers)
  if (raw.api_key_env_vars?.length && !raw.is_local && runtime !== 'azure_openai') {
    fields.push({
      key: 'LLM_BINDING_API_KEY',
      label: 'fields.apiKey',
      type: 'password',
      required: !!raw.special_features?.requires_api_key,
    });
  }

  return fields;
}

function buildEmbeddingFields(raw: RawProvider): ProviderFieldConfig[] {
  const fields: ProviderFieldConfig[] = [];
  const isDynamicProvider = raw.special_features?.dynamic_models === true;

  // Model field
  if (raw.supported_models?.length) {
    fields.push({
      key: 'EMBEDDING_MODEL',
      label: 'fields.model',
      type: 'select',
      defaultValue: raw.default_model || '',
      required: true,
      options: raw.supported_models.map(m => ({
        value: m.model_id,
        label: m.display_name || m.name,
      })),
    });
  } else {
    const isOllama = raw.provider === 'ollama';
    fields.push({
      key: 'EMBEDDING_MODEL',
      label: 'fields.model',
      type: 'text',
      defaultValue: raw.default_model || '',
      required: true,
      isDynamicOllamaModel: isOllama,
      isDynamicProviderModel: raw.special_features?.dynamic_models === true,
    });
  }

  // Dimensions (auto-filled from model selection, shown as hint)
  fields.push({
    key: 'EMBEDDING_DIM',
    label: 'fields.dimensions',
    type: 'number',
    placeholder: '1024',
    disabled: !isDynamicProvider,
  });

  // Token limit hint
  fields.push({
    key: 'EMBEDDING_TOKEN_LIMIT',
    label: 'fields.tokenLimit',
    type: 'number',
    placeholder: '8192',
    disabled: true,
  });

  // Host field (local and configurable OpenAI-compatible providers)
  if (raw.base_url && (raw.is_local || raw.special_features?.dynamic_models === true)) {
    fields.push({
      key: 'EMBEDDING_BINDING_HOST',
      label: 'fields.apiHost',
      type: 'text',
      defaultValue: raw.base_url,
    });
  }

  // API key
  if (raw.api_key_env_vars?.length && !raw.is_local) {
    fields.push({
      key: 'EMBEDDING_BINDING_API_KEY',
      label: 'fields.apiKey',
      type: 'password',
      required: !!raw.special_features?.requires_api_key,
    });
  }

  return fields;
}

function buildRerankFields(raw: RawProvider): ProviderFieldConfig[] {
  const fields: ProviderFieldConfig[] = [];
  const usesCompatibilityProxy = !['cohere', 'jina', 'aliyun'].includes(raw.provider.toLowerCase());

  // Model field
  if (raw.supported_models?.length) {
    fields.push({
      key: 'RERANK_MODEL',
      label: 'fields.model',
      type: 'select',
      defaultValue: raw.default_model || '',
      required: true,
      options: raw.supported_models.map(m => ({
        value: m.model_id,
        label: m.display_name || m.name,
      })),
    });
  } else {
    const isOllama = raw.provider === 'ollama';
    fields.push({
      key: 'RERANK_MODEL',
      label: 'fields.model',
      type: 'text',
      defaultValue: raw.default_model || '',
      required: true,
      isDynamicOllamaModel: isOllama,
      isDynamicProviderModel: raw.special_features?.dynamic_models === true,
    });
  }

  // Host field
  if (raw.base_url) {
    fields.push({
      key: 'RERANK_BINDING_HOST',
      label: 'fields.apiHost',
      type: 'text',
      defaultValue: raw.base_url,
      // Proxy-backed providers get their real endpoint from System Settings.
      // LightRAG only displays it; runtime uses the local compatibility proxy.
      disabled: usesCompatibilityProxy,
      isSystemManaged: usesCompatibilityProxy,
    });
  }

  // API key
  if (raw.api_key_env_vars?.length && !raw.is_local) {
    fields.push({
      key: 'RERANK_BINDING_API_KEY',
      label: 'fields.apiKey',
      type: 'password',
      required: !!raw.special_features?.requires_api_key,
    });
  }

  return fields;
}

/**
 * Convert raw backend provider data to the ProviderConfig format expected by the UI.
 * This is the sole place where field definitions are derived from provider metadata.
 */
export function buildProviderConfig(raw: RawProvider, type: 'llm' | 'embedding' | 'rerank'): ProviderConfig {
  const isOllama = raw.provider === 'ollama';
  const fields = type === 'llm' ? buildLLMFields(raw)
    : type === 'embedding' ? buildEmbeddingFields(raw)
    : buildRerankFields(raw);

  const config: ProviderConfig = {
    id: raw.provider,
    name: raw.display_name,
    description: raw.description,
    fields,
  };

  if (raw.regions?.length) {
    config.regions = raw.regions as ('cn' | 'intl')[];
  }
  if (isOllama) {
    config.isOllama = true;
  }
  if (raw.special_features?.dynamic_models === true) {
    config.hasDynamicModels = true;
  }

  // Embedding model metadata (dimensions per model)
  if (type === 'embedding' && raw.supported_models?.length) {
    const modelMetadata: Record<string, { dimensions?: number; max_tokens?: number }> = {};
    for (const m of raw.supported_models) {
      modelMetadata[m.model_id] = {
        dimensions: m.dimensions,
        max_tokens: m.max_tokens,
      };
    }
    config.modelMetadata = modelMetadata;
  }

  return config;
}

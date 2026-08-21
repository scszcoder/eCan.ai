// Provider-based configuration structure for LightRAG Settings.
// This file contains:
//   - Shared TypeScript interfaces used by both the provider config and SettingsTab.
//   - Common field definitions that apply across all providers of a type.
//   - Storage provider definitions (not from backend JSON).
//   - Region utility functions.
//
// LLM / Embedding / Reranking provider data comes from the backend IPC
// (lightrag.getSystemProviders) and is transformed into ProviderConfig by
// buildProviderFields.ts. No hardcoded provider list is needed.

export interface ProviderFieldConfig {
  key: string;
  label?: string;
  type?: 'text' | 'number' | 'select' | 'textarea' | 'password' | 'boolean';
  defaultValue?: string;
  placeholder?: string;
  tooltip?: string;
  options?: Array<{ value: string; label: string }>;
  required?: boolean;
  isSystemManaged?: boolean;
  disabled?: boolean;
  isDynamicOllamaModel?: boolean;
}

export interface ProviderConfig {
  id: string;
  name: string;
  description?: string;
  fields: ProviderFieldConfig[];
  modelMetadata?: Record<string, { dimensions?: number; max_tokens?: number }>;
  isOllama?: boolean;
  regions?: ('cn' | 'intl')[];
}

export const DEFAULT_PROVIDER_BY_REGION = {
  cn: { provider: 'deepseek', model: 'deepseek-v4-flash', displayName: 'DeepSeek V4 Flash' },
  intl: { provider: 'openai', model: 'gpt-5.6-sol', displayName: 'GPT-5.6 Sol' }
} as const;

export const DEFAULT_EMBEDDING_BY_REGION = {
  cn: { provider: 'jina', model: 'jina-embeddings-v3', displayName: 'Jina Embeddings V3' },
  intl: { provider: 'openai', model: 'text-embedding-3-large', displayName: 'OpenAI text-embedding-3-large' }
} as const;

export const DEFAULT_RERANK_BY_REGION = {
  cn: { provider: 'aliyun', model: 'gte-rerank-v2', displayName: 'Aliyun GTE Rerank v2' },
  intl: { provider: 'cohere', model: 'rerank-v3.5', displayName: 'Cohere Rerank v3.5' }
} as const;

export function getProvidersByRegion<T extends ProviderConfig>(
  providers: T[],
  region: 'cn' | 'intl'
): T[] {
  return providers.filter(p => !p.regions || p.regions.includes(region));
}

// ==================== Common Fields ====================
export const LLM_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'LLM_TIMEOUT', label: 'fields.requestTimeout', type: 'number', placeholder: '60' }
];

export const EMBEDDING_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'EMBEDDING_TIMEOUT', label: 'fields.requestTimeout', type: 'number', placeholder: '60', tooltip: 'tooltips.embeddingTimeout' }
];

export const RERANKING_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'RERANK_BY_DEFAULT', label: 'fields.enableByDefault', type: 'boolean', tooltip: 'tooltips.rerankByDefault' },
  { key: 'MIN_RERANK_SCORE', label: 'fields.minRerankScore', type: 'number', placeholder: '0.15', tooltip: 'tooltips.minRerankScore' }
];

// ==================== Storage ====================
export const STORAGE_COMMON_POSTGRES: ProviderFieldConfig[] = [
  { key: 'POSTGRES_HOST', label: 'fields.postgresHost', type: 'text', defaultValue: 'localhost' },
  { key: 'POSTGRES_PORT', label: 'fields.postgresPort', type: 'number', defaultValue: '5432' },
  { key: 'POSTGRES_USER', label: 'fields.postgresUser', type: 'text', defaultValue: 'postgres' },
  { key: 'POSTGRES_PASSWORD', label: 'fields.postgresPassword', type: 'password' },
  { key: 'POSTGRES_DATABASE', label: 'fields.postgresDatabase', type: 'text', defaultValue: 'lightrag' }
];

export const STORAGE_PROVIDERS: ProviderConfig[] = [
  { id: 'null', name: 'providers.noneDisabled', description: 'Disable storage functionality', fields: [] },
  {
    id: 'local', name: 'Local Disk', description: 'Store files on local disk',
    fields: [{ key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './storage', placeholder: './storage', required: true }]
  },
  {
    id: 's3', name: 'S3 Compatible', description: 'Store files in S3 compatible storage',
    fields: [
      { key: 'STORAGE_S3_BUCKET', label: 'fields.s3Bucket', type: 'text', required: true },
      { key: 'STORAGE_S3_REGION', label: 'fields.s3Region', type: 'text', defaultValue: 'us-east-1' },
      { key: 'STORAGE_S3_ENDPOINT', label: 'fields.s3Endpoint', type: 'text', placeholder: 'https://s3.amazonaws.com' },
      { key: 'STORAGE_S3_ACCESS_KEY', label: 'fields.s3AccessKey', type: 'password', required: true },
      { key: 'STORAGE_S3_SECRET_KEY', label: 'fields.s3SecretKey', type: 'password', required: true }
    ]
  }
];

export const STORAGE_KV_PROVIDERS: ProviderConfig[] = STORAGE_PROVIDERS;
export const STORAGE_VECTOR_PROVIDERS: ProviderConfig[] = STORAGE_PROVIDERS;
export const STORAGE_GRAPH_PROVIDERS: ProviderConfig[] = STORAGE_PROVIDERS;
export const STORAGE_DOC_STATUS_PROVIDERS: ProviderConfig[] = [
  { id: 'null', name: 'providers.noneDisabled', description: 'Disable document status storage', fields: [] },
  {
    id: 'local', name: 'Local Disk', description: 'Store document status locally',
    fields: [{ key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './storage', placeholder: './storage' }]
  }
];

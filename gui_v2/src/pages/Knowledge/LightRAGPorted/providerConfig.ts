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
//
// Note: there is no generic STORAGE_PROVIDERS export. LightRAG's storage backends
// (KV / Vector / Graph / DocStatus) are each tied to a specific backend class
// (see lightrag/kg/__init__.py STORAGES dict) — S3 / Tencent COS are app-level
// object stores, not LightRAG storage backends, so the previous generic
// `null | local | s3` list was removed. The four lists below enumerate the
// real backends LightRAG supports; `null` is included to let users disable a
// storage tier (which the launcher treats as "don't initialize").
//
// For cn users, Tencent COS is used as the app-level object store (see
// apps/cn/config/cloud_endpoints.json -> storage_region / storage_bucket).
// That's configured at the app layer, not in these per-tier provider lists.

export const STORAGE_COMMON_POSTGRES: ProviderFieldConfig[] = [
  { key: 'POSTGRES_HOST', label: 'fields.postgresHost', type: 'text', defaultValue: 'localhost' },
  { key: 'POSTGRES_PORT', label: 'fields.postgresPort', type: 'number', defaultValue: '5432' },
  { key: 'POSTGRES_USER', label: 'fields.postgresUser', type: 'text', defaultValue: 'postgres' },
  { key: 'POSTGRES_PASSWORD', label: 'fields.postgresPassword', type: 'password' },
  { key: 'POSTGRES_DATABASE', label: 'fields.postgresDatabase', type: 'text', defaultValue: 'lightrag' },
  { key: 'POSTGRES_MAX_CONNECTIONS', label: 'fields.postgresMaxConnections', type: 'number', defaultValue: '12' }
];

// KV storage backends supported by LightRAG. i18n keys are used for name/description
// so existing translations (providers.* / fields.*) can be reused.
export const STORAGE_KV_PROVIDERS: ProviderConfig[] = [
  { id: 'null', name: 'providers.noneDisabled', description: 'Disable storage functionality', fields: [] },
  {
    id: 'JsonKVStorage', name: 'providers.jsonKvStorage', description: 'JSON file-backed KV storage (default, lightweight)',
    regions: ['cn', 'intl'],
    fields: [{ key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './rag_storage', placeholder: './rag_storage' }]
  },
  {
    id: 'RedisKVStorage', name: 'providers.redisKvStorage', description: 'Redis-backed KV storage (recommended for production)',
    fields: [
      { key: 'REDIS_URI', label: 'fields.redisUri', type: 'text', defaultValue: 'redis://localhost:6379', required: true },
      { key: 'REDIS_SOCKET_TIMEOUT', label: 'fields.redisSocketTimeout', type: 'number', defaultValue: '30' },
      { key: 'REDIS_CONNECT_TIMEOUT', label: 'fields.redisConnectTimeout', type: 'number', defaultValue: '10' },
      { key: 'REDIS_MAX_CONNECTIONS', label: 'fields.redisMaxConnections', type: 'number', defaultValue: '100' },
      { key: 'REDIS_RETRY_ATTEMPTS', label: 'fields.redisRetryAttempts', type: 'number', defaultValue: '3' }
    ]
  },
  {
    id: 'PGKVStorage', name: 'providers.pgKvStorage', description: 'PostgreSQL-backed KV storage (shared with PG common settings)',
    fields: []
  },
  {
    id: 'MongoKVStorage', name: 'providers.mongoKvStorage', description: 'MongoDB-backed KV storage',
    fields: [
      { key: 'MONGO_URI', label: 'fields.mongoUri', type: 'text', defaultValue: 'mongodb://localhost:27017/', required: true },
      { key: 'MONGO_DATABASE', label: 'fields.mongoDatabase', type: 'text', defaultValue: 'LightRAG' }
    ]
  }
];

// Vector storage backends supported by LightRAG. Faiss is the default local file-backed
// option; Milvus / Qdrant / PGVectorStorage are production-grade.
export const STORAGE_VECTOR_PROVIDERS: ProviderConfig[] = [
  { id: 'null', name: 'providers.noneDisabled', description: 'Disable vector storage (not recommended for RAG)', fields: [] },
  {
    id: 'NanoVectorDBStorage', name: 'providers.nanoVectorStorage', description: 'Nano vector DB storage (default)',
    fields: [{ key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './rag_storage', placeholder: './rag_storage' }]
  },
  {
    id: 'FaissVectorDBStorage', name: 'providers.faissVectorStorage', description: 'Meta Faiss local vector DB (recommended for test deployment)',
    fields: [{ key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './rag_storage', placeholder: './rag_storage' }]
  },
  {
    id: 'MilvusVectorDBStorage', name: 'providers.milvusVectorStorage', description: 'Milvus distributed vector DB (recommended for production)',
    fields: [
      { key: 'MILVUS_URI', label: 'fields.milvusUri', type: 'text', defaultValue: 'http://localhost:19530', required: true },
      { key: 'MILVUS_DB_NAME', label: 'fields.milvusDbName', type: 'text', defaultValue: 'lightrag' },
      { key: 'MILVUS_USER', label: 'fields.milvusUser', type: 'text' },
      { key: 'MILVUS_PASSWORD', label: 'fields.milvusPassword', type: 'password' },
      { key: 'MILVUS_TOKEN', label: 'fields.milvusToken', type: 'password' }
    ]
  },
  {
    id: 'QdrantVectorDBStorage', name: 'providers.qdrantVectorStorage', description: 'Qdrant vector DB (recommended for production)',
    fields: [
      { key: 'QDRANT_URL', label: 'fields.qdrantUrl', type: 'text', defaultValue: 'http://localhost:6333', required: true },
      { key: 'QDRANT_API_KEY', label: 'fields.qdrantApiKey', type: 'password' }
    ]
  },
  {
    id: 'PGVectorStorage', name: 'providers.pgVectorStorage', description: 'PostgreSQL with pgvector (shared with PG common settings)',
    fields: []
  },
  {
    id: 'MongoVectorDBStorage', name: 'providers.mongoVectorStorage', description: 'MongoDB Atlas vector search (Atlas Cloud only)',
    fields: [
      { key: 'MONGO_URI', label: 'fields.mongoUri', type: 'text', defaultValue: 'mongodb://localhost:27017/', required: true },
      { key: 'MONGO_DATABASE', label: 'fields.mongoDatabase', type: 'text', defaultValue: 'LightRAG' }
    ]
  }
];

export const STORAGE_GRAPH_PROVIDERS: ProviderConfig[] = [
  { id: 'null', name: 'providers.noneDisabled', description: 'Disable graph storage (not recommended for RAG)', fields: [] },
  {
    id: 'NetworkXStorage', name: 'providers.networkXStorage', description: 'NetworkX in-process graph (default, lightweight)',
    fields: [{ key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './rag_storage', placeholder: './rag_storage' }]
  },
  {
    id: 'Neo4JStorage', name: 'providers.neo4jStorage', description: 'Neo4j graph database',
    fields: [
      { key: 'NEO4J_URI', label: 'fields.neo4jUri', type: 'text', defaultValue: 'neo4j+s://localhost:7687', required: true },
      { key: 'NEO4J_USERNAME', label: 'fields.neo4jUsername', type: 'text', defaultValue: 'neo4j' },
      { key: 'NEO4J_PASSWORD', label: 'fields.neo4jPassword', type: 'password', required: true },
      { key: 'NEO4J_DATABASE', label: 'fields.neo4jDatabase', type: 'text', defaultValue: 'neo4j' },
      { key: 'NEO4J_MAX_CONNECTION_POOL_SIZE', label: 'fields.neo4jMaxConnectionPoolSize', type: 'number', defaultValue: '100' },
      { key: 'NEO4J_CONNECTION_TIMEOUT', label: 'fields.neo4jConnectionTimeout', type: 'number', defaultValue: '30' },
      { key: 'NEO4J_CONNECTION_ACQUISITION_TIMEOUT', label: 'fields.neo4jConnectionAcquisitionTimeout', type: 'number', defaultValue: '30' },
      { key: 'NEO4J_MAX_TRANSACTION_RETRY_TIME', label: 'fields.neo4jMaxTransactionRetryTime', type: 'number', defaultValue: '30' },
      { key: 'NEO4J_MAX_CONNECTION_LIFETIME', label: 'fields.neo4jMaxConnectionLifetime', type: 'number', defaultValue: '300' },
      { key: 'NEO4J_LIVENESS_CHECK_TIMEOUT', label: 'fields.neo4jLivenessCheckTimeout', type: 'number', defaultValue: '30' },
      { key: 'NEO4J_KEEP_ALIVE', label: 'fields.neo4jKeepAlive', type: 'boolean', defaultValue: 'true' }
    ]
  },
  {
    id: 'MemgraphStorage', name: 'providers.memgraphStorage', description: 'Memgraph in-memory graph database',
    fields: [
      { key: 'MEMGRAPH_URI', label: 'fields.memgraphUri', type: 'text', defaultValue: 'bolt://localhost:7687', required: true },
      { key: 'MEMGRAPH_USERNAME', label: 'fields.memgraphUsername', type: 'text' },
      { key: 'MEMGRAPH_PASSWORD', label: 'fields.memgraphPassword', type: 'password' },
      { key: 'MEMGRAPH_DATABASE', label: 'fields.memgraphDatabase', type: 'text', defaultValue: 'memgraph' }
    ]
  },
  {
    id: 'PGGraphStorage', name: 'providers.pgGraphStorage', description: 'PostgreSQL-backed graph storage (shared with PG common settings)',
    fields: []
  },
  {
    id: 'MongoGraphStorage', name: 'providers.mongoGraphStorage', description: 'MongoDB-backed graph storage',
    fields: [
      { key: 'MONGO_URI', label: 'fields.mongoUri', type: 'text', defaultValue: 'mongodb://localhost:27017/', required: true },
      { key: 'MONGO_DATABASE', label: 'fields.mongoDatabase', type: 'text', defaultValue: 'LightRAG' }
    ]
  }
];

export const STORAGE_DOC_STATUS_PROVIDERS: ProviderConfig[] = [
  { id: 'null', name: 'providers.noneDisabled', description: 'Disable document status storage', fields: [] },
  {
    id: 'JsonDocStatusStorage', name: 'providers.jsonDocStatusStorage', description: 'JSON file-backed document status (default, lightweight)',
    fields: [{ key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './rag_storage', placeholder: './rag_storage' }]
  },
  {
    id: 'RedisDocStatusStorage', name: 'providers.redisDocStatusStorage', description: 'Redis-backed document status (recommended for production)',
    fields: [
      { key: 'REDIS_URI', label: 'fields.redisUri', type: 'text', defaultValue: 'redis://localhost:6379', required: true },
      { key: 'REDIS_SOCKET_TIMEOUT', label: 'fields.redisSocketTimeout', type: 'number', defaultValue: '30' },
      { key: 'REDIS_CONNECT_TIMEOUT', label: 'fields.redisConnectTimeout', type: 'number', defaultValue: '10' },
      { key: 'REDIS_MAX_CONNECTIONS', label: 'fields.redisMaxConnections', type: 'number', defaultValue: '100' },
      { key: 'REDIS_RETRY_ATTEMPTS', label: 'fields.redisRetryAttempts', type: 'number', defaultValue: '3' }
    ]
  },
  {
    id: 'PGDocStatusStorage', name: 'providers.pgDocStatusStorage', description: 'PostgreSQL-backed document status (shared with PG common settings)',
    fields: []
  },
  {
    id: 'MongoDocStatusStorage', name: 'providers.mongoDocStatusStorage', description: 'MongoDB-backed document status',
    fields: [
      { key: 'MONGO_URI', label: 'fields.mongoUri', type: 'text', defaultValue: 'mongodb://localhost:27017/', required: true },
      { key: 'MONGO_DATABASE', label: 'fields.mongoDatabase', type: 'text', defaultValue: 'LightRAG' }
    ]
  }
];

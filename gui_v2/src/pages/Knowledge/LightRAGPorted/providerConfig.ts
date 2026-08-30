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
  isDynamicProviderModel?: boolean;
}

export interface ProviderConfig {
  id: string;
  name: string;
  description?: string;
  fields: ProviderFieldConfig[];
  modelMetadata?: Record<string, { dimensions?: number; max_tokens?: number }>;
  isOllama?: boolean;
  hasDynamicModels?: boolean;
  regions?: ('cn' | 'intl')[];
}

export const DEFAULT_PROVIDER_BY_REGION = {
  cn: { provider: 'ecanai', model: '', displayName: 'eCanAI' },
  intl: { provider: 'ecanai', model: '', displayName: 'eCanAI' }
} as const;

export const DEFAULT_EMBEDDING_BY_REGION = {
  cn: { provider: 'ecanai', model: 'text-embedding-v3', displayName: 'eCanAI text-embedding-v3' },
  intl: { provider: 'ecanai', model: 'text-embedding-v3', displayName: 'eCanAI text-embedding-v3' }
} as const;

export const DEFAULT_RERANK_BY_REGION = {
  cn: { provider: 'ecanai', model: 'gte-rerank', displayName: 'eCanAI gte-rerank' },
  intl: { provider: 'ecanai', model: 'gte-rerank', displayName: 'eCanAI gte-rerank' }
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

// ==================== Document Parsing Engines ====================
//
// LightRAG 1.5+ routes each file to a content-extraction engine through the
// LIGHTRAG_PARSER rule table (rules are evaluated left to right, first match
// wins). "native" is the built-in engine; "mineru" (PDF / images) and
// "docling" (Office docs) are external parser services configured through
// their own env vars (MINERU_* / DOCLING_*).
//
// The UI-only PARSING_ENGINE key selects a preset routing table; it is
// filtered out on the backend before persisting to lightrag.env.
export const PARSER_PRESETS = {
  native: '*:native-teP,*:legacy-R',
  // Rules are first-match-wins. Keep the selected external engine first;
  // otherwise native consumes DOCX before MinerU/Docling can handle it.
  // Native and legacy remain capability-based fallbacks.
  mineru: '*:mineru-teP,*:native-teP,*:legacy-R',
  docling: '*:docling-teP,*:native-teP,*:legacy-R'
} as const;

export const PARSER_PROVIDERS: ProviderConfig[] = [
  {
    id: 'native',
    name: 'providers.parserNative',
    description: 'LightRAG built-in native parser (default, no external service required)',
    fields: [
      { key: 'PARSER_IMAGE_ANALYSIS', label: 'fields.parserImageAnalysis', type: 'boolean', defaultValue: 'false', tooltip: 'tooltips.parserImageAnalysis' },
      { key: 'LIGHTRAG_PARSER', label: 'fields.parserRouting', type: 'textarea', defaultValue: PARSER_PRESETS.native, tooltip: 'tooltips.parserRouting' }
    ]
  },
  {
    id: 'mineru',
    name: 'providers.parserMineru',
    description: 'MinerU multimodal parser service (PDF / Office / images)',
    fields: [
      { key: 'PARSER_IMAGE_ANALYSIS', label: 'fields.parserImageAnalysis', type: 'boolean', defaultValue: 'false', tooltip: 'tooltips.parserImageAnalysis' },
      { key: 'MINERU_API_MODE', label: 'fields.mineruProvider', type: 'select', defaultValue: 'local', options: [
        { value: 'local', label: 'fields.providerLocal' },
        { value: 'official', label: 'fields.providerOfficial' }
      ], tooltip: 'tooltips.mineruProvider' },
      { key: 'MINERU_OFFICIAL_ENDPOINT', label: 'fields.mineruEndpoint', type: 'text', defaultValue: 'https://mineru.net', placeholder: 'https://mineru.net', tooltip: 'tooltips.mineruEndpoint' },
      { key: 'MINERU_LOCAL_ENDPOINT', label: 'fields.mineruEndpoint', type: 'text', defaultValue: 'http://127.0.0.1:8000', placeholder: 'http://127.0.0.1:8000', tooltip: 'tooltips.mineruLocalEndpoint' },
      { key: 'MINERU_API_TOKEN', label: 'fields.mineruApiKey', type: 'password', required: true, tooltip: 'tooltips.mineruApiKey' },
      { key: 'MINERU_MODEL_VERSION', label: 'fields.mineruModelVersion', type: 'select', defaultValue: 'pipeline', options: [
        { value: 'pipeline', label: 'fields.mineruModelPipeline' },
        { value: 'vlm', label: 'fields.mineruModelVlm' }
      ], tooltip: 'tooltips.mineruModelVersion' },
      { key: 'MINERU_IS_OCR', label: 'fields.mineruIsOcr', type: 'boolean', defaultValue: 'false', tooltip: 'tooltips.mineruIsOcr' },
      { key: 'MINERU_LANGUAGE', label: 'fields.mineruLanguage', type: 'select', defaultValue: 'ch', options: [
        { value: 'ch', label: 'fields.languageChineseMixed' },
        { value: 'ch_server', label: 'fields.languageChineseMixedServer' },
        { value: 'korean', label: 'fields.languageKorean' },
        { value: 'ta', label: 'fields.languageTamil' },
        { value: 'te', label: 'fields.languageTelugu' },
        { value: 'ka', label: 'fields.languageKannada' },
        { value: 'th', label: 'fields.languageThai' },
        { value: 'el', label: 'fields.languageGreek' },
        { value: 'arabic', label: 'fields.languageArabic' },
        { value: 'east_slavic', label: 'fields.languageEastSlavic' },
        { value: 'cyrillic', label: 'fields.languageCyrillic' },
        { value: 'devanagari', label: 'fields.languageDevanagari' }
      ], tooltip: 'tooltips.mineruLanguage' },
      { key: 'MINERU_ENABLE_TABLE', label: 'fields.mineruEnableTable', type: 'boolean', defaultValue: 'true', tooltip: 'tooltips.mineruEnableTable' },
      { key: 'MINERU_ENABLE_FORMULA', label: 'fields.mineruEnableFormula', type: 'boolean', defaultValue: 'true', tooltip: 'tooltips.mineruEnableFormula' },
      { key: 'MINERU_LOCAL_BACKEND', label: 'fields.mineruBackend', type: 'select', defaultValue: 'hybrid-auto-engine', options: [
        { value: 'hybrid-auto-engine', label: 'fields.mineruBackendHybrid' },
        { value: 'pipeline', label: 'fields.mineruBackendPipeline' },
        { value: 'vlm-auto-engine', label: 'fields.mineruBackendVlm' }
      ], tooltip: 'tooltips.mineruBackend' },
      { key: 'MINERU_LOCAL_PARSE_METHOD', label: 'fields.mineruParseMethod', type: 'select', defaultValue: 'auto', options: [
        { value: 'auto', label: 'fields.parseMethodAuto' },
        { value: 'txt', label: 'fields.parseMethodText' },
        { value: 'ocr', label: 'fields.parseMethodOcr' }
      ] },
      { key: 'MINERU_LOCAL_IMAGE_ANALYSIS', label: 'fields.mineruServerImageProcessing', type: 'boolean', defaultValue: 'false', tooltip: 'tooltips.mineruServerImageProcessing' },
      { key: 'MINERU_ADDITIONAL_SUFFIXES', label: 'fields.mineruAdditionalSuffixes', type: 'text', placeholder: 'doc,xls,ppt', tooltip: 'tooltips.additionalSuffixes' },
      { key: 'MAX_PARALLEL_PARSE_MINERU', label: 'fields.maxParallelParse', type: 'number', defaultValue: '2', tooltip: 'tooltips.maxParallelParse' },
      { key: 'LIGHTRAG_PARSER', label: 'fields.parserRouting', type: 'textarea', defaultValue: PARSER_PRESETS.mineru, tooltip: 'tooltips.parserRouting' }
    ]
  },
  {
    id: 'docling',
    name: 'providers.parserDocling',
    description: 'Docling document parsing service, alternative to MinerU (PDF / Office / images)',
    fields: [
      { key: 'PARSER_IMAGE_ANALYSIS', label: 'fields.parserImageAnalysis', type: 'boolean', defaultValue: 'false', tooltip: 'tooltips.parserImageAnalysis' },
      { key: 'DOCLING_ENDPOINT', label: 'fields.doclingEndpoint', type: 'text', defaultValue: 'http://localhost:5001', placeholder: 'http://localhost:5001', required: true, tooltip: 'tooltips.doclingEndpoint' },
      { key: 'DOCLING_API_KEY', label: 'fields.doclingApiKey', type: 'password', required: true, tooltip: 'tooltips.doclingApiKey' },
      { key: 'DOCLING_ADDITIONAL_SUFFIXES', label: 'fields.doclingAdditionalSuffixes', type: 'text', placeholder: 'doc,ppt,xls', tooltip: 'tooltips.additionalSuffixes' },
      { key: 'MAX_PARALLEL_PARSE_DOCLING', label: 'fields.maxParallelParse', type: 'number', defaultValue: '2', tooltip: 'tooltips.maxParallelParse' },
      { key: 'LIGHTRAG_PARSER', label: 'fields.parserRouting', type: 'textarea', defaultValue: PARSER_PRESETS.docling, tooltip: 'tooltips.parserRouting' }
    ]
  }
];

// Configuration structure for LightRAG settings
export interface FieldConfig {
  key: string;
  label?: string; // Optional override for label (i18n key or text)
  type: 'text' | 'number' | 'select' | 'textarea' | 'directory' | 'password' | 'boolean';
  defaultValue?: string;
  placeholder?: string;
  tooltip?: string; // i18n key for tooltip
  options?: Array<{ value: string; label: string }>;
  section?: string; // Sub-section within tab
  disabled?: boolean; // Whether the field is read-only
}

export interface TabConfig {
  key: string;
  label: string; // i18n key
  icon: string;
  fields: FieldConfig[];
}

// Configuration tabs structure
export const SETTINGS_TABS: TabConfig[] = [
  {
    key: 'basic',
    label: 'pages.knowledge.settings.tabs.basic',
    icon: 'CloudServerOutlined',
    fields: []
  },
  {
    key: 'reranking',
    label: 'pages.knowledge.settings.tabs.reranking',
    icon: 'SortAscendingOutlined',
    fields: []
  },
  {
    key: 'llm',
    label: 'pages.knowledge.settings.tabs.llm',
    icon: 'RobotOutlined',
    fields: []
  },
  {
    key: 'embedding',
    label: 'pages.knowledge.settings.tabs.embedding',
    icon: 'BlockOutlined',
    fields: []
  },
  {
    key: 'storage',
    label: 'pages.knowledge.settings.tabs.storage',
    icon: 'DatabaseOutlined',
    fields: []
  },
  {
    key: 'evaluation',
    label: 'pages.knowledge.settings.tabs.evaluation',
    icon: 'ExperimentOutlined',
    fields: []
  }
];

// Basic Configuration Fields (Server, SSL, Directories, Logging, Auth)
export const BASIC_FIELDS: FieldConfig[] = [
  // Server Settings (all disabled)
  { key: 'HOST', type: 'text', defaultValue: '0.0.0.0', section: 'server', tooltip: 'tooltips.host', disabled: true },
  { key: 'PORT', type: 'number', defaultValue: '9621', section: 'server', tooltip: 'tooltips.port', disabled: true },
  { key: 'WEBUI_TITLE', type: 'text', defaultValue: 'eCan.ai Graph KB', section: 'server', disabled: true },
  { key: 'WEBUI_DESCRIPTION', type: 'text', defaultValue: 'eCan.ai RAG System', section: 'server', disabled: true },
  { key: 'WORKERS', type: 'number', placeholder: '2', section: 'server', tooltip: 'tooltips.workers', disabled: true },
  { key: 'TIMEOUT', type: 'number', placeholder: '150', section: 'server', tooltip: 'tooltips.timeout', disabled: true },
  { key: 'CORS_ORIGINS', type: 'text', placeholder: 'http://localhost:3000,http://localhost:8080', section: 'server', tooltip: 'tooltips.corsOrigins', disabled: true },
  
  // SSL Configuration
  { key: 'SSL', type: 'boolean', placeholder: 'false', section: 'ssl', tooltip: 'tooltips.ssl' },
  { key: 'SSL_CERTFILE', type: 'text', placeholder: '/path/to/cert.pem', section: 'ssl' },
  { key: 'SSL_KEYFILE', type: 'text', placeholder: '/path/to/key.pem', section: 'ssl' },
  
  // Directory Configuration
  { key: 'INPUT_DIR', type: 'directory', placeholder: './inputs', section: 'directories', tooltip: 'tooltips.inputDir' },
  { key: 'WORKING_DIR', type: 'directory', placeholder: './rag_storage', section: 'directories', tooltip: 'tooltips.workingDir' },
  { key: 'TIKTOKEN_CACHE_DIR', type: 'directory', placeholder: '/app/data/tiktoken', section: 'directories', tooltip: 'tooltips.tiktokenCacheDir' },
  
  // Logging Configuration
  { key: 'LOG_LEVEL', type: 'select', placeholder: 'INFO', section: 'logging', options: [
    { value: 'DEBUG', label: 'DEBUG' },
    { value: 'INFO', label: 'INFO' },
    { value: 'WARNING', label: 'WARNING' },
    { value: 'ERROR', label: 'ERROR' }
  ]},
  { key: 'VERBOSE', label: 'fields.verbose', type: 'boolean', placeholder: 'False', section: 'logging' },
  { key: 'LOG_MAX_BYTES', type: 'number', placeholder: '10485760', section: 'logging' },
  { key: 'LOG_BACKUP_COUNT', type: 'number', placeholder: '5', section: 'logging' },
  { key: 'LOG_DIR', type: 'directory', placeholder: '/path/to/log/directory', section: 'logging', disabled: true },
  
  // Authentication (all disabled)
  { key: 'AUTH_ACCOUNTS', type: 'text', placeholder: 'admin:admin123,user1:pass456', section: 'auth', tooltip: 'tooltips.authAccounts', disabled: true },
  { key: 'TOKEN_SECRET', type: 'password', placeholder: 'Your-Key-For-LightRAG-API-Server', section: 'auth', disabled: true },
  { key: 'TOKEN_EXPIRE_HOURS', type: 'number', placeholder: '48', section: 'auth', disabled: true },
  { key: 'GUEST_TOKEN_EXPIRE_HOURS', type: 'number', placeholder: '24', section: 'auth', disabled: true },
  { key: 'JWT_ALGORITHM', type: 'text', placeholder: 'HS256', section: 'auth', disabled: true },
  { key: 'LIGHTRAG_API_KEY', type: 'password', placeholder: 'your-secure-api-key-here', section: 'auth', tooltip: 'tooltips.apiKey', disabled: true },
  { key: 'WHITELIST_PATHS', type: 'text', placeholder: '/health,/api/*', section: 'auth', disabled: true }
];

// RAG Parameters (Query, Document Processing, Concurrency, Other)
export const RAG_FIELDS: FieldConfig[] = [
  // Query Configuration
  { key: 'ENABLE_LLM_CACHE', type: 'boolean', defaultValue: 'true', section: 'query', tooltip: 'tooltips.enableLlmCache' },
  { key: 'COSINE_THRESHOLD', type: 'number', placeholder: '0.4', section: 'query' },
  { key: 'TOP_K', type: 'number', placeholder: '15', section: 'query', tooltip: 'tooltips.topK' },
  { key: 'CHUNK_TOP_K', type: 'number', placeholder: '10', section: 'query', tooltip: 'tooltips.chunkTopK' },
  { key: 'MAX_ENTITY_TOKENS', type: 'number', placeholder: '6000', section: 'query', tooltip: 'tooltips.maxEntityTokens' },
  { key: 'MAX_RELATION_TOKENS', type: 'number', placeholder: '8000', section: 'query', tooltip: 'tooltips.maxRelationTokens' },
  { key: 'MAX_TOTAL_TOKENS', type: 'number', placeholder: '30000', section: 'query', tooltip: 'tooltips.maxTotalTokens' },
  { key: 'KG_CHUNK_PICK_METHOD', type: 'select', placeholder: 'VECTOR', section: 'query', options: [
    { value: 'VECTOR', label: 'VECTOR' },
    { value: 'WEIGHT', label: 'WEIGHT' }
  ], tooltip: 'tooltips.kgChunkPickMethod' },
  
  // Document Processing
  { key: 'ENABLE_LLM_CACHE_FOR_EXTRACT', type: 'boolean', defaultValue: 'true', section: 'document' },
  { key: 'SUMMARY_LANGUAGE', type: 'text', defaultValue: 'English, Chinese', section: 'document', tooltip: 'tooltips.summaryLanguage' },
  { key: 'PDF_DECRYPT_PASSWORD', type: 'password', placeholder: 'your_pdf_password_here', section: 'document' },
  { key: 'ENTITY_TYPES', type: 'textarea', placeholder: '["Person", "Organization", "Location", "Event", "Concept"]', section: 'document', tooltip: 'tooltips.entityTypes' },
  { key: 'CHUNK_SIZE', type: 'number', placeholder: '1200', section: 'document', tooltip: 'tooltips.chunkSize' },
  { key: 'CHUNK_OVERLAP_SIZE', type: 'number', placeholder: '100', section: 'document' },
  { key: 'FORCE_LLM_SUMMARY_ON_MERGE', type: 'number', placeholder: '8', section: 'document', tooltip: 'tooltips.forceLlmSummary' },
  { key: 'SUMMARY_MAX_TOKENS', type: 'number', placeholder: '1200', section: 'document' },
  { key: 'SUMMARY_LENGTH_RECOMMENDED', type: 'number', placeholder: '600', section: 'document' },
  { key: 'SUMMARY_CONTEXT_SIZE', type: 'number', placeholder: '12000', section: 'document' },
  { key: 'MAX_SOURCE_IDS_PER_ENTITY', type: 'number', placeholder: '300', section: 'document' },
  { key: 'MAX_SOURCE_IDS_PER_RELATION', type: 'number', placeholder: '300', section: 'document' },
  { key: 'SOURCE_IDS_LIMIT_METHOD', type: 'select', placeholder: 'FIFO', section: 'document', options: [
    { value: 'FIFO', label: 'FIFO' },
    { value: 'KEEP', label: 'KEEP' }
  ]},
  { key: 'MAX_FILE_PATHS', type: 'number', placeholder: '100', section: 'document' },
  { key: 'RELATED_CHUNK_NUMBER', type: 'number', placeholder: '5', section: 'document', tooltip: 'tooltips.relatedChunkNumber' },
  
  // Concurrency
  { key: 'MAX_ASYNC', type: 'number', defaultValue: '6', section: 'concurrency', tooltip: 'tooltips.maxAsync' },
  { key: 'MAX_PARALLEL_INSERT', type: 'number', defaultValue: '3', section: 'concurrency', tooltip: 'tooltips.maxParallelInsert' },
  { key: 'EMBEDDING_FUNC_MAX_ASYNC', type: 'number', placeholder: '4', section: 'concurrency' },
  { key: 'EMBEDDING_BATCH_NUM', type: 'number', placeholder: '64', section: 'concurrency' },
  
  // Other
  { key: 'OLLAMA_EMULATING_MODEL_NAME', type: 'text', placeholder: 'lightrag', section: 'other' },
  { key: 'OLLAMA_EMULATING_MODEL_TAG', type: 'text', defaultValue: 'latest', section: 'other' },
  { key: 'MAX_GRAPH_NODES', type: 'number', placeholder: '1000', section: 'other', tooltip: 'tooltips.maxGraphNodes' },
  { key: 'WORKSPACE', type: 'text', placeholder: 'space1', section: 'other', tooltip: 'tooltips.workspace' }
];

// Continue with other tabs...
export const RERANKING_FIELDS: FieldConfig[] = [
  { key: 'RERANK_BINDING', type: 'select', defaultValue: 'null', options: [
    { value: 'null', label: 'None' },
    { value: 'cohere', label: 'Cohere' },
    { value: 'jina', label: 'Jina' },
    { value: 'aliyun', label: 'Aliyun' }
  ], tooltip: 'settings.tooltips.rerankBinding' },
  { key: 'RERANK_BY_DEFAULT', type: 'boolean', placeholder: 'True', tooltip: 'settings.tooltips.rerankByDefault' },
  { key: 'MIN_RERANK_SCORE', type: 'number', placeholder: '0.25', tooltip: 'settings.tooltips.minRerankScore' },
  { key: 'RERANK_MODEL', type: 'text', placeholder: 'BAAI/bge-reranker-v2-m3', section: 'model' },
  { key: 'RERANK_BINDING_HOST', type: 'text', placeholder: 'http://localhost:8000/v1/rerank', section: 'model' },
  { key: 'RERANK_BINDING_API_KEY', type: 'password', placeholder: 'your_rerank_api_key_here', section: 'model' }
];

// LLM Configuration Fields
export const LLM_FIELDS: FieldConfig[] = [
  // Basic LLM
  { key: 'LLM_BINDING', type: 'select', defaultValue: 'openai', section: 'basic', options: [
    { value: 'openai', label: 'OpenAI' },
    { value: 'ollama', label: 'Ollama' },
    { value: 'azure_openai', label: 'Azure OpenAI' },
    { value: 'gemini', label: 'Gemini' },
    { value: 'aws_bedrock', label: 'AWS Bedrock' },
    { value: 'lollms', label: 'Lollms' }
  ], tooltip: 'settings.tooltips.llmBinding' },
  { key: 'LLM_MODEL', type: 'text', defaultValue: 'gpt-5', section: 'basic' },
  { key: 'LLM_BINDING_HOST', type: 'text', defaultValue: 'https://api.openai.com/v1', section: 'basic' },
  { key: 'LLM_BINDING_API_KEY', type: 'password', defaultValue: 'your_api_key', section: 'basic' },
  { key: 'LLM_TIMEOUT', type: 'number', placeholder: '180', section: 'basic', tooltip: 'settings.tooltips.llmTimeout' },
  
  // Azure OpenAI
  { key: 'AZURE_OPENAI_API_VERSION', type: 'text', placeholder: '2024-08-01-preview', section: 'azure' },
  { key: 'AZURE_OPENAI_DEPLOYMENT', type: 'text', placeholder: 'my-gpt-mini-deployment', section: 'azure' },
  
  // Gemini
  { key: 'GEMINI_LLM_MAX_OUTPUT_TOKENS', type: 'number', placeholder: '9000', section: 'gemini' },
  { key: 'GEMINI_LLM_TEMPERATURE', type: 'number', placeholder: '0.7', section: 'gemini' },
  { key: 'GEMINI_LLM_THINKING_CONFIG', type: 'textarea', placeholder: '{"thinking_budget": -1, "include_thoughts": true}', section: 'gemini', tooltip: 'settings.tooltips.geminiThinking' },
  
  // OpenAI Specific
  { key: 'OPENAI_LLM_REASONING_EFFORT', type: 'select', placeholder: 'minimal', section: 'openai', options: [
    { value: 'minimal', label: 'Minimal' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' }
  ]},
  { key: 'OPENAI_LLM_EXTRA_BODY', type: 'textarea', placeholder: '{"reasoning": {"enabled": false}}', section: 'openai' },
  { key: 'OPENAI_LLM_TEMPERATURE', type: 'number', placeholder: '0.9', section: 'openai' },
  { key: 'OPENAI_LLM_MAX_TOKENS', type: 'number', placeholder: '9000', section: 'openai' },
  { key: 'OPENAI_LLM_MAX_COMPLETION_TOKENS', type: 'number', defaultValue: '9000', section: 'openai' },
  
  // Ollama
  { key: 'OLLAMA_LLM_NUM_CTX', type: 'number', defaultValue: '32768', section: 'ollama', tooltip: 'settings.tooltips.ollamaNumCtx' },
  { key: 'OLLAMA_LLM_NUM_PREDICT', type: 'number', placeholder: '9000', section: 'ollama' },
  { key: 'OLLAMA_LLM_STOP', type: 'textarea', placeholder: '["</s>", "<|EOT|>"]', section: 'ollama' },
  
  // Bedrock
  { key: 'BEDROCK_LLM_TEMPERATURE', type: 'number', placeholder: '1.0', section: 'bedrock' }
];

// Embedding Configuration Fields
export const EMBEDDING_FIELDS: FieldConfig[] = [
  // Basic Embedding
  { key: 'EMBEDDING_BINDING', type: 'select', defaultValue: 'openai', section: 'basic', options: [
    { value: 'openai', label: 'OpenAI' },
    { value: 'ollama', label: 'Ollama' },
    { value: 'azure_openai', label: 'Azure OpenAI' },
    { value: 'gemini', label: 'Gemini' },
    { value: 'jina', label: 'Jina' },
    { value: 'aws_bedrock', label: 'AWS Bedrock' },
    { value: 'lollms', label: 'Lollms' }
  ], tooltip: 'settings.tooltips.embeddingBinding' },
  { key: 'EMBEDDING_MODEL', type: 'text', defaultValue: 'text-embedding-3-large', section: 'basic' },
  { key: 'EMBEDDING_DIM', type: 'number', defaultValue: '3072', section: 'basic', tooltip: 'settings.tooltips.embeddingDim' },
  { key: 'EMBEDDING_SEND_DIM', type: 'boolean', defaultValue: 'true', section: 'basic', tooltip: 'settings.tooltips.embeddingSendDim' },
  { key: 'EMBEDDING_TOKEN_LIMIT', type: 'number', defaultValue: '8192', section: 'basic' },
  { key: 'EMBEDDING_BINDING_HOST', type: 'text', defaultValue: 'https://api.openai.com/v1', section: 'basic' },
  { key: 'EMBEDDING_BINDING_API_KEY', type: 'password', defaultValue: 'your_api_key', section: 'basic' },
  { key: 'EMBEDDING_TIMEOUT', type: 'number', placeholder: '60', section: 'basic' },
  
  // Azure Embedding
  { key: 'AZURE_EMBEDDING_API_VERSION', type: 'text', placeholder: '2024-08-01-preview', section: 'azure' },
  { key: 'AZURE_EMBEDDING_DEPLOYMENT', type: 'text', placeholder: 'my-text-embedding-3-large-deployment', section: 'azure' },
  
  // Ollama Embedding
  { key: 'OLLAMA_EMBEDDING_NUM_CTX', type: 'number', defaultValue: '8192', section: 'ollama' }
];

// Storage Configuration Fields - REMOVED as they are now handled by ProviderSelector
// See providerConfig.ts for storage provider configurations

// Evaluation Configuration Fields
export const EVALUATION_FIELDS: FieldConfig[] = [
  // LLM Evaluation
  { key: 'EVAL_LLM_MODEL', type: 'text', placeholder: 'gpt-4o-mini', section: 'llm', tooltip: 'settings.tooltips.evalLlmModel' },
  { key: 'EVAL_LLM_BINDING_API_KEY', type: 'password', placeholder: 'your_api_key', section: 'llm', tooltip: 'settings.tooltips.evalLlmApiKey' },
  { key: 'EVAL_LLM_BINDING_HOST', type: 'text', placeholder: 'https://api.openai.com/v1', section: 'llm' },
  
  // Embedding Evaluation
  { key: 'EVAL_EMBEDDING_MODEL', type: 'text', placeholder: 'text-embedding-3-large', section: 'embedding' },
  { key: 'EVAL_EMBEDDING_BINDING_API_KEY', type: 'password', placeholder: 'your_embedding_api_key', section: 'embedding' },
  { key: 'EVAL_EMBEDDING_BINDING_HOST', type: 'text', placeholder: 'https://api.openai.com/v1', section: 'embedding' },
  
  // Performance Tuning
  { key: 'EVAL_MAX_CONCURRENT', type: 'number', placeholder: '2', section: 'performance', tooltip: 'settings.tooltips.evalMaxConcurrent' },
  { key: 'EVAL_QUERY_TOP_K', type: 'number', placeholder: '10', section: 'performance' },
  { key: 'EVAL_LLM_MAX_RETRIES', type: 'number', placeholder: '5', section: 'performance' },
  { key: 'EVAL_LLM_TIMEOUT', type: 'number', placeholder: '180', section: 'performance' }
];

// Export field mappings
export const FIELDS_BY_TAB: Record<string, FieldConfig[]> = {
  basic: BASIC_FIELDS,
  rag: RAG_FIELDS,
  reranking: [], // Now uses ProviderSelector
  llm: [], // Now uses ProviderSelector
  embedding: [], // Now uses ProviderSelector
  storage: [], // Now uses ProviderSelector
  evaluation: EVALUATION_FIELDS
};

// Mark which tabs use provider-based configuration
export const PROVIDER_BASED_TABS = ['reranking', 'llm', 'embedding', 'storage'];

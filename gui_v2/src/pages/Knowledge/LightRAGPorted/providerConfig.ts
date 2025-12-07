// Provider-based configuration structure for LLM, Embedding, Reranking, and Storage

export interface ProviderFieldConfig {
  key: string;
  label?: string; // i18n key like 'fields.model' or direct text
  type: 'text' | 'number' | 'select' | 'textarea' | 'password' | 'boolean';
  defaultValue?: string;
  placeholder?: string;
  tooltip?: string;
  options?: Array<{ value: string; label: string }>;
  required?: boolean;
  isSystemManaged?: boolean;
  disabled?: boolean;
  isDynamicOllamaModel?: boolean; // If true, model list should be fetched dynamically from Ollama API
}

export interface ProviderConfig {
  id: string;
  name: string;
  description?: string;
  fields: ProviderFieldConfig[];
  modelMetadata?: Record<string, { dimensions?: number; max_tokens?: number }>;
  isOllama?: boolean; // If true, this provider uses Ollama and supports dynamic model fetching
}

// ==================== Reranking Providers ====================
export const RERANKING_PROVIDERS: ProviderConfig[] = [
  {
    id: 'null',
    name: 'providers.noneDisabled', // i18n key
    description: 'Disable reranking functionality',
    fields: []
  },
  {
    id: 'cohere',
    name: 'Cohere',
    description: 'Cohere reranking service',
    fields: [
      { key: 'RERANK_MODEL', label: 'Model', type: 'text', defaultValue: 'rerank-english-v3.0', placeholder: 'rerank-english-v3.0', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'https://api.cohere.com/v2/rerank', placeholder: 'https://api.cohere.com/v2/rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'API Key', type: 'password', placeholder: 'your_cohere_api_key', required: true }
    ]
  },
  {
    id: 'jina',
    name: 'Jina AI',
    description: 'Jina AI reranking service',
    fields: [
      { key: 'RERANK_MODEL', label: 'Model', type: 'text', defaultValue: 'jina-reranker-v2-base-multilingual', placeholder: 'jina-reranker-v2-base-multilingual', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'https://api.jina.ai/v1/rerank', placeholder: 'https://api.jina.ai/v1/rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'API Key', type: 'password', placeholder: 'your_jina_api_key', required: true }
    ]
  },
  {
    id: 'aliyun',
    name: 'Aliyun (阿里云)',
    description: 'Aliyun reranking service',
    fields: [
      { key: 'RERANK_MODEL', label: 'Model', type: 'text', defaultValue: 'gte-rerank', placeholder: 'gte-rerank', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank', placeholder: 'https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'API Key', type: 'password', placeholder: 'your_aliyun_api_key', required: true }
    ]
  },
  {
    id: 'voyageai',
    name: 'Voyage AI',
    description: 'Voyage AI reranking service',
    fields: [
      { key: 'RERANK_MODEL', label: 'Model', type: 'text', defaultValue: 'rerank-2', placeholder: 'rerank-2', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'https://api.voyageai.com/v1/rerank', placeholder: 'https://api.voyageai.com/v1/rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'API Key', type: 'password', placeholder: 'your_voyage_api_key', required: true }
    ]
  },
  {
    id: 'siliconflow',
    name: 'SiliconFlow',
    description: 'SiliconFlow (BGE) reranking service',
    fields: [
      { key: 'RERANK_MODEL', label: 'Model', type: 'text', defaultValue: 'BAAI/bge-reranker-v2-m3', placeholder: 'BAAI/bge-reranker-v2-m3', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'https://api.siliconflow.cn/v1/rerank', placeholder: 'https://api.siliconflow.cn/v1/rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'API Key', type: 'password', placeholder: 'your_siliconflow_api_key', required: true }
    ]
  },
  {
    id: 'ollama',
    name: 'Ollama',
    description: 'Ollama local reranking service',
    isOllama: true,
    fields: [
      { key: 'RERANK_MODEL', label: 'fields.model', type: 'text', defaultValue: 'bge-m3', placeholder: 'bge-m3', required: true, isDynamicOllamaModel: true },
      { key: 'RERANK_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'http://127.0.0.1:11434' },
      { key: 'RERANK_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'fields.optional' }
    ]
  },
  {
    id: 'baidu_qianfan',
    name: 'Baidu Qianfan',
    description: 'Baidu Qianfan reranking service',
    fields: [
      { key: 'RERANK_MODEL', label: 'Model', type: 'text', defaultValue: 'bce-reranker-base_v1', placeholder: 'bce-reranker-base_v1', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/reranker', placeholder: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/reranker' },
      { key: 'RERANK_BINDING_API_KEY', label: 'API Key', type: 'password', placeholder: 'your_baidu_api_key', required: true }
    ]
  }
];

export const RERANKING_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'RERANK_BY_DEFAULT', label: 'fields.enableByDefault', type: 'boolean', placeholder: 'True', tooltip: 'tooltips.rerankByDefault' },
  { key: 'MIN_RERANK_SCORE', label: 'fields.minRerankScore', type: 'number', placeholder: '0.0', tooltip: 'tooltips.minRerankScore' }
];

// ==================== LLM Providers ====================
export const LLM_PROVIDERS: ProviderConfig[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'OpenAI GPT models',
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'gpt-4o', required: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.openai.com/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-...', required: true },
      { key: 'OPENAI_LLM_TEMPERATURE', label: 'fields.temperature', type: 'number', placeholder: '0.9' },
      { key: 'OPENAI_LLM_MAX_COMPLETION_TOKENS', label: 'fields.maxCompletionTokens', type: 'number', defaultValue: '9000' },
      { key: 'OPENAI_LLM_REASONING_EFFORT', label: 'fields.reasoningEffort', type: 'select', placeholder: 'minimal', options: [
        { value: 'minimal', label: 'options.minimal' },
        { value: 'medium', label: 'options.medium' },
        { value: 'high', label: 'options.high' }
      ]}
    ]
  },
  {
    id: 'ollama',
    name: 'Ollama',
    description: 'Local Ollama models',
    isOllama: true,
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', placeholder: 'qwen2.5:32b', required: true, isDynamicOllamaModel: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'http://127.0.0.1:11434' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'fields.optional' },
      { key: 'OLLAMA_LLM_NUM_CTX', label: 'fields.contextWindow', type: 'number', defaultValue: '32768', tooltip: 'tooltips.ollamaNumCtx' },
      { key: 'OLLAMA_LLM_NUM_PREDICT', label: 'fields.maxPredictTokens', type: 'number', placeholder: '9000' }
    ]
  },
  {
    id: 'azure_openai',
    name: 'Azure OpenAI',
    description: 'Microsoft Azure OpenAI Service',
    fields: [
      { key: 'LLM_MODEL', label: 'Model', type: 'text', placeholder: 'gpt-4o', required: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', placeholder: 'https://your-resource.openai.azure.com', required: true },
      { key: 'LLM_BINDING_API_KEY', label: 'API Key', type: 'password', required: true },
      { key: 'AZURE_OPENAI_API_VERSION', label: 'API Version', type: 'text', placeholder: '2024-08-01-preview' },
      { key: 'AZURE_OPENAI_DEPLOYMENT', label: 'Deployment Name', type: 'text', placeholder: 'my-gpt-deployment', required: true }
    ]
  },
  {
    id: 'google',
    name: 'Google Gemini',
    description: 'Google Gemini models',
    fields: [
      { key: 'LLM_MODEL', label: 'Model', type: 'text', placeholder: 'gemini-2.0-flash-thinking-exp', required: true },
      { key: 'LLM_BINDING_API_KEY', label: 'API Key', type: 'password', required: true },
      { key: 'GEMINI_LLM_MAX_OUTPUT_TOKENS', label: 'Max Output Tokens', type: 'number', placeholder: '9000' },
      { key: 'GEMINI_LLM_TEMPERATURE', label: 'Temperature', type: 'number', placeholder: '0.7' },
      { key: 'GEMINI_LLM_THINKING_CONFIG', label: 'Thinking Config (JSON)', type: 'textarea', placeholder: '{"thinking_budget": -1}', tooltip: 'tooltips.geminiThinking' }
    ]
  },
  {
    id: 'bedrock',
    name: 'AWS Bedrock',
    description: 'Amazon Bedrock models',
    fields: [
      { key: 'LLM_MODEL', label: 'Model ID', type: 'text', placeholder: 'anthropic.claude-3-5-sonnet-20241022-v2:0', required: true },
      { key: 'BEDROCK_LLM_TEMPERATURE', label: 'Temperature', type: 'number', placeholder: '1.0' }
    ]
  },
  {
    id: 'lollms',
    name: 'Lollms',
    description: 'Lollms local server',
    fields: [
      { key: 'LLM_MODEL', label: 'Model', type: 'text', required: true },
      { key: 'LLM_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'http://localhost:9600' }
    ]
  },
  {
    id: 'dashscope',
    name: 'Qwen (DashScope)',
    description: 'Alibaba Qwen models via DashScope',
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'qwen-max', required: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-...', required: true }
    ]
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    description: 'DeepSeek AI models',
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'deepseek-chat', required: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.deepseek.com/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-...', required: true }
    ]
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Anthropic Claude models',
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'claude-3-5-sonnet-20241022', required: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.anthropic.com' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-ant-...', required: true }
    ]
  },
  {
    id: 'baidu_qianfan',
    name: 'Baidu Qianfan',
    description: 'Baidu Qianfan (ERNIE) models',
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'ernie-4.0-8k', required: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://aip.baidubce.com' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'bytedance',
    name: 'Bytedance Doubao',
    description: 'Bytedance Doubao (豆包) models',
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'doubao-pro-32k', required: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://ark.cn-beijing.volces.com/api/v3' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  }
];

export const LLM_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'LLM_TIMEOUT', label: 'fields.requestTimeout', type: 'number', placeholder: '180', tooltip: 'tooltips.llmTimeout' }
];

// ==================== Embedding Providers ====================
export const EMBEDDING_PROVIDERS: ProviderConfig[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'OpenAI embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'text-embedding-3-large', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '3072', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.openai.com/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true },
      { key: 'EMBEDDING_TOKEN_LIMIT', label: 'fields.tokenLimit', type: 'number', defaultValue: '8192' }
    ]
  },
  {
    id: 'ollama',
    name: 'Ollama',
    description: 'Local Ollama embedding models',
    isOllama: true,
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', placeholder: 'bge-m3:latest', required: true, isDynamicOllamaModel: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', placeholder: '1024', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'http://127.0.0.1:11434' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'fields.optional' }
    ]
  },
  {
    id: 'azure_openai',
    name: 'Azure OpenAI',
    description: 'Azure OpenAI embedding service',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'Model', type: 'text', placeholder: 'text-embedding-3-large', required: true },
      { key: 'EMBEDDING_DIM', label: 'Dimensions', type: 'number', placeholder: '3072', defaultValue: '3072', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', placeholder: 'https://your-resource.openai.azure.com', required: true },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'google',
    name: 'Google Gemini',
    description: 'Google Gemini embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'Model', type: 'text', placeholder: 'text-embedding-004', required: true },
      { key: 'EMBEDDING_DIM', label: 'Dimensions', type: 'number', placeholder: '768', defaultValue: '768', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'API Key', type: 'password', required: true }
    ]
  },
  {
    id: 'jina',
    name: 'Jina AI',
    description: 'Jina AI embedding service',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'Model', type: 'text', placeholder: 'jina-embeddings-v3', required: true },
      { key: 'EMBEDDING_DIM', label: 'Dimensions', type: 'number', placeholder: '1024', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'https://api.jina.ai/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'API Key', type: 'password', required: true }
    ]
  },
  {
    id: 'bedrock',
    name: 'AWS Bedrock',
    description: 'AWS Bedrock embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'Model ID', type: 'text', placeholder: 'amazon.titan-embed-text-v2:0', required: true },
      { key: 'EMBEDDING_DIM', label: 'Dimensions', type: 'number', placeholder: '1024', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' }
    ]
  },
  {
    id: 'lollms',
    name: 'Lollms',
    description: 'Lollms embedding service',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'Model', type: 'text', required: true },
      { key: 'EMBEDDING_BINDING_HOST', label: 'API Host', type: 'text', defaultValue: 'http://localhost:9600' }
    ]
  },
  {
    id: 'alibaba_qwen',
    name: 'Qwen (DashScope)',
    description: 'Alibaba Qwen embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'text-embedding-v3', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'baidu_qianfan',
    name: 'Baidu Qianfan',
    description: 'Baidu Qianfan embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'Embedding-V1', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://aip.baidubce.com' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'doubao',
    name: 'Bytedance Doubao',
    description: 'Bytedance Doubao embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'doubao-embedding', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://ark.cn-beijing.volces.com/api/v3' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'voyageai',
    name: 'Voyage AI',
    description: 'Voyage AI embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'voyage-3', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.voyageai.com/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'cohere',
    name: 'Cohere',
    description: 'Cohere embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'embed-english-v3.0', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.cohere.com/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'huggingface',
    name: 'HuggingFace',
    description: 'HuggingFace embedding models',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'sentence-transformers/all-MiniLM-L6-v2', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '384', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api-inference.huggingface.co' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  }
];

export const EMBEDDING_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'EMBEDDING_TIMEOUT', label: 'fields.requestTimeout', type: 'number', placeholder: '30', tooltip: 'tooltips.embeddingTimeout' },
  { 
    key: 'EMBEDDING_SEND_DIM', 
    label: 'fields.sendDimensions', 
    type: 'boolean', 
    defaultValue: 'true', 
    tooltip: 'tooltips.embeddingSendDim',
    disabled: true  // Make read-only - auto-determined by provider
  }
];

// ==================== Common Configurations ====================

export const STORAGE_COMMON_POSTGRES: ProviderFieldConfig[] = [
  { key: 'POSTGRES_HOST', label: 'fields.host', type: 'text', placeholder: 'localhost' },
  { key: 'POSTGRES_PORT', label: 'fields.port', type: 'number', placeholder: '5432' },
  { key: 'POSTGRES_USER', label: 'fields.user', type: 'text', placeholder: 'postgres' },
  { key: 'POSTGRES_PASSWORD', label: 'fields.password', type: 'password' },
  { key: 'POSTGRES_DATABASE', label: 'fields.database', type: 'text', placeholder: 'lightrag' },
  { key: 'POSTGRES_MAX_CONNECTIONS', label: 'fields.maxConnections', type: 'number', placeholder: '12' },
  { key: 'POSTGRES_SSL_MODE', label: 'fields.sslMode', type: 'select', placeholder: 'require', options: [
    { value: 'disable', label: 'options.disabled' },
    { value: 'allow', label: 'Allow' },
    { value: 'prefer', label: 'Prefer' },
    { value: 'require', label: 'Require' },
    { value: 'verify-ca', label: 'Verify CA' },
    { value: 'verify-full', label: 'Verify Full' }
  ]},
  { key: 'POSTGRES_CONNECTION_RETRIES', label: 'fields.connectionRetries', type: 'number', placeholder: '3', tooltip: 'tooltips.connectionRetries' },
  { key: 'POSTGRES_CONNECTION_RETRY_BACKOFF', label: 'fields.retryBackoff', type: 'number', placeholder: '0.5', tooltip: 'tooltips.retryBackoff' },
  { key: 'POSTGRES_CONNECTION_RETRY_MAX_BACKOFF', label: 'fields.retryMaxBackoff', type: 'number', placeholder: '5.0' },
  { key: 'POSTGRES_POOL_CLOSE_TIMEOUT', label: 'fields.poolCloseTimeout', type: 'number', placeholder: '5.0' },
  { key: 'POSTGRES_STATEMENT_CACHE_SIZE', label: 'fields.statementCacheSize', type: 'number', placeholder: '100' }
];

// ==================== Storage Providers ====================
export const STORAGE_KV_PROVIDERS: ProviderConfig[] = [
  { id: 'JsonKVStorage', name: 'JSON File', description: 'Local JSON file storage', fields: [] },
  { 
    id: 'RedisKVStorage', 
    name: 'Redis', 
    description: 'Redis key-value store', 
    fields: [
      { key: 'REDIS_URI', label: 'fields.uri', type: 'text', placeholder: 'redis://localhost:6379', tooltip: 'tooltips.redisUri' },
      { key: 'REDIS_HOST', label: 'fields.host', type: 'text', placeholder: 'localhost' },
      { key: 'REDIS_PORT', label: 'fields.port', type: 'number', placeholder: '6379' },
      { key: 'REDIS_PASSWORD', label: 'fields.password', type: 'password', placeholder: 'optional' },
      { key: 'REDIS_MAX_CONNECTIONS', label: 'Max Connections', type: 'number', placeholder: '100' },
      { key: 'REDIS_RETRY_ATTEMPTS', label: 'Retry Attempts', type: 'number', placeholder: '3' }
    ]
  },
  { 
    id: 'PGKVStorage', 
    name: 'PostgreSQL', 
    description: 'PostgreSQL storage', 
    fields: [] // Common fields moved to STORAGE_COMMON_POSTGRES
  },
  { 
    id: 'MongoKVStorage', 
    name: 'MongoDB', 
    description: 'MongoDB key-value storage', 
    fields: [
      { key: 'MONGO_URI', label: 'fields.uri', type: 'text', placeholder: 'mongodb://root:root@localhost:27017/' },
      { key: 'MONGO_DATABASE', label: 'fields.database', type: 'text', placeholder: 'LightRAG' }
    ] 
  }
];

export const STORAGE_VECTOR_PROVIDERS: ProviderConfig[] = [
  { id: 'NanoVectorDBStorage', name: 'NanoVectorDB', description: 'Lightweight local vector database', fields: [] },
  { id: 'FaissVectorDBStorage', name: 'Faiss', description: 'Facebook AI Similarity Search', fields: [] },
  { id: 'MilvusVectorDBStorage', name: 'Milvus', description: 'Milvus vector database', fields: [
    { key: 'MILVUS_URI', label: 'fields.uri', type: 'text', placeholder: 'http://localhost:19530' },
    { key: 'MILVUS_DB_NAME', label: 'fields.database', type: 'text', placeholder: 'lightrag' },
    { key: 'MILVUS_USER', label: 'fields.user', type: 'text', placeholder: 'root' },
    { key: 'MILVUS_PASSWORD', label: 'fields.password', type: 'password' }
  ]},
  { id: 'QdrantVectorDBStorage', name: 'Qdrant', description: 'Qdrant vector search engine', fields: [
    { key: 'QDRANT_URL', label: 'fields.uri', type: 'text', placeholder: 'http://localhost:6333' },
    { key: 'QDRANT_API_KEY', label: 'fields.apiKey', type: 'password' }
  ]},
  { id: 'PGVectorStorage', name: 'PostgreSQL (pgvector)', description: 'PostgreSQL with pgvector extension', fields: [
    { key: 'POSTGRES_VECTOR_INDEX_TYPE', label: 'fields.vectorIndexType', type: 'select', placeholder: 'HNSW', options: [
      { value: 'HNSW', label: 'HNSW' },
      { value: 'IVFFlat', label: 'IVFFlat' },
      { value: 'VCHORDRQ', label: 'VCHORDRQ' }
    ]},
    { key: 'POSTGRES_HNSW_M', label: 'HNSW M', type: 'number', placeholder: '16' },
    { key: 'POSTGRES_HNSW_EF', label: 'HNSW EF', type: 'number', placeholder: '200' },
    { key: 'POSTGRES_IVFFLAT_LISTS', label: 'IVFFlat Lists', type: 'number', placeholder: '100' },
    { key: 'POSTGRES_VCHORDRQ_BUILD_OPTIONS', label: 'VCHORDRQ Build Options', type: 'text', placeholder: '' },
    { key: 'POSTGRES_VCHORDRQ_PROBES', label: 'VCHORDRQ Probes', type: 'number', placeholder: '' },
    { key: 'POSTGRES_VCHORDRQ_EPSILON', label: 'VCHORDRQ Epsilon', type: 'number', placeholder: '1.9' }
  ]},
  { 
    id: 'MongoVectorDBStorage', 
    name: 'MongoDB (Atlas)', 
    description: 'MongoDB Atlas vector storage', 
    fields: [
      { key: 'MONGO_URI', label: 'fields.uri', type: 'text', placeholder: 'mongodb+srv://...' },
      { key: 'MONGO_DATABASE', label: 'fields.database', type: 'text', placeholder: 'LightRAG' }
    ] 
  }
];

export const STORAGE_GRAPH_PROVIDERS: ProviderConfig[] = [
  { id: 'NetworkXStorage', name: 'NetworkX', description: 'Local NetworkX graph storage', fields: [] },
  { id: 'Neo4JStorage', name: 'Neo4j', description: 'Neo4j graph database', fields: [
    { key: 'NEO4J_URI', label: 'fields.uri', type: 'text', placeholder: 'neo4j+s://xxx.databases.neo4j.io' },
    { key: 'NEO4J_USERNAME', label: 'fields.username', type: 'text', placeholder: 'neo4j' },
    { key: 'NEO4J_PASSWORD', label: 'fields.password', type: 'password' },
    { key: 'NEO4J_DATABASE', label: 'fields.database', type: 'text', placeholder: 'neo4j' },
    { key: 'NEO4J_MAX_CONNECTION_POOL_SIZE', label: 'Max Pool Size', type: 'number', placeholder: '100' },
    { key: 'NEO4J_KEEP_ALIVE', label: 'Keep Alive', type: 'boolean', placeholder: 'true' }
  ]},
  { id: 'MemgraphStorage', name: 'Memgraph', description: 'Memgraph graph database', fields: [
    { key: 'MEMGRAPH_URI', label: 'fields.uri', type: 'text', placeholder: 'bolt://localhost:7687' },
    { key: 'MEMGRAPH_USERNAME', label: 'fields.username', type: 'text' },
    { key: 'MEMGRAPH_PASSWORD', label: 'fields.password', type: 'password' },
    { key: 'MEMGRAPH_DATABASE', label: 'fields.database', type: 'text', placeholder: 'memgraph' }
  ]},
  { id: 'PGGraphStorage', name: 'PostgreSQL (Apache AGE)', description: 'PostgreSQL with Apache AGE', fields: [] // Common fields moved to STORAGE_COMMON_POSTGRES
  },
  { 
    id: 'MongoGraphStorage', 
    name: 'MongoDB', 
    description: 'MongoDB graph storage', 
    fields: [
      { key: 'MONGO_URI', label: 'fields.uri', type: 'text', placeholder: 'mongodb://root:root@localhost:27017/' },
      { key: 'MONGO_DATABASE', label: 'fields.database', type: 'text', placeholder: 'LightRAG' }
    ] 
  }
];

export const STORAGE_DOC_STATUS_PROVIDERS: ProviderConfig[] = [
  { id: 'JsonDocStatusStorage', name: 'JSON File', description: 'Local JSON file storage', fields: [] },
  { id: 'RedisDocStatusStorage', name: 'Redis', description: 'Redis storage', fields: [
    { key: 'REDIS_URI', label: 'fields.uri', type: 'text', placeholder: 'redis://localhost:6379' },
    { key: 'REDIS_HOST', label: 'fields.host', type: 'text', placeholder: 'localhost' },
    { key: 'REDIS_PORT', label: 'fields.port', type: 'number', placeholder: '6379' },
    { key: 'REDIS_PASSWORD', label: 'fields.password', type: 'password', placeholder: 'optional' },
    { key: 'REDIS_MAX_CONNECTIONS', label: 'Max Connections', type: 'number', placeholder: '100' }
  ]},
  { id: 'PGDocStatusStorage', name: 'PostgreSQL', description: 'PostgreSQL storage', fields: [] // Common fields moved to STORAGE_COMMON_POSTGRES
  },
  { 
    id: 'MongoDocStatusStorage', 
    name: 'MongoDB', 
    description: 'MongoDB document status storage', 
    fields: [
      { key: 'MONGO_URI', label: 'fields.uri', type: 'text', placeholder: 'mongodb://root:root@localhost:27017/' },
      { key: 'MONGO_DATABASE', label: 'fields.database', type: 'text', placeholder: 'LightRAG' }
    ] 
  }
];

// Remove STORAGE_COMMON_FIELDS as each provider now has its own fields

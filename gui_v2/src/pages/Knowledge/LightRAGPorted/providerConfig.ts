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
  regions?: ('cn' | 'intl')[]; // Regions where this provider is available. If undefined, available in all regions.
}

// ==================== Region Configuration ====================
// CN version: DeepSeek (default), Qwen (DashScope), Baidu Qianfan (ERNIE), ChatGLM (Zhipu), Bytedance Doubao
// INTL version: OpenAI (default), Anthropic Claude, Google Gemini, AWS Bedrock, Azure OpenAI
// DeepSeek is available in both regions

export const DEFAULT_PROVIDER_BY_REGION = {
  cn: {
    provider: 'deepseek',
    model: 'deepseek-v4-flash',
    displayName: 'DeepSeek V4 Flash'
  },
  intl: {
    provider: 'openai',
    model: 'gpt-5.6-sol',
    displayName: 'GPT-5.6 Sol'
  }
} as const;

/**
 * Filter providers by region.
 * Providers without a regions field are available in all regions.
 */
export function getProvidersByRegion<T extends ProviderConfig>(
  providers: T[],
  region: 'cn' | 'intl'
): T[] {
  return providers.filter(p => !p.regions || p.regions.includes(region));
}

/**
 * Get the default provider config for a region.
 */
export function getDefaultProvider<T extends ProviderConfig>(
  providers: T[],
  region: 'cn' | 'intl'
): T | undefined {
  return providers.find(p => p.id === DEFAULT_PROVIDER_BY_REGION[region].provider);
}

// ==================== Reranking Providers ====================
// All regions: Jina, Alibaba Qwen, SiliconFlow, Baidu, Ollama, RyoAIS
// INTL only: Cohere, Voyage AI
export const RERANKING_PROVIDERS: ProviderConfig[] = [
  {
    id: 'null',
    name: 'providers.noneDisabled',
    description: 'Disable reranking functionality',
    fields: []
  },
  {
    id: 'cohere',
    name: 'Cohere',
    description: 'Cohere reranking service (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'RERANK_MODEL', label: 'fields.model', type: 'text', defaultValue: 'rerank-v3.5', placeholder: 'rerank-v3.5', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.cohere.com/v2/rerank', placeholder: 'https://api.cohere.com/v2/rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'your_cohere_api_key', required: true }
    ]
  },
  {
    id: 'jina',
    name: 'Jina AI',
    description: 'Jina AI reranking service (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'RERANK_MODEL', label: 'fields.model', type: 'text', defaultValue: 'jina-reranker-v2-base-multilingual', placeholder: 'jina-reranker-v2-base-multilingual', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.jina.ai/v1/rerank', placeholder: 'https://api.jina.ai/v1/rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'your_jina_api_key', required: true }
    ]
  },
  {
    id: 'aliyun',
    name: 'Aliyun (阿里云)',
    description: 'Aliyun reranking service (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'RERANK_MODEL', label: 'fields.model', type: 'text', defaultValue: 'gte-rerank-v2', placeholder: 'gte-rerank-v2', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank', placeholder: 'https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'your_aliyun_api_key', required: true }
    ]
  },
  {
    id: 'voyageai',
    name: 'Voyage AI',
    description: 'Voyage AI reranking service (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'RERANK_MODEL', label: 'fields.model', type: 'text', defaultValue: 'rerank-2', placeholder: 'rerank-2', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.voyageai.com/v1/rerank', placeholder: 'https://api.voyageai.com/v1/rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'your_voyage_api_key', required: true }
    ]
  },
  {
    id: 'siliconflow',
    name: 'SiliconFlow',
    description: 'SiliconFlow (BGE) reranking service (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'RERANK_MODEL', label: 'fields.model', type: 'text', defaultValue: 'BAAI/bge-reranker-v2-m3', placeholder: 'BAAI/bge-reranker-v2-m3', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.siliconflow.cn/v1/rerank', placeholder: 'https://api.siliconflow.cn/v1/rerank' },
      { key: 'RERANK_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'your_siliconflow_api_key', required: true }
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
    description: 'Baidu Qianfan reranking service (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'RERANK_MODEL', label: 'fields.model', type: 'text', defaultValue: 'bce-reranker-base_v1', placeholder: 'bce-reranker-base_v1', required: true },
      { key: 'RERANK_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/reranker', placeholder: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/reranker' },
      { key: 'RERANK_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'your_baidu_api_key', required: true }
    ]
  },
  {
    id: 'ryoais',
    name: 'RyoAIS',
    description: 'RyoAIS local reranking service (OpenAI-compatible)',
    fields: [
      { key: 'RERANK_MODEL', label: 'fields.model', type: 'text', defaultValue: 'jina-reranker-v2-base-multilingual', placeholder: 'jina-reranker-v2-base-multilingual', required: true, tooltip: 'Generic model name (will be mapped to RyoAIS BGE model by proxy)' },
      { key: 'RERANK_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'http://192.168.1.43:8000/v1', placeholder: 'http://localhost:8000/v1' },
      { key: 'RERANK_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'fields.optional' }
    ]
  }
];

export const RERANKING_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'RERANK_BY_DEFAULT', label: 'fields.enableByDefault', type: 'boolean', placeholder: 'True', tooltip: 'tooltips.rerankByDefault' },
  { key: 'MIN_RERANK_SCORE', label: 'fields.minRerankScore', type: 'number', placeholder: '0.15', tooltip: 'tooltips.minRerankScore' }
];

// ==================== LLM Providers ====================
// All regions: OpenAI, DeepSeek, Qwen, Kimi, MiniMax, ChatGLM, Ollama, RyoAIS
// INTL preferred: Anthropic Claude, Google Gemini, Azure, AWS Bedrock
// CN preferred: Bytedance Doubao

export const LLM_PROVIDERS: ProviderConfig[] = [
  // ===== INTL Only Providers =====
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'OpenAI GPT-5.6 models (INTL default)',
    regions: ['intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'gpt-5.6-sol', required: true, tooltip: 'Models: gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna, gpt-5.5' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.openai.com/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-...', required: true },
      { key: 'OPENAI_LLM_TEMPERATURE', label: 'fields.temperature', type: 'number', placeholder: '0.9' },
      { key: 'OPENAI_LLM_MAX_COMPLETION_TOKENS', label: 'fields.maxCompletionTokens', type: 'number', defaultValue: '9000' }
    ]
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Anthropic Claude 5 models (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'claude-opus-5', required: true, tooltip: 'Models: claude-fable-5, claude-opus-5, claude-sonnet-5, claude-haiku-4.5' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.anthropic.com' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-ant-...', required: true }
    ]
  },
  {
    id: 'google',
    name: 'Google Gemini',
    description: 'Google Gemini 3.7 models (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'gemini-3.7-flash', required: true, tooltip: 'Models: gemini-3.7-flash, gemini-3.6-flash, gemini-3.5-flash, gemini-3.1-pro' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true },
      { key: 'GEMINI_LLM_MAX_OUTPUT_TOKENS', label: 'fields.maxOutputTokens', type: 'number', placeholder: '9000' },
      { key: 'GEMINI_LLM_TEMPERATURE', label: 'fields.temperature', type: 'number', placeholder: '0.7' }
    ]
  },
  {
    id: 'azure_openai',
    name: 'Azure OpenAI',
    description: 'Azure OpenAI GPT-5.6 models (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.deploymentName', type: 'text', defaultValue: 'gpt-5.6-sol', required: true },
      { key: 'AZURE_OPENAI_ENDPOINT', label: 'fields.azureEndpoint', type: 'text', defaultValue: 'https://your-resource.openai.azure.com', required: true },
      { key: 'AZURE_OPENAI_API_KEY', label: 'fields.apiKey', type: 'password', required: true },
      { key: 'AZURE_OPENAI_API_VERSION', label: 'fields.apiVersion', type: 'text', defaultValue: '2024-02-15-preview' }
    ]
  },
  {
    id: 'bedrock',
    name: 'AWS Bedrock',
    description: 'AWS Bedrock Claude 5 models (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'anthropic.claude-opus-53', required: true, tooltip: 'Models: claude-fable-53, claude-opus-53, claude-sonnet-53, nova-pro' },
      { key: 'AWS_ACCESS_KEY_ID', label: 'fields.awsAccessKey', type: 'text' },
      { key: 'AWS_SECRET_ACCESS_KEY', label: 'fields.awsSecretKey', type: 'password' },
      { key: 'AWS_REGION', label: 'fields.awsRegion', type: 'text', defaultValue: 'us-east-1' }
    ]
  },
  // ===== CN Only Providers =====
  {
    id: 'deepseek',
    name: 'DeepSeek',
    description: 'DeepSeek V4 models (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'deepseek-v4-flash', required: true, tooltip: 'Models: deepseek-v4-flash, deepseek-v4-pro, deepseek-chat, deepseek-reasoner' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.deepseek.com/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-...', required: true }
    ]
  },
  {
    id: 'dashscope',
    name: 'Qwen (DashScope)',
    description: 'Alibaba Qwen3.8 models (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'qwen3.8-max', required: true, tooltip: 'Models: qwen3.8-max, qwen3.7-max, qwen3.7-plus, qwen3.6-flash' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-...', required: true }
    ]
  },
  {
    id: 'baidu_qianfan',
    name: 'Baidu Qianfan',
    description: 'Baidu ERNIE 5.1 models (CN)',
    regions: ['cn'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'ernie-5.1', required: true, tooltip: 'Models: ernie-5.1, ernie-5.0, ernie-5.0-thinking-latest, ernie-4.5-turbo-128k' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://qianfan.baidubce.com/v2' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'zhipuai',
    name: 'ChatGLM (Zhipu AI)',
    description: 'Zhipu AI GLM-5.3 models (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'glm-5.3', required: true, tooltip: 'Models: glm-5.3, glm-5.2, glm-5.1, glm-5, glm-5v-turbo' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://open.bigmodel.cn/api/paas/v4' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'bytedance',
    name: 'Bytedance Doubao',
    description: 'Bytedance Doubao Seed 1.6 models (CN)',
    regions: ['cn'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'doubao-seed-1.6', required: true, tooltip: 'Models: doubao-seed-1.6, doubao-seed-1.6-thinking, doubao-seed-1.6-vision' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://ark.cn-beijing.volces.com/api/v3' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password' }
    ]
  },
  {
    id: 'moonshot',
    name: 'Kimi (Moonshot AI)',
    description: 'Moonshot AI Kimi models (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'kimi-k2', required: true, tooltip: 'Models: kimi-k2, kimi-k2.5, kimi-k1.5, moonshot-v1-32k' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.moonshot.cn/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'sk-...', required: true }
    ]
  },
  {
    id: 'minimax',
    name: 'MiniMax',
    description: 'MiniMax AI models (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'MiniMax-Text-01', required: true, tooltip: 'Models: MiniMax-Text-01, abab6.5s' },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.minimax.chat/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: '...', required: true }
    ]
  },
  // ===== Local Providers (Both regions) =====
  {
    id: 'ollama',
    name: 'Ollama',
    description: 'Local Ollama models (both regions)',
    isOllama: true,
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'llama3.3', required: true, isDynamicOllamaModel: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'http://localhost:11434' }
    ]
  },
  {
    id: 'ryoais',
    name: 'RyoAIS',
    description: 'RyoAIS local models (both regions)',
    fields: [
      { key: 'LLM_MODEL', label: 'fields.model', type: 'text', defaultValue: 'qwen2.5-14b', required: true },
      { key: 'LLM_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'http://localhost/v1' },
      { key: 'LLM_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'fields.optional' }
    ]
  }
];

// ==================== Embedding Providers ====================
// CN: Jina, Qwen, Baidu, Bytedance, SiliconFlow, Ollama, RyoAIS
// INTL: OpenAI, Jina, Qwen, Baidu, HuggingFace, Bytedance, Azure, Cohere, Voyage, Ollama, RyoAIS

export const DEFAULT_EMBEDDING_BY_REGION = {
  cn: {
    provider: 'jina',
    model: 'jina-embeddings-v3',
    displayName: 'Jina Embeddings V3'
  },
  intl: {
    provider: 'openai',
    model: 'text-embedding-3-large',
    displayName: 'OpenAI text-embedding-3-large'
  }
} as const;

export const EMBEDDING_PROVIDERS: ProviderConfig[] = [
  // ===== CN/INTL Both (global) =====
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'OpenAI embedding models (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'text-embedding-3-large', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '3072', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.openai.com/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true },
      { key: 'EMBEDDING_TOKEN_LIMIT', label: 'fields.tokenLimit', type: 'number', defaultValue: '8192' }
    ]
  },
  {
    id: 'jina',
    name: 'Jina AI',
    description: 'Jina AI embeddings (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'jina-embeddings-v3', required: true, tooltip: 'Models: jina-embeddings-v3, jina-embeddings-v2-base-en' },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.jina.ai/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'ollama',
    name: 'Ollama',
    description: 'Local Ollama embeddings (both regions)',
    isOllama: true,
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'nomic-embed-text', required: true, isDynamicOllamaModel: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '768', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'http://localhost:11434' }
    ]
  },
  // ===== CN Only =====
  {
    id: 'alibaba_qwen',
    name: 'Qwen (DashScope)',
    description: 'Qwen embeddings (both regions)',
    regions: ['cn', 'intl'],
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
    description: 'Baidu embeddings (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'tao-8k', required: true, tooltip: 'Models: tao-8k, bge-large-zh, bge-large-en' },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://qianfan.baidubce.com/v2' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'doubao',
    name: 'Bytedance Doubao',
    description: 'Doubao embeddings (both regions)',
    regions: ['cn', 'intl'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'doubao-embedding', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://ark.cn-beijing.volces.com/api/v3/embeddings' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password' }
    ]
  },
  {
    id: 'siliconflow',
    name: 'SiliconFlow',
    description: 'SiliconFlow BGE embeddings (CN)',
    regions: ['cn'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'BAAI/bge-m3', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.siliconflow.cn/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  // ===== INTL Only =====
  {
    id: 'cohere',
    name: 'Cohere',
    description: 'Cohere embeddings (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'embed-english-v3.0', required: true, tooltip: 'Models: embed-english-v3.0, embed-multilingual-v3.0' },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.cohere.ai/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'voyageai',
    name: 'Voyage AI',
    description: 'Voyage AI embeddings (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'voyage-3', required: true, tooltip: 'Models: voyage-3, voyage-3-lite, voyage-large-2' },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api.voyageai.com/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  {
    id: 'huggingface',
    name: 'HuggingFace',
    description: 'HuggingFace embeddings (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'sentence-transformers/all-MiniLM-L6-v2', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '384', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'https://api-inference.huggingface.co' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password' }
    ]
  },
  {
    id: 'google',
    name: 'Google Gemini',
    description: 'Google Gemini embeddings (INTL)',
    regions: ['intl'],
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'text-embedding-004', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '768', tooltip: 'tooltips.embeddingDim' },
      { key: 'GEMINI_API_KEY', label: 'fields.apiKey', type: 'password', required: true }
    ]
  },
  // ===== Local (Both) =====
  {
    id: 'ryoais',
    name: 'RyoAIS',
    description: 'RyoAIS embeddings (both regions)',
    fields: [
      { key: 'EMBEDDING_MODEL', label: 'fields.model', type: 'text', defaultValue: 'bge-m3', required: true },
      { key: 'EMBEDDING_DIM', label: 'fields.dimensions', type: 'number', defaultValue: '1024', tooltip: 'tooltips.embeddingDim' },
      { key: 'EMBEDDING_BINDING_HOST', label: 'fields.apiHost', type: 'text', defaultValue: 'http://localhost/v1' },
      { key: 'EMBEDDING_BINDING_API_KEY', label: 'fields.apiKey', type: 'password', placeholder: 'fields.optional' }
    ]
  }
];

// ==================== LLM Common Fields ====================
export const LLM_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'LLM_TIMEOUT', label: 'fields.requestTimeout', type: 'number', placeholder: '60' }
];

// ==================== Embedding Common Fields ====================
export const EMBEDDING_COMMON_FIELDS: ProviderFieldConfig[] = [
  { key: 'EMBEDDING_TIMEOUT', label: 'fields.requestTimeout', type: 'number', placeholder: '60', tooltip: 'tooltips.embeddingTimeout' }
];

// ==================== Storage Common Fields ====================
export const STORAGE_COMMON_POSTGRES: ProviderFieldConfig[] = [
  { key: 'POSTGRES_HOST', label: 'fields.postgresHost', type: 'text', defaultValue: 'localhost' },
  { key: 'POSTGRES_PORT', label: 'fields.postgresPort', type: 'number', defaultValue: '5432' },
  { key: 'POSTGRES_USER', label: 'fields.postgresUser', type: 'text', defaultValue: 'postgres' },
  { key: 'POSTGRES_PASSWORD', label: 'fields.postgresPassword', type: 'password' },
  { key: 'POSTGRES_DATABASE', label: 'fields.postgresDatabase', type: 'text', defaultValue: 'lightrag' }
];

// ==================== Storage Providers ====================
export const STORAGE_PROVIDERS: ProviderConfig[] = [
  {
    id: 'null',
    name: 'providers.noneDisabled',
    description: 'Disable storage functionality',
    fields: []
  },
  {
    id: 'local',
    name: 'Local Disk',
    description: 'Store files on local disk',
    fields: [
      { key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './storage', placeholder: './storage', required: true }
    ]
  },
  {
    id: 's3',
    name: 'S3 Compatible',
    description: 'Store files in S3 compatible storage',
    fields: [
      { key: 'STORAGE_S3_BUCKET', label: 'fields.s3Bucket', type: 'text', required: true },
      { key: 'STORAGE_S3_REGION', label: 'fields.s3Region', type: 'text', defaultValue: 'us-east-1' },
      { key: 'STORAGE_S3_ENDPOINT', label: 'fields.s3Endpoint', type: 'text', placeholder: 'https://s3.amazonaws.com' },
      { key: 'STORAGE_S3_ACCESS_KEY', label: 'fields.s3AccessKey', type: 'password', required: true },
      { key: 'STORAGE_S3_SECRET_KEY', label: 'fields.s3SecretKey', type: 'password', required: true }
    ]
  }
];

// Aliases for storage providers (same list for KV, Vector, Graph)
export const STORAGE_KV_PROVIDERS: ProviderConfig[] = STORAGE_PROVIDERS;
export const STORAGE_VECTOR_PROVIDERS: ProviderConfig[] = STORAGE_PROVIDERS;
export const STORAGE_GRAPH_PROVIDERS: ProviderConfig[] = STORAGE_PROVIDERS;
export const STORAGE_DOC_STATUS_PROVIDERS: ProviderConfig[] = [
  {
    id: 'null',
    name: 'providers.noneDisabled',
    description: 'Disable document status storage',
    fields: []
  },
  {
    id: 'local',
    name: 'Local Disk',
    description: 'Store document status locally',
    fields: [
      { key: 'STORAGE_LOCAL_PATH', label: 'fields.storagePath', type: 'text', defaultValue: './storage', placeholder: './storage', required: true }
    ]
  }
];

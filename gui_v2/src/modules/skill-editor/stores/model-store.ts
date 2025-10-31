/**
 * Model store (lightweight): returns provider->models mapping.
 * If a global override exists (window.__MODEL_MAP__), use it; otherwise, use defaults.
 */

export type ModelMap = Record<string, string[]>;

export interface ProviderConfig {
  apiHost: string;
  apiKeyTemplate: string;
}

export type ProviderConfigMap = Record<string, ProviderConfig>;

declare global {
  interface Window {
    __MODEL_MAP__?: ModelMap;
    __PROVIDER_CONFIG__?: ProviderConfigMap;
  }
}

export const DEFAULT_MODEL_MAP: ModelMap = {
  'OpenAI': [
    'gpt-5',
    'gpt-5-mini',
    'o3-pro',
    'o3',
    'o3-mini',
    'o1-preview',
    'o1',
    'o1-mini',
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4.1',
    'gpt-4.1-mini',
    'gpt-4-turbo',
    'gpt-4',
    'gpt-3.5-turbo',
  ],
  'Azure OpenAI': [
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4-turbo',
    'gpt-4',
    'gpt-35-turbo',
  ],
  'Anthropic Claude': [
    'claude-4.5-sonnet',
    'claude-4-sonnet',
    'claude-4-opus',
    'claude-3-7-sonnet-latest',
    'claude-3-5-sonnet-20241022',
    'claude-3-5-haiku-20241022',
    'claude-3-opus-20240229',
    'claude-3-sonnet-20240229',
    'claude-3-haiku-20240307',
  ],
  'AWS Bedrock': [
    'anthropic.claude-3-5-sonnet-20241022-v2:0',
    'anthropic.claude-3-5-haiku-20241022-v1:0',
    'anthropic.claude-3-opus-20240229-v1:0',
    'anthropic.claude-3-sonnet-20240229-v1:0',
    'anthropic.claude-3-haiku-20240307-v1:0',
  ],
  'Google Gemini': [
    'gemini-2.0-pro',
    'gemini-2.0-flash',
    'gemini-2.0-flash-exp',
    'gemini-1.5-pro',
    'gemini-1.5-flash',
    'gemini-1.5-flash-8b',
  ],
  'DeepSeek': [
    'deepseek-v3',
    'deepseek-r1',
    'deepseek-reasoner',
    'deepseek-chat',
    'deepseek-coder',
  ],
  'Qwen (DashScope)': [
    'qwen-max',
    'qwen-plus',
    'qwen-turbo',
    'qwen-long',
    'qwen-coder-plus',
    'qwen-vl-plus',
  ],
  'Bytedance': [
    'doubao-pro-256k',
    'doubao-pro-128k',
    'doubao-pro-32k',
    'doubao-lite-128k',
    'doubao-lite-32k',
  ],
  'Ollama (Local)': [
    'llama3.3:70b',
    'llama3.2:latest',
    'qwen2.5:latest',
    'deepseek-r1:latest',
    'mistral:latest',
    'codellama:latest',
  ],
};

export const DEFAULT_PROVIDER_CONFIG: ProviderConfigMap = {
  'OpenAI': {
    apiHost: 'https://api.openai.com/v1',
    apiKeyTemplate: 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
  },
  'Azure OpenAI': {
    apiHost: 'https://YOUR_RESOURCE.openai.azure.com',
    apiKeyTemplate: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
  },
  'Anthropic Claude': {
    apiHost: 'https://api.anthropic.com/v1',
    apiKeyTemplate: 'sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
  },
  'AWS Bedrock': {
    apiHost: 'https://bedrock-runtime.us-east-1.amazonaws.com',
    apiKeyTemplate: 'AKIAXXXXXXXXXXXXXXXX',
  },
  'Google Gemini': {
    apiHost: 'https://generativelanguage.googleapis.com/v1beta',
    apiKeyTemplate: 'AIzaxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
  },
  'DeepSeek': {
    apiHost: 'https://api.deepseek.com/v1',
    apiKeyTemplate: 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
  },
  'Qwen (DashScope)': {
    apiHost: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    apiKeyTemplate: 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
  },
  'Bytedance': {
    apiHost: 'https://ark.cn-beijing.volces.com/api/v3',
    apiKeyTemplate: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
  },
  'Ollama (Local)': {
    apiHost: 'http://localhost:11434/v1',
    apiKeyTemplate: 'ollama',
  },
};

export function getModelMap(): ModelMap {
  return window.__MODEL_MAP__ ?? DEFAULT_MODEL_MAP;
}

export function getProviderConfig(): ProviderConfigMap {
  return window.__PROVIDER_CONFIG__ ?? DEFAULT_PROVIDER_CONFIG;
}

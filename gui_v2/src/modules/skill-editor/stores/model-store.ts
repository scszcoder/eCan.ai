/**
 * Model store (lightweight): returns provider->models mapping.
 * If a global override exists (window.__MODEL_MAP__), use it; otherwise, use defaults.
 */

export type ModelMap = Record<string, string[]>;

declare global {
  interface Window {
    __MODEL_MAP__?: ModelMap;
  }
}

export const DEFAULT_MODEL_MAP: ModelMap = {
  OpenAI: [
    'gpt-5',
    'gpt-5-mini',
    'gpt-4.1',
    'gpt-4.1-mini',
    'gpt-4o',
    'gpt-realtime',
    'gpt-audio',
    'o1',
    'o1-pro',
    'o3',
    'o3-deep-research',
    'o3-pro',
  ],
  Anthropic: ['claude-4-sonnet-latest', 'claude-3-7-sonnet-latest', 'claude-4-1-opus-latest'],
  Google: ['germini-2.5-pro', 'gemini-2.5'],
  Alibaba: ['qwen3-max-preview', 'qwen-plus-2025-09-11', 'qwen-flash'],
  Deepseek: ['deepseek-v3', 'deepseek-r1'],
  Bytedance: ['doubao-1.6'],
};

export function getModelMap(): ModelMap {
  return window.__MODEL_MAP__ ?? DEFAULT_MODEL_MAP;
}

import { traverseWorkflowNodes } from './traverse-workflow-nodes';

export const API_KEY_PLACEHOLDER = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
export const API_KEY_REGEX = /api[\-_]?key/i;

const sanitizeValue = (value: any, path: string[] = []) => {
  if (!value || typeof value !== 'object') {
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((entry, idx) => sanitizeValue(entry, [...path, String(idx)]));
    return;
  }

  Object.keys(value).forEach((key) => {
    const child = value[key];
    if (API_KEY_REGEX.test(key)) {
      if (typeof child === 'string') {
        value[key] = API_KEY_PLACEHOLDER;
      } else if (child && typeof child === 'object') {
        if (typeof child.content === 'string') {
          child.content = API_KEY_PLACEHOLDER;
        }
        sanitizeValue(child, [...path, key]);
      }
      return;
    }

    if (child && typeof child === 'object') {
      sanitizeValue(child, [...path, key]);
    }
  });
};

/**
 * Recursively sanitize apiKey fields in any object tree.
 */
export const sanitizeApiKeysDeep = (value: any) => {
  sanitizeValue(value);
};

/**
 * Sanitize node payloads (data/raw/etc) in-place.
 */
export const sanitizeNodeApiKeys = (nodes: any[]) => {
  if (!nodes || !Array.isArray(nodes)) return;

  traverseWorkflowNodes(nodes, (node: any) => {
    if (!node || typeof node !== 'object') return;
    sanitizeValue(node.data);
    sanitizeValue(node.raw);
  });
};

const INLINE_PROMPT_IDS = new Set(['inline', 'in-line', '']);

const getFlowContent = (value: any): any => {
  if (value && typeof value === 'object' && 'content' in value) {
    return value.content;
  }
  return value;
};

const setFlowString = (target: any, key: string, content: string, type = 'template') => {
  if (!target || typeof target !== 'object') return;
  target[key] = { type, content };
};

const parseJsonObject = (raw: any): any => {
  try {
    const parsed = typeof raw === 'string' && raw.trim() ? JSON.parse(raw) : {};
    return (parsed && typeof parsed === 'object') ? parsed : {};
  } catch {
    return {};
  }
};

const normalizeBrowserMonitor = (item: any) => {
  const base = (item && typeof item === 'object') ? { ...item } : {};
  const parsed = parseJsonObject(base.cdpFilterExpr);
  const looksLikeFullMonitor =
    !!parsed &&
    typeof parsed === 'object' &&
    (
      parsed.sourceType ||
      parsed.source_type ||
      parsed.urlPatterns ||
      parsed.url_patterns ||
      parsed.domSelector ||
      parsed.dom_selector ||
      parsed.domCheckIntervalMs ||
      parsed.dom_check_interval_ms
    );

  // mt060: form fields (base) are AUTHORITATIVE over anything parsed from
  // cdpFilterExpr.  Previously this was {...base, ...parsed}, so a stale
  // monitor-level value embedded in cdpFilterExpr would override the user's
  // freshly-edited form field on the next save/load.  base wins; parsed only
  // fills gaps (so the migration case where base is empty still works).
  const merged = looksLikeFullMonitor ? { ...parsed, ...base } : base;
  const nestedExpr = looksLikeFullMonitor ? (parsed.cdpFilterExpr ?? parsed.cdp_filter_expr) : base.cdpFilterExpr;
  const domCfg = parseJsonObject(nestedExpr);

  return {
    label: merged.label ?? '',
    enabled: merged.enabled !== false,
    sourceType: merged.sourceType ?? merged.source_type ?? 'http_polling',
    urlPatterns: merged.urlPatterns ?? merged.url_patterns ?? '',
    contentFilters: merged.contentFilters ?? merged.content_filters ?? '',
    methods: merged.methods ?? '',
    minBodyLength: merged.minBodyLength ?? merged.min_body_length ?? 10,
    frameDirection: merged.frameDirection ?? merged.frame_direction ?? 'incoming',
    sseEventTypes: merged.sseEventTypes ?? merged.sse_event_types ?? '',
    domSelector: merged.domSelector ?? merged.dom_selector ?? '',
    domAttributes: merged.domAttributes ?? merged.dom_attributes ?? false,
    domChildList: merged.domChildList ?? merged.dom_child_list ?? true,
    domSubtree: merged.domSubtree ?? merged.dom_subtree ?? true,
    // mt060: default MUST match form-meta.tsx and backend event_monitor.py (750).
    // This save-side copy was left at 250 when the others moved to 750, so a
    // monitor without an explicit value was silently downgraded to 250 on save.
    domCheckIntervalMs: merged.domCheckIntervalMs ?? merged.dom_check_interval_ms ?? 750,
    cdpDomain: merged.cdpDomain ?? merged.cdp_domain ?? '',
    cdpEventMethod: merged.cdpEventMethod ?? merged.cdp_event_method ?? '',
    cdpFilterExpr: typeof nestedExpr === 'string' ? nestedExpr : (typeof base.cdpFilterExpr === 'string' ? base.cdpFilterExpr : ''),
  };
};

const normalizePromptFields = (node: any) => {
  const inputsValues = node?.data?.inputsValues;
  if (!inputsValues || typeof inputsValues !== 'object') return;

  const promptSelection = String(getFlowContent(inputsValues.promptSelection) || '').trim();
  const systemPromptId = String(getFlowContent(inputsValues.systemPromptId) || '').trim();
  const promptId = String(getFlowContent(inputsValues.promptId) || '').trim();

  if (systemPromptId && !INLINE_PROMPT_IDS.has(systemPromptId.toLowerCase())) {
    setFlowString(inputsValues, 'systemPrompt', '', 'template');
  }

  const effectivePromptSelection = promptSelection || promptId;
  if (effectivePromptSelection && !INLINE_PROMPT_IDS.has(effectivePromptSelection.toLowerCase())) {
    setFlowString(inputsValues, 'prompt', '', 'template');
  }
};

const normalizeBrowserAutomationNode = (node: any) => {
  normalizePromptFields(node);
  const inputsValues = node?.data?.inputsValues;
  const eventMonitors = inputsValues?.eventMonitors;
  const content = eventMonitors?.content;
  if (!eventMonitors || !Array.isArray(content)) return;

  eventMonitors.content = content.map((item: any) => normalizeBrowserMonitor(item));
};

const normalizeLlmNode = (node: any) => {
  normalizePromptFields(node);
};

export const normalizeNodesForSave = (nodes: any[]) => {
  if (!nodes || !Array.isArray(nodes)) return;

  traverseWorkflowNodes(nodes, (node: any) => {
    if (!node || typeof node !== 'object') return;
    const type = String(node.type || '');
    if (type === 'browser-automation') {
      normalizeBrowserAutomationNode(node);
    } else if (type === 'llm') {
      normalizeLlmNode(node);
    }
  });
};

/**
 * Mask API keys for display (keep first 3, last 3 characters).
 */
export const maskApiKeyForDisplay = (apiKey: string | null | undefined): string => {
  if (!apiKey) return '';
  if (apiKey === API_KEY_PLACEHOLDER) {
    return API_KEY_PLACEHOLDER;
  }
  if (apiKey.includes('***')) {
    return apiKey;
  }
  if (apiKey.length <= 6) {
    return '***';
  }

  const head = apiKey.slice(0, 3);
  const tail = apiKey.slice(-3);
  return `${head}***${tail}`;
};

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

  nodes.forEach((node: any) => {
    if (!node || typeof node !== 'object') return;
    sanitizeValue(node.data);
    sanitizeValue(node.raw);
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

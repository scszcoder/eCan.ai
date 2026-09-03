/**
 * Build ProviderConfig[] for the document parsing engines from backend data
 * served by `lightrag.getParserEngines`.
 *
 * The backend (knowledge/lightrag_parser_config.py) is the source of truth
 * for env variable names, defaults, options and endpoint requirements; the
 * static PARSER_PROVIDERS list is only a fallback for older backends.
 */
import type { ProviderConfig, ProviderFieldConfig } from './providerConfig';
import { PARSER_PROVIDERS } from './providerConfig';

export interface ParserEngineField {
  key: string;
  label?: string;
  type?: 'text' | 'number' | 'select' | 'textarea' | 'password' | 'boolean';
  defaultValue?: string;
  placeholder?: string;
  tooltip?: string;
  required?: boolean;
  options?: Array<{ value: string; label: string }>;
  /**
   * Marks a field whose value is sourced from account state (not the
   * ``.env`` file). The UI renders these as read-only with a "System"
   * badge; the save path refreshes them from secure_store before
   * persistence.
   */
  isSystemManaged?: boolean;
}

export interface ParserEngineDefinition {
  id: string;
  name: string;
  description?: string;
  fields?: ParserEngineField[];
}

export function buildParserProviders(
  raw: ParserEngineDefinition[] | undefined | null
): ProviderConfig[] {
  if (!raw || !Array.isArray(raw) || raw.length === 0) {
    return PARSER_PROVIDERS;
  }

  return raw.map(engine => {
    const backendFields: ProviderFieldConfig[] = (engine.fields || []).map(f => ({
      key: f.key,
      label: f.label,
      type: f.type || 'text',
      defaultValue: f.defaultValue,
      placeholder: f.placeholder,
      tooltip: f.tooltip,
      required: f.required,
      options: f.options,
      isSystemManaged: f.isSystemManaged,
    }));

    // A running desktop backend can be one process/version behind the Vite
    // UI during development. Merge its values into the current static schema
    // instead of replacing that schema wholesale, otherwise newly introduced
    // fields (for example DOCLING_API_KEY) remain invisible until a full app
    // restart. Backend definitions still win for matching fields.
    const fallback = PARSER_PROVIDERS.find(provider => provider.id === engine.id);
    const backendByKey = new Map(backendFields.map(field => [field.key, field]));
    const fallbackKeys = new Set((fallback?.fields || []).map(field => field.key));
    const fields: ProviderFieldConfig[] = [
      ...(fallback?.fields || []).map(field => ({
        ...field,
        ...backendByKey.get(field.key),
      })),
      ...backendFields.filter(field => !fallbackKeys.has(field.key)),
    ];

    return {
      id: engine.id,
      name: engine.name,
      description: engine.description,
      fields,
    };
  });
}

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
    const fields: ProviderFieldConfig[] = (engine.fields || []).map(f => ({
      key: f.key,
      label: f.label,
      type: f.type || 'text',
      defaultValue: f.defaultValue,
      placeholder: f.placeholder,
      tooltip: f.tooltip,
      required: f.required,
      options: f.options,
    }));

    return {
      id: engine.id,
      name: engine.name,
      description: engine.description,
      fields,
    };
  });
}

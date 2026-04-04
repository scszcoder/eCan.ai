/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Field } from '@flowgram.ai/free-layout-editor';
import { DynamicValueInput } from '@flowgram.ai/form-materials';
import { Button, Input } from '@douyinfe/semi-ui';

import { FormItem } from '../form-item';
import { Feedback } from '../feedback';
import { CollapsiblePromptEditor } from '../CollapsiblePromptEditor';
import { JsonSchema } from '../../typings';
import { useNodeRenderContext } from '../../hooks';
import { maskApiKeyForDisplay, API_KEY_PLACEHOLDER, API_KEY_REGEX } from '../../utils/sanitize-utils';
import { getCommonFieldLabel } from '../../utils/field-labels';

interface FormInputsProps {
  extraFilter?: (key: string) => boolean;
}

interface MaskedApiKeyInputProps {
  field: any;
  fieldState: any;
  readonly: boolean;
  t: any;
}

const MaskedApiKeyInput = ({ field, fieldState, readonly, t }: MaskedApiKeyInputProps) => {
  const extractValue = (): string => {
    const v = field.value;
    if (v && typeof v === 'object' && 'content' in v) {
      return v.content ?? '';
    }
    if (typeof v === 'string') {
      return v;
    }
    return '';
  };

  const [isEditing, setIsEditing] = useState(false);
  const [localValue, setLocalValue] = useState<string>(extractValue());

  useEffect(() => {
    if (!isEditing) {
      setLocalValue(extractValue());
    }
  }, [field.value, isEditing]);

  useEffect(() => {
    if (field.value == null && localValue === '') {
      field.onChange({ type: 'constant', content: API_KEY_PLACEHOLDER });
    }
  }, []);

  const handleChange = (value: string) => {
    setLocalValue(value);
    field.onChange({ type: 'constant', content: value });
  };

  const displayValue = isEditing ? localValue : maskApiKeyForDisplay(localValue || API_KEY_PLACEHOLDER);

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <div style={{ flex: 1 }}>
        <Input
          value={displayValue}
          type={isEditing ? 'password' : 'text'}
          readOnly={!isEditing || readonly}
          onChange={(val) => handleChange(val)}
          placeholder={t('formInputs.apiKeyPlaceholder')}
          disabled={readonly && !isEditing}
        />
      </div>
      {!readonly && (
        <Button
          type={isEditing ? 'primary' : 'tertiary'}
          onClick={() => setIsEditing((prev) => !prev)}
        >
          {isEditing ? t('formInputs.done') : t('formInputs.edit')}
        </Button>
      )}
      <Feedback errors={fieldState?.errors} warnings={fieldState?.warnings} />
    </div>
  );
};

export function FormInputs({ extraFilter }: FormInputsProps = {}) {
  const { readonly } = useNodeRenderContext();
  const { t } = useTranslation('skillEditor');

  // Ensure the PromptEditor receives a FlowValue whose `content` is a string.
  // Some upstream values may accidentally be objects/arrays, which will crash the underlying CodeEditor.
  const sanitizeFlowValue = (val: any, schema?: any, asPlainString?: boolean) => {
    try {
      if (val && typeof val === 'object' && 'content' in val) {
        const c = (val as any).content;
        if (!asPlainString && typeof c === 'string') return val;
        const safe = c == null
          ? ''
          : (typeof c === 'object' ? JSON.stringify(c, null, 2) : String(c));
        return asPlainString ? safe : { ...val, content: safe };
      }
      // If value is not a FlowValue, coerce into one with string content
      if (schema) {
        const t = schema.type;
        // For string-like editors (code editors in lib), always pass a string doc
        if (t === 'string') {
          const safe = val == null
            ? ''
            : (typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val));
          return asPlainString ? safe : ({ type: 'constant', content: safe } as any);
        }
        // For arrays/objects, still avoid crashing editors that expect text rendering
        if (t === 'array' || t === 'object') {
          // Prefer leaving as constant JSON string so CodeEditor can open it
          const safe = val == null
            ? (t === 'array' ? '[]' : '{}')
            : (typeof val === 'string' ? val : JSON.stringify(val, null, 2));
          return asPlainString ? safe : ({ type: 'constant', content: safe } as any);
        }
      }
    } catch (_) {}
    return asPlainString ? (val == null ? '' : String(val)) : val;
  };

  const renderFromSchema = (inputsField: any, sourceLabel: string) => {
    let required = inputsField.value?.required || [];
    let properties = inputsField.value?.properties;
    try {
      console.debug(`[MCP][FormInputs] (${sourceLabel}) inputs schema value =`, inputsField.value);
      console.debug(`[MCP][FormInputs] (${sourceLabel}) required =`, required);
      console.debug(`[MCP][FormInputs] (${sourceLabel}) properties keys =`, properties ? Object.keys(properties) : 'none');
    } catch {}
    // Fallback: if only 'input' object exists, expand it
    try {
      const onlyInput = properties && Object.keys(properties).length === 1 && properties.input && properties.input.type === 'object';
      if (onlyInput) {
        console.warn(`[MCP][FormInputs] (${sourceLabel}) expanding nested 'input' object into root properties`);
        const inner = properties.input.properties || {};
        properties = inner;
        const innerReq = Array.isArray(properties.input?.required) ? properties.input.required : (inputsField.value?.required || []);
        required = Array.isArray(innerReq) ? innerReq : Object.keys(inner);
      }
    } catch {}
    if (!properties || Object.keys(properties).length === 0) {
      return (
        <div className="mcp-form-inputs-wrapper" style={{ background: '#fff', color: '#111', padding: 8, borderRadius: 4 }}>
          <div style={{ fontSize: 12, opacity: 0.8 }}>{t('formInputs.noParameters', { source: sourceLabel })}</div>
        </div>
      );
    }
    const keys = Object.keys(properties);
    const content = keys
      .filter((key) => (extraFilter ? extraFilter(key) : true))
      .map((key) => {
      const property = properties[key];
      try { console.debug('[MCP][FormInputs] rendering field:', key, 'schema=', property); } catch {}

      // Skip fields that are rendered by a custom section elsewhere (e.g., attachments in LLM form)
      if (property?.extra?.skipDefault || property?.extra?.formComponent === 'custom-attachments') {
        return null;
      }

      const formComponent = property.extra?.formComponent;

      const vertical = ['prompt-editor'].includes(formComponent || '');

      const renderStringInput = (key: string, property: any, field: any, fieldState: any) => {
        if (API_KEY_REGEX.test(key)) {
          return (
            <MaskedApiKeyInput
              field={field}
              fieldState={fieldState}
              readonly={readonly}
              t={t}
            />
          );
        }

        const plain = sanitizeFlowValue(field.value, property, true) as string;
        try { console.debug('[MCP][FormInputs] string input field value =', plain); } catch {}
        return (
          <input
            style={{ width: '100%', padding: 6, border: '1px solid var(--semi-color-border)', backgroundColor: '#fff', color: '#111' }}
            value={plain}
            onChange={(e) => field.onChange({ type: 'constant', content: e.target.value })}
            disabled={readonly}
          />
        );
      };

      return (
        <Field key={key} name={`inputsValues.${key}`} defaultValue={property.default}>
          {({ field, fieldState }) => (
            <FormItem
              name={key}
              label={getCommonFieldLabel(key, t)}
              vertical={vertical}
              type={property.type as string}
              required={required.includes(key)}
            >
              {formComponent === 'prompt-editor' ? (
                <CollapsiblePromptEditor
                  value={sanitizeFlowValue(field.value, property)}
                  onChange={field.onChange}
                  readonly={readonly}
                  hasError={Object.keys(fieldState?.errors || {}).length > 0}
                  defaultCollapsed={true}
                  collapsedLines={3}
                />
              ) : null}
              {!formComponent && (
                (() => {
                  if (property?.type === 'string') {
                    return renderStringInput(key, property, field, fieldState);
                  }
                  if (property?.type === 'number' || property?.type === 'integer') {
                    const isInteger = property?.type === 'integer';
                    // Extract the actual number value from FlowValue
                    let numValue = '';
                    if (field.value && typeof field.value === 'object' && 'content' in field.value) {
                      numValue = field.value.content === '' ? '' : String(field.value.content);
                    } else if (field.value !== null && field.value !== undefined) {
                      numValue = String(field.value);
                    }
                    try { console.debug('[MCP][FormInputs] number input field value =', numValue, 'isInteger=', isInteger); } catch {}
                    return (
                      <input
                        type="number"
                        step={isInteger ? '1' : 'any'}
                        style={{ width: '100%', padding: 6, border: '1px solid var(--semi-color-border)', backgroundColor: '#fff', color: '#111' }}
                        value={numValue}
                        onChange={(e) => {
                          const val = e.target.value;
                          const schemaType = isInteger ? 'integer' : 'number';
                          // Only store non-empty values, convert to number
                          if (val === '') {
                            field.onChange({ type: 'constant', content: '', schema: { type: schemaType } });
                          } else {
                            const parsed = isInteger ? parseInt(val, 10) : parseFloat(val);
                            field.onChange({ type: 'constant', content: isNaN(parsed) ? val : parsed, schema: { type: schemaType } });
                          }
                        }}
                        disabled={readonly}
                      />
                    );
                  }
                  const adjustedSchema = property;
                  try { console.debug('[MCP][FormInputs] DynamicValueInput schema =', adjustedSchema); } catch {}
                  return (
                    <div className="mcp-form-inputs-dvi">
                      <DynamicValueInput
                        value={sanitizeFlowValue(field.value, adjustedSchema, true)}
                        onChange={field.onChange}
                        readonly={readonly}
                        hasError={Object.keys(fieldState?.errors || {}).length > 0}
                        schema={adjustedSchema}
                      />
                    </div>
                  );
                })()
              )}
              <Feedback errors={fieldState?.errors} warnings={fieldState?.warnings} />
            </FormItem>
          )}
        </Field>
      );
    });
    return (
      <div className="mcp-form-inputs-wrapper" style={{ background: '#fff' }}>
        {content.filter(Boolean)}
      </div>
    );
  };

  return (
    <>
      <Field<any> name="data.callable">
        {() => <></>}
      </Field>

      <Field<JsonSchema> name="data.inputs">
        {({ field: dataInputsField }) => {
          // Prefer data.inputs; if empty, fallback to inputs
          const v = dataInputsField?.value;
          const hasProps = v && v.properties && Object.keys(v.properties).length > 0;
          if (hasProps) return renderFromSchema(dataInputsField, 'data.inputs');
          console.debug('[MCP][FormInputs] data.inputs is empty, falling back to inputs');
          return (
            <Field<JsonSchema> name="inputs">
              {({ field: legacyInputsField }) => {
                const lv = legacyInputsField?.value;
                const lHas = lv && lv.properties && Object.keys(lv.properties).length > 0;
                if (lHas) return renderFromSchema(legacyInputsField, 'inputs');
                console.warn('[MCP][FormInputs] both data.inputs and inputs are empty; deriving from data.callable.params');
                return (
                  <Field<any> name="data.callable">
                    {({ field: callableField }) => {
                      const callable = callableField?.value || {};
                      const params = callable?.params || { type: 'object', properties: {} };
                      const rp = params?.properties || {};
                      const hasInput = rp.input && typeof rp.input === 'object' && rp.input.type === 'object';
                      const derivedProps = hasInput ? (rp.input.properties || {}) : rp;
                      const derivedReq = (params && typeof params === 'object' && 'required' in params)
                        ? (Array.isArray(params.required) ? params.required : Object.keys(derivedProps))
                        : [];
                      const derivedSchema = { type: 'object', properties: derivedProps, required: derivedReq } as any;
                      const fakeField = { value: derivedSchema };
                      return renderFromSchema(fakeField, 'callable.params');
                    }}
                  </Field>
                );
              }}
            </Field>
          );
        }}
      </Field>
    </>
  );
}

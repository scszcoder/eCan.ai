/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { Field } from '@flowgram.ai/free-layout-editor';
import { DynamicValueInput, PromptEditorWithVariables } from '@flowgram.ai/form-materials';

import { FormItem } from '../form-item';
import { Feedback } from '../feedback';
import { JsonSchema } from '../../typings';
import { useNodeRenderContext } from '../../hooks';

interface FormInputsProps {
  extraFilter?: (key: string) => boolean;
}

export function FormInputs({ extraFilter }: FormInputsProps = {}) {
  const { readonly } = useNodeRenderContext();

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
          <div style={{ fontSize: 12, opacity: 0.8 }}>[MCP][FormInputs] No parameters to render for this tool. Source: {sourceLabel}</div>
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

      return (
        <Field key={key} name={`inputsValues.${key}`} defaultValue={property.default}>
          {({ field, fieldState }) => (
            <FormItem
              name={key}
              vertical={vertical}
              type={property.type as string}
              required={required.includes(key)}
            >
              {formComponent === 'prompt-editor' && (
                <PromptEditorWithVariables
                  value={sanitizeFlowValue(field.value, property)}
                  onChange={field.onChange}
                  readonly={readonly}
                  hasError={Object.keys(fieldState?.errors || {}).length > 0}
                />
              )}
              {!formComponent && (
                (() => {
                  if (property?.type === 'string') {
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
                  }
                  if (property?.type === 'number') {
                    // Extract the actual number value from FlowValue
                    let numValue = '';
                    if (field.value && typeof field.value === 'object' && 'content' in field.value) {
                      numValue = field.value.content === '' ? '' : String(field.value.content);
                    } else if (field.value !== null && field.value !== undefined) {
                      numValue = String(field.value);
                    }
                    try { console.debug('[MCP][FormInputs] number input field value =', numValue); } catch {}
                    return (
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        style={{ width: '100%', padding: 6, border: '1px solid var(--semi-color-border)', backgroundColor: '#fff', color: '#111' }}
                        value={numValue}
                        onChange={(e) => {
                          const val = e.target.value;
                          // Only store non-empty values, convert to number
                          if (val === '') {
                            field.onChange({ type: 'constant', content: '', schema: { type: 'number' } });
                          } else {
                            const parsed = parseFloat(val);
                            field.onChange({ type: 'constant', content: isNaN(parsed) ? val : parsed, schema: { type: 'number' } });
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
        <div style={{ fontSize: 12, color: '#444', marginBottom: 6 }}>[MCP][FormInputs] Rendering parameters: {keys.join(', ')}</div>
        {content.filter(Boolean)}
      </div>
    );
  };

  return (
    <>
      {/* Diagnostic: log callable params parsed keys regardless of effect status */}
      <Field<any> name="data.callable">
        {({ field }) => {
          try {
            const callable = field.value || {};
            const ps = callable?.params || { type: 'object', properties: {} };
            const rp = ps?.properties || {};
            const hasInput = rp.input && typeof rp.input === 'object' && rp.input.type === 'object';
            const rawProps = hasInput ? (rp.input.properties || {}) : rp;
            const keys = Object.keys(rawProps || {});
            console.log('[MCP][Diag] callable.name =', callable?.name, 'parsed keys from callable.params =', keys);
            if ((callable?.name || '').toLowerCase() === 'mouse_move') {
              console.log('[MCP][Diag][mouse_move] expected keys: location, post_wait | actual:', keys);
            }
          } catch (e) {
            console.warn('[MCP][Diag] failed to parse callable params:', e);
          }
          return null;
        }}
      </Field>

      <Field<JsonSchema> name="data.inputs">
        {({ field: dataInputsField }) => {
          // Prefer data.inputs; if empty, fallback to inputs
          const v = dataInputsField?.value;
          const hasProps = v && v.properties && Object.keys(v.properties).length > 0;
          if (hasProps) return renderFromSchema(dataInputsField, 'data.inputs');
          console.warn('[MCP][FormInputs] data.inputs is empty, falling back to inputs');
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
                      const derivedReq = hasInput
                        ? (Array.isArray(rp.input?.required) ? rp.input.required : Object.keys(derivedProps))
                        : (Array.isArray(params.required) ? params.required : Object.keys(derivedProps));
                      const derivedSchema = { type: 'object', properties: derivedProps, required: derivedReq } as any;
                      const fakeField = { value: derivedSchema };
                      console.log('[MCP][FormInputs] Derived schema from callable.params =', derivedSchema);
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

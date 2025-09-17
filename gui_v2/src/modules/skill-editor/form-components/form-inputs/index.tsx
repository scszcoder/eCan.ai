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

export function FormInputs() {
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

  return (
    <Field<JsonSchema> name="inputs">
      {({ field: inputsField }) => {
        const required = inputsField.value?.required || [];
        const properties = inputsField.value?.properties;
        if (!properties) {
          return <></>;
        }
        const content = Object.keys(properties).map((key) => {
          const property = properties[key];

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
                        return (
                          <input
                            style={{ width: '100%', padding: 6, border: '1px solid var(--semi-color-border)' }}
                            value={plain}
                            onChange={(e) => field.onChange({ type: 'constant', content: e.target.value })}
                            disabled={readonly}
                          />
                        );
                      }
                      const adjustedSchema = property;
                      return (
                        <DynamicValueInput
                          value={sanitizeFlowValue(field.value, adjustedSchema, true)}
                          onChange={field.onChange}
                          readonly={readonly}
                          hasError={Object.keys(fieldState?.errors || {}).length > 0}
                          schema={adjustedSchema}
                        />
                      );
                    })()
                  )}
                  <Feedback errors={fieldState?.errors} warnings={fieldState?.warnings} />
                </FormItem>
              )}
            </Field>
          );
        });
        return <>{content.filter(Boolean)}</>;
      }}
    </Field>
  );
}

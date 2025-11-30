import React from 'react';
import { Field } from '@flowgram.ai/free-layout-editor';
import { PromptEditorWithVariables } from '@flowgram.ai/form-materials';
import { FormItem } from './form-item';
import { Feedback } from './feedback';
import { PromptSelector, IN_LINE_PROMPT_ID } from './PromptSelector';
import { useNodeRenderContext } from '../hooks';

interface PromptInputWithSelectorProps {
  promptFieldName: string;
  promptIdFieldName: string;
  label: string;
  promptType?: 'systemPrompt' | 'prompt';
  schema?: any;
  required?: boolean;
}

export const PromptInputWithSelector: React.FC<PromptInputWithSelectorProps> = ({
  promptFieldName,
  promptIdFieldName,
  label,
  promptType = 'prompt',
  schema,
  required = false,
}) => {
  const { readonly } = useNodeRenderContext();

  const sanitizeFlowValue = (val: any, schema?: any) => {
    try {
      if (val && typeof val === 'object' && 'content' in val) {
        const c = (val as any).content;
        if (typeof c === 'string') return val;
        const safe = c == null
          ? ''
          : (typeof c === 'object' ? JSON.stringify(c, null, 2) : String(c));
        return { ...val, content: safe };
      }
      // If value is not a FlowValue, coerce into one with string content
      if (schema?.type === 'string') {
        const safe = val == null
          ? ''
          : (typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val));
        return { type: 'constant', content: safe } as any;
      }
    } catch (_) {}
    return val;
  };

  return (
    <>
      {/* Prompt Selector Dropdown */}
      <FormItem name={`${promptIdFieldName}_selector`} vertical type="string">
        <Field<any> name={promptIdFieldName}>
          {({ field }) => {
            const promptId = field.value?.content || field.value || IN_LINE_PROMPT_ID;
            return (
              <PromptSelector
                value={promptId}
                onChange={(val) => {
                  // Store as FlowValue with content
                  field.onChange({ type: 'constant', content: val });
                }}
                promptType={promptType}
              />
            );
          }}
        </Field>
      </FormItem>

      {/* Prompt Editor - only show if In-line Prompt is selected */}
      <Field<any> name={promptIdFieldName}>
        {({ field: promptIdField }) => {
          const promptId = promptIdField.value?.content || promptIdField.value || IN_LINE_PROMPT_ID;
          const showPromptEditor = promptId === IN_LINE_PROMPT_ID;
          
          if (!showPromptEditor) return null;

          return (
            <FormItem name={label} vertical type="string" required={required}>
              <Field<any> name={promptFieldName}>
                {({ field, fieldState }) => (
                  <>
                    <PromptEditorWithVariables
                      value={sanitizeFlowValue(field.value, schema)}
                      onChange={field.onChange}
                      readonly={readonly}
                      hasError={Object.keys(fieldState?.errors || {}).length > 0}
                    />
                    <Feedback errors={fieldState?.errors} warnings={fieldState?.warnings} />
                  </>
                )}
              </Field>
            </FormItem>
          );
        }}
      </Field>
    </>
  );
};

import React from 'react';
import { Field } from '@flowgram.ai/free-layout-editor';
import { useTranslation } from 'react-i18next';
import { FormItem } from './form-item';
import { Feedback } from './feedback';
import { PromptSelector, IN_LINE_PROMPT_ID } from './PromptSelector';
import { CollapsiblePromptEditor } from './CollapsiblePromptEditor';
import { useNodeRenderContext } from '../hooks';
import { getCommonFieldLabel } from '../utils/field-labels';

interface PromptInputWithSelectorProps {
  promptFieldName: string;
  promptIdFieldName: string;
  label: string;
  promptType?: 'systemPrompt' | 'prompt';
  schema?: any;
  required?: boolean;
}

// Separate component to handle visibility with CSS instead of unmounting
// This avoids the PromptEditor internal unmount warning
const PromptEditorField: React.FC<{
  showPromptEditor: boolean;
  promptFieldName: string;
  label: string;
  schema?: any;
  required: boolean;
  readonly: boolean;
  sanitizeFlowValue: (val: any, schema?: any) => any;
}> = ({ showPromptEditor, promptFieldName, label, schema, required, readonly, sanitizeFlowValue }) => {
  return (
    <div style={{ display: showPromptEditor ? 'block' : 'none' }}>
      <FormItem name={label} vertical type="string" required={required}>
        <Field<any> name={promptFieldName}>
          {({ field, fieldState }) => (
            <>
              <CollapsiblePromptEditor
                value={sanitizeFlowValue(field.value, schema)}
                onChange={field.onChange}
                readonly={readonly}
                hasError={Object.keys(fieldState?.errors || {}).length > 0}
                defaultCollapsed={true}
                collapsedLines={3}
              />
              <Feedback errors={fieldState?.errors} warnings={fieldState?.warnings} />
            </>
          )}
        </Field>
      </FormItem>
    </div>
  );
};

export const PromptInputWithSelector: React.FC<PromptInputWithSelectorProps> = ({
  promptFieldName,
  promptIdFieldName,
  label,
  promptType = 'prompt',
  schema,
  required = false,
}) => {
  const { readonly } = useNodeRenderContext();
  const { t } = useTranslation('skillEditor');

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
      <FormItem 
        name={`${promptIdFieldName}_selector`} 
        label={getCommonFieldLabel(`${promptIdFieldName.split('.').pop()}_selector`, t)}
        vertical 
        type="string"
      >
        <Field<any> name={promptIdFieldName}>
          {({ field }) => {
            const promptId = field.value?.content || field.value || IN_LINE_PROMPT_ID;
            return (
              <Field<any> name={promptFieldName}>
                {({ field: promptField }) => (
                  <PromptSelector
                    value={promptId}
                    onChange={(val) => {
                      field.onChange({ type: 'constant', content: val });
                      if (val !== IN_LINE_PROMPT_ID) {
                        promptField.onChange({ type: 'template', content: '' });
                      }
                    }}
                    promptType={promptType}
                  />
                )}
              </Field>
            );
          }}
        </Field>
      </FormItem>

      {/* Prompt Editor — always rendered (never unmounted) so the inner React root stays stable.
          A scoped Field reads promptId; CSS display controls visibility. */}
      <Field<any> name={promptIdFieldName}>
        {({ field: promptIdField }) => {
          const promptId = promptIdField.value?.content || promptIdField.value || IN_LINE_PROMPT_ID;
          return (
            <div style={{ display: promptId === IN_LINE_PROMPT_ID ? 'block' : 'none' }}>
              <PromptEditorField
                showPromptEditor={promptId === IN_LINE_PROMPT_ID}
                promptFieldName={promptFieldName}
                label={label}
                schema={schema}
                required={required}
                readonly={readonly}
                sanitizeFlowValue={sanitizeFlowValue}
              />
            </div>
          );
        }}
      </Field>
    </>
  );
};

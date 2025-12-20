/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useEffect } from 'react';
import { Field } from '@flowgram.ai/free-layout-editor';
import { SafeCodeEditor } from '../../../components/SafeCodeEditor';
import { Divider, Select, Input, Button } from '@douyinfe/semi-ui';

import { useIsSidebar, useNodeRenderContext } from '../../../hooks';

const EVENT_OPTIONS = [
  { label: 'Timer expiration', value: 'timer' },
  { label: 'Message arrival', value: 'message' },
  { label: 'Data changed', value: 'data_changed' },
  { label: 'Hard interrupt', value: 'hard_interrupt' },
];

export function EventEditor() {
  const isSidebar = useIsSidebar();
  const { readonly } = useNodeRenderContext();

  if (!isSidebar) return null;

  return (
    <>
      <Divider />

      {/* Event selector */}
      <Field<string> name="event.type">
        {({ field: eventTypeField }) => (
          <div style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
              <Select
                value={eventTypeField.value || 'timer'}
                onChange={(val) => eventTypeField.onChange(val as string)}
                style={{ width: 220 }}
                optionList={EVENT_OPTIONS}
                disabled={readonly}
              />
            </div>
          </div>
        )}
      </Field>

      {/* i_tag input */}
      <Field<string> name="event.i_tag">
        {({ field }) => (
          <div style={{ marginBottom: 12 }}>
            <div style={{ marginBottom: 6, fontSize: 12, color: 'var(--semi-color-text-2)' }}>i_tag</div>
            <Input
              value={field.value || ''}
              onChange={(val) => field.onChange(val as string)}
              placeholder="Enter interrupt tag (i_tag)"
              disabled={readonly}
            />
          </div>
        )}
      </Field>

      {/* Script language and template reset */}
      <Field<string> name="script.language">
        {({ field: langField }) => {
          const currentLang = (langField.value as string) || 'python';
          return (
            <div style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <Select
                  value={currentLang}
                  onChange={(val) => langField.onChange(val as string)}
                  style={{ width: 180 }}
                  optionList={[
                    { label: 'Python', value: 'python' },
                    { label: 'JavaScript', value: 'javascript' },
                    { label: 'TypeScript', value: 'typescript' },
                  ]}
                  disabled={readonly}
                />
                {/* Reset code to template */}
                <Field<string> name="script.content">
                  {({ field: contentField }) => {
                    const templates: Record<string, string> = {
                      python: `# Event handler: implement your logic here\n# Access state and runtime like other nodes\nfrom typing import Any, Dict\n\ndef main(state: Dict[str, Any], *, runtime, store):\n  # Use state['event'] for event details, and state['i_tag'] if needed\n  state['result'] = {'event': state.get('event_type'), 'i_tag': state.get('i_tag')}\n  return {'status': 'ok'}\n`,
                      javascript: `// Event handler template\nasync function main({ params }) {\n  // params may include event metadata and i_tag\n  return { status: 'ok', result: { event: params.event_type, i_tag: params.i_tag } };\n}`,
                      typescript: `// Event handler template\nexport async function main({ params }: { params: any }) {\n  return { status: 'ok', result: { event: String(params?.event_type || ''), i_tag: String(params?.i_tag || '') } };\n}`,
                    };
                    const handleReset = () => {
                      const tmpl = templates[currentLang] || templates.python;
                      Promise.resolve().then(() => contentField.onChange(tmpl));
                    };
                    return (
                      <Button onClick={handleReset} size="small">Reset to template</Button>
                    );
                  }}
                </Field>
              </div>

              {/* Monaco code editor */}
              <Field<string> name="script.content">
                {({ field }) => {
                  const safeValue = field.value ?? '';
                  const trimmed = safeValue.trimStart();
                  const isLegacyJsHeader =
                    trimmed.startsWith('// Event handler template') ||
                    safeValue.includes('Event handler template');
                  const pythonTemplate = `# Event handler: implement your logic here\n# Access state and runtime like other nodes\nfrom typing import Any, Dict\n\ndef main(state: Dict[str, Any], *, runtime, store):\n  # Use state['event'] for event details, and state['i_tag'] if needed\n  state['result'] = {'event': state.get('event_type'), 'i_tag': state.get('i_tag')}\n  return {'status': 'ok'}\n`;
                  useEffect(() => {
                    if (isLegacyJsHeader && safeValue !== pythonTemplate) {
                      setTimeout(() => {
                        if (currentLang !== 'python') langField.onChange('python');
                        field.onChange(pythonTemplate);
                      }, 0);
                    }
                  // eslint-disable-next-line react-hooks/exhaustive-deps
                  }, [isLegacyJsHeader]);
                  const handleChange = (value: string) => {
                    if (value === field.value) return;
                    Promise.resolve().then(() => field.onChange(value));
                  };
                  const displayValue = isLegacyJsHeader ? pythonTemplate : safeValue;
                  const displayLang = isLegacyJsHeader ? 'python' : currentLang;
                  return (
                    <SafeCodeEditor
                      languageId={displayLang}
                      value={displayValue}
                      onChange={handleChange}
                      readonly={readonly}
                    />
                  );
                }}
              </Field>
            </div>
          );
        }}
      </Field>
    </>
  );
}

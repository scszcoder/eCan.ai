/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useEffect } from 'react';
import { Field } from '@flowgram.ai/free-layout-editor';
import { SafeCodeEditor } from '../../../components/SafeCodeEditor';
import { Divider, Select, Button } from '@douyinfe/semi-ui';

import { useIsSidebar, useNodeRenderContext } from '../../../hooks';
import { FormItem } from '../../../form-components';

export function Code() {
  const isSidebar = useIsSidebar();
  const { readonly } = useNodeRenderContext();

  if (!isSidebar) {
    return null;
  }

  return (
    <>
      <Divider />
      {/* Language selector */}
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
                />
                {/* Reset current node's code to template for selected language */}
                <Field<string> name="script.content">
                  {({ field: contentField }) => {
                    const templates: Record<string, string> = {
                      python: `# Here, you can retrieve input variables from the node using 'state' \nimport time\ndef main(state, *, runtime, store):\n  # Build the output object\n  print("in myfunc0.........",state)\n  time.sleep(5)\n  print("myfunc0 woke now, outa here.....")\n  state["result"] = "myfun0 success"\n  return {"status": "myfunc0 succeeded!!!"\n}`,
                      javascript: `// Here, you can retrieve input variables from the node using 'params' and output results using 'ret'.\nasync function main({ params }) {\n  const ret = { key0: params.input + params.input };\n  return ret;\n}`,
                      typescript: `// Here, you can retrieve input variables from the node using 'params' and output results using 'ret'.\nexport async function main({ params }: { params: any }) {\n  const ret = { key0: String(params.input) + String(params.input) };\n  return ret;\n}`,
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

              {/* Editor bound to content, using selected language */}
              <Field<string> name="script.content">
                {({ field }) => {
                  const safeValue = field.value ?? '';
                  // Legacy JS template detection (from older builds)
                  const trimmed = safeValue.trimStart();
                  const isLegacyJsHeader =
                    trimmed.startsWith('// Here, you can retrieve input variables') ||
                    safeValue.includes("retrieve input variables from the node using 'params'") ||
                    safeValue.includes('Xiaoming');
                  const pythonTemplate = `# Here, you can retrieve input variables from the node using 'state' \nimport time\ndef main(state, *, runtime, store):\n  # Build the output object\n  print("in myfunc0.........",state)\n  time.sleep(5)\n  print("myfunc0 woke now, outa here.....")\n  state["result"] = "myfun0 success"\n  return {"status": "myfunc0 succeeded!!!"\n}`;
                  // Run migration as an effect so the editor shows the template immediately on open
                  useEffect(() => {
                    if (isLegacyJsHeader && safeValue !== pythonTemplate) {
                      // Defer a tick to avoid synchronous form update during render
                      setTimeout(() => {
                        if (currentLang !== 'python') langField.onChange('python');
                        field.onChange(pythonTemplate);
                      }, 0);
                    }
                  // eslint-disable-next-line react-hooks/exhaustive-deps
                  }, [isLegacyJsHeader]);
                  // One-time migration: if we detect the legacy header, replace with python template
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

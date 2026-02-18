/**
 * Run-code specific controls for an MCP node.
 * Renders a language selector and a collapsible Monaco editor
 * when the selected callable is "run_code".
 */

import { useState, useCallback } from 'react';
import { Field } from '@flowgram.ai/free-layout-editor';
import { Select, Button } from '@douyinfe/semi-ui';
import { IconChevronDown, IconChevronRight } from '@douyinfe/semi-icons';
import { SafeCodeEditor } from '../../../components/SafeCodeEditor';
import { useIsSidebar, useNodeRenderContext } from '../../../hooks';

const LANGUAGE_OPTIONS = [
  { label: 'Python', value: 'python' },
  { label: 'JavaScript', value: 'javascript' },
  { label: 'Bash', value: 'bash' },
  { label: 'PowerShell', value: 'powershell' },
];

const LANGUAGE_TEMPLATES: Record<string, string> = {
  python: `# Write your Python code here
def main():
    print("Hello from run_code")
    return {"result": "success"}

main()
`,
  javascript: `// Write your JavaScript code here
async function main() {
  const result = { message: "Hello from run_code" };
  console.log(JSON.stringify(result));
  return result;
}

main();
`,
  bash: `#!/bin/bash
# Write your Bash script here
echo "Hello from run_code"
`,
  powershell: `# Write your PowerShell script here
Write-Output "Hello from run_code"
`,
};

/** Map our language values to Monaco language IDs */
const MONACO_LANG_MAP: Record<string, string> = {
  python: 'python',
  javascript: 'javascript',
  bash: 'shell',
  powershell: 'powershell',
};

export function RunCodeEditor() {
  const isSidebar = useIsSidebar();
  const { readonly } = useNodeRenderContext();
  const [expanded, setExpanded] = useState(false);

  return (
    <Field<{ name?: string } | undefined> name="data.callable">
      {({ field: callableField }) => {
        const callableName = callableField.value?.name ?? '';
        const isRunCode = callableName === 'run_code';
        if (!isRunCode) return <></>;

        return (
          <div style={{ marginTop: 12 }}>
            {/* Divider */}
            <div style={{ height: 1, background: '#e8e8e8', margin: '0 0 12px 0', width: '100%' }} />
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Run Code Settings</div>

            {/* Language selector */}
            <Field<string> name="data.run_code_language">
              {({ field: langField }) => {
                const currentLang = langField.value || 'python';
                return (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>Language</div>
                    <Select
                      value={currentLang}
                      onChange={(val) => langField.onChange(val as string)}
                      style={{ width: '100%' }}
                      optionList={LANGUAGE_OPTIONS}
                      disabled={readonly}
                    />
                  </div>
                );
              }}
            </Field>

            {/* Collapsible Source Code editor — only full editor in sidebar */}
            <Field<string> name="data.run_code_source">
              {({ field: srcField }) => (
                <Field<string> name="data.run_code_language">
                  {({ field: langField }) => {
                    const lang = langField.value || 'python';
                    const source = srcField.value ?? '';
                    const monacoLang = MONACO_LANG_MAP[lang] || 'plaintext';

                    const handleCodeChange = useCallback(
                      (val: string) => {
                        if (val !== srcField.value) {
                          Promise.resolve().then(() => srcField.onChange(val));
                        }
                      },
                      [srcField]
                    );

                    const handleLoadTemplate = useCallback(() => {
                      srcField.onChange(LANGUAGE_TEMPLATES[lang] || '');
                    }, [lang, srcField]);

                    return (
                      <div style={{ marginBottom: 10 }}>
                        {/* Header row — always visible */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            cursor: 'pointer',
                            userSelect: 'none',
                            marginBottom: expanded ? 8 : 0,
                          }}
                          onClick={() => setExpanded((e) => !e)}
                        >
                          {expanded ? (
                            <IconChevronDown size="small" />
                          ) : (
                            <IconChevronRight size="small" />
                          )}
                          <span style={{ fontSize: 12, color: '#666' }}>
                            Source Code {source ? `(${source.split('\n').length} lines)` : '(empty)'}
                          </span>
                          {expanded && (
                            <Button
                              size="small"
                              theme="borderless"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleLoadTemplate();
                              }}
                              style={{ marginLeft: 'auto', fontSize: 11 }}
                            >
                              Load Template
                            </Button>
                          )}
                        </div>

                        {/* Editor body */}
                        {expanded && (
                          isSidebar ? (
                            <SafeCodeEditor
                              languageId={monacoLang}
                              value={source}
                              onChange={handleCodeChange}
                              readonly={readonly}
                              style={{ height: '260px' }}
                            />
                          ) : (
                            /* On-canvas fallback: plain textarea (Monaco is too heavy inline) */
                            <textarea
                              value={source}
                              onChange={(e) => srcField.onChange(e.target.value)}
                              readOnly={readonly}
                              style={{
                                width: '100%',
                                height: 160,
                                fontFamily: 'monospace',
                                fontSize: 12,
                                padding: 8,
                                border: '1px solid var(--semi-color-border)',
                                borderRadius: 4,
                                resize: 'vertical',
                                background: '#1e1e1e',
                                color: '#d4d4d4',
                              }}
                            />
                          )
                        )}
                      </div>
                    );
                  }}
                </Field>
              )}
            </Field>
          </div>
        );
      }}
    </Field>
  );
}

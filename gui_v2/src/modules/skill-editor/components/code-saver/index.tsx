import { Field, useClientContext } from '@flowgram.ai/free-layout-editor';
import { Button, Input, Notification, Space } from '@douyinfe/semi-ui';

import { useNodeRenderContext } from '../../hooks';
import { FormItem } from '../../form-components';

export function CodeSaver() {
  const { readonly, node } = useNodeRenderContext();
  const { document } = useClientContext();

  const placeholder = 'myskills/skill0/file_name0.py';

  // We need access to the field's onChange method to update it.
  // The handleSave function will be defined inside the render prop.

  return (
    <>
      <FormItem name="file_name" required={false}>
        <Field<string> name="script.fileName">
          {({ field }) => {
            const handleSave = async () => {
              const diagram = document.toJSON();
              const currentNodeData = diagram.nodes.find(n => n.id === node.id)?.data;

              const fileName = field.value || placeholder;
              const content = currentNodeData?.script?.content || '';

              if (!fileName) {
                Notification.error({ title: 'Error', content: 'File name is required to save.', duration: 3 });
                return;
              }

              try {
                const handle = await window.showSaveFilePicker({
                  suggestedName: fileName,
                  types: [
                    {
                      description: 'Python Files',
                      accept: { 'text/python': ['.py'] },
                    },
                    {
                      description: 'Text Files',
                      accept: { 'text/plain': ['.txt'] },
                    },
                  ],
                });
                const writable = await handle.createWritable();
                await writable.write(content);
                await writable.close();

                // This is the correct way to update the field's value
                // We use setTimeout to ensure this runs in the next event loop,
                // preventing a race condition with the component re-rendering.
                setTimeout(() => {
                  field.onChange(handle.name);
                }, 0);

                Notification.success({ title: 'Success', content: `File saved as: ${handle.name}`, duration: 3 });
              } catch (error) {
                if (error instanceof DOMException && error.name === 'AbortError') {
                  console.log('Save operation was cancelled by user');
                } else {
                  Notification.error({ title: 'Error', content: `Failed to save file: ${error}`, duration: 3 });
                }
              }
            };

            return (
              <>
                <Input
                  value={field.value}
                  onChange={(value) => field.onChange(value)}
                  placeholder={placeholder}
                  readonly={readonly}
                />
                {/* Action buttons: Save and Load File */}
                <Field<string> name="script.content">
                  {({ field: contentField }) => (
                    <Field<string> name="script.language">
                      {({ field: langField }) => {
                        const detectLanguage = (filename: string) => {
                          const lower = filename.toLowerCase();
                          if (lower.endsWith('.py')) return 'python';
                          if (lower.endsWith('.ts')) return 'typescript';
                          if (lower.endsWith('.js')) return 'javascript';
                          return langField.value || 'python';
                        };

                        const handleLoad = async () => {
                          try {
                            // Prefer File System Access API when available
                            // @ts-ignore
                            if (window.showOpenFilePicker) {
                              // @ts-ignore
                              const [handle] = await window.showOpenFilePicker({
                                multiple: false,
                                types: [
                                  { description: 'Code Files', accept: { 'text/plain': ['.py', '.js', '.ts', '.txt'] } },
                                ],
                              });
                              const file = await handle.getFile();
                              const text = await file.text();
                              // Update content and file name
                              setTimeout(() => {
                                contentField.onChange(text);
                                field.onChange(handle.name);
                                const lang = detectLanguage(handle.name);
                                if (lang !== langField.value) langField.onChange(lang);
                              }, 0);
                              Notification.success({ title: 'Loaded', content: `Loaded file: ${handle.name}`, duration: 3 });
                            } else {
                              // Fallback: hidden input
                              const input = document.createElement('input');
                              input.type = 'file';
                              input.accept = '.py,.js,.ts,.txt';
                              input.onchange = async () => {
                                const file = (input.files && input.files[0]) || null;
                                if (!file) return;
                                const text = await file.text();
                                setTimeout(() => {
                                  contentField.onChange(text);
                                  field.onChange(file.name);
                                  const lang = detectLanguage(file.name);
                                  if (lang !== langField.value) langField.onChange(lang);
                                }, 0);
                                Notification.success({ title: 'Loaded', content: `Loaded file: ${file.name}`, duration: 3 });
                              };
                              input.click();
                            }
                          } catch (error) {
                            if (error instanceof DOMException && error.name === 'AbortError') {
                              console.log('Open operation was cancelled by user');
                            } else {
                              Notification.error({ title: 'Error', content: `Failed to load file: ${error}`, duration: 3 });
                            }
                          }
                        };

                        return (
                          <Space style={{ marginTop: '10px' }}>
                            <Button onClick={handleSave} disabled={readonly}>
                              Save
                            </Button>
                            <Button onClick={handleLoad} disabled={readonly}>
                              Load File
                            </Button>
                          </Space>
                        );
                      }}
                    </Field>
                  )}
                </Field>
              </>
            );
          }}
        </Field>
      </FormItem>
    </>
  );
}

/**
 * LLM node custom form: adds Model Provider dropdown above Model Name, using model-store
 */
import React, { useRef, useState } from 'react';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, Button, Space, Tag, Tooltip } from '@douyinfe/semi-ui';
import { IconPaperclip, IconDelete } from '@douyinfe/semi-icons';
import { defaultFormMeta } from '../default-form-meta';
import { FormContent, FormHeader, FormItem, FormInputs } from '../../form-components';
import { DisplayOutputs, createInferInputsPlugin } from '@flowgram.ai/form-materials';
import { getModelMap } from '../../stores/model-store';

export const FormRender = ({ form }: FormRenderProps<any>) => {
  const modelMap = getModelMap();
  const providers = Object.keys(modelMap);

  return (
    <>
      <FormHeader />
      <FormContent>
        <Divider />
        {/* Model Provider selector */}
        <FormItem name="modelProvider" type="string" vertical>
          <Field<string> name="inputsValues.modelProvider.content">
            {({ field: providerField }) => {
              const currentProvider = (providerField.value as string) || providers[0] || 'OpenAI';
              const providerOptions = providers.map(p => ({ label: p, value: p }));
              return (
                <div style={{ width: '100%', maxWidth: '100%' }}>
                  <Select
                    value={currentProvider}
                    onChange={(val) => providerField.onChange(val as string)}
                    optionList={providerOptions}
                    style={{ width: '100%' }}
                    dropdownMatchSelectWidth
                    size="small"
                  />
                </div>
              );
            }}
          </Field>
        </FormItem>

        {/* Model Name selector depends on provider */}
        <FormItem name="modelName" type="string" vertical>
          <Field<string> name="inputsValues.modelName.content">
            {({ field: modelField }) => (
              <Field<string> name="inputsValues.modelProvider.content">
                {({ field: providerField }) => {
                  const provider = (providerField.value as string) || providers[0] || 'OpenAI';
                  const models = modelMap[provider] || [];
                  const modelOptions = models.map(m => ({ label: m, value: m }));
                  const value = modelField.value || models[0] || '';
                  // Auto-correct model name if it's not in provider list
                  if (value && models.length && !models.includes(value)) {
                    setTimeout(() => modelField.onChange(models[0]), 0);
                  }
                  return (
                    <div style={{ width: '100%', maxWidth: '100%' }}>
                      <Select
                        value={value}
                        onChange={(val) => modelField.onChange(val as string)}
                        optionList={modelOptions}
                        style={{ width: '100%' }}
                        dropdownMatchSelectWidth
                        size="small"
                      />
                    </div>
                  );
                }}
              </Field>
            )}
          </Field>
        </FormItem>
        {/* Attachments section */}
        <Divider />
        <FormItem name="attachments" type="array" vertical>
          <Field<any[]> name="inputsValues.attachments.content">
            {({ field: attField }) => {
              const files = Array.isArray(attField.value) ? attField.value : [];
              const setFiles = (next: any[]) => setTimeout(() => attField.onChange(next), 0);

              const handleAdd = async () => {
                try {
                  // @ts-ignore
                  if (window.showOpenFilePicker) {
                    // @ts-ignore
                    const handles = await window.showOpenFilePicker({ multiple: true });
                    const newItems: any[] = [];
                    for (const handle of handles) {
                      const file = await handle.getFile();
                      const dataUrl = await new Promise<string>((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload = () => resolve(String(reader.result));
                        reader.onerror = reject;
                        reader.readAsDataURL(file);
                      });
                      newItems.push({ name: file.name, type: file.type, size: file.size, dataUrl });
                    }
                    setFiles([...(files || []), ...newItems]);
                  } else {
                    const input = document.createElement('input');
                    input.type = 'file';
                    input.multiple = true;
                    input.onchange = async () => {
                      const fl = input.files ? Array.from(input.files) : [];
                      const newItems: any[] = [];
                      for (const f of fl) {
                        const dataUrl = await new Promise<string>((resolve, reject) => {
                          const reader = new FileReader();
                          reader.onload = () => resolve(String(reader.result));
                          reader.onerror = reject;
                          reader.readAsDataURL(f);
                        });
                        newItems.push({ name: f.name, type: f.type, size: f.size, dataUrl });
                      }
                      setFiles([...(files || []), ...newItems]);
                    };
                    input.click();
                  }
                } catch (e) {
                  console.error('Attachment add failed', e);
                }
              };

              const handleRemoveAt = (idx: number) => {
                const next = [...files];
                next.splice(idx, 1);
                setFiles(next);
              };

              // Voice recorder utilities (press-and-hold to record)
              const mediaRecorderRef = useRef<MediaRecorder | null>(null);
              const mediaStreamRef = useRef<MediaStream | null>(null);
              const chunksRef = useRef<Blob[]>([]);
              const [isRecording, setIsRecording] = useState(false);

              const startRecording = async () => {
                try {
                  if (isRecording) return;
                  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                  mediaStreamRef.current = stream;
                  const mimeType = 'audio/webm';
                  const recorder = new MediaRecorder(stream, { mimeType });
                  mediaRecorderRef.current = recorder;
                  chunksRef.current = [];
                  recorder.ondataavailable = (e) => {
                    if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
                  };
                  recorder.onstop = async () => {
                    try {
                      const blob = new Blob(chunksRef.current, { type: mimeType });
                      const dataUrl: string = await new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload = () => resolve(String(reader.result));
                        reader.onerror = reject;
                        reader.readAsDataURL(blob);
                      });
                      const fileName = `recording-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`;
                      const newItem = { name: fileName, type: mimeType, size: blob.size, dataUrl };
                      setFiles([...(files || []), newItem]);
                    } catch (err) {
                      console.error('Recording finalize failed', err);
                    } finally {
                      // stop all tracks
                      mediaStreamRef.current?.getTracks().forEach(t => t.stop());
                      mediaStreamRef.current = null;
                      mediaRecorderRef.current = null;
                      chunksRef.current = [];
                      setIsRecording(false);
                    }
                  };
                  recorder.start();
                  setIsRecording(true);
                } catch (err) {
                  console.error('Microphone access/recording failed', err);
                  setIsRecording(false);
                }
              };

              const stopRecording = () => {
                try {
                  if (mediaRecorderRef.current && isRecording) {
                    mediaRecorderRef.current.stop();
                  }
                } catch (err) {
                  console.error('Stop recording error', err);
                  setIsRecording(false);
                }
              };

              return (
                <div style={{ width: '100%' }}>
                  <Space wrap>
                    {(files || []).map((f, idx) => (
                      <Tag key={`${f.name}-${idx}`} closable onClose={() => handleRemoveAt(idx)}>
                        {f.name}
                      </Tag>
                    ))}
                  </Space>
                  <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Tooltip content="Add attachment(s)">
                      <Button icon={<IconPaperclip />} onClick={handleAdd} size="small">
                        Add Attachment
                      </Button>
                    </Tooltip>
                    <Tooltip content={isRecording ? 'Recording... release to finish' : 'Hold to record voice'}>
                      <Button
                        icon={<span role="img" aria-label="mic">🎤</span>}
                        size="small"
                        type={isRecording ? 'secondary' : 'tertiary'}
                        onMouseDown={startRecording}
                        onMouseUp={stopRecording}
                        onMouseLeave={() => isRecording && stopRecording()}
                        onTouchStart={startRecording}
                        onTouchEnd={stopRecording}
                      >
                        {isRecording ? 'Recording…' : 'Hold to Record'}
                      </Button>
                    </Tooltip>
                  </div>
                </div>
              );
            }}
          </Field>
        </FormItem>
        {/* Render the rest of inputs using the default component */}
        <FormInputs />
        <Divider />
        <DisplayOutputs displayFromScope />
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta = {
  render: (props) => <FormRender {...props} />,
  effect: defaultFormMeta.effect,
  validate: defaultFormMeta.validate,
  plugins: [createInferInputsPlugin({ sourceKey: 'inputsValues', targetKey: 'inputs' })],
};

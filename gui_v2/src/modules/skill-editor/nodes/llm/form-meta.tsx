/**
 * LLM node custom form: adds Model Provider dropdown above Model Name
 * All LLM configuration is dynamically loaded from backend llm_providers.json
 */
import { useMemo, useRef, useState, useEffect } from 'react';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, Button, Space, Tag, Tooltip } from '@douyinfe/semi-ui';
import { IconPaperclip } from '@douyinfe/semi-icons';
import { defaultFormMeta } from '../default-form-meta';
import { FormContent, FormHeader, FormItem, FormInputs } from '../../form-components';
import { PromptInputWithSelector } from '../../form-components/PromptInputWithSelector';
import { DisplayOutputs, createInferInputsPlugin } from '@flowgram.ai/form-materials';
import { get_ipc_api } from '../../../../services/ipc_api';
import { usePromptStore } from '../../../../stores/promptStore';
import { useUserStore } from '../../../../stores/userStore';

// Temporary in-memory storage for user-configured values (per provider)
// This preserves user settings when switching between providers during the current session
interface ProviderSettings {
  apiKey?: string;
  apiHost?: string;
  temperature?: number;
  modelName?: string;
}

// Global storage for current editing session (cleared on page refresh/logout)
const tempProviderStorage: Map<string, ProviderSettings> = new Map();

// Provider configuration from backend
interface LLMProvider {
  name: string;
  display_name: string;
  class_name: string;
  provider: string;
  api_key_env_vars: string[];
  base_url: string | null;
  default_model: string;
  description: string;
  documentation_url: string;
  is_local: boolean;
  api_key_configured: boolean;
  supported_models: Array<{
    name: string;
    display_name: string;
    model_id: string;
    default_temperature: number;
    max_tokens: number;
    supports_streaming: boolean;
    supports_function_calling: boolean;
    supports_vision: boolean;
    cost_per_1k_tokens: number;
    description: string;
  }>;
  // Credentials (if configured)
  api_key?: string;
  credentials?: {
    api_key?: string;
    azure_endpoint?: string;
    aws_access_key_id?: string;
    aws_secret_access_key?: string;
  };
}

// Cache for providers data
let providersCache: LLMProvider[] = [];
let providersCacheTime: number = 0;
const CACHE_TTL = 10000; // 10 seconds cache

// Fetch all providers with credentials from backend
async function fetchProvidersWithCredentials(): Promise<LLMProvider[]> {
  const now = Date.now();
  if (providersCache.length > 0 && now - providersCacheTime < CACHE_TTL) {
    return providersCache;
  }

  try {
    const response = await get_ipc_api().getLLMProvidersWithCredentials<{ providers: LLMProvider[] }>();
    if (response.success && response.data?.providers) {
      providersCache = response.data.providers;
      providersCacheTime = now;
      console.log('[LLM Node] Loaded providers from backend:', providersCache.map(p => p.name));
      return providersCache;
    }
  } catch (error) {
    console.error('[LLM Node] Failed to fetch providers:', error);
  }
  return [];
}

export const FormRender = (_props: FormRenderProps<any>) => {
  const username = useUserStore((s) => s.username || 'user');
  const { prompts, fetch, fetched } = usePromptStore();
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [loading, setLoading] = useState(true);

  // Load providers on mount
  useEffect(() => {
    fetchProvidersWithCredentials().then((data) => {
      setProviders(data);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!fetched && username) {
      fetch(username);
    }
  }, [fetched, fetch, username]);

  const promptOptions = useMemo(() => {
    const base = prompts.map((prompt) => {
      const location = prompt.location === 'sample_prompts' ? 'sample' : 'my';
      const label = `${location}:${prompt.title || prompt.topic || prompt.id}`;
      return {
        label,
        value: prompt.id,
      };
    });
    return [
      { label: 'In-line Prompt', value: 'inline' as const },
      ...base,
    ];
  }, [prompts]);

  // Build provider options
  const providerOptions = providers.map(p => ({ label: p.display_name, value: p.name }));
  
  // Build model map (provider name -> models)
  const modelMap: Record<string, string[]> = {};
  providers.forEach(p => {
    modelMap[p.name] = p.supported_models.map(m => m.model_id || m.name);
  });

  // Get provider config by name
  const getProviderConfig = (providerName: string) => {
    return providers.find(p => p.name === providerName);
  };

  // Get default API key template for provider
  const getApiKeyTemplate = (providerName: string): string => {
    // Generate appropriate placeholder based on provider
    if (providerName.includes('OpenAI')) {
      return 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
    } else if (providerName.includes('Anthropic') || providerName.includes('Claude')) {
      return 'sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
    } else if (providerName.includes('Google') || providerName.includes('Gemini')) {
      return 'AIzaxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
    } else if (providerName.includes('AWS') || providerName.includes('Bedrock')) {
      return 'AKIAXXXXXXXXXXXXXXXX';
    } else if (providerName.includes('DeepSeek')) {
      return 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
    } else if (providerName.includes('Qwen') || providerName.includes('DashScope')) {
      return 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
    } else if (providerName.includes('Bytedance') || providerName.includes('Doubao')) {
      return 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
    } else if (providerName.includes('Ollama')) {
      return 'ollama';
    } else {
      return 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
    }
  };

  if (loading) {
    return (
      <>
        <FormHeader />
        <FormContent>
          <div style={{ padding: '20px', textAlign: 'center' }}>
            Loading LLM providers...
          </div>
        </FormContent>
      </>
    );
  }

  return (
    <>
      <FormHeader />
      <FormContent>
        <Divider />
        <FormItem name="promptSelection" type="string" vertical>
          <Field<string> name="inputsValues.promptSelection.content">
            {({ field: promptSelectorField }) => {
              const selected = (promptSelectorField.value as string) || 'inline';
              return (
                <Select
                  value={selected}
                  optionList={promptOptions}
                  onChange={(val) => promptSelectorField.onChange(val as string)}
                  style={{ width: '100%' }}
                  size="small"
                  dropdownMatchSelectWidth
                />
              );
            }}
          </Field>
        </FormItem>
        {/* Model Provider selector */}
        <FormItem name="modelProvider" type="string" vertical>
          <Field<string> name="inputsValues.modelProvider.content">
            {({ field: providerField }) => {
              const currentProvider = (providerField.value as string) || (providers[0]?.name) || 'OpenAI';
              
              return (
                <Field<string> name="inputsValues.apiHost.content">
                  {({ field: apiHostField }) => (
                    <Field<string> name="inputsValues.apiKey.content">
                      {({ field: apiKeyField }) => (
                        <Field<number> name="inputsValues.temperature.content">
                          {({ field: temperatureField }) => (
                            <Field<string> name="inputsValues.modelName.content">
                              {({ field: modelNameField }) => {
                                // Auto-fill logic when provider changes
                                useEffect(() => {
                                  const providerConfig = getProviderConfig(currentProvider);
                                  if (!providerConfig) return;

                                  // Save current values to temp storage (for future use)

                                  // Get or create temporary settings for current provider
                                  let tempSettings = tempProviderStorage.get(currentProvider);
                                  if (!tempSettings) {
                                    tempSettings = {};
                                    tempProviderStorage.set(currentProvider, tempSettings);
                                  }

                                  console.log(`[LLM Node] Provider: ${currentProvider}, Configured: ${!!providerConfig.api_key_configured}, Temp: ${!!tempSettings.apiKey}`);

                                  // === API KEY LOGIC ===
                                  // Priority: 1. Temp storage -> 2. Backend credentials -> 3. Default template
                                  if (tempSettings.apiKey) {
                                    // Use temporarily saved value
                                    setTimeout(() => apiKeyField.onChange(tempSettings.apiKey!), 0);
                                    console.log(`[LLM Node] Restored API key from temp storage for ${currentProvider}`);
                                  } else if (providerConfig.api_key_configured) {
                                    // Use API key from backend
                                    let apiKey = '';
                                    if (providerConfig.credentials) {
                                      // Handle special providers with multiple credentials
                                      if (currentProvider === 'Azure OpenAI' && providerConfig.credentials.api_key) {
                                        apiKey = providerConfig.credentials.api_key;
                                      } else if (currentProvider === 'AWS Bedrock' && providerConfig.credentials.aws_access_key_id) {
                                        apiKey = providerConfig.credentials.aws_access_key_id;
                                      }
                                    } else if (providerConfig.api_key) {
                                      apiKey = providerConfig.api_key;
                                    }

                                    if (apiKey) {
                                      setTimeout(() => apiKeyField.onChange(apiKey), 0);
                                      console.log(`[LLM Node] Auto-filled API key from backend for ${currentProvider}`);
                                    } else {
                                      setTimeout(() => apiKeyField.onChange(getApiKeyTemplate(currentProvider)), 0);
                                    }
                                  } else {
                                    // Use default template
                                    console.log(`[LLM Node] No config found, using template for ${currentProvider}`);
                                    setTimeout(() => apiKeyField.onChange(getApiKeyTemplate(currentProvider)), 0);
                                  }

                                  // === API HOST LOGIC ===
                                  // Priority: 1. Temp storage -> 2. Backend base_url -> 3. Default
                                  if (tempSettings.apiHost) {
                                    setTimeout(() => apiHostField.onChange(tempSettings.apiHost!), 0);
                                  } else if (providerConfig.credentials?.azure_endpoint) {
                                    // Special case for Azure
                                    setTimeout(() => apiHostField.onChange(providerConfig.credentials!.azure_endpoint!), 0);
                                  } else {
                                    // Use base_url or empty string
                                    setTimeout(() => apiHostField.onChange(providerConfig.base_url || ''), 0);
                                  }

                                  // === TEMPERATURE LOGIC ===
                                  // Priority: 1. Temp storage -> 2. Keep existing (or default 0.5)
                                  if (tempSettings.temperature !== undefined) {
                                    setTimeout(() => temperatureField.onChange(tempSettings.temperature!), 0);
                                  }
                                  // Otherwise, keep existing value

                                  // === MODEL NAME LOGIC ===
                                  // Priority: 1. Temp storage -> 2. Configured model -> 3. First in list
                                  const models = modelMap[currentProvider] || [];
                                  if (tempSettings.modelName && models.includes(tempSettings.modelName)) {
                                    setTimeout(() => modelNameField.onChange(tempSettings.modelName!), 0);
                                  } else if (providerConfig.default_model && models.includes(providerConfig.default_model)) {
                                    setTimeout(() => modelNameField.onChange(providerConfig.default_model), 0);
                                  } else if (models.length > 0) {
                                    setTimeout(() => modelNameField.onChange(models[0]), 0);
                                  }

                                }, [currentProvider, providers]);

                                return (
                                  <div style={{ width: '100%', maxWidth: '100%' }}>
                                    <Select
                                      value={currentProvider}
                                      onChange={(val) => providerField.onChange(val as string)}
                                      optionList={providerOptions}
                                      style={{ width: '100%' }}
                                      dropdownMatchSelectWidth
                                      size="small"
                                      placeholder="Select LLM Provider"
                                    />
                                  </div>
                                );
                              }}
                            </Field>
                          )}
                        </Field>
                      )}
                    </Field>
                  )}
                </Field>
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
                  const provider = (providerField.value as string) || (providers[0]?.name) || 'OpenAI';
                  const models = modelMap[provider] || [];
                  const modelOptions = models.map(m => ({ label: m, value: m }));
                  const value = modelField.value || models[0] || '';
                  
                  // Auto-correct model name if it's not in provider list
                  useEffect(() => {
                    if (value && models.length && !models.includes(value)) {
                      setTimeout(() => modelField.onChange(models[0]), 0);
                    }
                  }, [provider, value, models]);

                  return (
                    <div style={{ width: '100%', maxWidth: '100%' }}>
                      <Select
                        value={value}
                        onChange={(val) => modelField.onChange(val as string)}
                        optionList={modelOptions}
                        style={{ width: '100%' }}
                        dropdownMatchSelectWidth
                        size="small"
                        placeholder="Select Model"
                      />
                    </div>
                  );
                }}
              </Field>
            )}
          </Field>
        </FormItem>
        <Field<string> name="inputsValues.promptSelection.content">
          {({ field: promptSelectorField }) => (
            <FormItem name="attachments" type="array" vertical>
              <Field<any[]> name="inputsValues.attachments.content">
                {({ field: attField }) => {
                  const files = Array.isArray(attField.value) ? attField.value : [];
                  const setFiles = (next: any[]) => setTimeout(() => attField.onChange(next), 0);

              const handleAdd = async () => {
                try {
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
                    return;
                  }

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

              const attachmentsBlock = (
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

              // Hide attachments when using external library prompt
              if ((promptSelectorField.value as string) && promptSelectorField.value !== 'inline') {
                return null;
              }

              return attachmentsBlock;
            }}
          </Field>
        </FormItem>
          )}
        </Field>

        {/* System Prompt with Selector */}
        <Divider />
        <PromptInputWithSelector
          promptFieldName="inputsValues.systemPrompt"
          promptIdFieldName="inputsValues.systemPromptId"
          label="System Prompt"
          promptType="systemPrompt"
          schema={{ type: 'string' }}
        />

        {/* User Prompt with Selector */}
        <PromptInputWithSelector
          promptFieldName="inputsValues.prompt"
          promptIdFieldName="inputsValues.promptId"
          label="Prompt"
          promptType="prompt"
          schema={{ type: 'string' }}
        />

        {/* Render the rest of inputs using the default component */}
        <Field<string> name="inputsValues.promptSelection.content">
          {({ field: promptSelectorField }) => (
            <FormInputs
              extraFilter={(key) => {
                if ((key === 'systemPrompt' || key === 'prompt') && promptSelectorField.value && promptSelectorField.value !== 'inline') {
                  return false;
                }
                return true;
              }}
            />
          )}
        </Field>
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

/**
 * Browser Automation node custom form
 */
import { useEffect, useMemo, useState } from 'react';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Divider, Select } from '@douyinfe/semi-ui';
import { defaultFormMeta } from '../default-form-meta';
import { FormContent, FormHeader, FormItem, FormInputs } from '../../form-components';
import { PromptInputWithSelector } from '../../form-components/PromptInputWithSelector';
import { DisplayOutputs } from '@flowgram.ai/form-materials';
import { get_ipc_api } from '../../../../services/ipc_api';
import { usePromptStore } from '../../../../stores/promptStore';
import { useUserStore } from '../../../../stores/userStore';

const TOOL_OPTIONS = [
  { label: 'browser-use', value: 'browser-use' },
  { label: 'crawl4ai', value: 'crawl4ai' },
  { label: 'browsebase', value: 'browsebase' },
];

const BROWSER_OPTIONS = [
  { label: 'New Chromium', value: 'new chromium' },
  { label: 'Existing Chrome', value: 'existing chrome' },
  { label: 'Ads Power', value: 'ads power' },
  { label: 'Ziniao', value: 'ziniao' },
  { label: 'Multi-Login', value: 'multi-login' },
];

const BROWSER_DRIVER_OPTIONS = [
  { label: 'Native', value: 'native' },
  { label: 'Selenium', value: 'selenium' },
  { label: 'Playwright', value: 'playwright' },
  { label: 'Puppeteer', value: 'puppeteer' },
];

// Cache for LLM providers from backend
let cachedProviders: Map<string, any> = new Map();
let cacheTime: number = 0;
const CACHE_TTL = 5000; // 5 seconds

async function fetchLLMProviders(): Promise<Map<string, any>> {
  const now = Date.now();
  if (cachedProviders.size > 0 && now - cacheTime < CACHE_TTL) {
    return cachedProviders;
  }

  try {
    const response = await get_ipc_api().getLLMProvidersWithCredentials<{ providers: any[] }>();
    if (response.success && response.data?.providers) {
      const map = new Map();
      response.data.providers.forEach((provider: any) => {
        map.set(provider.name, provider);
      });
      cachedProviders = map;
      cacheTime = now;
      return map;
    }
  } catch (error) {
    console.error('[Browser Automation] Failed to fetch LLM providers:', error);
  }
  return new Map();
}

export const FormRender = (_props: FormRenderProps<any>) => {
  const username = useUserStore((s) => s.username || 'user');
  const { prompts, fetch, fetched } = usePromptStore();
  const [llmProviders, setLlmProviders] = useState<Map<string, any>>(new Map());

  useEffect(() => {
    fetchLLMProviders().then(setLlmProviders);
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

  const providers = Array.from(llmProviders.keys());
  const modelMap: Record<string, string[]> = {};
  llmProviders.forEach((provider, name) => {
    modelMap[name] = provider.supported_models?.map((m: any) => m.name) || [];
  });

  return (
    <>
      <FormHeader />
      <FormContent>
        <Divider />
        <FormItem name="promptSelection" type="string" vertical>
          <Field<string> name="inputsValues.promptSelection.content">
            {({ field: promptSelectorField }) => (
              <Select
                value={(promptSelectorField.value as string) || 'inline'}
                onChange={(val) => promptSelectorField.onChange(val as string)}
                optionList={promptOptions}
                style={{ width: '100%' }}
                dropdownMatchSelectWidth
                size="small"
              />
            )}
          </Field>
        </FormItem>
        {/* Tool selector */}
        <FormItem name="tool" type="string" vertical>
          <Field<string> name="inputsValues.tool.content">
            {({ field }) => (
              <Select
                value={(field.value as string) || TOOL_OPTIONS[0].value}
                onChange={(val) => field.onChange(val as string)}
                optionList={TOOL_OPTIONS}
                style={{ width: '100%' }}
                dropdownMatchSelectWidth
                size="small"
              />
            )}
          </Field>
        </FormItem>

        {/* Browser selector */}
        <FormItem name="browser" type="string" vertical>
          <Field<string> name="inputsValues.browser.content">
            {({ field }) => (
              <Select
                value={(field.value as string) || BROWSER_OPTIONS[0].value}
                onChange={(val) => field.onChange(val as string)}
                optionList={BROWSER_OPTIONS}
                style={{ width: '100%' }}
                dropdownMatchSelectWidth
                size="small"
              />
            )}
          </Field>
        </FormItem>

        {/* Browser Driver selector */}
        <FormItem name="browserDriver" type="string" vertical>
          <Field<string> name="inputsValues.browserDriver.content">
            {({ field }) => (
              <Select
                value={(field.value as string) || BROWSER_DRIVER_OPTIONS[0].value}
                onChange={(val) => field.onChange(val as string)}
                optionList={BROWSER_DRIVER_OPTIONS}
                style={{ width: '100%' }}
                dropdownMatchSelectWidth
                size="small"
              />
            )}
          </Field>
        </FormItem>

        {/* CDP Port input */}
        <FormItem name="cdpPort" type="string" vertical>
          <Field<string> name="inputsValues.cdpPort.content">
            {({ field }) => (
              <input
                type="text"
                value={(field.value as string) || ''}
                onChange={(e) => field.onChange(e.target.value)}
                placeholder="CDP Port (e.g., 9222)"
                style={{ width: '100%', padding: '6px 12px', fontSize: '14px', border: '1px solid #d9d9d9', borderRadius: '3px' }}
              />
            )}
          </Field>
        </FormItem>

        {/* Model Provider selector */}
        <FormItem name="modelProvider" type="string" vertical>
          <Field<string> name="inputsValues.modelProvider.content">
            {({ field: providerField }) => {
              const currentProvider = (providerField.value as string) || providers[0] || 'OpenAI';
              const providerOptions = providers.map(p => ({ label: p, value: p }));
              return (
                <Select
                  value={currentProvider}
                  onChange={(val) => providerField.onChange(val as string)}
                  optionList={providerOptions}
                  style={{ width: '100%' }}
                  dropdownMatchSelectWidth
                  size="small"
                />
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
                  if (value && models.length && !models.includes(value)) {
                    setTimeout(() => modelField.onChange(models[0]), 0);
                  }
                  return (
                    <Select
                      value={value}
                      onChange={(val) => modelField.onChange(val as string)}
                      optionList={modelOptions}
                      style={{ width: '100%' }}
                      dropdownMatchSelectWidth
                      size="small"
                    />
                  );
                }}
              </Field>
            )}
          </Field>
        </FormItem>

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

        {/* Render the rest of inputs using the default component (temperature, etc) */}
        <Field<string> name="inputsValues.promptSelection.content">
          {({ field: promptSelectorField }) => (
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
};

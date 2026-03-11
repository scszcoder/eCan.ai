/**
 * Browser Automation node custom form
 */
import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, Button, Checkbox } from '@douyinfe/semi-ui';
import { IconEdit } from '@douyinfe/semi-icons';
import { defaultFormMeta } from '../default-form-meta';
import { FormContent, FormHeader, FormItem, FormInputs } from '../../form-components';
import { PromptInputWithSelector } from '../../form-components/PromptInputWithSelector';
import { DisplayOutputs, createInferInputsPlugin } from '@flowgram.ai/form-materials';
import { get_ipc_api } from '../../../../services/ipc_api';
import { usePromptStore } from '../../../../stores/promptStore';
import { useUserStore } from '../../../../stores/userStore';
import { getCommonFieldLabel } from '../../utils/field-labels';

// Browser profile interface
interface BrowserProfile {
  id: string;
  name: string;
  isDefault: boolean;
}

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

const PromptSelectionDropdown = ({
  selected,
  username,
  prompts,
  fetch,
  promptStoreLoading,
  promptOptions,
  onChange,
  onEdit,
}: {
  selected: string;
  username: string;
  prompts: any[];
  fetch: (username: string, force?: boolean) => Promise<void>;
  promptStoreLoading: boolean;
  promptOptions: any[];
  onChange: (val: string) => void;
  onEdit: () => void;
}) => {
  const [refreshing, setRefreshing] = useState(false);
  const attemptedIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!selected || selected === 'inline') return;
    if (!username) return;
    const exists = prompts.some((p: any) => p?.id === selected);
    if (exists) return;
    // Prevent infinite loop: only attempt once per ID
    if (attemptedIds.current.has(selected)) return;
    if (promptStoreLoading || refreshing) return;
    attemptedIds.current.add(selected);
    setRefreshing(true);
    fetch(username, true).finally(() => setRefreshing(false));
  }, [selected, username, prompts, fetch, promptStoreLoading]);

  const showEditButton = selected && selected !== 'inline';

  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', width: '100%' }}>
      <Select
        value={selected}
        onChange={(val) => onChange(val as string)}
        optionList={promptOptions}
        style={{ flex: 1 }}
        dropdownMatchSelectWidth
        size="small"
        loading={refreshing}
      />
      {showEditButton && (
        <Button
          icon={<IconEdit />}
          size="small"
          theme="borderless"
          onClick={onEdit}
          style={{ flexShrink: 0 }}
        />
      )}
    </div>
  );
};

export const FormRender = (_props: FormRenderProps<any>) => {
  const { t } = useTranslation('skillEditor');
  const navigate = useNavigate();
  const username = useUserStore((s) => s.username || 'user');
  const { prompts, fetch, fetched, loading: promptStoreLoading } = usePromptStore();
  const [llmProviders, setLlmProviders] = useState<Map<string, any>>(new Map());
  const [browserProfiles, setBrowserProfiles] = useState<BrowserProfile[]>([]);

  // Fetch browser profiles from backend
  const fetchBrowserProfiles = useCallback(async () => {
    try {
      const response = await get_ipc_api().getBrowserUseSettings<{ profiles: BrowserProfile[] }>();
      if (response.success && response.data?.profiles) {
        setBrowserProfiles(response.data.profiles);
      }
    } catch (error) {
      console.error('[Browser Automation] Failed to fetch browser profiles:', error);
    }
  }, []);

  useEffect(() => {
    fetchLLMProviders().then(setLlmProviders);
    fetchBrowserProfiles();
  }, [fetchBrowserProfiles]);

  useEffect(() => {
    if (!fetched && username) {
      fetch(username);
    }
  }, [fetched, fetch, username]);

  const promptOptions = useMemo(() => {
    const base = prompts.map((prompt) => {
      const location = prompt.source === 'sample_prompts' ? 'sample' : 'my';
      const label = `${location}:${prompt.title || prompt.topic || prompt.id}`;
      return {
        label,
        value: prompt.id,
      };
    });
    return [
      { label: t('nodes.browserAutomation.inlinePrompt'), value: 'inline' as const },
      ...base,
    ];
  }, [prompts, t]);

  const providers = Array.from(llmProviders.keys());
  const modelMap: Record<string, string[]> = {};
  llmProviders.forEach((provider, name) => {
    modelMap[name] = provider.supported_models?.map((m: any) => m.name) || [];
  });

  // Memoized options with i18n
  const TOOL_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.tools.browserUse'), value: 'browser-use' },
    { label: t('nodes.browserAutomation.tools.crawl4ai'), value: 'crawl4ai' },
    { label: t('nodes.browserAutomation.tools.browsebase'), value: 'browsebase' },
  ], [t]);

  const BROWSER_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.browsers.newChromium'), value: 'new chromium' },
    { label: t('nodes.browserAutomation.browsers.existingChrome'), value: 'existing chrome' },
    { label: t('nodes.browserAutomation.browsers.adsPower'), value: 'ads power' },
    { label: t('nodes.browserAutomation.browsers.ziniao'), value: 'ziniao' },
    { label: t('nodes.browserAutomation.browsers.multiLogin'), value: 'multi-login' },
  ], [t]);

  const BROWSER_DRIVER_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.drivers.native'), value: 'native' },
    { label: t('nodes.browserAutomation.drivers.selenium'), value: 'selenium' },
    { label: t('nodes.browserAutomation.drivers.playwright'), value: 'playwright' },
    { label: t('nodes.browserAutomation.drivers.puppeteer'), value: 'puppeteer' },
  ], [t]);

  const SHOP_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.shops.amazon'), value: 'amazon' },
    { label: t('nodes.browserAutomation.shops.ebay'), value: 'ebay' },
    { label: t('nodes.browserAutomation.shops.etsy'), value: 'etsy' },
    { label: t('nodes.browserAutomation.shops.walmart'), value: 'walmart' },
    { label: t('nodes.browserAutomation.shops.tiktok'), value: 'tiktok' },
    { label: t('nodes.browserAutomation.shops.shopify'), value: 'shopify' },
    { label: t('nodes.browserAutomation.shops.woocommerce'), value: 'woocommerce' },
    { label: t('nodes.browserAutomation.shops.custom'), value: 'custom' },
  ], [t]);

  const RUN_ENVIRONMENT_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.runEnvironments.fullLocal'), value: 'full_local' },
    { label: t('nodes.browserAutomation.runEnvironments.passiveLocal'), value: 'passive_local' },
    { label: t('nodes.browserAutomation.runEnvironments.hybridCloud'), value: 'hybrid_cloud' },
    { label: t('nodes.browserAutomation.runEnvironments.fullCloud'), value: 'full_cloud' },
  ], [t]);

  const PRIVACY_STRATEGY_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.privacyStrategies.none'), value: 'none' },
    { label: t('nodes.browserAutomation.privacyStrategies.patternFilter'), value: 'pattern_filter' },
    { label: t('nodes.browserAutomation.privacyStrategies.localLlm'), value: 'local_llm' },
  ], [t]);

  return (
    <>
      <FormHeader />
      <FormContent>
        <Divider />
        <FormItem name="promptSelection" label={getCommonFieldLabel('promptSelection', t)} type="string" vertical>
          <Field<string> name="inputsValues.promptSelection.content">
            {({ field: promptSelectorField }) => {
              const selectedValue = (promptSelectorField.value as string) || 'inline';
              return (
                <PromptSelectionDropdown
                  selected={selectedValue}
                  username={username}
                  prompts={prompts}
                  fetch={fetch}
                  promptStoreLoading={promptStoreLoading}
                  promptOptions={promptOptions}
                  onChange={(val) => promptSelectorField.onChange(val as string)}
                  onEdit={() => {
                    navigate(`/prompts?id=${encodeURIComponent(selectedValue)}&edit=true`);
                  }}
                />
              );
            }}
          </Field>
        </FormItem>
        {/* Tool selector */}
        <FormItem name="tool" label={getCommonFieldLabel('tool', t)} type="string" vertical>
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
        <FormItem name="browser" label={getCommonFieldLabel('browser', t)} type="string" vertical>
          <Field<string> name="inputsValues.browser.content">
            {({ field }) => {
              const browserValue = (field.value as string) || BROWSER_OPTIONS[0].value;
              return (
                <>
                  <Select
                    value={browserValue}
                    onChange={(val) => field.onChange(val as string)}
                    optionList={BROWSER_OPTIONS}
                    style={{ width: '100%' }}
                    dropdownMatchSelectWidth
                    size="small"
                  />
                  {browserValue === 'existing chrome' && (
                    <div style={{ marginTop: 6, padding: '6px 8px', backgroundColor: '#fff7e6', border: '1px solid #ffd591', borderRadius: 4, fontSize: 11, lineHeight: 1.5 }}>
                      <strong style={{ color: '#000' }}>Please be sure to launch Chrome using the following command:</strong>
                      <div style={{ marginTop: 4, fontFamily: 'monospace', fontSize: 10, wordBreak: 'break-all', color: '#333' }}>
                        chrome.exe --remote-debugging-port=9228 --user-data-dir="C:\chrome_data" --disable-features=SharedStorage,InterestCohort
                      </div>
                    </div>
                  )}
                </>
              );
            }}
          </Field>
        </FormItem>

        {/* Browser Driver selector */}
        <FormItem name="browserDriver" label={getCommonFieldLabel('browserDriver', t)} type="string" vertical>
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
        <FormItem name="cdpPort" label={getCommonFieldLabel('cdpPort', t)} type="string" vertical>
          <Field<string> name="inputsValues.cdpPort.content">
            {({ field }) => (
              <input
                type="text"
                value={(field.value as string) || '9228'}
                onChange={(e) => field.onChange(e.target.value)}
                placeholder={t('nodes.browserAutomation.cdpPortPlaceholder')}
                style={{ width: '100%', padding: '6px 12px', fontSize: '14px', border: '1px solid #d9d9d9', borderRadius: '3px', color: '#000000', backgroundColor: '#ffffff' }}
              />
            )}
          </Field>
        </FormItem>

        {/* Run Environment selector */}
        <FormItem name="runEnvironment" label={getCommonFieldLabel('runEnvironment', t)} type="string" vertical>
          <Field<string> name="inputsValues.runEnvironment.content">
            {({ field }) => (
              <Select
                value={(field.value as string) || 'full_local'}
                onChange={(val) => field.onChange(val as string)}
                optionList={RUN_ENVIRONMENT_OPTIONS}
                style={{ width: '100%' }}
                dropdownMatchSelectWidth
                size="small"
              />
            )}
          </Field>
        </FormItem>

        {/* Privacy Strategy selector */}
        <FormItem name="privacyStrategy" label={getCommonFieldLabel('privacyStrategy', t)} type="string" vertical>
          <Field<string> name="inputsValues.privacyStrategy.content">
            {({ field }) => (
              <Select
                value={(field.value as string) || 'none'}
                onChange={(val) => field.onChange(val as string)}
                optionList={PRIVACY_STRATEGY_OPTIONS}
                style={{ width: '100%' }}
                dropdownMatchSelectWidth
                size="small"
              />
            )}
          </Field>
        </FormItem>

        {/* Enable Judge checkbox */}
        <FormItem name="enableJudge" label={getCommonFieldLabel('enableJudge', t)} type="boolean" vertical>
          <Field<boolean> name="inputsValues.enableJudge.content">
            {({ field }) => (
              <Checkbox
                checked={!!field.value}
                onChange={(e) => field.onChange((e.target as HTMLInputElement).checked)}
              >
                {t('nodes.browserAutomation.enableJudgeDesc')}
              </Checkbox>
            )}
          </Field>
        </FormItem>

        {/* Shop selector */}
        <FormItem name="shopName" label={getCommonFieldLabel('shopName', t)} type="string" vertical>
          <Field<string> name="inputsValues.shopName.content">
            {({ field: shopField }) => (
              <Field<string> name="inputsValues.customShopName.content">
                {({ field: customShopField }) => {
                  const shopValue = (shopField.value as string) || SHOP_OPTIONS[0].value;
                  const isCustom = shopValue === 'custom';
                  return (
                    <>
                      <Select
                        value={shopValue}
                        onChange={(val) => shopField.onChange(val as string)}
                        optionList={SHOP_OPTIONS}
                        style={{ width: '100%' }}
                        dropdownMatchSelectWidth
                        size="small"
                      />
                      {isCustom && (
                        <input
                          type="text"
                          value={(customShopField.value as string) || ''}
                          onChange={(e) => customShopField.onChange(e.target.value)}
                          placeholder={t('nodes.browserAutomation.customShopPlaceholder')}
                          style={{ width: '100%', padding: '6px 12px', fontSize: '14px', border: '1px solid #d9d9d9', borderRadius: '3px', marginTop: '8px', color: '#000000', backgroundColor: '#ffffff' }}
                        />
                      )}
                    </>
                  );
                }}
              </Field>
            )}
          </Field>
        </FormItem>

        {/* Model Provider selector */}
        <FormItem name="modelProvider" label={getCommonFieldLabel('modelProvider', t)} type="string" vertical>
          <Field<string> name="inputsValues.modelProvider.content">
            {({ field: providerField }) => {
              const currentProvider = (providerField.value as string) || providers[0] || 'OpenAI';
              const providerOptions = providers.map(p => ({ label: p, value: p }));

              // Persist resolved provider back to document model if missing
              useEffect(() => {
                if (!providerField.value && currentProvider) {
                  setTimeout(() => providerField.onChange(currentProvider), 0);
                  console.log(`[Browser Node] Persisted missing modelProvider: ${currentProvider}`);
                }
              }, [currentProvider, providerField.value]);

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
        <FormItem name="modelName" label={getCommonFieldLabel('modelName', t)} type="string" vertical>
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

        {/* Use Thinking checkbox */}
        <FormItem name="useThinking" label={getCommonFieldLabel('useThinking', t)} type="boolean" vertical>
          <Field<boolean> name="inputsValues.useThinking.content">
            {({ field }) => (
              <Checkbox
                checked={!!field.value}
                onChange={(e) => field.onChange((e.target as HTMLInputElement).checked)}
              >
                {t('nodes.browserAutomation.useThinkingDesc')}
              </Checkbox>
            )}
          </Field>
        </FormItem>

        {/* Use Vision checkbox */}
        <FormItem name="useVision" label={getCommonFieldLabel('useVision', t)} type="boolean" vertical>
          <Field<boolean> name="inputsValues.useVision.content">
            {({ field }) => (
              <Checkbox
                checked={!!field.value}
                onChange={(e) => field.onChange((e.target as HTMLInputElement).checked)}
              >
                {t('nodes.browserAutomation.useVisionDesc')}
              </Checkbox>
            )}
          </Field>
        </FormItem>

        {/* Browser Profile selector */}
        <FormItem name="profile" label={getCommonFieldLabel('profile', t)} type="string" vertical>
          <Field<string> name="inputsValues.profile.content">
            {({ field }) => {
              const profileOptions = [
                { label: t('nodes.browserAutomation.defaultProfile'), value: '' },
                ...browserProfiles.map(p => ({
                  label: p.isDefault ? `${p.name} ★` : p.name,
                  value: p.name,
                }))
              ];
              return (
                <Select
                  value={(field.value as string) || ''}
                  onChange={(val) => field.onChange(val as string)}
                  optionList={profileOptions}
                  style={{ width: '100%' }}
                  dropdownMatchSelectWidth
                  size="small"
                  placeholder={t('nodes.browserAutomation.profile')}
                />
              );
            }}
          </Field>
        </FormItem>

        {/* System Prompt with Selector */}
        <Divider />
        <PromptInputWithSelector
          promptFieldName="inputsValues.systemPrompt"
          promptIdFieldName="inputsValues.systemPromptId"
          label={t('nodes.llm.systemPrompt')}
          promptType="systemPrompt"
          schema={{ type: 'string' }}
        />

        {/* User Prompt with Selector */}
        <PromptInputWithSelector
          promptFieldName="inputsValues.prompt"
          promptIdFieldName="inputsValues.promptId"
          label={t('nodes.llm.prompt')}
          promptType="prompt"
          schema={{ type: 'string' }}
        />

        {/* Render the rest of inputs using the default component (temperature, etc) */}
        <Field<string> name="inputsValues.promptSelection.content">
          {({ field: promptSelectorField }) => {
            // List of fields that are already rendered manually above
            const manuallyRenderedFields = [
              'promptSelection',
              'tool',
              'browser',
              'browserDriver',
              'cdpPort',
              'runEnvironment',
              'privacyStrategy',
              'enableJudge',
              'shopName',
              'customShopName',
              'modelProvider',
              'modelName',
              'useThinking',
              'useVision',
              'profile',
            ];
            
            return (
              <FormInputs
                extraFilter={(key) => {
                  // Filter out manually rendered fields
                  if (manuallyRenderedFields.includes(key)) {
                    return false;
                  }
                  // Filter out prompt fields when using prompt library
                  if ((key === 'systemPrompt' || key === 'prompt') && promptSelectorField.value && promptSelectorField.value !== 'inline') {
                    return false;
                  }
                  return true;
                }}
              />
            );
          }}
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

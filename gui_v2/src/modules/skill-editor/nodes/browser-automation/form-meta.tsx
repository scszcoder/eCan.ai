/**
 * Browser Automation node custom form
 */
import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, Button, Checkbox, Input, InputNumber, Typography, TextArea } from '@douyinfe/semi-ui';
import { IconChevronDown, IconChevronRight, IconEdit } from '@douyinfe/semi-icons';
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

// Textarea that keeps a local draft so partial JSON doesn't revert the value mid-edit.
const DomRawJsonEditor: React.FC<{ value: string; onCommit: (text: string) => void }> = ({ value, onCommit }) => {
  const [draft, setDraft] = useState(value);
  useEffect(() => { setDraft(value); }, [value]);
  return (
    <TextArea
      value={draft}
      rows={8}
      onChange={(val) => setDraft(String(val))}
      onBlur={() => onCommit(draft)}
    />
  );
};

export const FormRender = (_props: FormRenderProps<any>) => {
  const { t } = useTranslation('skillEditor');
  const navigate = useNavigate();
  const username = useUserStore((s) => s.username || 'user');
  const { prompts, fetch, fetched, loading: promptStoreLoading } = usePromptStore();
  const [llmProviders, setLlmProviders] = useState<Map<string, any>>(new Map());
  const [browserProfiles, setBrowserProfiles] = useState<BrowserProfile[]>([]);
  const platform = useMemo(() => {
    if (typeof navigator === 'undefined') return 'linux';
    const userAgent = navigator.userAgent.toLowerCase();
    if (userAgent.includes('windows')) return 'windows';
    if (userAgent.includes('mac os') || userAgent.includes('macintosh')) return 'macos';
    return 'linux';
  }, []);

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

  const SOURCE_TYPE_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.sourceTypes.httpPolling'), value: 'http_polling' },
    { label: t('nodes.browserAutomation.sourceTypes.websocket'), value: 'websocket' },
    { label: t('nodes.browserAutomation.sourceTypes.sse'), value: 'sse' },
    { label: t('nodes.browserAutomation.sourceTypes.domMutation'), value: 'dom_mutation' },
    { label: t('nodes.browserAutomation.sourceTypes.cdpRaw'), value: 'cdp_raw' },
  ], [t]);

  const FRAME_DIRECTION_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.frameDirections.incoming'), value: 'incoming' },
    { label: t('nodes.browserAutomation.frameDirections.outgoing'), value: 'outgoing' },
    { label: t('nodes.browserAutomation.frameDirections.both'), value: 'both' },
  ], [t]);
  const MONITOR_DONE_POLICY_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.monitorDonePolicies.keep'), value: 'keep' },
    { label: t('nodes.browserAutomation.monitorDonePolicies.stop'), value: 'stop' },
  ], [t]);
  const LOOP_HISTORY_MODE_OPTIONS = useMemo(() => [
    { label: t('nodes.browserAutomation.loopHistoryModes.clear'), value: 'clear' },
    { label: t('nodes.browserAutomation.loopHistoryModes.trim5'), value: 'trim:5' },
    { label: t('nodes.browserAutomation.loopHistoryModes.trim10'), value: 'trim:10' },
    { label: t('nodes.browserAutomation.loopHistoryModes.trim20'), value: 'trim:20' },
    { label: t('nodes.browserAutomation.loopHistoryModes.accumulate'), value: 'accumulate' },
  ], [t]);

  const [eventMonitorsExpanded, setEventMonitorsExpanded] = useState(false);
  const [hotPathExpanded, setHotPathExpanded] = useState(false);
  const [nodeBehaviorExpanded, setNodeBehaviorExpanded] = useState(false);
  const [expandedMonitorIndexes, setExpandedMonitorIndexes] = useState<number[]>([]);

  const parseDomExtractorConfig = useCallback((raw: any) => {
    try {
      const parsed = typeof raw === 'string' && raw.trim() ? JSON.parse(raw) : {};
      return typeof parsed === 'object' && parsed ? parsed : {};
    } catch {
      return {};
    }
  }, []);

  const normalizeMonitorItem = useCallback((item: any) => {
    const base = (item && typeof item === 'object') ? { ...item } : {};
    const parsed = parseDomExtractorConfig(base?.cdpFilterExpr);
    const looksLikeFullMonitor =
      !!parsed &&
      typeof parsed === 'object' &&
      (
        parsed.sourceType ||
        parsed.source_type ||
        parsed.urlPatterns ||
        parsed.url_patterns ||
        parsed.domSelector ||
        parsed.dom_selector ||
        parsed.domCheckIntervalMs ||
        parsed.dom_check_interval_ms
      );

    const merged = looksLikeFullMonitor ? { ...base, ...parsed } : base;
    const nestedExpr = looksLikeFullMonitor ? (parsed?.cdpFilterExpr ?? parsed?.cdp_filter_expr) : base?.cdpFilterExpr;
    const domCfg = parseDomExtractorConfig(nestedExpr);
    const domItem = Array.isArray(domCfg?.items) && domCfg.items[0]
      ? domCfg.items[0]
      : (typeof domCfg === 'object' && domCfg ? domCfg : {});
    const domFields = domItem?.fields || {};

    return {
      label: merged?.label ?? '',
      enabled: merged?.enabled !== false,
      sourceType: merged?.sourceType ?? merged?.source_type ?? 'http_polling',
      urlPatterns: merged?.urlPatterns ?? merged?.url_patterns ?? '',
      contentFilters: merged?.contentFilters ?? merged?.content_filters ?? '',
      methods: merged?.methods ?? '',
      minBodyLength: merged?.minBodyLength ?? merged?.min_body_length ?? 10,
      frameDirection: merged?.frameDirection ?? merged?.frame_direction ?? 'incoming',
      sseEventTypes: merged?.sseEventTypes ?? merged?.sse_event_types ?? '',
      domSelector: merged?.domSelector ?? merged?.dom_selector ?? '',
      domAttributes: merged?.domAttributes ?? merged?.dom_attributes ?? false,
      domChildList: merged?.domChildList ?? merged?.dom_child_list ?? true,
      domSubtree: merged?.domSubtree ?? merged?.dom_subtree ?? true,
      domCheckIntervalMs: merged?.domCheckIntervalMs ?? merged?.dom_check_interval_ms ?? 250,
      cdpDomain: merged?.cdpDomain ?? merged?.cdp_domain ?? '',
      cdpEventMethod: merged?.cdpEventMethod ?? merged?.cdp_event_method ?? '',
      cdpFilterExpr: typeof nestedExpr === 'string' ? nestedExpr : '',
      domPageUrlPatterns: Array.isArray(domCfg?.page_url_patterns) ? domCfg.page_url_patterns.join(', ') : '',
      domExtractorRoots: Array.isArray(domCfg?.roots) ? domCfg.roots.join(', ') : '',
      domItemSelector: domItem?.selector ?? domCfg?.item_selector ?? '',
      domKeyFields: Array.isArray(domCfg?.identity?.key_fields)
        ? domCfg.identity.key_fields.join(', ')
        : (domCfg?.key_field ?? 'session'),
      domKeyField: domCfg?.key_field ?? 'session',
      domEmitOn: domCfg?.emit_on ?? 'added',
      domTopN: domCfg?.top_n ?? 10,
      domEmptyTextPatterns: Array.isArray(domCfg?.empty_text_patterns) ? domCfg.empty_text_patterns.join(', ') : '',
      domSessionSource: domFields?.session?.source ?? 'attr',
      domSessionSelector: domFields?.session?.selector ?? '',
      domSessionAttr: domFields?.session?.attr ?? 'href',
      domSessionRegex: domFields?.session?.regex ?? '',
      domSessionGroup: domFields?.session?.group ?? 1,
      domChatUrlSource: domFields?.chatUrl?.source ?? 'attr',
      domChatUrlSelector: domFields?.chatUrl?.selector ?? '',
      domChatUrlAttr: domFields?.chatUrl?.attr ?? 'href',
      domNameSource: domFields?.name?.source ?? 'text',
      domNameSelector: domFields?.name?.selector ?? '',
      domNameClosest: domFields?.name?.closest ?? '',
      domNameRegex: domFields?.name?.regex ?? '',
      domNameGroup: domFields?.name?.group ?? 1,
      domNameSplitBefore: domFields?.name?.split_before ?? '',
    };
  }, [parseDomExtractorConfig]);

  const buildDomExtractorConfig = useCallback((item: any) => {
    const roots = String(item?.domExtractorRoots ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const pageUrlPatterns = String(item?.domPageUrlPatterns ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const emptyTextPatterns = String(item?.domEmptyTextPatterns ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    const keyFields = String(item?.domKeyFields ?? item?.domKeyField ?? 'session')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    const config = {
      page_url_patterns: pageUrlPatterns,
      roots,
      items: [
        {
          selector: String(item?.domItemSelector ?? '').trim(),
          fields: {
            session: {
              source: String(item?.domSessionSource ?? 'attr').trim() || 'attr',
              selector: String(item?.domSessionSelector ?? '').trim(),
              attr: String(item?.domSessionAttr ?? '').trim(),
              regex: String(item?.domSessionRegex ?? '').trim(),
              group: Number(item?.domSessionGroup ?? 1) || 1,
            },
            chatUrl: {
              source: String(item?.domChatUrlSource ?? 'attr').trim() || 'attr',
              selector: String(item?.domChatUrlSelector ?? '').trim(),
              attr: String(item?.domChatUrlAttr ?? '').trim(),
            },
            name: {
              source: String(item?.domNameSource ?? 'text').trim() || 'text',
              selector: String(item?.domNameSelector ?? '').trim(),
              closest: String(item?.domNameClosest ?? '').trim(),
              regex: String(item?.domNameRegex ?? '').trim(),
              group: Number(item?.domNameGroup ?? 1) || 1,
              split_before: String(item?.domNameSplitBefore ?? '').trim(),
            },
          },
        },
      ],
      key_field: keyFields[0] || 'session',
      identity: {
        key_fields: keyFields.length > 0 ? keyFields : ['session'],
      },
      empty_text_patterns: emptyTextPatterns,
      emit_on: String(item?.domEmitOn ?? 'added').trim() || 'added',
      top_n: Number(item?.domTopN ?? 10) || 10,
    } as any;

    if (!config.items[0].fields.session.selector) delete config.items[0].fields.session.selector;
    if (!config.items[0].fields.session.attr) delete config.items[0].fields.session.attr;
    if (!config.items[0].fields.session.regex) delete config.items[0].fields.session.regex;
    if (!config.items[0].fields.chatUrl.selector) delete config.items[0].fields.chatUrl.selector;
    if (!config.items[0].fields.chatUrl.attr) delete config.items[0].fields.chatUrl.attr;
    if (!config.items[0].fields.name.selector) delete config.items[0].fields.name.selector;
    if (!config.items[0].fields.name.closest) delete config.items[0].fields.name.closest;
    if (!config.items[0].fields.name.regex) delete config.items[0].fields.name.regex;
    if (!config.items[0].fields.name.split_before) delete config.items[0].fields.name.split_before;
    return config;
  }, []);

  const serializeMonitorItem = useCallback((item: any) => {
    const normalized = normalizeMonitorItem(item);
    const serialized: any = {
      label: normalized.label || '',
      enabled: normalized.enabled !== false,
      sourceType: normalized.sourceType || 'http_polling',
      urlPatterns: normalized.urlPatterns || '',
      contentFilters: normalized.contentFilters || '',
      methods: normalized.methods || '',
      minBodyLength: Number(normalized.minBodyLength ?? 10) || 10,
      frameDirection: normalized.frameDirection || 'incoming',
      sseEventTypes: normalized.sseEventTypes || '',
      domSelector: normalized.domSelector || '',
      domAttributes: !!normalized.domAttributes,
      domChildList: normalized.domChildList !== false,
      domSubtree: normalized.domSubtree !== false,
      domCheckIntervalMs: Number(normalized.domCheckIntervalMs ?? 250) || 250,
      cdpDomain: normalized.cdpDomain || '',
      cdpEventMethod: normalized.cdpEventMethod || '',
      cdpFilterExpr: normalized.cdpFilterExpr || '',
    };

    if (serialized.sourceType === 'dom_mutation') {
      // Only rebuild from form fields if the user hasn't provided their own valid JSON.
      // If cdpFilterExpr already contains valid JSON, preserve it as-is.
      const raw = (normalized.cdpFilterExpr || '').trim();
      let hasUserJson = false;
      if (raw) {
        try { JSON.parse(raw); hasUserJson = true; } catch { /* invalid — rebuild */ }
      }
      if (!hasUserJson) {
        serialized.cdpFilterExpr = JSON.stringify(buildDomExtractorConfig(normalized), null, 2);
      }
    }

    return serialized;
  }, [buildDomExtractorConfig, normalizeMonitorItem]);

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
                <Field<string> name="inputsValues.cdpPort.content">
                  {({ field: cdpPortField }) => {
                    const cdpPort = (cdpPortField.value as string) || '9228';
                    const chromeLaunchCommand =
                      platform === 'windows'
                        ? `chrome.exe --remote-debugging-port=${cdpPort} --user-data-dir="C:\\chrome_data" --disable-features=SharedStorage,InterestCohort`
                        : platform === 'macos'
                          ? `/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=${cdpPort} --user-data-dir="/tmp/chrome_data" --disable-features=SharedStorage,InterestCohort`
                          : `google-chrome --remote-debugging-port=${cdpPort} --user-data-dir="/tmp/chrome_data" --disable-features=SharedStorage,InterestCohort`;

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
                            <strong style={{ color: '#000' }}>{t('nodes.browserAutomation.chromeLaunchCommandHint')}</strong>
                            <div style={{ marginTop: 4, fontFamily: 'monospace', fontSize: 10, wordBreak: 'break-all', color: '#333' }}>
                              {chromeLaunchCommand}
                            </div>
                          </div>
                        )}
                      </>
                    );
                  }}
                </Field>
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

        {/* CDP Port: auto-assign checkbox + manual port input */}
        <FormItem name="cdpPort" label={getCommonFieldLabel('cdpPort', t)} type="string" vertical>
          <Field<boolean> name="inputsValues.cdpPortAuto.content">
            {({ field: autoField }) => (
              <>
                <Checkbox
                  checked={!!autoField.value}
                  onChange={(e) => autoField.onChange((e.target as HTMLInputElement).checked)}
                  style={{ marginBottom: 6 }}
                >
                  {t('nodes.browserAutomation.cdpPortAutoDesc')}
                </Checkbox>
                {!autoField.value && (
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
                )}
              </>
            )}
          </Field>
        </FormItem>

        {/* Headless Mode checkbox */}
        <FormItem name="headless" label={getCommonFieldLabel('headless', t)} type="boolean" vertical>
          <Field<boolean> name="inputsValues.headless.content">
            {({ field }) => (
              <Checkbox
                checked={!!field.value}
                onChange={(e) => field.onChange((e.target as HTMLInputElement).checked)}
              >
                {t('nodes.browserAutomation.headlessDesc')}
              </Checkbox>
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

        {/* Performance Optimization Section */}
        <Divider>{t('nodes.browserAutomation.performanceSettings')}</Divider>

        {/* Flash Mode checkbox */}
        <FormItem name="flashMode" label={getCommonFieldLabel('flashMode', t)} type="boolean" vertical>
          <Field<boolean> name="inputsValues.flashMode.content">
            {({ field }) => (
              <Checkbox
                checked={!!field.value}
                onChange={(e) => field.onChange((e.target as HTMLInputElement).checked)}
              >
                {t('nodes.browserAutomation.flashModeDesc')}
              </Checkbox>
            )}
          </Field>
        </FormItem>

        {/* Max Steps input */}
        <FormItem name="maxSteps" label={getCommonFieldLabel('maxSteps', t)} type="number" vertical>
          <Field<string> name="inputsValues.maxSteps.content">
            {({ field }) => (
              <input
                type="number"
                value={(field.value as string) || ''}
                onChange={(e) => field.onChange(e.target.value)}
                placeholder={t('nodes.browserAutomation.maxStepsPlaceholder')}
                style={{ width: '100%', padding: '6px 12px', fontSize: '14px', border: '1px solid #d9d9d9', borderRadius: '3px', color: '#000000', backgroundColor: '#ffffff' }}
                min="1"
                max="100"
              />
            )}
          </Field>
        </FormItem>

        {/* Max Actions Per Step input */}
        <FormItem name="maxActionsPerStep" label={getCommonFieldLabel('maxActionsPerStep', t)} type="number" vertical>
          <Field<string> name="inputsValues.maxActionsPerStep.content">
            {({ field }) => (
              <input
                type="number"
                value={(field.value as string) || ''}
                onChange={(e) => field.onChange(e.target.value)}
                placeholder={t('nodes.browserAutomation.maxActionsPerStepPlaceholder')}
                style={{ width: '100%', padding: '6px 12px', fontSize: '14px', border: '1px solid #d9d9d9', borderRadius: '3px', color: '#000000', backgroundColor: '#ffffff' }}
                min="1"
                max="20"
              />
            )}
          </Field>
        </FormItem>

        {/* DOM Focus Selector */}
        <FormItem name="domFocusSelector" label={getCommonFieldLabel('domFocusSelector', t)} type="string" vertical>
          <Field<string> name="inputsValues.domFocusSelector.content">
            {({ field }) => (
              <input
                type="text"
                value={(field.value as string) || ''}
                onChange={(e) => field.onChange(e.target.value)}
                placeholder={t('nodes.browserAutomation.domFocusSelectorPlaceholder')}
                style={{ width: '100%', padding: '6px 12px', fontSize: '14px', border: '1px solid #d9d9d9', borderRadius: '3px', color: '#000000', backgroundColor: '#ffffff' }}
              />
            )}
          </Field>
        </FormItem>

        {/* DOM Limit */}
        <FormItem name="domLimit" label={getCommonFieldLabel('domLimit', t)} type="number" vertical>
          <Field<string> name="inputsValues.domLimit.content">
            {({ field }) => (
              <input
                type="number"
                value={(field.value as string) || ''}
                onChange={(e) => field.onChange(e.target.value)}
                placeholder={t('nodes.browserAutomation.domLimitPlaceholder')}
                style={{ width: '100%', padding: '6px 12px', fontSize: '14px', border: '1px solid #d9d9d9', borderRadius: '3px', color: '#000000', backgroundColor: '#ffffff' }}
                min="1000"
                max="50000"
              />
            )}
          </Field>
        </FormItem>

        {/* Loop History Mode */}
        <FormItem name="loopHistoryMode" label={t('nodes.browserAutomation.loopHistoryMode')} type="string" vertical>
          <Field<string> name="inputsValues.loopHistoryMode.content">
            {({ field }) => (
              <Select
                value={(field.value as string) || 'clear'}
                onChange={(val) => field.onChange(val as string)}
                optionList={LOOP_HISTORY_MODE_OPTIONS}
                style={{ width: '100%' }}
                size="small"
              />
            )}
          </Field>
        </FormItem>

        {/* Actionable Field */}
        <FormItem name="actionableField" label={t('nodes.browserAutomation.actionableField')} type="string" vertical>
          <Field<string> name="inputsValues.actionableField.content">
            {({ field }) => (
              <input
                type="text"
                value={(field.value as string) || ''}
                onChange={(e) => field.onChange(e.target.value)}
                placeholder={t('nodes.browserAutomation.actionableFieldPlaceholder')}
                style={{ width: '100%', padding: '6px 12px', fontSize: '14px', border: '1px solid #d9d9d9', borderRadius: '3px', color: '#000000', backgroundColor: '#ffffff' }}
              />
            )}
          </Field>
        </FormItem>

        {/* Hot-Path Optimization Section (collapsible) */}
        <div
          style={{ cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center', gap: 4, padding: '8px 0' }}
          onClick={() => setHotPathExpanded(!hotPathExpanded)}
        >
          {hotPathExpanded ? <IconChevronDown size="small" /> : <IconChevronRight size="small" />}
          <Divider style={{ flex: 1, margin: 0 }}>{t('nodes.browserAutomation.hotPathSection', 'Hot-Path Optimization')}</Divider>
        </div>
        {hotPathExpanded && (
          <div style={{ marginBottom: 8 }}>
            <Typography.Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              {t('nodes.browserAutomation.hotPathSectionDesc', 'Skip the LLM for deterministic operations. Configure action sequences triggered by event type and payload fields.')}
            </Typography.Text>
            <FormItem name="hotPathActions" label={t('nodes.browserAutomation.hotPathActions', 'Hot-Path Actions (JSON)')} type="string" vertical>
              <Field<string> name="inputsValues.hotPathActions.content">
                {({ field }) => (
                  <TextArea
                    value={(field.value as string) || ''}
                    onChange={(val) => field.onChange(val)}
                    placeholder={'[{"trigger":{"event_type":"chat_message","has_fields":["response_text"]},"actions":[{"tool":"tool_name","args":{"param":"{{field}}"}}]}]'}
                    autosize={{ minRows: 3, maxRows: 10 }}
                    style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                  />
                )}
              </Field>
            </FormItem>
            <FormItem name="autoDispatch" label={t('nodes.browserAutomation.autoDispatch', 'Auto-Dispatch Config (JSON)')} type="string" vertical>
              <Field<string> name="inputsValues.autoDispatch.content">
                {({ field }) => (
                  <TextArea
                    value={(field.value as string) || ''}
                    onChange={(val) => field.onChange(val)}
                    placeholder={'{"trigger":{"event_type":"browser_event","require_actionable":true},"agent_selection":{"strategy":"first_available"},"payload_template":{"key":"{{field}}"},"item_filter":{"required_fields":["field1"]},"dispatch":{"tool":"send_chat","dedup":true}}'}
                    autosize={{ minRows: 3, maxRows: 10 }}
                    style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                  />
                )}
              </Field>
            </FormItem>
          </div>
        )}

        {/* Node Behavior Section (collapsible) — assignment, preDispatch, stepPatches, siteAdapter, tabPolicy */}
        <div
          style={{ cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center', gap: 4, padding: '8px 0' }}
          onClick={() => setNodeBehaviorExpanded(!nodeBehaviorExpanded)}
        >
          {nodeBehaviorExpanded ? <IconChevronDown size="small" /> : <IconChevronRight size="small" />}
          <Divider style={{ flex: 1, margin: 0 }}>{t('nodes.browserAutomation.nodeBehaviorSection', 'Node Behavior')}</Divider>
        </div>
        {nodeBehaviorExpanded && (
          <div style={{ marginBottom: 8 }}>
            <Typography.Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              {t('nodes.browserAutomation.nodeBehaviorSectionDesc', 'Data-driven configuration that replaces per-skill hardcoded behavior. Leave blank for generic defaults; fill in to enable skill-specific flows (e.g. rt_chat_bot, customer_front_desk).')}
            </Typography.Text>
            <FormItem name="assignment" label={t('nodes.browserAutomation.assignment', 'Assignment Config (JSON)')} type="string" vertical>
              <Field<string> name="inputsValues.assignment.content">
                {({ field }) => (
                  <TextArea
                    value={(field.value as string) || ''}
                    onChange={(val) => field.onChange(val)}
                    placeholder={'{"enabled":true,"require_any_of":["session_id","customer_id"],"on_missing":"skip_node","scope_contract_template":"[ASSIGNED SCOPE]\\nsession_id={session_id}\\ntab_id={tab_id}","navigate_field":"chat_url","strip_url_regex":"https?://[^\\\\s]+/chat\\\\?session=[^\\\\s]+","strip_url_replacement":"[assigned chat tab already open]"}'}
                    autosize={{ minRows: 3, maxRows: 12 }}
                    style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                  />
                )}
              </Field>
            </FormItem>
            <FormItem name="preDispatch" label={t('nodes.browserAutomation.preDispatch', 'Pre-Dispatch Config (JSON)')} type="string" vertical>
              <Field<string> name="inputsValues.preDispatch.content">
                {({ field }) => (
                  <TextArea
                    value={(field.value as string) || ''}
                    onChange={(val) => field.onChange(val)}
                    placeholder={'{"enabled":true,"source_monitor_label":"conversation_became_active","require_url_path":"/control","allowed_statuses":["ok","empty","no_match"],"item_fields":{"session_id":["session","session_id","customer_id"],"customer_name":["customer_name","name"],"chat_url":["chat_url"]},"chat_url_template":"http://127.0.0.1:9877/chat?session={session_id}","recipient_filter":{"task_keywords":["feige_chat"],"skill_keywords":["rt_chat_bot"]},"dispatched_flag_attr":"_ecan_frontdesk_dispatched_all"}'}
                    autosize={{ minRows: 3, maxRows: 12 }}
                    style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                  />
                )}
              </Field>
            </FormItem>
            <FormItem name="stepPatches" label={t('nodes.browserAutomation.stepPatches', 'Step Patches (JSON)')} type="string" vertical>
              <Field<string> name="inputsValues.stepPatches.content">
                {({ field }) => (
                  <TextArea
                    value={(field.value as string) || ''}
                    onChange={(val) => field.onChange(val)}
                    placeholder={'{"refocus_assigned_tab":true,"abort_when_pre_dispatched":true,"pre_dispatch_flag_attr":"_ecan_frontdesk_dispatched_all"}'}
                    autosize={{ minRows: 3, maxRows: 10 }}
                    style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                  />
                )}
              </Field>
            </FormItem>
            <FormItem name="hookBundles" label={t('nodes.browserAutomation.hookBundles', 'Hook Bundles (JSON)')} type="string" vertical>
              <Field<string> name="inputsValues.hookBundles.content">
                {({ field }) => (
                  <TextArea
                    value={(field.value as string) || ''}
                    onChange={(val) => field.onChange(val)}
                    placeholder={'[{"path":"feige_chat","enabled":true,"config":{"cooldown_ms":1500}},{"path":"/abs/path/to/custom_bundle","config":{}}]'}
                    autosize={{ minRows: 3, maxRows: 10 }}
                    style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                  />
                )}
              </Field>
            </FormItem>
            <FormItem name="siteAdapter" label={t('nodes.browserAutomation.siteAdapter', 'Site Adapter (JSON)')} type="string" vertical>
              <Field<string> name="inputsValues.siteAdapter.content">
                {({ field }) => (
                  <TextArea
                    value={(field.value as string) || ''}
                    onChange={(val) => field.onChange(val)}
                    placeholder={'{"name":"feige","sidebar":{"item_selector":"[data-qa-id=\\"qa-conversation-chat-item\\"]","name_readers":[{"selector":".MP1bk3ccfHC9V2SnPCGD","source":"attr","attr":"title"},{"selector":".Jv6FtqUv5VoYARd2pp4y","source":"text"}],"active_strategies":[{"type":"class_token","token":"active"},{"type":"aria_selected"},{"type":"odd_one_out"}]},"header":{"root_selector":"#topbar-left-info","exclude_texts":["添加备注"],"max_text_len":60},"verify_policy":"affirmative_and_no_conflict"}'}
                    autosize={{ minRows: 3, maxRows: 12 }}
                    style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                  />
                )}
              </Field>
            </FormItem>
            <FormItem name="tabPolicy" label={t('nodes.browserAutomation.tabPolicy', 'Tab Policy')} type="string" vertical>
              <Field<string> name="inputsValues.tabPolicy.content">
                {({ field }) => (
                  <Select
                    value={(field.value as string) || ''}
                    onChange={(val) => field.onChange(val as string)}
                    optionList={[
                      { label: t('nodes.browserAutomation.tabPolicyStrict', 'strict_single_tab (default — never switch_tab)'), value: '' },
                      { label: t('nodes.browserAutomation.tabPolicyAllowAssigned', 'allow_assigned_tab (permit focusing the assigned tab_id)'), value: 'allow_assigned_tab' },
                    ]}
                    style={{ width: '100%' }}
                    size="small"
                  />
                )}
              </Field>
            </FormItem>
          </div>
        )}

        {/* Event Monitors Section (collapsible) */}
        <div
          style={{ cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center', gap: 4, padding: '8px 0' }}
          onClick={() => setEventMonitorsExpanded(!eventMonitorsExpanded)}
        >
          {eventMonitorsExpanded ? <IconChevronDown size="small" /> : <IconChevronRight size="small" />}
          <Divider style={{ flex: 1, margin: 0 }}>{t('nodes.browserAutomation.eventMonitors')}</Divider>
        </div>
        {eventMonitorsExpanded && (
          <div style={{ marginBottom: 8 }}>
            <Typography.Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              {t('nodes.browserAutomation.eventMonitorsDesc')}
            </Typography.Text>
            <FormItem name="eventMonitorDonePolicy" label={t('nodes.browserAutomation.eventMonitorDonePolicy')} type="string" vertical>
              <Field<string> name="inputsValues.eventMonitorDonePolicy.content">
                {({ field }) => (
                  <Select
                    value={(field.value as string) || 'keep'}
                    onChange={(val) => field.onChange(val as string)}
                    optionList={MONITOR_DONE_POLICY_OPTIONS}
                    style={{ width: '100%' }}
                    size="small"
                  />
                )}
              </Field>
            </FormItem>
            <Field<any> name="inputsValues.eventMonitors">
              {({ field }) => {
                const raw = Array.isArray(field.value?.content) ? (field.value.content as any[]) : [];
                const toObj = (item: any) =>
                  typeof item === 'string'
                    ? { label: '', enabled: true, sourceType: 'http_polling' }
                    : normalizeMonitorItem(item);
                const arr = raw.map(toObj);
                const setArray = (next: any[]) => field.onChange({ type: 'constant', content: next.map(serializeMonitorItem) });
                const addOne = () =>
                  {
                    const nextIndex = arr.length;
                    setArray([...arr, { label: '', enabled: true, sourceType: 'http_polling', urlPatterns: '', contentFilters: '', methods: '', minBodyLength: 10, domCheckIntervalMs: 250 }]);
                    setExpandedMonitorIndexes((prev) => (prev.includes(nextIndex) ? prev : [...prev, nextIndex]));
                  };
                const removeAt = (idx: number) => {
                  const next = [...arr];
                  next.splice(idx, 1);
                  setArray(next);
                  setExpandedMonitorIndexes((prev) =>
                    prev
                      .filter((x) => x !== idx)
                      .map((x) => (x > idx ? x - 1 : x))
                  );
                };
                const updateAt = (idx: number, key: string, val: any) => {
                  const next = [...arr];
                  next[idx] = { ...next[idx], [key]: val };
                  // Only auto-rebuild cdpFilterExpr from form fields when the user edits a
                  // structural field (not cdpFilterExpr itself) AND no custom JSON is present.
                  if (next[idx]?.sourceType === 'dom_mutation' && key !== 'cdpFilterExpr') {
                    const existing = (next[idx].cdpFilterExpr || '').trim();
                    let hasUserJson = false;
                    if (existing) {
                      try { JSON.parse(existing); hasUserJson = true; } catch { /* rebuild */ }
                    }
                    if (!hasUserJson) {
                      next[idx].cdpFilterExpr = JSON.stringify(buildDomExtractorConfig(next[idx]), null, 2);
                    }
                  }
                  setArray(next);
                };
                const isMonitorExpanded = (idx: number) => expandedMonitorIndexes.includes(idx);
                const toggleMonitorExpanded = (idx: number) => {
                  setExpandedMonitorIndexes((prev) =>
                    prev.includes(idx) ? prev.filter((x) => x !== idx) : [...prev, idx]
                  );
                };

                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {arr.map((item, i) => {
                      const st = item.sourceType || 'http_polling';
                      return (
                        <div
                          key={i}
                          style={{
                            border: '1px solid #e0e0e0',
                            borderRadius: 6,
                            padding: 10,
                            backgroundColor: item.enabled ? '#fafafa' : '#f0f0f0',
                            opacity: item.enabled ? 1 : 0.6,
                          }}
                        >
                          {/* Header: enabled toggle + delete */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <Button
                                theme="borderless"
                                type="tertiary"
                                size="small"
                                icon={isMonitorExpanded(i) ? <IconChevronDown size="small" /> : <IconChevronRight size="small" />}
                                onClick={() => toggleMonitorExpanded(i)}
                                aria-label={isMonitorExpanded(i) ? 'Collapse monitor' : 'Expand monitor'}
                              />
                              <Checkbox
                                checked={item.enabled}
                                onChange={(e) => updateAt(i, 'enabled', (e.target as HTMLInputElement).checked)}
                              >
                                <span style={{ fontWeight: 600, fontSize: 12 }}>
                                  #{i + 1} {item.label ? `- ${item.label}` : ''}
                                </span>
                              </Checkbox>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <Typography.Text type="tertiary" size="small">{st}</Typography.Text>
                              <Button type="danger" theme="borderless" size="small" onClick={() => removeAt(i)}>
                                {t('nodes.browserAutomation.deleteMonitor')}
                              </Button>
                            </div>
                          </div>

                          {isMonitorExpanded(i) && (
                            <>
                          {/* Label */}
                          <div style={{ marginBottom: 6 }}>
                            <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                              {t('nodes.browserAutomation.monitorLabel')}
                            </label>
                            <Input
                              value={item.label}
                              placeholder={t('nodes.browserAutomation.monitorLabelPlaceholder')}
                              onChange={(val) => updateAt(i, 'label', String(val))}
                              size="small"
                            />
                          </div>

                          {/* Source Type */}
                          <div style={{ marginBottom: 6 }}>
                            <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                              {t('nodes.browserAutomation.monitorSourceType')}
                            </label>
                            <Select
                              value={st}
                              onChange={(val) => updateAt(i, 'sourceType', val as string)}
                              optionList={SOURCE_TYPE_OPTIONS}
                              style={{ width: '100%' }}
                              size="small"
                            />
                          </div>

                          {/* URL Patterns (shown for http_polling, websocket, sse) */}
                          {['http_polling', 'websocket', 'sse'].includes(st) && (
                            <div style={{ marginBottom: 6 }}>
                              <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                {t('nodes.browserAutomation.monitorUrlPatterns')}
                              </label>
                              <Input
                                value={item.urlPatterns}
                                placeholder={t('nodes.browserAutomation.monitorUrlPatternsPlaceholder')}
                                onChange={(val) => updateAt(i, 'urlPatterns', String(val))}
                                size="small"
                              />
                            </div>
                          )}

                          {/* HTTP Polling specific fields */}
                          {st === 'http_polling' && (
                            <>
                              <div style={{ marginBottom: 6 }}>
                                <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                  {t('nodes.browserAutomation.monitorContentFilters')}
                                </label>
                                <Input
                                  value={item.contentFilters}
                                  placeholder={t('nodes.browserAutomation.monitorContentFiltersPlaceholder')}
                                  onChange={(val) => updateAt(i, 'contentFilters', String(val))}
                                  size="small"
                                />
                              </div>
                              <div style={{ display: 'flex', gap: 8 }}>
                                <div style={{ flex: 1 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorMethods')}
                                  </label>
                                  <Input
                                    value={item.methods}
                                    placeholder={t('nodes.browserAutomation.monitorMethodsPlaceholder')}
                                    onChange={(val) => updateAt(i, 'methods', String(val))}
                                    size="small"
                                  />
                                </div>
                                <div style={{ width: 100 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorMinBodyLength')}
                                  </label>
                                  <InputNumber
                                    value={item.minBodyLength}
                                    min={0}
                                    onChange={(val) => updateAt(i, 'minBodyLength', Number(val || 0))}
                                    size="small"
                                    style={{ width: '100%' }}
                                  />
                                </div>
                              </div>
                            </>
                          )}

                          {/* WebSocket specific fields */}
                          {st === 'websocket' && (
                            <>
                              <div style={{ marginBottom: 6 }}>
                                <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                  {t('nodes.browserAutomation.monitorFrameDirection')}
                                </label>
                                <Select
                                  value={item.frameDirection || 'incoming'}
                                  onChange={(val) => updateAt(i, 'frameDirection', val as string)}
                                  optionList={FRAME_DIRECTION_OPTIONS}
                                  style={{ width: '100%' }}
                                  size="small"
                                />
                              </div>
                              <div style={{ marginBottom: 6 }}>
                                <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                  {t('nodes.browserAutomation.monitorContentFilters')}
                                </label>
                                <Input
                                  value={item.contentFilters}
                                  placeholder={t('nodes.browserAutomation.monitorContentFiltersPlaceholder')}
                                  onChange={(val) => updateAt(i, 'contentFilters', String(val))}
                                  size="small"
                                />
                              </div>
                            </>
                          )}

                          {/* SSE specific fields */}
                          {st === 'sse' && (
                            <>
                              <div style={{ marginBottom: 6 }}>
                                <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                  {t('nodes.browserAutomation.monitorSseEventTypes')}
                                </label>
                                <Input
                                  value={item.sseEventTypes}
                                  placeholder="message, update"
                                  onChange={(val) => updateAt(i, 'sseEventTypes', String(val))}
                                  size="small"
                                />
                              </div>
                              <div style={{ marginBottom: 6 }}>
                                <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                  {t('nodes.browserAutomation.monitorContentFilters')}
                                </label>
                                <Input
                                  value={item.contentFilters}
                                  placeholder={t('nodes.browserAutomation.monitorContentFiltersPlaceholder')}
                                  onChange={(val) => updateAt(i, 'contentFilters', String(val))}
                                  size="small"
                                />
                              </div>
                            </>
                          )}

                          {/* DOM Mutation specific fields */}
                          {st === 'dom_mutation' && (
                            <>
                              <div style={{ marginBottom: 6 }}>
                                <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                  {t('nodes.browserAutomation.monitorDomSelector')}
                                </label>
                                <Input
                                  value={item.domSelector}
                                  placeholder="#chat-container"
                                  onChange={(val) => updateAt(i, 'domSelector', String(val))}
                                  size="small"
                                />
                                <div style={{ marginTop: 6, width: 140 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    DOM Check Interval (ms)
                                  </label>
                                  <InputNumber
                                    value={item.domCheckIntervalMs || 250}
                                    min={50}
                                    step={50}
                                    onChange={(val) => updateAt(i, 'domCheckIntervalMs', Number(val || 250))}
                                    size="small"
                                    style={{ width: '100%' }}
                                  />
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                                  <Checkbox checked={item.domChildList} onChange={(e) => updateAt(i, 'domChildList', (e.target as HTMLInputElement).checked)}>
                                    childList
                                  </Checkbox>
                                  <Checkbox checked={item.domSubtree} onChange={(e) => updateAt(i, 'domSubtree', (e.target as HTMLInputElement).checked)}>
                                    subtree
                                  </Checkbox>
                                  <Checkbox checked={item.domAttributes} onChange={(e) => updateAt(i, 'domAttributes', (e.target as HTMLInputElement).checked)}>
                                    attributes
                                  </Checkbox>
                                </div>
                              </div>
                              <div style={{ marginBottom: 6 }}>
                                <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                  {t('nodes.browserAutomation.monitorContentFilters')}
                                </label>
                                <Input
                                  value={item.contentFilters}
                                  placeholder={t('nodes.browserAutomation.monitorContentFiltersPlaceholder')}
                                  onChange={(val) => updateAt(i, 'contentFilters', String(val))}
                                  size="small"
                                />
                              </div>
                              <div style={{ border: '1px dashed #d0d0d0', borderRadius: 6, padding: 8, marginBottom: 6 }}>
                                <div style={{ fontSize: 11, fontWeight: 600, color: '#666', marginBottom: 6 }}>
                                  {t('nodes.browserAutomation.monitorDomExtractor')}
                                </div>
                                <div style={{ marginBottom: 6 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorDomPageUrlPatterns')}
                                  </label>
                                  <Input value={item.domPageUrlPatterns} placeholder={t('nodes.browserAutomation.monitorDomPageUrlPatternsPlaceholder')} onChange={(val) => updateAt(i, 'domPageUrlPatterns', String(val))} size="small" />
                                </div>
                                <div style={{ marginBottom: 6 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorDomRoots')}
                                  </label>
                                  <Input value={item.domExtractorRoots} placeholder={t('nodes.browserAutomation.monitorDomRootsPlaceholder')} onChange={(val) => updateAt(i, 'domExtractorRoots', String(val))} size="small" />
                                </div>
                                <div style={{ marginBottom: 6 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorDomItemSelector')}
                                  </label>
                                  <Input value={item.domItemSelector} placeholder={t('nodes.browserAutomation.monitorDomItemSelectorPlaceholder')} onChange={(val) => updateAt(i, 'domItemSelector', String(val))} size="small" />
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                      {t('nodes.browserAutomation.monitorDomKeyFields')}
                                    </label>
                                    <Input value={item.domKeyFields} placeholder="session, time_text, preview" onChange={(val) => updateAt(i, 'domKeyFields', String(val))} size="small" />
                                  </div>
                                  <div style={{ width: 140 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                      {t('nodes.browserAutomation.monitorDomEmitOn')}
                                    </label>
                                    <Select value={item.domEmitOn || 'added'} onChange={(val) => updateAt(i, 'domEmitOn', val as string)} optionList={[{ label: 'added', value: 'added' }, { label: 'changed', value: 'changed' }, { label: 'reordered', value: 'reordered' }, { label: 'top_changed', value: 'top_changed' }, { label: 'added_or_reordered', value: 'added_or_reordered' }]} size="small" style={{ width: '100%' }} />
                                  </div>
                                  <div style={{ width: 100 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                      {t('nodes.browserAutomation.monitorDomTopN')}
                                    </label>
                                    <InputNumber value={item.domTopN || 10} min={1} onChange={(val) => updateAt(i, 'domTopN', Number(val || 10))} size="small" style={{ width: '100%' }} />
                                  </div>
                                </div>
                                <div style={{ marginBottom: 6 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorDomEmptyTextPatterns')}
                                  </label>
                                  <Input value={item.domEmptyTextPatterns} placeholder={t('nodes.browserAutomation.monitorDomEmptyTextPatternsPlaceholder')} onChange={(val) => updateAt(i, 'domEmptyTextPatterns', String(val))} size="small" />
                                </div>
                                <div style={{ fontSize: 11, fontWeight: 600, color: '#666', marginBottom: 6 }}>
                                  {t('nodes.browserAutomation.monitorDomFields')}
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Session Source</label>
                                    <Select value={item.domSessionSource || 'attr'} onChange={(val) => updateAt(i, 'domSessionSource', val as string)} optionList={[{ label: 'attr', value: 'attr' }, { label: 'text', value: 'text' }, { label: 'closest_text', value: 'closest_text' }]} size="small" style={{ width: '100%' }} />
                                  </div>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Session Selector</label>
                                    <Input value={item.domSessionSelector} onChange={(val) => updateAt(i, 'domSessionSelector', String(val))} size="small" />
                                  </div>
                                  <div style={{ width: 110 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Attr</label>
                                    <Input value={item.domSessionAttr} onChange={(val) => updateAt(i, 'domSessionAttr', String(val))} size="small" />
                                  </div>
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Session Regex</label>
                                    <Input value={item.domSessionRegex} onChange={(val) => updateAt(i, 'domSessionRegex', String(val))} size="small" />
                                  </div>
                                  <div style={{ width: 90 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Group</label>
                                    <InputNumber value={item.domSessionGroup} min={1} onChange={(val) => updateAt(i, 'domSessionGroup', Number(val || 1))} size="small" style={{ width: '100%' }} />
                                  </div>
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Chat URL Selector</label>
                                    <Input value={item.domChatUrlSelector} onChange={(val) => updateAt(i, 'domChatUrlSelector', String(val))} size="small" />
                                  </div>
                                  <div style={{ width: 110 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Chat URL Attr</label>
                                    <Input value={item.domChatUrlAttr} onChange={(val) => updateAt(i, 'domChatUrlAttr', String(val))} size="small" />
                                  </div>
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                                  <div style={{ width: 150 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Name Source</label>
                                    <Select value={item.domNameSource || 'text'} onChange={(val) => updateAt(i, 'domNameSource', val as string)} optionList={[{ label: 'text', value: 'text' }, { label: 'closest_text', value: 'closest_text' }, { label: 'attr', value: 'attr' }]} size="small" style={{ width: '100%' }} />
                                  </div>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Name Selector</label>
                                    <Input value={item.domNameSelector} onChange={(val) => updateAt(i, 'domNameSelector', String(val))} size="small" />
                                  </div>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Name Closest</label>
                                    <Input value={item.domNameClosest} onChange={(val) => updateAt(i, 'domNameClosest', String(val))} size="small" />
                                  </div>
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Name Regex</label>
                                    <Input value={item.domNameRegex} onChange={(val) => updateAt(i, 'domNameRegex', String(val))} size="small" />
                                  </div>
                                  <div style={{ width: 90 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Group</label>
                                    <InputNumber value={item.domNameGroup} min={1} onChange={(val) => updateAt(i, 'domNameGroup', Number(val || 1))} size="small" style={{ width: '100%' }} />
                                  </div>
                                  <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Split Before</label>
                                    <Input value={item.domNameSplitBefore} onChange={(val) => updateAt(i, 'domNameSplitBefore', String(val))} size="small" />
                                  </div>
                                </div>
                                <div style={{ marginBottom: 6 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorDomRawJson')}
                                  </label>
                                  <DomRawJsonEditor
                                    value={item.cdpFilterExpr}
                                    onCommit={(text) => {
                                      const next = [...arr];
                                      next[i] = normalizeMonitorItem({ ...next[i], cdpFilterExpr: text });
                                      setArray(next);
                                    }}
                                  />
                                </div>
                              </div>
                            </>
                          )}

                          {/* CDP Raw specific fields */}
                          {st === 'cdp_raw' && (
                            <>
                              <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                                <div style={{ flex: 1 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorCdpDomain')}
                                  </label>
                                  <Input
                                    value={item.cdpDomain}
                                    placeholder="Network"
                                    onChange={(val) => updateAt(i, 'cdpDomain', String(val))}
                                    size="small"
                                  />
                                </div>
                                <div style={{ flex: 2 }}>
                                  <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                    {t('nodes.browserAutomation.monitorCdpEventMethod')}
                                  </label>
                                  <Input
                                    value={item.cdpEventMethod}
                                    placeholder="Network.responseReceived"
                                    onChange={(val) => updateAt(i, 'cdpEventMethod', String(val))}
                                    size="small"
                                  />
                                </div>
                              </div>
                              <div style={{ marginBottom: 6 }}>
                                <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>
                                  {t('nodes.browserAutomation.monitorCdpFilterExpr')}
                                </label>
                                <Input
                                  value={item.cdpFilterExpr}
                                  placeholder="response.url contains '/api/price'"
                                  onChange={(val) => updateAt(i, 'cdpFilterExpr', String(val))}
                                  size="small"
                                />
                              </div>
                            </>
                          )}
                            </>
                          )}
                        </div>
                      );
                    })}
                    <div>
                      <Button size="small" onClick={addOne}>
                        {t('nodes.browserAutomation.addMonitor')}
                      </Button>
                    </div>
                  </div>
                );
              }}
            </Field>
          </div>
        )}

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
              'flashMode',
              'maxSteps',
              'maxActionsPerStep',
              'domFocusSelector',
              'domLimit',
              'loopHistoryMode',
              'actionableField',
              'hotPathActions',
              'autoDispatch',
              'assignment',
              'preDispatch',
              'stepPatches',
              'hookBundles',
              'siteAdapter',
              'tabPolicy',
              'eventMonitors',
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

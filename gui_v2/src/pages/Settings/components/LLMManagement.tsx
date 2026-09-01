import React, { useState, useEffect, useMemo, useCallback, useImperativeHandle, useRef } from "react";
import {
  Table,
  Button,
  Input,
  Radio,
  Space,
  Tooltip,
  App,
  Select,
  Checkbox,
} from "antd";
import {
  DeleteOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  GlobalOutlined,
  ReloadOutlined,
  ScanOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { get_ipc_api } from "../../../services/ipc_api";
import { useIsCN } from "../../../contexts/AppConfigContext";
import type { LLMProvider } from "../types";
import { isOllamaProvider, validateOllamaProvider } from "../utils/ollamaValidation";
import { saveOllamaConfig } from "../utils/ollamaConfigUtils";
import { isRyoAISProvider, validateRyoAISProvider } from "../utils/ryoaisValidation";
import { saveRyoAISConfig } from "../utils/ryoaisConfigUtils";
import ProviderStatus from "./ProviderStatus";

interface LLMManagementProps {
  username: string | null;
  defaultLLM?: string; // Default LLM passed from settings
  settingsLoaded?: boolean; // Flag indicating whether settings have been loaded
  onDefaultLLMChange?: (newDefaultLLM: string, newDefaultModel?: string) => void; // Callback to notify parent of default LLM changes
  onSharedProviderUpdate?: (sharedProviders: Array<{ name: string; type: string }>) => void; // Callback to notify parent of shared provider updates
}

const getOllamaRootUrl = (host: string) => {
  try {
    const u = new URL(host);
    return `${u.protocol}//${u.host}`;
  } catch {
    return host;
  }
};

const getRyoaisRootUrl = (host: string) => {
  try {
    const u = new URL(host);
    return `${u.protocol}//${u.host}`;
  } catch {
    return host;
  }
};

type ModelOption = { label: string; value: string; description?: string };

const LLMManagement = React.forwardRef<
  { loadProviders: () => Promise<void> },
  LLMManagementProps
>(({
  username,
  defaultLLM: propDefaultLLM,
  settingsLoaded,
  onDefaultLLMChange,
  onSharedProviderUpdate,
}, ref) => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();

  // Get current region for provider filtering
  const isCN = useIsCN();
  const currentRegion = isCN ? 'cn' : 'intl';

  // Use ref to always get the latest region value in async callbacks
  const regionRef = useRef(currentRegion);
  useEffect(() => {
    regionRef.current = currentRegion;
  }, [currentRegion]);

  // State management
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [defaultLLM, setDefaultLLM] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [modelLoadingMap, setModelLoadingMap] = useState<
    Record<string, boolean>
  >({});
  // Track current model selection in the UI for each provider
  const [currentModelSelections, setCurrentModelSelections] = useState<
    Record<string, string>
  >({});
  const [visibleApiKeys, setVisibleApiKeys] = useState<Set<string>>(new Set());
  const [apiKeyValues, setApiKeyValues] = useState<Map<string, string>>(
    new Map()
  );
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState<string>("");
  const [editingAzureEndpoint, setEditingAzureEndpoint] = useState<string>("");
  const [editingAwsAccessKeyId, setEditingAwsAccessKeyId] =
    useState<string>("");
  const [editingAwsSecretAccessKey, setEditingAwsSecretAccessKey] =
    useState<string>("");
  const [editingLoading, setEditingLoading] = useState<boolean>(false);

  // Ollama dynamic model state
  const [ollamaLoading, setOllamaLoading] = useState(false);
  const [ollamaHost, setOllamaHost] = useState('http://127.0.0.1:11434');
  const [ollamaApiKey, setOllamaApiKey] = useState('');
  const [editingOllamaHost, setEditingOllamaHost] = useState(false);
  const [tempOllamaHost, setTempOllamaHost] = useState('');

  // RyoAIS dynamic model state
  const [ryoaisLoading, setRyoaisLoading] = useState(false);
  const [ryoaisHost, setRyoaisHost] = useState('http://localhost/v1');
  const [ryoaisApiKey, setRyoaisApiKey] = useState('');
  const [editingRyoaisHost, setEditingRyoaisHost] = useState(false);
  const [tempRyoaisHost, setTempRyoaisHost] = useState('');
  const [ryoaisScanning, setRyoaisScanning] = useState(false);
  const [ryoaisDevices, setRyoaisDevices] = useState<Array<{ name: string; url: string }>>([]);

  // Enable thinking state for Qwen providers
  const [enableThinkingMap, setEnableThinkingMap] = useState<Record<string, boolean>>({});

  // Fetch Ollama models and save to backend
  const fetchOllamaModels = useCallback(async (host?: string) => {
    const targetHost = host || ollamaHost;
    setOllamaLoading(true);
    try {
      // Pass username so backend can save to user-specific path
      const response = await get_ipc_api().getOllamaModels<{ models: Array<{ name: string; size: number }>; host: string }>(targetHost, username || undefined);
      if (response.success && response.data) {
        // Return true to indicate success, caller can reload providers if needed
        return true;
      } else {
        message.error(response.error?.message || t('pages.settings.ollama_fetch_error'));
        return false;
      }
    } catch (error: any) {
      message.error(error.message || t('pages.settings.ollama_fetch_error'));
      return false;
    } finally {
      setOllamaLoading(false);
    }
  }, [ollamaHost, username, message, t]);

  // Fetch RyoAIS models and save to backend
  const fetchRyoAISModels = useCallback(async (host?: string) => {
    const targetHost = host || ryoaisHost;
    setRyoaisLoading(true);
    try {
      // Pass username so backend can save to user-specific path
      const response = await get_ipc_api().getRyoAISModels<{ models: Array<{ name: string; size: number }>; host: string }>(targetHost, username || undefined, false);
      if (response.success && response.data) {
        // Return true to indicate success, caller can reload providers if needed
        return true;
      } else {
        message.error(response.error?.message || t('pages.settings.ryoais_fetch_error'));
        return false;
      }
    } catch (error: any) {
      message.error(error.message || t('pages.settings.ryoais_fetch_error'));
      return false;
    } finally {
      setRyoaisLoading(false);
    }
  }, [ryoaisHost, username, message, t]);

  // Scan for RyoAIS devices using mDNS
  const scanRyoAISDevices = useCallback(async () => {
    setRyoaisScanning(true);
    try {
      const response = await get_ipc_api().executeRequest<{
        devices: Array<{ name: string; url: string; hostname?: string; ip?: string }>;
        count: number;
        scan_duration: number;
      }>('ryoais.scanDevices', {
        timeout: 10,
        environment: 'production'
      });

      if (response && response.success && response.data) {
        const rawDevices = response.data.devices || [];
        const devices = rawDevices.map(device => {
          let url = device.url;
          if (!url.endsWith('/v1')) {
            url = url.replace(/\/$/, '') + '/v1';
          }
          return { ...device, url };
        });
        setRyoaisDevices(devices);
        if (devices.length > 0) {
          message.success(t('pages.settings.ryoais.scan_success', { count: devices.length }));
          if (devices.length === 1) {
            setTempRyoaisHost(devices[0].url);
            message.info(t('pages.settings.ryoais.auto_filled'));
          }
        } else {
          message.info(t('pages.settings.ryoais.no_devices_found'));
        }
      } else {
        message.error(t('pages.settings.ryoais.scan_failed'));
        setRyoaisDevices([]);
      }
    } catch (error: any) {
      console.error('[RyoAIS] Scan error:', error);
      message.error(t('pages.settings.ryoais.scan_error'));
      setRyoaisDevices([]);
    } finally {
      setRyoaisScanning(false);
    }
  }, [message, t]);

  // Load LLM providers
  const loadProviders = useCallback(async () => {
    if (!username) return;

    setLoading(true);
    try {
      const response = await get_ipc_api().getLLMProviders<{
        providers: LLMProvider[];
      }>(username || undefined);
      if (response.success && response.data) {
        const loadedProviders = response.data.providers;
        
        // Filter providers by region
        const region = regionRef.current;
        const filteredProviders = loadedProviders.filter((p) => {
          const regions = (p as any).regions;
          if (!regions || regions.length === 0) return true; // No region filter means all regions
          return regions.includes(region);
        });
        
        setProviders(filteredProviders);
        console.log(`✅ LLM providers loaded: ${filteredProviders.length} (region: ${region})`, filteredProviders);

        const ollamaProvider = loadedProviders.find(
          (p) =>
            (p.provider || "").toLowerCase() === "ollama" ||
            (p.name || "").toLowerCase().includes("ollama") ||
            (p.display_name || "").toLowerCase().includes("ollama")
        );
        const loadedOllamaHost = ollamaProvider?.base_url;
        if (!editingOllamaHost && loadedOllamaHost && loadedOllamaHost !== ollamaHost) {
          setOllamaHost(loadedOllamaHost);
        }

        // Load RyoAIS host from provider config
        const ryoaisProvider = loadedProviders.find(
          (p) =>
            (p.provider || "").toLowerCase() === "ryoais" ||
            (p.name || "").toLowerCase().includes("ryoais") ||
            (p.display_name || "").toLowerCase().includes("ryoais")
        );
        const loadedRyoaisHost = ryoaisProvider?.base_url;
        if (!editingRyoaisHost && loadedRyoaisHost && loadedRyoaisHost !== ryoaisHost) {
          setRyoaisHost(loadedRyoaisHost);
        }

        // Backfill RyoAIS API key from backend (security: only fill a masked
        // marker so the input renders "••••" instead of disappearing). The real
        // key is fetched on demand via getLLMProviderApiKey when user clicks "eye".
        if (ryoaisProvider?.api_key_configured && !ryoaisApiKey) {
          try {
            const keyResp = await get_ipc_api().getLLMProviderApiKey<{
              api_key?: string;
              credentials?: any;
            }>(ryoaisProvider.provider || ryoaisProvider.name, true);
            if (keyResp.success && keyResp.data?.api_key) {
              setRyoaisApiKey(keyResp.data.api_key);
            }
          } catch (e) {
            console.warn('[LLMManagement] Failed to backfill RyoAIS API key:', e);
          }
        }

        // Debug: Check OpenAI provider name
        const openaiProvider = loadedProviders.find(p => 
          p.name === 'OpenAI' || p.name === 'ChatOpenAI' || p.display_name?.toLowerCase().includes('openai')
        );
        if (openaiProvider) {
          console.log("🔍 [loadProviders] OpenAI provider found:", {
            name: openaiProvider.name,
            display_name: openaiProvider.display_name,
            api_key_configured: openaiProvider.api_key_configured
          });
        }
        console.log("🔍 [loadProviders] Current defaultLLM state:", defaultLLM);
      } else {
        message.error(
          `${t("pages.settings.failed_to_load_providers")}: ${
            response.error?.message
          }`
        );
      }
    } catch (error) {
      console.error("Error loading LLM providers:", error);
      message.error(t("pages.settings.failed_to_load_providers"));
    } finally {
      setLoading(false);
    }
  }, [username, defaultLLM, t, message, editingOllamaHost, ollamaHost, editingRyoaisHost, ryoaisHost, ryoaisApiKey]);

  // Expose loadProviders method via ref
  useImperativeHandle(ref, () => ({
    loadProviders,
  }), [loadProviders]);

  // loadDefaultLLM function removed, defaultLLM now passed from Settings page via props

  const modelOptionsCache = useMemo(() => {
    const cache: Record<string, ModelOption[]> = {};

    providers.forEach((provider) => {
      const supportedModels = Array.isArray(provider.supported_models)
        ? provider.supported_models
        : [];

      const options: ModelOption[] = [];
      const seen = new Set<string>();

      supportedModels.forEach((model: any) => {
        if (typeof model === "string") {
          if (!seen.has(model)) {
            options.push({ label: model, value: model });
            seen.add(model);
          }
          return;
        }

        if (model && typeof model === "object") {
          const value = model.name || model.model_id;
          if (!value || seen.has(value)) {
            return;
          }

          const label = model.display_name || value;
          const description = model.description;
          options.push({ label, value, description });
          seen.add(value);
        }
      });

      // If no models are defined, fall back to default model if available
      if (!options.length && provider.default_model) {
        options.push({
          label: provider.default_model,
          value: provider.default_model,
        });
      }

      cache[provider.name] = options;
    });

    return cache;
  }, [providers]);

  const handleModelSelection = useCallback(
    async (providerName: string, modelName: string) => {
      if (!modelName) {
        return;
      }

      // Find provider by name to get standard identifier
      const provider = providers.find((p) => p.name === providerName);
      if (!provider) {
        message.error(`Provider ${providerName} not found`);
        return;
      }
      
      // Use standard provider identifier for API calls
      const providerIdentifier = provider.provider;
      if (!providerIdentifier) {
        message.error(`Provider ${providerName} has no identifier`);
        return;
      }

      // Update UI state immediately
      setCurrentModelSelections((prev) => ({
        ...prev,
        [providerName]: modelName,
      }));

      setModelLoadingMap((prev) => ({ ...prev, [providerName]: true }));

      try {
        const response = await get_ipc_api().setLLMProviderModel<{
          message: string;
        }>(providerIdentifier, modelName);
        if (response.success) {
          message.success(t("pages.settings.model_update_success"));
          setProviders((prev) =>
            prev.map((provider) =>
              provider.name === providerName
                ? {
                    ...provider,
                    preferred_model: modelName,
                    default_model: modelName,
                  }
                : provider
            )
          );
        } else {
          const errorMessage = response.error?.message;
          message.error(
            errorMessage
              ? `${t("pages.settings.model_update_failed")}: ${errorMessage}`
              : t("pages.settings.model_update_failed")
          );
        }
      } catch (error) {
        console.error("Error updating provider model:", error);
        message.error(t("pages.settings.model_update_failed"));
      } finally {
        setModelLoadingMap((prev) => {
          const { [providerName]: _ignored, ...rest } = prev;
          return rest;
        });
      }
    },
    [message, t, providers]
  );

  const openDocumentation = useCallback(
    (url?: string | null) => {
      if (!url) {
        message.warning(t("pages.settings.documentation_unavailable"));
        return;
      }

      window.open(url, "_blank", "noopener,noreferrer");
    },
    [message, t]
  );

  // Check if provider is Qwen-based (supports enable_thinking option)
  const isQwenProvider = useCallback((provider: LLMProvider) => {
    const name = (provider.name || '').toLowerCase();
    const displayName = (provider.display_name || '').toLowerCase();
    const providerType = (provider.provider || '').toLowerCase();
    return name.includes('qwen') || name.includes('dashscope') || 
           displayName.includes('qwen') || displayName.includes('dashscope') ||
           providerType.includes('qwen') || providerType.includes('dashscope');
  }, []);

  // Handle enable_thinking toggle for Qwen providers
  const handleEnableThinkingChange = useCallback(
    async (providerName: string, enabled: boolean) => {
      const provider = providers.find((p) => p.name === providerName);
      if (!provider) {
        message.error(`Provider ${providerName} not found`);
        return;
      }

      const providerIdentifier = provider.provider;
      if (!providerIdentifier) {
        message.error(`Provider ${providerName} has no identifier`);
        return;
      }

      // Update local state immediately for responsive UI
      setEnableThinkingMap((prev) => ({ ...prev, [providerName]: enabled }));

      try {
        const response = await get_ipc_api().setLLMProviderEnableThinking<{ message: string }>(
          providerIdentifier,
          enabled
        );
        if (response.success) {
          message.success(`${providerName} enable_thinking set to ${enabled}`);
        } else {
          message.error(`Failed to update enable_thinking: ${response.error?.message}`);
          // Revert on failure
          setEnableThinkingMap((prev) => ({ ...prev, [providerName]: !enabled }));
        }
      } catch (error) {
        console.error("Error updating enable_thinking:", error);
        message.error("Failed to update enable_thinking setting");
        // Revert on failure
        setEnableThinkingMap((prev) => ({ ...prev, [providerName]: !enabled }));
      }
    },
    [providers, message]
  );

  // Set default LLM
  const handleDefaultLLMChange = async (providerName: string) => {
    // Find the provider by name (for display) to get its standard identifier
    const provider = providers.find((p) => p.name === providerName);
    if (!provider) {
      message.error(`Provider ${providerName} not found`);
      return;
    }

    // Use standard provider identifier for API calls
    const providerIdentifier = provider.provider;
    if (!providerIdentifier) {
      message.error(`Provider ${providerName} has no identifier`);
      return;
    }

    if (!provider.api_key_configured) {
      message.warning(
        `${providerName} ${t("pages.settings.provider_not_configured")}`
      );
      return;
    }

    // Get the currently selected model in the UI for this provider
    const selectedModel = currentModelSelections[providerName];
    
    // If user has selected a model in the UI, update it first
    if (selectedModel && selectedModel !== provider.preferred_model) {
      await handleModelSelection(providerName, selectedModel);
    }

    // Determine which model to use: UI selection > preferred_model > default_model
    const modelToUse = selectedModel || provider.preferred_model || provider.default_model || undefined;

    // Validate Ollama provider configuration
    const ollamaValidation = validateOllamaProvider(provider, modelToUse, t);
    if (!ollamaValidation.valid) {
      message.warning(ollamaValidation.errorMessage);
      return;
    }

    // Validate RyoAIS provider configuration
    const ryoaisValidation = validateRyoAISProvider(provider, modelToUse, t);
    if (!ryoaisValidation.valid) {
      message.warning(ryoaisValidation.errorMessage);
      return;
    }

    try {
      const response = await get_ipc_api().setDefaultLLM<{ message: string }>(
        providerIdentifier,  // Use standard identifier
        username || "",
        modelToUse
      );

      if (response.success) {
        setDefaultLLM(providerIdentifier);
        // Notify parent component to update settings - use providerIdentifier for consistency
        onDefaultLLMChange?.(providerIdentifier, modelToUse);
        message.success(
          `${t("pages.settings.default_llm_set")}: ${providerName} - ${t(
            "pages.settings.hot_updated"
          )}`
        );

        // No restart required - hot-update is supported
      } else {
        // If backend says provider is not configured, reload providers to sync
        if (response.error?.message?.includes("not configured")) {
          message.warning(
            `${providerName} ${t("pages.settings.provider_not_configured")}`
          );
          // Reload providers to sync with backend
          loadProviders();
        } else {
          message.error(
            `${t("pages.settings.failed_to_set_default")}: ${
              response.error?.message
            }`
          );
        }
      }
    } catch (error) {
      console.error("Error setting default LLM:", error);
      message.error(t("pages.settings.failed_to_set_default"));
    }
  };

  // Update provider configuration
  const updateProvider = async (
    name: string,  // This is provider.name (display name), need to convert to provider.provider
    apiKey: string,
    azureEndpoint?: string,
    awsAccessKeyId?: string,
    awsSecretAccessKey?: string,
  ) => {
    // Find provider by name to get standard identifier
    const provider = providers.find((p) => p.name === name);
    if (!provider) {
      message.error(`Provider ${name} not found`);
      return;
    }
    
    // Use standard provider identifier for API calls
    const providerIdentifier = provider.provider;
    if (!providerIdentifier) {
      message.error(`Provider ${name} has no identifier`);
      return;
    }

    try {
      const response = await get_ipc_api().updateLLMProvider<{
        message: string;
        auto_set_as_default?: boolean;
        default_llm?: string;
        default_llm_model?: string;
        settings?: {
          default_llm: string;
          default_llm_model: string;
        };
        shared_providers?: Array<{ name: string; type: string }>;
      }>(providerIdentifier, apiKey, azureEndpoint, awsAccessKeyId, awsSecretAccessKey);

      if (response.success) {
        const responseData = response.data;
        const autoSetAsDefault = responseData?.auto_set_as_default || false;
        
        // Show success message
        let successMessage = `${name} ${t("pages.settings.llm_updated_successfully")} - ${t(
          "pages.settings.hot_updated"
        )}`;
        
        if (autoSetAsDefault && responseData?.default_llm) {
          successMessage += ` - ${t("pages.settings.auto_set_as_default")}: ${responseData.default_llm}`;
        }
        
        message.success(successMessage);
        
        // If auto-set as default, update local state
        if (autoSetAsDefault && responseData?.settings) {
          console.log('🔄 Auto-set as default after update:', responseData.settings);
          setDefaultLLM(responseData.settings.default_llm);
          onDefaultLLMChange?.(
            responseData.settings.default_llm, 
            responseData.settings.default_llm_model
          );
        }
        
        // Reload providers to get updated state from backend
        await loadProviders();
        console.log("✅ Provider updated:", name);

        // Check for shared providers and notify parent to refresh other component
        if (responseData?.shared_providers && Array.isArray(responseData.shared_providers) && responseData.shared_providers.length > 0) {
          console.log("🔄 [LLM] Found shared providers, notifying parent:", responseData.shared_providers);
          onSharedProviderUpdate?.(responseData.shared_providers);
        }

        // No restart required - hot-update is supported
      } else {
        message.error(
          `${t("pages.settings.failed_to_update_provider")} ${name}: ${
            response.error?.message
          }`
        );
      }
    } catch (error) {
      console.error("Error updating provider:", error);
      message.error(`${t("pages.settings.failed_to_update_provider")} ${name}`);
    }
  };

  // Delete provider configuration
  const deleteProviderConfig = (name: string) => {
    // Find provider by name to get standard identifier
    const provider = providers.find((p) => p.name === name);
    if (!provider) {
      message.error(`Provider ${name} not found`);
      return;
    }
    
    // Use standard provider identifier for API calls
    const providerIdentifier = provider.provider;
    if (!providerIdentifier) {
      message.error(`Provider ${name} has no identifier`);
      return;
    }

    // Check if this is the default LLM (compare using all possible identifiers)
    const dlm = (defaultLLM || "").toLowerCase();
    const isDefault = providerIdentifier && (
      dlm === (providerIdentifier || "").toLowerCase()
      || dlm === (provider.class_name || "").toLowerCase()
      || dlm === (provider.name || "").toLowerCase()
      || dlm === (provider.display_name || "").toLowerCase()
    );
    
    // Show confirmation dialog using modal from App.useApp() for proper theme support
    modal.confirm({
      title: t("pages.settings.confirm_delete_provider"),
      content: (
        <div>
          <p>
            {t("pages.settings.confirm_delete_provider_message")}
          </p>
          {isDefault && (
            <p style={{ color: "#ff4d4f", marginTop: "8px", fontWeight: 500 }}>
              ⚠️ {t("pages.settings.warning_default_llm_deletion")}
            </p>
          )}
          <p style={{ marginTop: "8px", opacity: 0.65, fontSize: "13px" }}>
            {t("pages.settings.delete_warning_env_vars")}
          </p>
        </div>
      ),
      okText: t("common.delete"),
      okType: "danger",
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          const response = await get_ipc_api().deleteLLMProviderConfig<{
            message: string;
            was_default_llm?: boolean;
            new_default_llm?: string;
            new_default_model?: string;
            deleted_env_vars?: string[];
            reset_to_default?: boolean;
            settings?: {
              default_llm: string;
              default_llm_model: string;
            };
            shared_providers?: Array<{ name: string; type: string }>;
          }>(providerIdentifier, username || "");

          if (response.success && response.data) {
            const responseData = response.data;
            const wasDefaultLLM = responseData.was_default_llm || false;
            const newDefaultLLM = responseData.new_default_llm;
            const resetToDefault = responseData.reset_to_default || false;

            // Show success message
            if (wasDefaultLLM && newDefaultLLM) {
              const resetMessage = resetToDefault 
                ? ` ${t("pages.settings.reset_to_default_provider")}`
                : ` Default LLM changed to: ${newDefaultLLM}`;
              message.success(
                `${name} ${t("pages.settings.llm_config_deleted")} - ${t(
                  "pages.settings.hot_updated"
                )}.${resetMessage}`
              );
            } else {
              message.success(
                `${name} ${t("pages.settings.llm_config_deleted")} - ${t(
                  "pages.settings.hot_updated"
                )}`
              );
            }

            // Update local state immediately for better UX
            setProviders((prevProviders) =>
              prevProviders.map((provider) =>
                provider.name === name
                  ? { ...provider, api_key_configured: false }
                  : provider
              )
            );

            // Clear any cached API key values for this provider
            setApiKeyValues((prevValues) => {
              const newValues = new Map(prevValues);
              newValues.delete(name);
              return newValues;
            });

            // Remove from visible API keys
            setVisibleApiKeys((prevVisible) => {
              const newVisible = new Set(prevVisible);
              newVisible.delete(name);
              return newVisible;
            });

            // If this was the default LLM, update to new default
            if (wasDefaultLLM && newDefaultLLM) {
              setDefaultLLM(newDefaultLLM);
              // Notify parent component to update default_llm in settings
              // Use settings from response if available for complete update
              if (responseData.settings) {
                console.log('🔄 Updating settings after deletion:', responseData.settings);
                onDefaultLLMChange?.(
                  responseData.settings.default_llm, 
                  responseData.settings.default_llm_model
                );
              } else {
                onDefaultLLMChange?.(newDefaultLLM, responseData.new_default_model);
              }
            } else {
              // Check if this was the default LLM (compare using provider identifier)
              // providerIdentifier is already defined above
              if (providerIdentifier && (defaultLLM || "").toLowerCase() === (providerIdentifier || "").toLowerCase()) {
                // Fallback: if backend didn't return new_default_llm but this was default
                setDefaultLLM("");
                onDefaultLLMChange?.("", "");
              }
            }

            // Reload providers from backend to verify the deletion and get updated state
            setTimeout(() => {
              loadProviders();
            }, 500);
            
            // Check for shared providers and notify parent to refresh other component
            if (responseData?.shared_providers && Array.isArray(responseData.shared_providers) && responseData.shared_providers.length > 0) {
              console.log("🔄 [LLM] Found shared providers after deletion, notifying parent:", responseData.shared_providers);
              onSharedProviderUpdate?.(responseData.shared_providers);
            }
          } else {
            message.error(
              `${t("pages.settings.failed_to_delete_config")} ${name}: ${
                response.error?.message
              }`
            );
          }
        } catch (error) {
          console.error("Error deleting provider config:", error);
          message.error(`${t("pages.settings.failed_to_delete_config")} ${name}`);
        }
      },
    });
  };

  // API key editing related functions
  const startEditing = async (providerName: string) => {
    // Find the provider to check if it's configured
    const provider = providers.find((p) => p.name === providerName);
    if (!provider) {
      message.error(`Provider ${providerName} not found`);
      return;
    }

    // Use standard provider identifier for API calls
    const providerIdentifier = provider.provider;
    if (!providerIdentifier) {
      message.error(`Provider ${providerName} has no identifier`);
      return;
    }

    setEditingProvider(providerName);
    setEditingLoading(true);

    // If provider is configured, try to get the current credentials
    if (provider.api_key_configured) {
      try {
        const response = await get_ipc_api().getLLMProviderApiKey<{
          api_key?: string;
          credentials?: any;
        }>(providerIdentifier, true);
        if (response.success && response.data) {
          // Handle special cases with multiple credentials
          if (providerName === "AzureOpenAI" && response.data.credentials) {
            setEditingValue(response.data.credentials.api_key || "");
            setEditingAzureEndpoint(
              response.data.credentials.azure_endpoint || ""
            );
            setEditingAwsAccessKeyId("");
            setEditingAwsSecretAccessKey("");
          } else if (
            providerName === "ChatBedrockConverse" &&
            response.data.credentials
          ) {
            setEditingValue("");
            setEditingAzureEndpoint("");
            setEditingAwsAccessKeyId(
              response.data.credentials.aws_access_key_id || ""
            );
            setEditingAwsSecretAccessKey(
              response.data.credentials.aws_secret_access_key || ""
            );
          } else {
            setEditingValue(response.data.api_key || "");
            setEditingAzureEndpoint("");
            setEditingAwsAccessKeyId("");
            setEditingAwsSecretAccessKey("");
          }
        } else {
          // If failed to get credentials, start with empty values
          setEditingValue("");
          setEditingAzureEndpoint("");
          setEditingAwsAccessKeyId("");
          setEditingAwsSecretAccessKey("");
        }
      } catch (error) {
        console.error("Error fetching credentials for editing:", error);
        setEditingValue("");
        setEditingAzureEndpoint("");
        setEditingAwsAccessKeyId("");
        setEditingAwsSecretAccessKey("");
      }
    } else {
      // If not configured, start with empty values
      setEditingValue("");
      setEditingAzureEndpoint("");
      setEditingAwsAccessKeyId("");
      setEditingAwsSecretAccessKey("");
    }

    setEditingLoading(false);
  };

  const saveApiKey = async () => {
    if (editingProvider) {
      await updateProvider(
        editingProvider,
        editingValue,
        editingAzureEndpoint,
        editingAwsAccessKeyId,
        editingAwsSecretAccessKey
      );
      setEditingProvider(null);
      setEditingValue("");
      setEditingAzureEndpoint("");
      setEditingAwsAccessKeyId("");
      setEditingAwsSecretAccessKey("");
    }
  };

  const cancelEditing = () => {
    setEditingProvider(null);
    setEditingValue("");
    setEditingAzureEndpoint("");
    setEditingAwsAccessKeyId("");
    setEditingAwsSecretAccessKey("");
    setEditingLoading(false);
  };

  const handleToggleApiKeyVisibility = async (providerName: string) => {
    // Find the provider to check if it's local
    const provider = providers.find((p) => p.name === providerName);
    if (!provider) {
      message.error(`Provider ${providerName} not found`);
      return;
    }

    // Use standard provider identifier for API calls
    const providerIdentifier = provider.provider;
    if (!providerIdentifier) {
      message.error(`Provider ${providerName} has no identifier`);
      return;
    }

    // For local providers, show a different message
    if (provider.is_local) {
      message.info(
        `${providerName} ${t("pages.settings.local_service_no_api_key")}`
      );
      return;
    }

    const isCurrentlyVisible = visibleApiKeys.has(providerName);

    if (isCurrentlyVisible) {
      // Hide the API key
      const newVisible = new Set(visibleApiKeys);
      newVisible.delete(providerName);
      setVisibleApiKeys(newVisible);

      // Remove from cache
      const newValues = new Map(apiKeyValues);
      newValues.delete(providerName);
      setApiKeyValues(newValues);
    } else {
      // Show the API key - fetch it from backend
      try {
        const response = await get_ipc_api().getLLMProviderApiKey<{
          api_key: string;
        }>(providerIdentifier, true);

        if (response.success && response.data) {
          // Add to visible set
          const newVisible = new Set(visibleApiKeys);
          newVisible.add(providerName);
          setVisibleApiKeys(newVisible);

          // Cache the API key value
          const newValues = new Map(apiKeyValues);
          newValues.set(providerName, response.data.api_key);
          setApiKeyValues(newValues);
        } else {
          message.error(
            `${t("pages.settings.failed_to_get_api_key")}: ${
              response.error?.message
            }`
          );
        }
      } catch (error) {
        console.error("Error fetching API key:", error);
        message.error(t("pages.settings.failed_to_get_api_key"));
      }
    }
  };

  // Update local state when passed defaultLLM changes
  useEffect(() => {
    console.log('🔄 [LLMManagement] propDefaultLLM changed:', propDefaultLLM);
    if (propDefaultLLM !== undefined) {
      setDefaultLLM(propDefaultLLM);
      console.log('✅ [LLMManagement] Local defaultLLM updated to:', propDefaultLLM);
    }
  }, [propDefaultLLM]);

  // Initialize loading - wait for settings to load before loading providers
  useEffect(() => {
    if (username && settingsLoaded) {
      console.log('🔄 [LLMManagement] Conditions met, loading providers...');
      loadProviders();
      // No longer call loadDefaultLLM() as defaultLLM is passed from Settings page
    }
  }, [username, settingsLoaded, loadProviders]);

  // If user is not logged in
  if (!username) {
    return (
      <div style={{ marginTop: "20px", border: "1px solid #f0f0f0", borderRadius: "8px", background: "#fff" }}>
        <div style={{ textAlign: "center", padding: "40px", color: "#999" }}>
          🔐 {t("pages.settings.login_to_view_llm")}
        </div>
      </div>
    );
  }

  // Table column definitions
  const columns = [
    {
      title: t("pages.settings.llm_provider"),
      dataIndex: "display_name",
      key: "display_name",
      width: 150,
      ellipsis: true,
    },
    {
      title: t("pages.settings.status"),
      dataIndex: "api_key_configured",
      key: "status",
      width: 120,
      render: (_: boolean, record: LLMProvider) => (
        <ProviderStatus
          kind="llm"
          provider={record}
          model={currentModelSelections[record.name] || record.preferred_model || record.default_model || undefined}
        />
      ),
    },
    {
      title: t("pages.settings.api_key"),
      dataIndex: "api_key",
      key: "api_key",
      minWidth: 200,
      ellipsis: true,
      render: (_: any, record: LLMProvider) => {
        const isEditing = editingProvider === record.name;

        // Ollama specific rendering with host and optional API key (double-click to edit)
        if (isOllamaProvider(record)) {
          if (editingOllamaHost) {
            return (
              <Space direction="vertical" style={{ width: "100%" }} onKeyDown={(e) => { if (e.key === 'Escape') setEditingOllamaHost(false); }}>
                <Input
                  value={tempOllamaHost}
                  onChange={(e) => setTempOllamaHost(e.target.value)}
                  placeholder={t("pages.settings.ollama_host_placeholder")}
                  style={{ width: "300px" }}
                  addonBefore="Host"
                  autoFocus
                  id={`${record.name}-ollama-host-input`}
                />
                <Input.Password
                  value={ollamaApiKey}
                  onChange={(e) => setOllamaApiKey(e.target.value)}
                  placeholder={t("pages.settings.ollama_api_key_placeholder")}
                  style={{ width: "300px" }}
                  addonBefore="API Key"
                  id={`${record.name}-ollama-apikey-input`}
                />
                <Space>
                  <Button
                    size="small"
                    type="primary"
                    id={`${record.name}-ollama-save`}
                    onClick={async () => {
                      if (tempOllamaHost !== undefined) {
                        await saveOllamaConfig({
                          providerType: 'llm',
                          host: tempOllamaHost,
                          apiKey: ollamaApiKey,
                          onSuccess: async () => {
                            setOllamaHost(tempOllamaHost);
                            setEditingOllamaHost(false);
                            message.success(t("pages.settings.ollama_config_saved"));
                            try {
                              await fetchOllamaModels(tempOllamaHost);
                            } catch (error: any) {
                              message.warning(t("pages.settings.ollama_service_unavailable") || "Ollama service is not available. Configuration saved, but models could not be fetched.");
                            }
                          },
                          onError: (error) => message.error(error)
                        });
                      }
                    }}
                  >
                    {t("common.save")}
                  </Button>
                  <Button
                    size="small"
                    onClick={() => {
                      setEditingOllamaHost(false);
                      setTempOllamaHost(ollamaHost);
                    }}
                  >
                    {t("common.cancel")}
                  </Button>
                </Space>
              </Space>
            );
          }

          return (
            <div
              onDoubleClick={() => {
                setTempOllamaHost(ollamaHost);
                setEditingOllamaHost(true);
              }}
              style={{ cursor: 'text', userSelect: 'none' }}
              title="Double-click to edit"
              id={`${record.name}-ollama-apikey-cell`}
            >
              <Space direction="vertical" size={2}>
                <Space>
                  <span style={{ color: "#999", fontSize: "12px" }}>{t("pages.settings.host")}:</span>
                  <span style={{ fontFamily: "monospace", fontSize: "12px" }}>{ollamaHost}</span>
                </Space>
                {ollamaApiKey && (
                  <Space>
                    <span style={{ color: "#999", fontSize: "12px" }}>{t("pages.settings.api_key")}:</span>
                    <span style={{ fontFamily: "monospace", fontSize: "12px" }}>••••••••</span>
                  </Space>
                )}
              </Space>
            </div>
          );
        }

        // RyoAIS specific rendering with host and optional API key (double-click to edit)
        if (isRyoAISProvider(record)) {
          if (editingRyoaisHost) {
            const hasMultipleDevices = ryoaisDevices.length > 1;

            return (
              <Space direction="vertical" style={{ width: "100%" }} onKeyDown={(e) => { if (e.key === 'Escape') setEditingRyoaisHost(false); }}>
                <Space.Compact style={{ width: "300px" }}>
                  {hasMultipleDevices ? (
                    <Select
                      value={tempRyoaisHost}
                      onChange={setTempRyoaisHost}
                      placeholder={t("pages.settings.ryoais_host_placeholder")}
                      style={{ flex: 1 }}
                      optionLabelProp="label"
                      id={`${record.name}-ryoais-host-select`}
                    >
                      {ryoaisDevices.map(device => (
                        <Select.Option key={device.url} value={device.url} label={device.url}>
                          <div>
                            <div style={{ fontWeight: 500 }}>{device.url}</div>
                            {device.name && (
                              <div style={{ fontSize: '12px', color: '#999' }}>{device.name}</div>
                            )}
                          </div>
                        </Select.Option>
                      ))}
                    </Select>
                  ) : (
                    <Input
                      value={tempRyoaisHost}
                      onChange={(e) => setTempRyoaisHost(e.target.value)}
                      placeholder={t("pages.settings.ryoais_host_placeholder")}
                      style={{ flex: 1 }}
                      autoFocus
                      id={`${record.name}-ryoais-host-input`}
                    />
                  )}
                  <Tooltip title={t("pages.settings.ryoais.scan_devices")}>
                    <Button
                      icon={<ScanOutlined />}
                      loading={ryoaisScanning}
                      onClick={scanRyoAISDevices}
                      id={`${record.name}-ryoais-scan`}
                    />
                  </Tooltip>
                </Space.Compact>
                <Input.Password
                  value={ryoaisApiKey}
                  onChange={(e) => setRyoaisApiKey(e.target.value)}
                  placeholder={t("pages.settings.ryoais_api_key_placeholder")}
                  style={{ width: "300px" }}
                  addonBefore="API Key"
                  id={`${record.name}-ryoais-apikey-input`}
                />
                <Space>
                  <Button
                    size="small"
                    type="primary"
                    id={`${record.name}-ryoais-save`}
                    onClick={async () => {
                      if (tempRyoaisHost !== undefined) {
                        await saveRyoAISConfig({
                          providerType: 'llm',
                          host: tempRyoaisHost,
                          apiKey: ryoaisApiKey,
                          onSuccess: async () => {
                            setRyoaisHost(tempRyoaisHost);
                            await fetchRyoAISModels(tempRyoaisHost);
                            setEditingRyoaisHost(false);
                            message.success(t("pages.settings.ryoais_config_saved"));
                          },
                          onError: (error) => message.error(error)
                        });
                      }
                    }}
                  >
                    {t("common.save")}
                  </Button>
                  <Button
                    size="small"
                    onClick={() => {
                      setEditingRyoaisHost(false);
                      setTempRyoaisHost(ryoaisHost);
                    }}
                  >
                    {t("common.cancel")}
                  </Button>
                </Space>
              </Space>
            );
          }

          return (
            <div
              onDoubleClick={() => {
                setTempRyoaisHost(ryoaisHost);
                setEditingRyoaisHost(true);
              }}
              style={{ cursor: 'text', userSelect: 'none' }}
              title="Double-click to edit"
              id={`${record.name}-ryoais-apikey-cell`}
            >
              <Space direction="vertical" size={2}>
                <Space>
                  <span style={{ color: "#999", fontSize: "12px" }}>{t("pages.settings.host")}:</span>
                  <span style={{ fontFamily: "monospace", fontSize: "12px" }}>{ryoaisHost}</span>
                </Space>
                {ryoaisApiKey && (
                  <Space>
                    <span style={{ color: "#999", fontSize: "12px" }}>{t("pages.settings.api_key")}:</span>
                    <span style={{ fontFamily: "monospace", fontSize: "12px" }}>••••••••</span>
                  </Space>
                )}
              </Space>
            </div>
          );
        }

        if (isEditing) {
          return (
            <Space direction="vertical" style={{ width: "100%" }}>
              {/* Azure OpenAI specific fields */}
              {record.name === "AzureOpenAI" && (
                <>
                  <Input
                    value={editingAzureEndpoint}
                    onChange={(e) => setEditingAzureEndpoint(e.target.value)}
                    placeholder={
                      editingLoading
                        ? t("pages.settings.loading_current")
                        : t("pages.settings.enter_azure_endpoint")
                    }
                    style={{ width: "350px" }}
                    disabled={editingLoading}
                  />
                  <Input
                    value={editingValue}
                    onChange={(e) => setEditingValue(e.target.value)}
                    placeholder={
                      editingLoading
                        ? t("pages.settings.loading_current")
                        : t("pages.settings.enter_azure_api_key")
                    }
                    style={{ width: "350px" }}
                    disabled={editingLoading}
                  />
                </>
              )}

              {/* AWS Bedrock specific fields */}
              {record.name === "ChatBedrockConverse" && (
                <>
                  <Input
                    value={editingAwsAccessKeyId}
                    onChange={(e) => setEditingAwsAccessKeyId(e.target.value)}
                    placeholder={
                      editingLoading
                        ? t("pages.settings.loading_current")
                        : t("pages.settings.enter_aws_access_key_id")
                    }
                    style={{ width: "350px" }}
                    disabled={editingLoading}
                  />
                  <Input
                    value={editingAwsSecretAccessKey}
                    onChange={(e) =>
                      setEditingAwsSecretAccessKey(e.target.value)
                    }
                    placeholder={
                      editingLoading
                        ? t("pages.settings.loading_current")
                        : t("pages.settings.enter_aws_secret_access_key")
                    }
                    style={{ width: "350px" }}
                    disabled={editingLoading}
                    type="password"
                  />
                </>
              )}

              {/* Standard single API key field for other providers */}
              {record.name !== "AzureOpenAI" &&
                record.name !== "ChatBedrockConverse" && (
                  <Input
                    value={editingValue}
                    onChange={(e) => setEditingValue(e.target.value)}
                    placeholder={
                      editingLoading
                        ? t("pages.settings.loading_current")
                        : t("pages.settings.enter_api_key")
                    }
                    style={{ width: "350px" }}
                    disabled={editingLoading}
                  />
                )}

              <Space>
                <Button
                  size="small"
                  type="primary"
                  onClick={saveApiKey}
                  disabled={editingLoading}
                >
                  {t("common.save")}
                </Button>
                <Button
                  size="small"
                  onClick={cancelEditing}
                  disabled={editingLoading}
                >
                  {t("common.cancel")}
                </Button>
              </Space>
            </Space>
          );
        }

        const apiKeyText = record.is_local
          ? `🏠 ${t("pages.settings.local_service")}`
          : record.api_key_configured
          ? visibleApiKeys.has(record.name)
            ? apiKeyValues.get(record.name) || "••••••••••••••••"
            : "••••••••••••••••"
          : t("pages.settings.not_configured");

        return (
          <Space style={{ width: '100%', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            {!record.is_local ? (
              <span
                role="button"
                tabIndex={0}
                title={t("common.edit")}
                onDoubleClick={() => startEditing(record.name)}
                style={{
                  fontFamily: "monospace",
                  wordBreak: 'break-all',
                  whiteSpace: 'pre-wrap',
                  lineHeight: 1.4,
                  cursor: 'pointer',
                  borderRadius: 4,
                  padding: '2px 6px',
                  border: '1px dashed transparent',
                  transition: 'border-color 0.15s, background 0.15s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = '#d9d9d9';
                  (e.currentTarget as HTMLElement).style.background = '#fafafa';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = 'transparent';
                  (e.currentTarget as HTMLElement).style.background = 'transparent';
                }}
              >
                {apiKeyText}
              </span>
            ) : (
              <span style={{
                fontFamily: "monospace",
                wordBreak: 'break-all',
                whiteSpace: 'pre-wrap',
                lineHeight: 1.4
              }}>
                {apiKeyText}
              </span>
            )}
            {record.api_key_configured && !record.is_local && (
              <Tooltip
                title={
                  visibleApiKeys.has(record.name)
                    ? t("pages.settings.hide")
                    : t("pages.settings.show")
                }
              >
                <Button
                  size="small"
                  type="text"
                  icon={
                    visibleApiKeys.has(record.name) ? (
                      <EyeInvisibleOutlined />
                    ) : (
                      <EyeOutlined />
                    )
                  }
                  onClick={() => handleToggleApiKeyVisibility(record.name)}
                />
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: t("pages.settings.llm_model"),
      key: "model",
      width: 220,
      ellipsis: true,
      render: (_: any, record: LLMProvider) => {
        // Check if this is Ollama provider
        if (isOllamaProvider(record)) {
          // Use cached options derived from provider.supported_models (which are merged from ollama_tags.json)
          const ollamaOptions = modelOptionsCache[record.name] || [];
          const uiSelectedModel = currentModelSelections[record.name];
          const backendModel = record.preferred_model || record.default_model || undefined;
          const currentValue = uiSelectedModel || backendModel;

          return (
            <Space>
              <Select
                size="small"
                style={{ width: 160 }}
                value={currentValue || undefined}
                onChange={(value) => handleModelSelection(record.name, value)}
                loading={ollamaLoading || !!modelLoadingMap[record.name]}
                placeholder={ollamaLoading ? t("pages.settings.loading") : t("pages.settings.select_model")}
                optionLabelProp="label"
                popupMatchSelectWidth={false}
                showSearch
                allowClear
                notFoundContent={ollamaOptions.length === 0 ? t("pages.settings.no_models_available") : null}
              >
                {ollamaOptions.map((option) => (
                  <Select.Option key={option.value} value={option.value} label={option.label}>
                    {option.label}
                  </Select.Option>
                ))}
              </Select>
              <Tooltip title={t("pages.settings.refresh_models")}>
                <Button
                  size="small"
                  type="text"
                  icon={<ReloadOutlined spin={ollamaLoading} />}
                  onClick={async () => {
                    const success = await fetchOllamaModels();
                    if (success) {
                      // Reload providers to get merged Ollama models from backend
                      loadProviders();
                    }
                  }}
                />
              </Tooltip>
            </Space>
          );
        }

        // Check if this is RyoAIS provider
        if (isRyoAISProvider(record)) {
          // Use cached options derived from provider.supported_models (which are merged from ryoais_models.json)
          const ryoaisOptions = modelOptionsCache[record.name] || [];
          const uiSelectedModel = currentModelSelections[record.name];
          const backendModel = record.preferred_model || record.default_model || undefined;
          const currentValue = uiSelectedModel || backendModel;

          return (
            <Space>
              <Select
                size="small"
                style={{ width: 160 }}
                value={currentValue || undefined}
                onChange={(value) => handleModelSelection(record.name, value)}
                loading={ryoaisLoading || !!modelLoadingMap[record.name]}
                placeholder={ryoaisLoading ? t("pages.settings.loading") : t("pages.settings.select_model")}
                optionLabelProp="label"
                popupMatchSelectWidth={false}
                showSearch
                allowClear
                notFoundContent={ryoaisOptions.length === 0 ? t("pages.settings.no_models_available") : null}
              >
                {ryoaisOptions.map((option) => (
                  <Select.Option key={option.value} value={option.value} label={option.label}>
                    {option.label}
                  </Select.Option>
                ))}
              </Select>
              <Tooltip title={t("pages.settings.refresh_models")}>
                <Button
                  size="small"
                  type="text"
                  icon={<ReloadOutlined spin={ryoaisLoading} />}
                  onClick={async () => {
                    const success = await fetchRyoAISModels();
                    if (success) {
                      // Reload providers to get merged RyoAIS models from backend
                      loadProviders();
                    }
                  }}
                />
              </Tooltip>
            </Space>
          );
        }

        const options = modelOptionsCache[record.name] || [];

        if (!options.length) {
          return (
            <span style={{ color: "rgba(0, 0, 0, 0.45)" }}>
              {t("pages.settings.no_models_available")}
            </span>
          );
        }

        // Use UI-selected model if available, otherwise use backend preferred_model
        const uiSelectedModel = currentModelSelections[record.name];
        const backendModel = record.preferred_model || record.default_model || undefined;
        const currentValue = uiSelectedModel || backendModel;
        
        const hasCurrentValue = currentValue
          ? options.some((option) => option.value === currentValue)
          : false;
        const effectiveValue = hasCurrentValue
          ? currentValue
          : options[0]?.value;

        // Check if this is a Qwen provider to show enable_thinking option
        const showEnableThinking = isQwenProvider(record);
        const enableThinkingValue = enableThinkingMap[record.name] ?? record.enable_thinking ?? false;

        return (
          <Space direction="vertical" size={4}>
            <Select
              size="small"
              style={{ width: 180 }}
              value={effectiveValue}
              onChange={(value) => handleModelSelection(record.name, value)}
              loading={!!modelLoadingMap[record.name]}
              placeholder={t("pages.settings.select_model")}
              optionLabelProp="label"
              popupMatchSelectWidth={false}
            >
              {options.map((option) => (
                <Select.Option
                  key={option.value}
                  value={option.value}
                  label={option.label}
                >
                  {option.description ? (
                    <Tooltip title={option.description}>
                      <span>{option.label}</span>
                    </Tooltip>
                  ) : (
                    option.label
                  )}
                </Select.Option>
              ))}
            </Select>
            {showEnableThinking && (
              <Tooltip title={t("pages.settings.enable_thinking_tooltip")}>
                <Checkbox
                  checked={enableThinkingValue}
                  onChange={(e) => handleEnableThinkingChange(record.name, e.target.checked)}
                  style={{ fontSize: '12px' }}
                >
                  {t("pages.settings.enable_thinking")}
                </Checkbox>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: t("pages.settings.default"),
      dataIndex: "name",
      key: "default",
      width: 90,
      render: (name: string, record: LLMProvider) => {
        // Compare defaultLLM against all known identifiers for this provider
        // (settings may store class_name like "ChatOpenAI", provider id like "openai", or display name like "OpenAI")
        const providerIdentifier = record.provider;
        const dlm = (defaultLLM || "").toLowerCase();
        const isChecked = dlm === (providerIdentifier || "").toLowerCase()
          || dlm === (record.class_name || "").toLowerCase()
          || dlm === (record.name || "").toLowerCase()
          || dlm === (record.display_name || "").toLowerCase();
        // Debug logging for OpenAI specifically
        if (name === 'OpenAI' || name === 'ChatOpenAI' || providerIdentifier === 'openai') {
          console.log(`🔍 [Radio] ${name} (${providerIdentifier}): checked=${isChecked}, defaultLLM=${defaultLLM}, api_key_configured=${record.api_key_configured}`);
        }
        return (
          <Radio
            key={`radio-${providerIdentifier}-${defaultLLM}`}
            checked={isChecked}
            disabled={!record.api_key_configured}
            onClick={() => {
              if (record.api_key_configured && !isChecked) {
                handleDefaultLLMChange(name);
              }
            }}
          >
            {isChecked ? t("pages.settings.default") : ""}
          </Radio>
        );
      },
    },
    {
      title: t("pages.settings.actions"),
      key: "actions",
      width: 140,
      render: (_: any, record: LLMProvider) => {
        // Ollama specific actions
        if (isOllamaProvider(record)) {
          return (
            <Space>
              <Tooltip title={t("pages.settings.open_ollama")}>
                <Button
                  size="small"
                  type="text"
                  icon={<GlobalOutlined />}
                  onClick={() => window.open(getOllamaRootUrl(ollamaHost), '_blank')}
                  id={`${record.name}-open-host`}
                />
              </Tooltip>
              <Tooltip title={t("common.delete")}>
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  disabled
                />
              </Tooltip>
            </Space>
          );
        }

        // RyoAIS specific actions
        if (isRyoAISProvider(record)) {
          return (
            <Space>
              <Tooltip title={t("pages.settings.open_ryoais")}>
                <Button
                  size="small"
                  type="text"
                  icon={<GlobalOutlined />}
                  onClick={() => window.open(getRyoaisRootUrl(ryoaisHost), '_blank')}
                  id={`${record.name}-open-host`}
                />
              </Tooltip>
              <Tooltip title={t("common.delete")}>
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  disabled
                />
              </Tooltip>
            </Space>
          );
        }

        return (
          <Space>
            {!record.is_local && (
              <>
                <Tooltip title={t("pages.settings.open_docs")}>
                  <Button
                    size="small"
                    type="text"
                    icon={<GlobalOutlined />}
                    onClick={() => openDocumentation(record.documentation_url)}
                    disabled={!record.documentation_url}
                  />
                </Tooltip>
                <Tooltip title={t("common.delete")}>
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => deleteProviderConfig(record.name)}
                    disabled={!record.api_key_configured}
                  />
                </Tooltip>
              </>
            )}
            {record.is_local && (
              <span style={{ color: "#999", fontSize: "12px" }}>
                {t("pages.settings.local_service")}
              </span>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Table
        columns={columns}
        dataSource={providers}
        rowKey="name"
        loading={loading}
        pagination={false}
        size="small"
        scroll={{ y: 'calc(100vh - 280px)', x: 'max-content' }}
      />
    </div>
  );
});

LLMManagement.displayName = 'LLMManagement';

export default LLMManagement;

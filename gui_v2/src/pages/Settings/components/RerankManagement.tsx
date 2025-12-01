import React, { useState, useEffect, useMemo, useCallback, useImperativeHandle } from "react";
import {
  Table,
  Button,
  Input,
  Radio,
  Space,
  Tooltip,
  App,
  Select,
} from "antd";
import {
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  GlobalOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { get_ipc_api } from "../../../services/ipc_api";
import type { LLMProvider } from "../types";

interface RerankManagementProps {
  username: string | null;
  defaultRerank?: string; // Default Rerank passed from settings
  settingsLoaded?: boolean; // Flag indicating whether settings have been loaded
  onDefaultRerankChange?: (newDefaultRerank: string, newDefaultModel?: string) => void; // Callback to notify parent of default Rerank changes
  onSharedProviderUpdate?: (sharedProviders: Array<{ name: string; type: string }>) => void; // Callback to notify parent of shared provider updates
}

type ModelOption = { label: string; value: string; description?: string };

const RerankManagement = React.forwardRef<
  { loadProviders: () => Promise<void> },
  RerankManagementProps
>(({
  username,
  defaultRerank: propDefaultRerank,
  settingsLoaded,
  onDefaultRerankChange,
  onSharedProviderUpdate,
}, ref) => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();

  // State management
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [defaultRerank, setDefaultRerank] = useState<string>("");
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
  const [editingLoading, setEditingLoading] = useState<boolean>(false);

  // Load Rerank providers
  const loadProviders = useCallback(async () => {
    if (!username) return;

    setLoading(true);
    try {
      const response = await get_ipc_api().getRerankProviders<{
        providers: LLMProvider[];
      }>();
      if (response.success && response.data) {
        setProviders(response.data.providers);
        console.log("✅ Rerank providers loaded:", response.data.providers);
      } else {
        message.error(
          `${t("pages.settings.failed_to_load_providers")}: ${
            response.error?.message
          }`
        );
      }
    } catch (error) {
      console.error("Error loading Rerank providers:", error);
      message.error(t("pages.settings.failed_to_load_providers"));
    } finally {
      setLoading(false);
    }
  }, [username, t, message]);

  // Expose loadProviders method via ref
  useImperativeHandle(ref, () => ({
    loadProviders,
  }), [loadProviders]);

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

      // Update UI state immediately
      setCurrentModelSelections((prev) => ({
        ...prev,
        [providerName]: modelName,
      }));

      setModelLoadingMap((prev) => ({ ...prev, [providerName]: true }));

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

      try {
        const response = await get_ipc_api().setRerankProviderModel<{
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

  // Set default Rerank
  const handleDefaultRerankChange = async (providerName: string) => {
    // Find the provider to check its configuration status
    const provider = providers.find((p) => p.name === providerName);
    if (!provider) {
      message.error(`Provider ${providerName} not found`);
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

    // Use standard provider identifier for API calls
    const providerIdentifier = provider.provider;
    if (!providerIdentifier) {
      message.error(`Provider ${providerName} has no identifier`);
      return;
    }

    try {
      const response = await get_ipc_api().setDefaultRerank<{ message: string }>(
        providerIdentifier,  // Use standard identifier
        username || "",
        modelToUse
      );

      if (response.success) {
        setDefaultRerank(providerName);
        // Notify parent component to update settings - use providerIdentifier for consistency
        onDefaultRerankChange?.(providerIdentifier, modelToUse);
        message.success(
          `${t("pages.settings.default_rerank_set")}: ${providerName}`
        );
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
      console.error("Error setting default Rerank:", error);
      message.error(t("pages.settings.failed_to_set_default"));
    }
  };

  // Update provider configuration
  const updateProvider = async (
    name: string,  // This is provider.name (display name), need to convert to provider.provider
    apiKey: string,
    azureEndpoint?: string
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
      const response = await get_ipc_api().updateRerankProvider<{
        message: string;
        auto_set_as_default?: boolean;
        default_rerank?: string;
        default_rerank_model?: string;
        settings?: {
          default_rerank: string;
          default_rerank_model: string;
        };
        shared_providers?: Array<{ name: string; type: string }>;
      }>(providerIdentifier, apiKey, azureEndpoint);

      if (response.success) {
        const responseData = response.data;
        const autoSetAsDefault = responseData?.auto_set_as_default || false;
        
        // Show success message
        let successMessage = `${name} ${t("pages.settings.rerank_updated_successfully")}`;
        
        if (autoSetAsDefault && responseData?.default_rerank) {
          successMessage += ` - ${t("pages.settings.auto_set_as_default")}: ${responseData.default_rerank}`;
        }
        
        message.success(successMessage);
        
        // If auto-set as default, update local state
        if (autoSetAsDefault && responseData?.settings) {
          console.log('🔄 Auto-set as default after update:', responseData.settings);
          setDefaultRerank(responseData.settings.default_rerank);
          onDefaultRerankChange?.(
            responseData.settings.default_rerank, 
            responseData.settings.default_rerank_model
          );
        }
        
        await loadProviders(); // Reload data
        console.log("✅ Provider updated:", name);

        // Check for shared providers and notify parent to refresh other component
        if (responseData?.shared_providers && Array.isArray(responseData.shared_providers) && responseData.shared_providers.length > 0) {
          console.log("🔄 [Rerank] Found shared providers, notifying parent:", responseData.shared_providers);
          onSharedProviderUpdate?.(responseData.shared_providers);
        }
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

    // Check if this is the default Rerank (compare using provider identifier)
    const isDefault = providerIdentifier && (defaultRerank || "").toLowerCase() === (providerIdentifier || "").toLowerCase();
    
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
              ⚠️ {t("pages.settings.warning_default_rerank_deletion")}
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
          const response = await get_ipc_api().deleteRerankProviderConfig<{
            message: string;
            was_default_rerank?: boolean;
            new_default_rerank?: string;
            new_default_model?: string;
            deleted_env_vars?: string[];
            reset_to_default?: boolean;
            settings?: {
              default_rerank: string;
              default_rerank_model: string;
            };
            shared_providers?: Array<{ name: string; type: string }>;
          }>(providerIdentifier, username || "");

          if (response.success && response.data) {
            const responseData = response.data;
            const wasDefaultRerank = responseData.was_default_rerank || false;
            const newDefaultRerank = responseData.new_default_rerank;
            const resetToDefault = responseData.reset_to_default || false;

            // Show success message
            if (wasDefaultRerank && newDefaultRerank) {
              const resetMessage = resetToDefault 
                ? ` ${t("pages.settings.reset_to_default_provider")}`
                : ` Default Rerank changed to: ${newDefaultRerank}`;
              message.success(
                `${name} ${t("pages.settings.rerank_config_deleted")}.${resetMessage}`
              );
            } else {
              message.success(
                `${name} ${t("pages.settings.rerank_config_deleted")}`
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

            // If this was the default Rerank, update to new default
            if (wasDefaultRerank && newDefaultRerank) {
              setDefaultRerank(newDefaultRerank);
              // Notify parent component to update default_rerank in settings
              // Use settings from response if available for complete update
              if (responseData.settings) {
                console.log('🔄 Updating settings after deletion:', responseData.settings);
                onDefaultRerankChange?.(
                  responseData.settings.default_rerank, 
                  responseData.settings.default_rerank_model
                );
              } else {
                onDefaultRerankChange?.(newDefaultRerank, responseData.new_default_model);
              }
            } else {
              // Check if this was the default Rerank (compare using provider identifier)
              // providerIdentifier is already defined above
              if (providerIdentifier && (defaultRerank || "").toLowerCase() === (providerIdentifier || "").toLowerCase()) {
                // Fallback: if backend didn't return new_default_rerank but this was default
                setDefaultRerank("");
                onDefaultRerankChange?.("", "");
              }
            }

            // Reload providers from backend to verify the deletion and get updated state
            setTimeout(() => {
              loadProviders();
            }, 500);
            
            // Check for shared providers and notify parent to refresh other component
            if (responseData?.shared_providers && Array.isArray(responseData.shared_providers) && responseData.shared_providers.length > 0) {
              console.log("🔄 [Rerank] Found shared providers after deletion, notifying parent:", responseData.shared_providers);
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
        const response = await get_ipc_api().getRerankProviderApiKey<{
          api_key?: string;
          credentials?: any;
        }>(providerIdentifier, true);
        if (response.success && response.data) {
          // Handle special cases with multiple credentials
          if (providerName === "Azure OpenAI" && response.data.credentials) {
            setEditingValue(response.data.credentials.api_key || "");
            setEditingAzureEndpoint(
              response.data.credentials.azure_endpoint || ""
            );
          } else {
            setEditingValue(response.data.api_key || "");
            setEditingAzureEndpoint("");
          }
        } else {
          // If failed to get credentials, start with empty values
          setEditingValue("");
          setEditingAzureEndpoint("");
        }
      } catch (error) {
        console.error("Error fetching credentials for editing:", error);
        setEditingValue("");
        setEditingAzureEndpoint("");
      }
    } else {
      // If not configured, start with empty values
      setEditingValue("");
      setEditingAzureEndpoint("");
    }

    setEditingLoading(false);
  };

  const saveApiKey = async () => {
    if (editingProvider) {
      await updateProvider(
        editingProvider,
        editingValue,
        editingAzureEndpoint
      );
      setEditingProvider(null);
      setEditingValue("");
      setEditingAzureEndpoint("");
    }
  };

  const cancelEditing = () => {
    setEditingProvider(null);
    setEditingValue("");
    setEditingAzureEndpoint("");
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
        const response = await get_ipc_api().getRerankProviderApiKey<{
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

  // Update local state when passed defaultRerank changes
  useEffect(() => {
    console.log('🔄 [RerankManagement] propDefaultRerank changed:', propDefaultRerank);
    if (propDefaultRerank !== undefined) {
      setDefaultRerank(propDefaultRerank);
      console.log('✅ [RerankManagement] Local defaultRerank updated to:', propDefaultRerank);
    }
  }, [propDefaultRerank]);

  // Initialize loading - wait for settings to load before loading providers
  useEffect(() => {
    if (username && settingsLoaded) {
      loadProviders();
    }
  }, [username, settingsLoaded]);

  // If user is not logged in
  if (!username) {
    return (
      <div style={{ marginTop: "20px", border: "1px solid #f0f0f0", borderRadius: "8px", background: "#fff" }}>
        <div style={{ textAlign: "center", padding: "40px", color: "#999" }}>
          🔐 {t("pages.settings.login_to_view_rerank")}
        </div>
      </div>
    );
  }

  // Table column definitions
  const columns = [
    {
      title: t("pages.settings.rerank_provider"),
      dataIndex: "display_name",
      key: "display_name",
      width: 150,
    },
    {
      title: t("pages.settings.status"),
      dataIndex: "api_key_configured",
      key: "status",
      width: 100,
      render: (isConfigured: boolean) => (
        <span style={{ color: isConfigured ? "#52c41a" : "#ff4d4f" }}>
          {isConfigured
            ? `✅ ${t("pages.settings.configured")}`
            : `❌ ${t("pages.settings.not_configured")}`}
        </span>
      ),
    },
    {
      title: t("pages.settings.api_key"),
      dataIndex: "api_key",
      key: "api_key",
      width: 280,
      render: (_: any, record: LLMProvider) => {
        const isEditing = editingProvider === record.name;

        if (isEditing) {
          return (
            <Space direction="vertical" style={{ width: "100%" }}>
              {/* Azure OpenAI specific fields */}
              {record.name === "Azure OpenAI" && (
                <>
                  <Input
                    value={editingAzureEndpoint}
                    onChange={(e) => setEditingAzureEndpoint(e.target.value)}
                    placeholder={
                      editingLoading
                        ? "Loading current Azure endpoint..."
                        : "Enter Azure endpoint (https://your-resource.openai.azure.com)"
                    }
                    style={{ width: "350px" }}
                    disabled={editingLoading}
                  />
                  <Input
                    value={editingValue}
                    onChange={(e) => setEditingValue(e.target.value)}
                    placeholder={
                      editingLoading
                        ? "Loading current API key..."
                        : "Enter Azure OpenAI API key"
                    }
                    style={{ width: "350px" }}
                    disabled={editingLoading}
                  />
                </>
              )}

              {/* Standard single API key field for other providers */}
              {record.name !== "Azure OpenAI" && (
                <Input
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  placeholder={
                    editingLoading
                      ? "Loading current API key..."
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
          ? "🏠 Local Service"
          : record.api_key_configured
          ? visibleApiKeys.has(record.name)
            ? apiKeyValues.get(record.name) || "••••••••••••••••"
            : "••••••••••••••••"
          : t("pages.settings.not_configured");

        return (
          <Space style={{ width: '100%', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <span style={{ 
              fontFamily: "monospace",
              wordBreak: 'break-all',
              whiteSpace: 'pre-wrap',
              lineHeight: 1.4
            }}>
              {apiKeyText}
            </span>
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
      title: t("pages.settings.rerank_model"),
      key: "model",
      width: 200,
      render: (_: any, record: LLMProvider) => {
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

        return (
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
        );
      },
    },
    {
      title: t("pages.settings.default"),
      dataIndex: "name",
      key: "default",
      width: 80,
      render: (name: string, record: LLMProvider) => {
        // Compare using provider identifier (canonical), not display name
        const providerIdentifier = record.provider;
        const isChecked = (defaultRerank || "").toLowerCase() === (providerIdentifier || "").toLowerCase();
        return (
          <Radio
            key={`radio-${providerIdentifier}-${defaultRerank}`}
            checked={isChecked}
            disabled={!record.api_key_configured}
            onClick={() => {
              if (record.api_key_configured && !isChecked) {
                handleDefaultRerankChange(name);
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
      width: "15%",
      render: (_: any, record: LLMProvider) => (
        <Space>
          {!record.is_local && (
            <>
              <Tooltip title={t("common.edit")}>
                <Button
                  size="small"
                  type="text"
                  icon={<EditOutlined />}
                  onClick={() => startEditing(record.name)}
                />
              </Tooltip>
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
                  icon={<DeleteOutlined style={{ color: "#ff4d4f" }} />}
                  style={{ color: "#ff4d4f" }}
                  onClick={() => deleteProviderConfig(record.name)}
                  disabled={!record.api_key_configured}
                />
              </Tooltip>
            </>
          )}
          {record.is_local && (
            <span style={{ color: "#999", fontSize: "12px" }}>
              Local Service
            </span>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", paddingTop: 16 }}>
      <Table
        columns={columns}
        dataSource={providers}
        rowKey="name"
        loading={loading}
        pagination={false}
        size="small"
        sticky={true}
        scroll={{ y: 'calc(100vh - 280px)', x: undefined }}
      />
    </div>
  );
});

RerankManagement.displayName = 'RerankManagement';

export default RerankManagement;


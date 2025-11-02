import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  Card,
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

interface LLMManagementProps {
  username: string | null;
  defaultLLM?: string; // Default LLM passed from settings
  settingsLoaded?: boolean; // Flag indicating whether settings have been loaded
  onDefaultLLMChange?: (newDefaultLLM: string) => void; // Callback to notify parent of default LLM changes
}

type ModelOption = { label: string; value: string; description?: string };

const LLMManagement: React.FC<LLMManagementProps> = ({
  username,
  defaultLLM: propDefaultLLM,
  settingsLoaded,
  onDefaultLLMChange,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();

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

  // Load LLM providers
  const loadProviders = async () => {
    if (!username) return;

    setLoading(true);
    try {
      const response = await get_ipc_api().getLLMProviders<{
        providers: LLMProvider[];
      }>();
      if (response.success && response.data) {
        setProviders(response.data.providers);
        console.log("✅ LLM providers loaded:", response.data.providers);
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
  };

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

      // Update UI state immediately
      setCurrentModelSelections((prev) => ({
        ...prev,
        [providerName]: modelName,
      }));

      setModelLoadingMap((prev) => ({ ...prev, [providerName]: true }));

      try {
        const response = await get_ipc_api().setLLMProviderModel<{
          message: string;
        }>(providerName, modelName);
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
    [message, t]
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

  // Set default LLM
  const handleDefaultLLMChange = async (providerName: string) => {
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

    try {
      const response = await get_ipc_api().setDefaultLLM<{ message: string }>(
        providerName,
        username || "",
        modelToUse
      );

      if (response.success) {
        setDefaultLLM(providerName);
        // Notify parent component to update settings
        onDefaultLLMChange?.(providerName);
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
    name: string,
    apiKey: string,
    azureEndpoint?: string,
    awsAccessKeyId?: string,
    awsSecretAccessKey?: string
  ) => {
    try {
      const response = await get_ipc_api().updateLLMProvider<{
        message: string;
      }>(name, apiKey, azureEndpoint, awsAccessKeyId, awsSecretAccessKey);

      if (response.success) {
        message.success(
          `${name} ${t("pages.settings.llm_updated_successfully")} - ${t(
            "pages.settings.hot_updated"
          )}`
        );
        await loadProviders(); // Reload data
        console.log("✅ Provider updated:", name);

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
  const deleteProviderConfig = async (name: string) => {
    try {
      const response = await get_ipc_api().deleteLLMProviderConfig<{
        message: string;
      }>(name, username || "");

      if (response.success) {
        message.success(
          `${name} ${t("pages.settings.llm_config_deleted")} - ${t(
            "pages.settings.hot_updated"
          )}`
        );

        // No restart required - changes take effect immediately

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

        // If this was the default LLM, clear it
        if (defaultLLM === name) {
          setDefaultLLM("");
          // Notify parent component to clear default_llm in settings
          onDefaultLLMChange?.("");
        }

        // Reload providers from backend to verify the deletion
        setTimeout(() => {
          loadProviders();
        }, 500);
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
  };

  // API key editing related functions
  const startEditing = async (providerName: string) => {
    // Find the provider to check if it's configured
    const provider = providers.find((p) => p.name === providerName);
    if (!provider) {
      message.error(`Provider ${providerName} not found`);
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
        }>(providerName, true);
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
        }>(providerName, true);

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
    if (propDefaultLLM !== undefined) {
      setDefaultLLM(propDefaultLLM);
    }
  }, [propDefaultLLM]);

  // Initialize loading - wait for settings to load before loading providers
  useEffect(() => {
    if (username && settingsLoaded) {
      loadProviders();
      // No longer call loadDefaultLLM() as defaultLLM is passed from Settings page
    }
  }, [username, settingsLoaded]);

  // If user is not logged in
  if (!username) {
    return (
      <Card
        title={t("pages.settings.llm_management")}
        style={{ marginTop: "20px" }}
      >
        <div style={{ textAlign: "center", padding: "40px", color: "#999" }}>
          🔐 {t("pages.settings.login_to_view_llm")}
        </div>
      </Card>
    );
  }

  // Table column definitions
  const columns = [
    {
      title: t("pages.settings.llm_provider"),
      dataIndex: "display_name",
      key: "display_name",
      width: "20%",
    },
    {
      title: t("pages.settings.status"),
      dataIndex: "api_key_configured",
      key: "status",
      width: "15%",
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
      width: "35%",
      render: (_: any, record: LLMProvider) => {
        const isEditing = editingProvider === record.name;

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

              {/* AWS Bedrock specific fields */}
              {record.name === "ChatBedrockConverse" && (
                <>
                  <Input
                    value={editingAwsAccessKeyId}
                    onChange={(e) => setEditingAwsAccessKeyId(e.target.value)}
                    placeholder={
                      editingLoading
                        ? "Loading current AWS Access Key ID..."
                        : "Enter AWS Access Key ID"
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
                        ? "Loading current AWS Secret Access Key..."
                        : "Enter AWS Secret Access Key"
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

        return (
          <Space>
            <span style={{ fontFamily: "monospace" }}>
              {record.is_local
                ? "🏠 Local Service"
                : record.api_key_configured
                ? visibleApiKeys.has(record.name)
                  ? apiKeyValues.get(record.name) || "••••••••••••••••"
                  : "••••••••••••••••"
                : t("pages.settings.not_configured")}
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
      title: t("pages.settings.llm_model"),
      key: "model",
      width: "20%",
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
            style={{ minWidth: 220 }}
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
      width: "15%",
      render: (name: string, record: LLMProvider) => (
        <Radio
          checked={defaultLLM === name}
          disabled={!record.api_key_configured}
          onClick={() => {
            if (record.api_key_configured && defaultLLM !== name) {
              handleDefaultLLMChange(name);
            }
          }}
        >
          {defaultLLM === name ? t("pages.settings.default") : ""}
        </Radio>
      ),
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
    <Card
      title={t("pages.settings.llm_management")}
      style={{ marginTop: "20px" }}
    >
      <Table
        columns={columns}
        dataSource={providers}
        rowKey="name"
        loading={loading}
        pagination={false}
        size="small"
      />
    </Card>
  );
};

export default LLMManagement;

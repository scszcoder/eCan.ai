import React, { useEffect, useState, useCallback } from 'react';
import { Select, Button, Divider, message, Modal, Space, Tooltip, Checkbox } from 'antd';
import { 
  AmazonOutlined, 
  ShoppingCartOutlined, 
  SaveOutlined, 
  EyeOutlined,
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CaretRightOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { useLabelConfigStore, LabelConfig, ConfigSource } from '../../stores/labelConfigStore';
import LabelPreview from './LabelPreview';
import ConfigPanel from './ConfigPanel';

const PageContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px;
  background: var(--bg-primary, #0f172a);
  overflow: hidden;
`;

const TitleRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
`;

const Title = styled.h1`
  font-size: 20px;
  font-weight: 600;
  color: #f8fafc;
  margin: 0;
`;

const ConfigName = styled.span`
  font-size: 14px;
  color: #94a3b8;
  margin-left: 12px;
  font-weight: 400;
`;

const SelectRow = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
`;

const RefreshButton = styled(Button)`
  &.ant-btn {
    background: transparent !important;
    border: 1px solid #334155 !important;
    color: rgba(203, 213, 225, 0.9) !important;
    
    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
      color: rgba(248, 250, 252, 0.95) !important;
      border-color: #475569 !important;
    }
  }
`;

const StyledSelect = styled(Select)`
  width: 400px;
  
  .ant-select-selector {
    background: var(--bg-secondary, #1e293b) !important;
    border-color: #334155 !important;
  }
  
  .ant-select-selection-item {
    color: #f8fafc !important;
  }
`;

const ContentRow = styled.div`
  display: flex;
  flex: 1;
  gap: 20px;
  min-height: 0;
  overflow: hidden;
`;

const PreviewPanel = styled.div`
  flex: 2;
  display: flex;
  flex-direction: column;
  min-width: 0;
`;

const ConfigPanelWrapper = styled.div`
  flex: 1;
  min-width: 280px;
  max-width: 320px;
  display: flex;
  flex-direction: column;
`;

const PreviewContent = styled.div`
  flex: 1;
  min-height: 0;
`;

const ActionRow = styled.div`
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #334155;
`;

const ShopButton = styled(Button)`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const EbayIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path d="M5.939 14.127c0 1.086-.527 2.088-2.062 2.088-1.074 0-1.817-.586-1.817-1.672 0-1.074.73-1.66 1.817-1.66 1.535 0 2.062 1.002 2.062 1.244zm-2.062-2.916c-2.051 0-3.66 1.086-3.66 2.916 0 1.818 1.609 2.904 3.66 2.904 2.051 0 3.66-1.086 3.66-2.904 0-1.83-1.609-2.916-3.66-2.916zm5.936 2.916c0 1.086.527 2.088 2.062 2.088 1.074 0 1.817-.586 1.817-1.672 0-1.074-.73-1.66-1.817-1.66-1.535 0-2.062 1.002-2.062 1.244zm2.062-2.916c-2.051 0-3.66 1.086-3.66 2.916 0 1.818 1.609 2.904 3.66 2.904 2.051 0 3.66-1.086 3.66-2.904 0-1.83-1.609-2.916-3.66-2.916zm8.186 2.916c0 1.086-.527 2.088-2.062 2.088-1.074 0-1.817-.586-1.817-1.672 0-1.074.73-1.66 1.817-1.66 1.535 0 2.062 1.002 2.062 1.244zm-2.062-2.916c-2.051 0-3.66 1.086-3.66 2.916 0 1.818 1.609 2.904 3.66 2.904 2.051 0 3.66-1.086 3.66-2.904 0-1.83-1.609-2.916-3.66-2.916z"/>
  </svg>
);

const ShippingLabel: React.FC = () => {
  const {
    systemConfigs,
    userConfigs,
    selectedConfig,
    selectedSource,
    isCustomMode,
    customConfig,
    loading,
    defaultConfigId,
    fetchConfigs,
    forceRefresh,
    selectConfig,
    enterCustomMode,
    updateCustomConfig,
    saveCustomConfig,
    deleteUserConfig,
    checkNameExists,
    setDefaultConfig,
  } = useLabelConfigStore();

  const [previewConfig, setPreviewConfig] = useState<LabelConfig | null>(null);

  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  useEffect(() => {
    if (isCustomMode) {
      setPreviewConfig(customConfig);
    } else if (selectedConfig) {
      setPreviewConfig(selectedConfig);
    }
  }, [selectedConfig, isCustomMode, customConfig]);

  const handleSelectChange = useCallback((value: string) => {
    if (value === 'custom') {
      enterCustomMode();
      return;
    }

    // Find config in system or user configs
    const systemConfig = systemConfigs.find(c => c.id === value);
    if (systemConfig) {
      selectConfig(systemConfig, 'system');
      return;
    }

    const userConfig = userConfigs.find(c => c.id === value);
    if (userConfig) {
      selectConfig(userConfig, 'user');
    }
  }, [systemConfigs, userConfigs, selectConfig, enterCustomMode]);

  const handleConfigChange = useCallback((field: keyof LabelConfig, value: any) => {
    updateCustomConfig({ [field]: value });
  }, [updateCustomConfig]);

  const handlePreview = useCallback(() => {
    setPreviewConfig({ ...customConfig });
    message.success('Preview updated');
  }, [customConfig]);

  const handleSave = useCallback(async () => {
    if (!customConfig.name || !customConfig.name.trim()) {
      message.error('Please enter a configuration name');
      return;
    }

    // Check for duplicate name
    const exists = await checkNameExists(customConfig.name);
    if (exists) {
      Modal.confirm({
        title: 'Name Already Exists',
        content: `A configuration named "${customConfig.name}" already exists. Do you want to overwrite it?`,
        okText: 'Overwrite',
        cancelText: 'Cancel',
        onOk: async () => {
          const result = await saveCustomConfig(true);
          if (result.success) {
            message.success('Configuration saved successfully');
          } else {
            message.error(result.error || 'Failed to save configuration');
          }
        },
      });
      return;
    }

    const result = await saveCustomConfig();
    if (result.success) {
      message.success('Configuration saved successfully');
    } else {
      message.error(result.error || 'Failed to save configuration');
    }
  }, [customConfig, checkNameExists, saveCustomConfig]);

  const handleDelete = useCallback(async (id: string, name: string) => {
    Modal.confirm({
      title: 'Delete Configuration',
      content: `Are you sure you want to delete "${name}"?`,
      okText: 'Delete',
      okButtonProps: { danger: true },
      cancelText: 'Cancel',
      onOk: async () => {
        const result = await deleteUserConfig(id);
        if (result.success) {
          message.success('Configuration deleted');
        } else {
          message.error(result.error || 'Failed to delete configuration');
        }
      },
    });
  }, [deleteUserConfig]);

  const handleAmazonSearch = useCallback(() => {
    if (!selectedConfig) return;
    const searchTerm = encodeURIComponent(`${selectedConfig.name} shipping labels`);
    window.open(`https://www.amazon.com/s?k=${searchTerm}`, '_blank');
  }, [selectedConfig]);

  const handleEbaySearch = useCallback(() => {
    if (!selectedConfig) return;
    const searchTerm = encodeURIComponent(`${selectedConfig.name} shipping labels`);
    window.open(`https://www.ebay.com/sch/i.html?_nkw=${searchTerm}`, '_blank');
  }, [selectedConfig]);

  const currentValue = isCustomMode ? 'custom' : selectedConfig?.id;
  const displayConfig = isCustomMode ? customConfig : selectedConfig;
  const isEditable = isCustomMode;

  const isDefault = selectedConfig?.id === defaultConfigId;

  const handleSetDefault = useCallback(() => {
    if (selectedConfig && !isCustomMode) {
      setDefaultConfig(selectedConfig.id);
      message.success(`"${selectedConfig.name}" set as default`);
    }
  }, [selectedConfig, isCustomMode, setDefaultConfig]);

  // Build select options with dividers (flat list)
  const selectOptions = [
    // System configs
    ...systemConfigs.map(c => ({
      value: c.id,
      label: (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {c.id === defaultConfigId && (
            <CaretRightOutlined style={{ color: '#ef4444', fontSize: 12 }} />
          )}
          <span style={{ fontWeight: c.id === defaultConfigId ? 700 : 400 }}>{c.name}</span>
        </div>
      ),
    })),
    // Divider after system configs (if there are system configs)
    ...(systemConfigs.length > 0 ? [{
      value: '__divider_1__',
      label: <Divider style={{ margin: '4px 0', borderColor: '#334155' }} />,
      disabled: true,
      className: 'select-divider',
    }] : []),
    // User configs
    ...userConfigs.map(c => ({
      value: c.id,
      label: (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {c.id === defaultConfigId && (
              <CaretRightOutlined style={{ color: '#ef4444', fontSize: 12 }} />
            )}
            <span style={{ fontWeight: c.id === defaultConfigId ? 700 : 400 }}>{c.name}</span>
          </div>
          <Tooltip title="Delete">
            <DeleteOutlined 
              style={{ color: '#ef4444', fontSize: 12 }}
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(c.id, c.name);
              }}
            />
          </Tooltip>
        </div>
      ),
    })),
    // Divider before custom option
    {
      value: '__divider_2__',
      label: <Divider style={{ margin: '4px 0', borderColor: '#334155' }} />,
      disabled: true,
      className: 'select-divider',
    },
    // Custom option
    {
      value: 'custom',
      label: (
        <span style={{ color: '#3b82f6' }}>
          <PlusOutlined style={{ marginRight: 8 }} />
          Custom Configuration
        </span>
      ),
    },
  ];

  return (
    <PageContainer>
      <TitleRow>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Title>Shipping Label Configuration</Title>
          {displayConfig && !isCustomMode && (
            <ConfigName>— {displayConfig.name}</ConfigName>
          )}
          {isCustomMode && (
            <ConfigName style={{ color: '#3b82f6' }}>— Creating Custom Configuration</ConfigName>
          )}
        </div>
      </TitleRow>

      <SelectRow>
        <StyledSelect
          value={currentValue}
          onChange={handleSelectChange}
          loading={loading}
          placeholder="Select a label configuration"
          options={selectOptions}
          optionFilterProp="label"
          showSearch
        />
        <Tooltip title="Refresh configurations">
          <RefreshButton
            icon={<ReloadOutlined spin={loading} />}
            onClick={() => forceRefresh()}
            loading={loading}
          />
        </Tooltip>
        {!isCustomMode && selectedConfig && (
          <Checkbox
            checked={isDefault}
            onChange={handleSetDefault}
            disabled={isDefault}
            style={{ color: '#f8fafc', marginLeft: 8 }}
          >
            <span style={{ color: '#f8fafc' }}>Default</span>
          </Checkbox>
        )}
      </SelectRow>

      <ContentRow>
        <PreviewPanel>
          <PreviewContent>
            <LabelPreview config={previewConfig} maxWidth={500} maxHeight={550} />
          </PreviewContent>
          
          <ActionRow>
            {isCustomMode ? (
              <>
                <Button 
                  type="default" 
                  icon={<EyeOutlined />}
                  onClick={handlePreview}
                >
                  Preview
                </Button>
                <Button 
                  type="primary" 
                  icon={<SaveOutlined />}
                  onClick={handleSave}
                >
                  Save Configuration
                </Button>
              </>
            ) : selectedConfig && selectedSource !== 'custom' ? (
              <>
                <ShopButton 
                  type="default"
                  onClick={handleAmazonSearch}
                >
                  <AmazonOutlined style={{ fontSize: 18 }} />
                  Buy on Amazon
                </ShopButton>
                <ShopButton 
                  type="default"
                  onClick={handleEbaySearch}
                >
                  <EbayIcon />
                  Buy on eBay
                </ShopButton>
              </>
            ) : null}
          </ActionRow>
        </PreviewPanel>

        <ConfigPanelWrapper>
          <ConfigPanel
            config={displayConfig}
            isEditable={isEditable}
            onChange={handleConfigChange}
          />
        </ConfigPanelWrapper>
      </ContentRow>
    </PageContainer>
  );
};

export default ShippingLabel;

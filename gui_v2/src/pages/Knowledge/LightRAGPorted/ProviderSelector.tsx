import React from 'react';
import { Select, Input, Checkbox, Card, theme, Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ProviderConfig, ProviderFieldConfig } from './providerConfig';

interface ProviderSelectorProps {
  bindingKey: string;
  providers: ProviderConfig[];
  commonFields?: ProviderFieldConfig[];
  settings: Record<string, string>;
  onSettingChange: (key: string, value: string) => void;
}

const ProviderSelector: React.FC<ProviderSelectorProps> = ({
  bindingKey,
  providers,
  commonFields = [],
  settings,
  onSettingChange
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  
  const currentProviderId = settings[bindingKey] || providers[0]?.id || '';
  const currentProvider = providers.find(p => p.id === currentProviderId);

  const renderField = (field: ProviderFieldConfig) => {
    const value = settings[field.key] || field.defaultValue || '';
    // Translate placeholder only for select type with matching option values
    const placeholder = field.placeholder 
      ? (field.type === 'select' && field.options?.some(opt => opt.value === field.placeholder)
          ? t(`pages.knowledge.settings.placeholders.${field.placeholder}`)
          : field.placeholder)
      : '';
    const hasTooltip = !!field.tooltip;
    
    // Try to translate label if it looks like an i18n key (contains '.')
    const labelText = field.label 
      ? (field.label.includes('.') ? t(`pages.knowledge.settings.${field.label}`) : field.label)
      : field.key;
    
    const label = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 6 }}>
        <span style={{ fontWeight: 500, fontSize: 13, color: token.colorText }}>
          {labelText}
          {field.required && <span style={{ color: token.colorError, marginLeft: 2 }}>*</span>}
        </span>
        {hasTooltip && (
          <Tooltip title={t(`pages.knowledge.settings.${field.tooltip}`)} placement="top">
            <QuestionCircleOutlined style={{ fontSize: 12, color: token.colorTextSecondary, cursor: 'help' }} />
          </Tooltip>
        )}
      </div>
    );

    const commonStyle = { width: '100%' };

    switch (field.type) {
      case 'text':
      case 'password':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Input
              type={field.type}
              value={value}
              placeholder={placeholder}
              onChange={(e) => onSettingChange(field.key, e.target.value)}
              style={commonStyle}
              size="small"
            />
          </div>
        );
      
      case 'number':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Input
              type="number"
              value={value}
              placeholder={placeholder}
              onChange={(e) => onSettingChange(field.key, e.target.value)}
              style={commonStyle}
              size="small"
            />
          </div>
        );
      
      case 'textarea':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Input.TextArea
              value={value}
              placeholder={placeholder}
              onChange={(e) => onSettingChange(field.key, e.target.value)}
              rows={2}
              style={commonStyle}
              size="small"
            />
          </div>
        );
      
      case 'select':
        // Translate option labels if they are i18n keys
        const translatedOptions = field.options?.map(opt => ({
          value: opt.value,
          label: opt.label.includes('.') 
            ? t(`pages.knowledge.settings.${opt.label}`)
            : opt.label
        }));
        
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            {label}
            <Select
              value={value || undefined}
              placeholder={placeholder}
              onChange={(val) => onSettingChange(field.key, val)}
              style={commonStyle}
              options={translatedOptions}
              size="small"
            />
          </div>
        );
      
      case 'boolean':
        return (
          <div key={field.key} style={{ marginBottom: 12 }}>
            <Checkbox
              checked={value === 'true' || value === 'True'}
              onChange={(e) => onSettingChange(field.key, e.target.checked ? 'true' : 'false')}
            >
              <span style={{ marginLeft: 8, fontSize: 13 }}>{labelText}</span>
              {hasTooltip && (
                <Tooltip title={t(`pages.knowledge.settings.${field.tooltip}`)} placement="top">
                  <QuestionCircleOutlined style={{ marginLeft: 4, color: token.colorTextSecondary, cursor: 'help' }} />
                </Tooltip>
              )}
            </Checkbox>
          </div>
        );
      
      default:
        return null;
    }
  };

  return (
    <div style={{ padding: '16px 0' }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ marginBottom: 6 }}>
          <span style={{ fontWeight: 600, fontSize: 14, color: token.colorText }}>
            {t('pages.knowledge.settings.provider.selectProvider')}
          </span>
        </div>
        <Select
          value={currentProviderId}
          onChange={(val) => onSettingChange(bindingKey, val)}
          style={{ width: '100%' }}
          size="middle"
          optionLabelProp="label"
        >
          {providers.map(p => {
            // Translate provider name if it's an i18n key
            const providerName = p.name.includes('.') 
              ? t(`pages.knowledge.settings.${p.name}`)
              : p.name;
            
            return (
              <Select.Option key={p.id} value={p.id} label={providerName}>
                <div>
                  <div style={{ fontWeight: 500 }}>{providerName}</div>
                  {p.description && (
                    <div style={{ fontSize: 12, color: token.colorTextSecondary }}>{p.description}</div>
                  )}
                </div>
              </Select.Option>
            );
          })}
        </Select>
      </div>

      {currentProvider && currentProvider.fields.length > 0 && (
        <Card
          size="small"
          title={`${currentProvider.name.includes('.') ? t(`pages.knowledge.settings.${currentProvider.name}`) : currentProvider.name} ${t('pages.knowledge.settings.provider.configuration')}`}
          style={{
            marginBottom: 20,
            borderColor: token.colorBorder
          }}
        >
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 12
          }}>
            {currentProvider.fields.map(field => renderField(field))}
          </div>
        </Card>
      )}

      {commonFields.length > 0 && (
        <Card
          size="small"
          title={t('pages.knowledge.settings.provider.commonSettings')}
          style={{
            borderColor: token.colorBorder
          }}
        >
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 12
          }}>
            {commonFields.map(field => renderField(field))}
          </div>
        </Card>
      )}
    </div>
  );
};

export default ProviderSelector;

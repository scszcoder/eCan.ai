import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import MappingEditor, { type MappingConfig } from './MappingEditor';
import { Collapse, Typography, TextArea, Button, Toast } from '@douyinfe/semi-ui';

const { Title, Text } = Typography;

export interface SkillLevelMappingConfig {
  developing: MappingConfig;
  released: MappingConfig;
  event_data_mapping?: Record<string, any>;
}

export function SkillLevelMappingEditor(props: {
  value?: SkillLevelMappingConfig | null;
  onChange?: (cfg: SkillLevelMappingConfig) => void;
}) {
  const { t } = useTranslation('skillEditor');
  const config = props.value || {
    developing: { mappings: [], options: { strict: false, apply_order: 'top_down' } },
    released: { mappings: [], options: { strict: true, apply_order: 'top_down' } },
    event_data_mapping: {},
  };

  const [edmText, setEdmText] = useState(() =>
    JSON.stringify(config.event_data_mapping || {}, null, 2)
  );
  const [edmError, setEdmError] = useState<string | null>(null);

  const handleDevelopingChange = useCallback((dev: MappingConfig) => {
    props.onChange?.({ ...config, developing: dev });
  }, [config, props.onChange]);

  const handleReleasedChange = useCallback((rel: MappingConfig) => {
    props.onChange?.({ ...config, released: rel });
  }, [config, props.onChange]);

  const handleEdmApply = useCallback(() => {
    try {
      const parsed = JSON.parse(edmText);
      if (typeof parsed !== 'object' || Array.isArray(parsed)) {
        setEdmError(t('mapping.mustBeJsonObject'));
        return;
      }
      setEdmError(null);
      props.onChange?.({ ...config, event_data_mapping: parsed });
      Toast.success(t('mapping.eventDataMappingUpdated'));
    } catch (e: any) {
      setEdmError(e.message || t('mapping.invalidJson'));
    }
  }, [edmText, config, props.onChange]);

  return (
    <div style={{ padding: '8px 0' }}>
      <Title heading={6} style={{ marginBottom: 12 }}>{t('mapping.skillLevelMappingRules')}</Title>
      <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 16 }}>
        {t('mapping.skillLevelMappingDesc')}
      </Text>
      
      <Collapse defaultActiveKey={['dev']} accordion={false}>
        <Collapse.Panel header={t('mapping.developmentModeMappings')} itemKey="dev">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              {t('mapping.developmentModeDesc')}
            </Text>
            <MappingEditor 
              value={config.developing}
              onChange={handleDevelopingChange}
            />
          </div>
        </Collapse.Panel>
        
        <Collapse.Panel header={t('mapping.releasedModeMappings')} itemKey="rel">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              {t('mapping.releasedModeDesc')}
            </Text>
            <MappingEditor 
              value={config.released}
              onChange={handleReleasedChange}
            />
          </div>
        </Collapse.Panel>

        <Collapse.Panel header={t('mapping.eventDataMapping')} itemKey="edm">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              {t('mapping.eventDataMappingDesc')}
            </Text>
            <TextArea
              value={edmText}
              onChange={(v) => { setEdmText(v); setEdmError(null); }}
              autosize={{ minRows: 4, maxRows: 16 }}
              placeholder='{ "passive_command": { "adapt_to_state": { "actions": "state.attributes.passive_command_actions" } } }'
              style={{ fontFamily: 'monospace', fontSize: 12 }}
            />
            {edmError && (
              <Text type="danger" size="small" style={{ display: 'block', marginTop: 4 }}>
                {edmError}
              </Text>
            )}
            <Button size="small" theme="solid" style={{ marginTop: 8 }} onClick={handleEdmApply}>
              {t('mapping.apply')}
            </Button>
          </div>
        </Collapse.Panel>

        <Collapse.Panel header={t('mapping.eventRouting')} itemKey="routing">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              {t('mapping.eventRoutingDesc')}
            </Text>
          </div>
        </Collapse.Panel>
      </Collapse>
    </div>
  );
}

export default SkillLevelMappingEditor;

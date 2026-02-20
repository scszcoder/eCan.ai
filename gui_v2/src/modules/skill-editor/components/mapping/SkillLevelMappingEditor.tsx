import React, { useCallback, useState } from 'react';
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
        setEdmError('Must be a JSON object');
        return;
      }
      setEdmError(null);
      props.onChange?.({ ...config, event_data_mapping: parsed });
      Toast.success('Event data mapping updated');
    } catch (e: any) {
      setEdmError(e.message || 'Invalid JSON');
    }
  }, [edmText, config, props.onChange]);

  return (
    <div style={{ padding: '8px 0' }}>
      <Title heading={6} style={{ marginBottom: 12 }}>Skill-Level Mapping Rules</Title>
      <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 16 }}>
        These rules apply to the entire skill and control event-to-state data mapping.
      </Text>
      
      <Collapse defaultActiveKey={['dev']} accordion={false}>
        <Collapse.Panel header="Development Mode Mappings" itemKey="dev">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              Mapping rules used when skill run_mode = "developing" (includes debug metadata)
            </Text>
            <MappingEditor 
              value={config.developing}
              onChange={handleDevelopingChange}
            />
          </div>
        </Collapse.Panel>
        
        <Collapse.Panel header="Released Mode Mappings" itemKey="rel">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              Mapping rules used when skill run_mode = "released" (production optimized)
            </Text>
            <MappingEditor 
              value={config.released}
              onChange={handleReleasedChange}
            />
          </div>
        </Collapse.Panel>

        <Collapse.Panel header="Event Data Mapping (adapt_to_state)" itemKey="edm">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              Per-skill config that maps event payload fields into the resuming node's state
              when a pending event arrives. Each key is an event type (e.g. "passive_command"),
              and the value contains an <code>adapt_to_state</code> object mapping source fields
              to target state paths.
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
              Apply
            </Button>
          </div>
        </Collapse.Panel>

        <Collapse.Panel header="Event Routing (Info)" itemKey="routing">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
              Event-to-task routing is now managed at the agent level via <code>event_routing.json</code>,
              not per-skill. When a task starts, the runner automatically detects pend_event nodes
              in the skill and registers the required event routes globally.
            </Text>
          </div>
        </Collapse.Panel>
      </Collapse>
    </div>
  );
}

export default SkillLevelMappingEditor;

import React, { useCallback } from 'react';
import MappingEditor, { type MappingConfig } from './MappingEditor';
import { Collapse, Typography, Input, Button, Space } from '@douyinfe/semi-ui';
import { IconPlus, IconDelete } from '@douyinfe/semi-icons';

const { Title, Text } = Typography;

export interface EventRoutingRule {
  task_selector: string;
  queue?: string;
}

export interface SkillLevelMappingConfig {
  developing: MappingConfig;
  released: MappingConfig;
  event_routing?: {
    [eventType: string]: EventRoutingRule;
  };
}

export function SkillLevelMappingEditor(props: {
  value?: SkillLevelMappingConfig | null;
  onChange?: (cfg: SkillLevelMappingConfig) => void;
}) {
  const config = props.value || {
    developing: { mappings: [], options: { strict: false, apply_order: 'top_down' } },
    released: { mappings: [], options: { strict: true, apply_order: 'top_down' } },
    event_routing: {}
  };

  const handleDevelopingChange = useCallback((dev: MappingConfig) => {
    props.onChange?.({ ...config, developing: dev });
  }, [config, props.onChange]);

  const handleReleasedChange = useCallback((rel: MappingConfig) => {
    props.onChange?.({ ...config, released: rel });
  }, [config, props.onChange]);

  const handleEventRoutingChange = useCallback((eventType: string, rule: EventRoutingRule | null) => {
    const newRouting = { ...(config.event_routing || {}) };
    if (rule === null) {
      delete newRouting[eventType];
    } else {
      newRouting[eventType] = rule;
    }
    props.onChange?.({ ...config, event_routing: newRouting });
  }, [config, props.onChange]);

  const addEventRoute = useCallback(() => {
    const newType = `custom_event_${Date.now()}`;
    handleEventRoutingChange(newType, { task_selector: 'name_contains:', queue: 'custom_queue' });
  }, [handleEventRoutingChange]);

  return (
    <div style={{ padding: '8px 0' }}>
      <Title heading={6} style={{ marginBottom: 12 }}>Skill-Level Mapping Rules</Title>
      <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 16 }}>
        These rules apply to the entire skill and control event-to-state mapping and event routing.
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
        
        <Collapse.Panel header="Event Routing" itemKey="routing">
          <div style={{ padding: '8px 0' }}>
            <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 12 }}>
              Define which events should trigger this skill and how they're routed to task queues.
            </Text>
            
            {Object.entries(config.event_routing || {}).map(([eventType, rule]) => (
              <div key={eventType} style={{ 
                marginBottom: 12, 
                padding: 12, 
                border: '1px solid #e0e0e0', 
                borderRadius: 6,
                background: '#fafafa'
              }}>
                <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                  <Text strong>{eventType}</Text>
                  <Button 
                    icon={<IconDelete />} 
                    type="danger" 
                    theme="borderless" 
                    size="small"
                    onClick={() => handleEventRoutingChange(eventType, null)}
                  />
                </Space>
                <Space vertical style={{ width: '100%' }} spacing={8}>
                  <div>
                    <Text type="tertiary" size="small">Task Selector:</Text>
                    <Input 
                      value={rule.task_selector}
                      placeholder="e.g., name_contains:chatter, id:task_123"
                      size="small"
                      onChange={(val) => handleEventRoutingChange(eventType, { ...rule, task_selector: val })}
                    />
                  </div>
                  <div>
                    <Text type="tertiary" size="small">Queue (optional):</Text>
                    <Input 
                      value={rule.queue || ''}
                      placeholder="e.g., chat_queue, a2a_queue, custom_queue"
                      size="small"
                      onChange={(val) => handleEventRoutingChange(eventType, { ...rule, queue: val })}
                    />
                  </div>
                </Space>
              </div>
            ))}
            
            <Button 
              icon={<IconPlus />} 
              onClick={addEventRoute}
              size="small"
              style={{ marginTop: 8 }}
            >
              Add Event Route
            </Button>
          </div>
        </Collapse.Panel>
      </Collapse>
    </div>
  );
}

export default SkillLevelMappingEditor;

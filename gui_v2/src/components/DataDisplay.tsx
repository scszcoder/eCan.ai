import React from 'react';
import { Card, List, Tag, Space, Typography, Spin, Alert } from 'antd';
import { useSystemStore } from '../stores/systemStore';

const { Title, Text } = Typography;

const DataDisplay: React.FC = () => {
  const { 
    agents, 
    skills, 
    tools, 
    tasks, 
    vehicles, 
    settings, 
    isLoading, 
    error 
  } = useSystemStore();

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
        <div style={{ marginTop: '16px' }}>加载数据中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        message="数据加载失败"
        description={error}
        type="error"
        showIcon
      />
    );
  }

  return (
    <div style={{ padding: '24px' }}>
      <Title level={2}>系统数据概览</Title>
      
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Agents */}
        <Card title={`代理 (${agents.length})`} size="small">
          <List
            size="small"
            dataSource={agents}
            renderItem={(agent) => (
              <List.Item>
                <List.Item.Meta
                  title={agent.card.name}
                  description={agent.card.description}
                />
                <Space>
                  <Tag color="blue">{agent.card.version}</Tag>
                  <Tag color={agent.card.capabilities.streaming ? 'green' : 'red'}>
                    {agent.card.capabilities.streaming ? '支持流式' : '不支持流式'}
                  </Tag>
                </Space>
              </List.Item>
            )}
          />
        </Card>

        {/* Skills */}
        <Card title={`技能 (${skills.length})`} size="small">
          <List
            size="small"
            dataSource={skills}
            renderItem={(skill) => (
              <List.Item>
                <List.Item.Meta
                  title={skill.name}
                  description={skill.description}
                />
                <Space>
                  <Tag color="purple">{skill.level}</Tag>
                  <Tag color="orange">{skill.version}</Tag>
                </Space>
              </List.Item>
            )}
          />
        </Card>

        {/* Tools */}
        <Card title={`工具 (${tools.length})`} size="small">
          <List
            size="small"
            dataSource={tools}
            renderItem={(tool) => (
              <List.Item>
                <List.Item.Meta
                  title={tool.name}
                  description={tool.description}
                />
                <Tag color="cyan">工具</Tag>
              </List.Item>
            )}
          />
        </Card>

        {/* Tasks */}
        <Card title={`任务 (${tasks.length})`} size="small">
          <List
            size="small"
            dataSource={tasks}
            renderItem={(task) => (
              <List.Item>
                <List.Item.Meta
                  title={task.skill}
                  description={`触发方式: ${task.trigger}`}
                />
                <Space>
                  <Tag color={task.priority === 'high' ? 'red' : 'green'}>
                    {task.priority}
                  </Tag>
                  <Tag color={task.state.top === 'ready' ? 'green' : 'orange'}>
                    {task.state.top}
                  </Tag>
                </Space>
              </List.Item>
            )}
          />
        </Card>

        {/* Vehicles */}
        <Card title={`车辆 (${vehicles.length})`} size="small">
          <List
            size="small"
            dataSource={vehicles}
            renderItem={(vehicle) => (
              <List.Item>
                <List.Item.Meta
                  title={vehicle.name}
                  description={`IP: ${vehicle.ip} | OS: ${vehicle.os}`}
                />
                <Space>
                  <Tag color={vehicle.status === 'running_idle' ? 'green' : 'red'}>
                    {vehicle.status}
                  </Tag>
                  <Text type="secondary">{vehicle.last_update_time}</Text>
                </Space>
              </List.Item>
            )}
          />
        </Card>

        {/* Settings */}
        {settings && (
          <Card title="系统设置" size="small">
            <List
              size="small"
              dataSource={[
                { key: '调试模式', value: settings.debug_mode ? '开启' : '关闭' },
                { key: '默认WiFi', value: settings.default_wifi },
                { key: '调度引擎', value: settings.schedule_engine },
                { key: '调度模式', value: settings.schedule_mode },
              ]}
              renderItem={(item) => (
                <List.Item>
                  <Text strong>{item.key}:</Text>
                  <Text>{item.value}</Text>
                </List.Item>
              )}
            />
          </Card>
        )}
      </Space>
    </div>
  );
};

export default DataDisplay; 
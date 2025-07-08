import React from 'react';
import { Empty, Card, Tag, Typography, Space, Divider } from 'antd';
import { 
  SettingOutlined, 
  CodeOutlined, 
  CheckCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
  ClockCircleOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useNotifications } from '../hooks/useNotifications';
import { getRandomNotificationData, getNotificationTestData } from '../data/notificationTestData';

const { Text, Title } = Typography;

const NotifyContainer = styled.div`
  padding: 20px;
  overflow-y: auto;
  height: 100%;
  width: 100%;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  position: relative;
  
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: 
      radial-gradient(circle at 20% 80%, rgba(102, 126, 234, 0.15) 0%, transparent 50%),
      radial-gradient(circle at 80% 20%, rgba(240, 147, 251, 0.15) 0%, transparent 50%),
      radial-gradient(circle at 40% 40%, rgba(0, 184, 148, 0.1) 0%, transparent 50%);
    pointer-events: none;
  }
`;

const EmptyContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  position: relative;
  z-index: 1;
`;

const NotificationCard = styled(Card)`
  margin-bottom: 20px;
  border-radius: 16px;
  border: none;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(20px);
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.3),
    0 4px 16px rgba(0, 0, 0, 0.2);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #667eea, #764ba2, #f093fb, #00b894);
    border-radius: 16px 16px 0 0;
  }
  
  &:hover {
    transform: translateY(-4px);
    background: rgba(255, 255, 255, 0.12);
    box-shadow: 
      0 12px 40px rgba(0, 0, 0, 0.4),
      0 8px 24px rgba(0, 0, 0, 0.3);
  }
  
  .ant-card-head {
    padding: 20px 24px 0;
    min-height: auto;
    border-bottom: none;
    background: transparent;
  }
  
  .ant-card-body {
    padding: 16px 24px 24px;
  }
  
  .ant-card-head-title {
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
  }
`;

const ConfigItem = styled.div`
  margin-bottom: 20px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(10px);
  
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: linear-gradient(180deg, #667eea, #764ba2);
    border-radius: 0 2px 2px 0;
  }
  
  &:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.2);
  }
`;

const ConfigLabel = styled.div`
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
`;

const ConfigValue = styled.div`
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
`;

const ConfigOptions = styled.div`
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
`;

const CodeBlock = styled.pre`
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.9);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  position: relative;
  backdrop-filter: blur(10px);
  
  &::before {
    content: 'JSON';
    position: absolute;
    top: 8px;
    right: 12px;
    font-size: 10px;
    color: rgba(255, 255, 255, 0.5);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
`;

const NotificationHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
`;

const NotificationTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const NotificationMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
`;

const StatusBadge = styled.div<{ status: string }>`
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: ${props => props.status === 'success' 
    ? 'linear-gradient(135deg, #00b894, #00cec9)' 
    : 'linear-gradient(135deg, #e17055, #d63031)'};
  color: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
`;

const TypeTag = styled(Tag)`
  border-radius: 20px;
  border: none;
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 4px 12px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
`;

const EmptyState = styled(Empty)`
  .ant-empty-description {
    color: rgba(255, 255, 255, 0.8);
    font-size: 16px;
  }
  
  .ant-empty-image {
    opacity: 0.7;
  }
`;

interface ConfigField {
  name: string;
  unit: string;
  type: string;
  options: string[] | string;
  default: string | string[];
}

interface ConfigData {
  [key: string]: ConfigField;
}

interface AgentNotifyProps {
  notifications?: Array<any>;
}

// 测试数据开关 - 修改此变量来控制是否使用测试数据
const USE_TEST_DATA = false;
const TEST_DATA_TYPE = 'mcuConfig' as 'random' | 'mcuConfig' | 'sensorConfig' | 'networkConfig' | 'motorConfig' | 'displayConfig' | 'robotConfig' | 'iotConfig' | 'errorData' | 'emptyData' | 'complexConfig';

// 解析配置数据的函数
const parseConfigData = (jsonString: string): ConfigData | null => {
  try {
    return JSON.parse(jsonString);
  } catch (error) {
    console.error('Failed to parse config data:', error);
    return null;
  }
};

// 获取字段类型图标
const getFieldTypeIcon = (type: string) => {
  const iconMap: Record<string, React.ReactNode> = {
    selection_list: <SettingOutlined style={{ color: '#667eea' }} />,
    range_scale: <CodeOutlined style={{ color: '#764ba2' }} />,
    check_box: <CheckCircleOutlined style={{ color: '#00b894' }} />,
    radio_button_group: <InfoCircleOutlined style={{ color: '#f093fb' }} />,
  };
  return iconMap[type] || <SettingOutlined style={{ color: '#95a5a6' }} />;
};

// 获取字段类型颜色
const getFieldTypeColor = (type: string) => {
  const colorMap: Record<string, string> = {
    selection_list: '#667eea',
    range_scale: '#764ba2',
    check_box: '#00b894',
    radio_button_group: '#f093fb',
  };
  return colorMap[type] || '#95a5a6';
};

// 渲染配置项的组件
const ConfigItemRenderer: React.FC<{ field: ConfigField; fieldKey: string }> = ({ field, fieldKey }) => {
  const renderDefaultValue = (defaultValue: string | string[], type: string) => {
    if (Array.isArray(defaultValue)) {
      return defaultValue.join(' - ');
    }
    return defaultValue;
  };

  const renderOptions = (options: string[] | string) => {
    if (Array.isArray(options)) {
      return options.map((option, index) => (
        <Tag 
          key={index} 
          style={{
            background: 'rgba(255, 255, 255, 0.1)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            color: 'rgba(255, 255, 255, 0.9)',
            borderRadius: '6px',
            fontSize: '11px',
            fontWeight: '500'
          }}
        >
          {option}
        </Tag>
      ));
    }
    return <Text code style={{ color: 'rgba(255, 255, 255, 0.9)', fontSize: '12px' }}>{options}</Text>;
  };

  return (
    <ConfigItem>
      <ConfigLabel>
        {getFieldTypeIcon(field.type)}
        <span>{field.name}</span>
        <Tag 
          style={{
            background: `${getFieldTypeColor(field.type)}20`,
            border: `1px solid ${getFieldTypeColor(field.type)}40`,
            color: getFieldTypeColor(field.type),
            borderRadius: '6px',
            fontSize: '10px',
            fontWeight: '600',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}
        >
          {field.type}
        </Tag>
        {field.unit && (
          <Text type="secondary" style={{ fontSize: '12px', color: 'rgba(255, 255, 255, 0.6)' }}>
            ({field.unit})
          </Text>
        )}
      </ConfigLabel>
      
      <ConfigValue>
        <Text style={{ color: 'rgba(255, 255, 255, 0.7)', fontWeight: '500' }}>Default: </Text>
        <Text code style={{ 
          color: 'rgba(255, 255, 255, 0.9)', 
          fontSize: '12px',
          background: 'rgba(255, 255, 255, 0.1)',
          padding: '2px 6px',
          borderRadius: '4px'
        }}>
          {renderDefaultValue(field.default, field.type)}
        </Text>
      </ConfigValue>
      
      {field.options && (
        <ConfigOptions>
          <Text type="secondary" style={{ marginRight: 8, fontSize: '12px', color: 'rgba(255, 255, 255, 0.6)' }}>Options: </Text>
          {renderOptions(field.options)}
        </ConfigOptions>
      )}
    </ConfigItem>
  );
};

// 渲染通知数据的组件
const NotificationRenderer: React.FC<{ notification: any }> = ({ notification }) => {
  const { t } = useTranslation();
  // 检查是否是新的数据格式
  if (notification.type === 'custom' && notification.code) {
    const configData = parseConfigData(notification.code.value);
    
    return (
      <NotificationCard>
        <NotificationHeader>
          <NotificationTitle>
            <Title level={5} style={{ margin: 0, color: 'rgba(255, 255, 255, 0.9)' }}>
              {notification.text}
            </Title>
            <TypeTag>Q&A</TypeTag>
          </NotificationTitle>
          <NotificationMeta>
            <ClockCircleOutlined />
            <span>{notification.time || new Date().toLocaleString()}</span>
          </NotificationMeta>
        </NotificationHeader>
        
        <Divider style={{ margin: '12px 0', borderColor: 'rgba(255, 255, 255, 0.1)' }} />
        
        {configData ? (
          <div>
            {Object.entries(configData).map(([key, field]) => (
              <ConfigItemRenderer key={key} fieldKey={key} field={field} />
            ))}
          </div>
        ) : (
          <CodeBlock>{notification.code.value}</CodeBlock>
        )}
      </NotificationCard>
    );
  }

  // 原有的通知格式
  return (
    <NotificationCard>
      <NotificationHeader>
        <NotificationTitle>
          <Title level={5} style={{ margin: 0, color: 'rgba(255, 255, 255, 0.9)' }}>
            {notification.title || notification.text}
          </Title>
          {notification.type && <TypeTag>{notification.type}</TypeTag>}
        </NotificationTitle>
        <NotificationMeta>
          <ClockCircleOutlined />
          <span>{notification.time || new Date().toLocaleString()}</span>
          {notification.status && (
            <StatusBadge status={notification.status}>
              {notification.status}
            </StatusBadge>
          )}
        </NotificationMeta>
      </NotificationHeader>
      
      <Divider style={{ margin: '12px 0', borderColor: 'rgba(255, 255, 255, 0.1)' }} />
      
      <div style={{ color: 'rgba(255, 255, 255, 0.8)', lineHeight: '1.6' }}>
        {notification.content || notification.text}
      </div>
    </NotificationCard>
  );
};

const AgentNotify: React.FC<AgentNotifyProps> = ({ notifications: propNotifications }) => {
  const { t } = useTranslation();
  const { notifications } = useNotifications();
  
  // 使用全局通知管理器管理的通知，如果有 props 传入则使用 props（向后兼容）
  let displayNotifications = propNotifications || notifications;
  
  // 如果启用测试数据，替换为测试数据
  if (USE_TEST_DATA) {
    let testData;
    if (TEST_DATA_TYPE === 'random') {
      testData = getRandomNotificationData();
    } else {
      testData = getNotificationTestData(TEST_DATA_TYPE);
    }

    const testNotification = {
      id: `test_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      ...testData,
      time: new Date().toLocaleString()
    };

    displayNotifications = [testNotification];
  }
  
  if (!displayNotifications || displayNotifications.length === 0) {
    return (
      <EmptyContainer>
        <EmptyState description={t('pages.chat.noAgentResults')} />
      </EmptyContainer>
    );
  }
  
  return (
    <NotifyContainer>
      {/* 通知列表 */}
      {displayNotifications.map((notification, index) => (
        <NotificationRenderer key={notification.id || index} notification={notification} />
      ))}
    </NotifyContainer>
  );
};

export default AgentNotify;
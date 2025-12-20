import React from 'react';
import { Space, Tag, Typography, Progress, Tooltip, Row, Col } from 'antd';
import { EnvironmentOutlined, ThunderboltOutlined, ToolOutlined, LaptopOutlined, UsergroupAddOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { Vehicle } from './types';
import StatusTag from '../../components/Common/StatusTag';

const { Text } = Typography;

const VehicleItemCard = styled.div<{ $selected: boolean }>`
  background: var(--bg-secondary);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 16px 18px;
  margin-bottom: 16px;
  width: 100%;
  box-sizing: border-box;
  transition: all 0.3s ease;
  cursor: pointer;
  overflow-x: hidden;
  border: 1px solid transparent;
  position: relative;
  
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    width: 4px;
    background: transparent;
    transition: all 0.3s ease;
  }
  
  &:hover {
    background: var(--bg-tertiary);
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    border-color: rgba(255, 255, 255, 0.1);
    
    &::before {
      width: 3px;
      background: var(--primary-color);
    }
  }
  
  ${props => props.$selected && `
    background: linear-gradient(135deg, rgba(24, 144, 255, 0.15) 0%, rgba(24, 144, 255, 0.05) 100%);
    border: 1px solid rgba(24, 144, 255, 0.4);
    box-shadow: 0 2px 8px rgba(24, 144, 255, 0.2);
    
    &::before {
      background: var(--primary-color);
    }
    
    &:hover {
      background: linear-gradient(135deg, rgba(24, 144, 255, 0.2) 0%, rgba(24, 144, 255, 0.08) 100%);
      border-color: rgba(24, 144, 255, 0.6);
      box-shadow: 0 4px 16px rgba(24, 144, 255, 0.3);
      
      &::before {
        width: 4px;
      }
    }
  `}
`;

interface VehicleItemProps {
    vehicle: Vehicle;
    selected: boolean;
    onClick: (vehicle: Vehicle) => void;
    t: any;
}

const VehicleItem: React.FC<VehicleItemProps> = ({ vehicle, selected, onClick, t }) => (
  <VehicleItemCard $selected={selected} onClick={() => onClick(vehicle)}>
    {/* 第一行：只DisplayName */}
    <Row align="middle" style={{ width: '100%' }} wrap={false}>
      <Col flex="auto" style={{ minWidth: 0 }}>
        <Text
          strong
          ellipsis
          style={{ flex: 1, minWidth: 0, display: 'inline-block', verticalAlign: 'middle', fontSize: 16 }}
        >
          {vehicle.name}
        </Text>
      </Col>
    </Row>
    {/* 第二行：Status+Tag（自动换行） */}
    <Space size={8} wrap style={{ margin: '10px 0 0 0', width: '100%', minWidth: 0 }}>
      <StatusTag status={vehicle.status} />
      {vehicle.arch && <Tag icon={<LaptopOutlined />} color="default">{vehicle.arch}</Tag>}
      {vehicle.os && <Tag icon={<ToolOutlined />} color="default">{vehicle.os}</Tag>}
      {vehicle.bot_ids && <Tag icon={<UsergroupAddOutlined />} color="purple">{t('pages.vehicles.botIds')}: {vehicle.bot_ids.length}</Tag>}
      {vehicle.functions && <Tag color="cyan">{vehicle.functions}</Tag>}
    </Space>
    {/* 第三行：电量进度条，靠左 */}
    <div style={{ margin: '10px 0 0 0', width: '100%', textAlign: 'left', maxWidth: '100%' }}>
      <Tooltip title={t('pages.vehicles.batteryLevel')}>
        <Progress
          percent={vehicle.battery ?? 0}
          size="small"
          status={(vehicle.battery ?? 0) < 20 ? 'exception' : 'normal'}
          format={p => <span><ThunderboltOutlined /> {p}%</span>}
          style={{ width: 120, minWidth: 80, maxWidth: '100%' }}
        />
      </Tooltip>
    </div>
    {/* Bottom：Position+任务 */}
    <Space size={8} style={{ width: '100%', marginTop: 10, minWidth: 0 }}>
      <EnvironmentOutlined />
      <Text type="secondary" ellipsis style={{ flex: 1, minWidth: 0 }}>
        {vehicle.location}
      </Text>
      {vehicle.currentTask && (
        <Tag color="processing" style={{ flexShrink: 0 }}>{t('pages.vehicles.currentTask')}: {vehicle.currentTask}</Tag>
      )}
    </Space>
  </VehicleItemCard>
);

export default VehicleItem; 
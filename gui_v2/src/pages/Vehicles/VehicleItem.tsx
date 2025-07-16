import React from 'react';
import { Space, Tag, Typography, Progress, Tooltip, Row, Col } from 'antd';
import { EnvironmentOutlined, ThunderboltOutlined, ToolOutlined, LaptopOutlined, UsergroupAddOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { Vehicle } from './types';
import StatusTag from '../../components/Common/StatusTag';

const { Text } = Typography;

const VehicleItemCard = styled.div`
  background: var(--bg-secondary);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  padding: 16px 18px;
  margin-bottom: 16px;
  width: 100%;
  box-sizing: border-box;
  transition: box-shadow 0.2s;
  cursor: pointer;
  overflow-x: hidden;
  &:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    background: var(--bg-tertiary);
  }
`;

interface VehicleItemProps {
    vehicle: Vehicle;
    onClick: (vehicle: Vehicle) => void;
    t: any;
}

const VehicleItem: React.FC<VehicleItemProps> = ({ vehicle, onClick, t }) => (
  <VehicleItemCard onClick={() => onClick(vehicle)}>
    {/* 第一行：只显示名称 */}
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
    {/* 第二行：状态+标签（自动换行） */}
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
    {/* 底部：位置+任务 */}
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
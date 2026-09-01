import React from 'react';
import { Tag, Progress, Tooltip, Row, Col } from 'antd';
import { EnvironmentOutlined, ThunderboltOutlined, ToolOutlined, LaptopOutlined, UsergroupAddOutlined, DesktopOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { keyframes } from '@emotion/react';
import type { Vehicle } from '@/types/domain/vehicle';
import StatusTag from '../../components/Common/StatusTag';

// ================= Animations =================
const slideInAnimation = keyframes`
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

// ================= List View =================
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

// ================= Grid View =================
const GridCardWrapper = styled.div<{ $selected?: boolean }>`
  background: ${props => props.$selected
    ? 'linear-gradient(135deg, rgba(24, 144, 255, 0.16) 0%, rgba(82, 196, 26, 0.08) 100%)'
    : 'rgba(255, 255, 255, 0.025)'};
  border: 1px solid ${props => props.$selected
    ? 'rgba(24, 144, 255, 0.58)'
    : 'rgba(255, 255, 255, 0.08)'};
  border-radius: 14px;
  padding: 0;
  cursor: pointer;
  transition: all 0.2s ease;
  animation: ${slideInAnimation} 0.3s ease-out;
  position: relative;
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;

  &:hover {
    background: ${props => props.$selected
      ? 'linear-gradient(135deg, rgba(24, 144, 255, 0.2) 0%, rgba(82, 196, 26, 0.12) 100%)'
      : 'rgba(255, 255, 255, 0.045)'};
    border-color: ${props => props.$selected
      ? 'rgba(24, 144, 255, 0.72)'
      : 'rgba(255, 255, 255, 0.14)'};
    transform: translateY(-2px);
    box-shadow: ${props => props.$selected
      ? '0 14px 30px rgba(24, 144, 255, 0.22)'
      : '0 12px 28px rgba(0, 0, 0, 0.25)'};
  }
`;

const GridCardHeader = styled.div<{ $gradient: string }>`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 14px 12px;
  background: linear-gradient(135deg, ${props => props.$gradient});
  position: relative;
  overflow: hidden;

  &::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0.25) 100%);
    pointer-events: none;
  }

  > * {
    position: relative;
    z-index: 1;
  }
`;

const GridIconBadge = styled.div`
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  .anticon {
    font-size: 18px;
    color: #fff;
  }
`;

const GridHeaderInfo = styled.div`
  min-width: 0;
  flex: 1;
`;

const GridName = styled.div`
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
`;

const GridSubtitle = styled.div`
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 4px;
`;

const GridCardBody = styled.div`
  padding: 12px 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
`;

const GridTagRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
`;

const GridTag = styled.div<{ $bg: string; $color: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  background: ${props => props.$bg};
  color: ${props => props.$color};
  border: 1px solid ${props => props.$color}30;

  .anticon {
    font-size: 11px;
  }
`;

const GridBatteryRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const GridCardFooter = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
`;

const GridFooterMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 0;
  flex: 1;

  .anticon {
    color: var(--text-muted);
    flex-shrink: 0;
  }
`;

const GridLocationText = styled.span`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const GridCurrentTaskTag = styled(Tag)`
  margin: 0 !important;
  flex-shrink: 0;
  font-size: 11px !important;
`;

// ================= Helpers =================
const STATUS_GRADIENT: Record<string, string> = {
  active: '#52c41a 0%, #389e0d 100%',
  idle: '#1890ff 0%, #096dd9 100%',
  busy: '#fa8c16 0%, #d46b08 100%',
  maintenance: '#722ed1 0%, #531d93 100%',
  offline: '#595959 0%, #262626 100%',
  disconnected: '#595959 0%, #262626 100%',
};

const DEFAULT_GRADIENT = '#1890ff 0%, #096dd9 100%';

const getHeaderGradient = (status: string): string => {
  const key = String(status || '').toLowerCase();
  return STATUS_GRADIENT[key] || DEFAULT_GRADIENT;
};

interface VehicleItemProps {
  vehicle: Vehicle;
  selected: boolean;
  onClick: (vehicle: Vehicle) => void;
  viewMode?: 'list' | 'grid';
  t: any;
}

// ================= Component =================
const VehicleItem: React.FC<VehicleItemProps> = ({
  vehicle,
  selected,
  onClick,
  viewMode = 'list',
  t,
}) => {
  // ============= Grid View =============
  if (viewMode === 'grid') {
    const battery = vehicle.battery ?? 0;
    const gradient = getHeaderGradient(vehicle.status as string);

    return (
      <GridCardWrapper $selected={selected} onClick={() => onClick(vehicle)}>
        {/* Header with gradient */}
        <GridCardHeader $gradient={gradient}>
          <GridIconBadge>
            <DesktopOutlined />
          </GridIconBadge>
          <GridHeaderInfo>
            <GridName title={vehicle.name}>{vehicle.name}</GridName>
            <GridSubtitle title={vehicle.ip || ''}>
              <EnvironmentOutlined />
              <span>{vehicle.ip || '—'}</span>
            </GridSubtitle>
          </GridHeaderInfo>
          <StatusTag status={vehicle.status as string} />
        </GridCardHeader>

        {/* Body */}
        <GridCardBody>
          {/* OS / Arch / Bot tags */}
          <GridTagRow>
            {vehicle.os && (
              <GridTag $bg="rgba(82, 196, 26, 0.1)" $color="#52c41a">
                <ToolOutlined />
                {vehicle.os}
              </GridTag>
            )}
            {vehicle.arch && (
              <GridTag $bg="rgba(24, 144, 255, 0.1)" $color="#1890ff">
                <LaptopOutlined />
                {vehicle.arch}
              </GridTag>
            )}
            {vehicle.bot_ids && vehicle.bot_ids.length > 0 && (
              <GridTag $bg="rgba(114, 46, 209, 0.12)" $color="#722ed1">
                <UsergroupAddOutlined />
                {vehicle.bot_ids.length}
              </GridTag>
            )}
            {vehicle.functions && (
              <GridTag $bg="rgba(0, 180, 180, 0.1)" $color="#00b8b8">
                {vehicle.functions}
              </GridTag>
            )}
          </GridTagRow>

          {/* Battery */}
          {typeof vehicle.battery === 'number' && (
            <GridBatteryRow>
              <Tooltip title={t('pages.vehicles.batteryLevel')}>
                <Progress
                  percent={battery}
                  size="small"
                  status={battery < 20 ? 'exception' : 'normal'}
                  format={(p) => (
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                      <ThunderboltOutlined /> {p}%
                    </span>
                  )}
                  style={{ flex: 1, minWidth: 0 }}
                />
              </Tooltip>
            </GridBatteryRow>
          )}
        </GridCardBody>

        {/* Footer */}
        <GridCardFooter>
          <GridFooterMeta>
            <EnvironmentOutlined />
            <GridLocationText title={vehicle.location}>
              {vehicle.location || '—'}
            </GridLocationText>
          </GridFooterMeta>
          {vehicle.currentTask && (
            <GridCurrentTaskTag color="processing">
              {vehicle.currentTask}
            </GridCurrentTaskTag>
          )}
        </GridCardFooter>
      </GridCardWrapper>
    );
  }

  // ============= List View (default) =============
  return (
    <VehicleItemCard $selected={selected} onClick={() => onClick(vehicle)}>
      {/* 第一行：只DisplayName */}
      <Row align="middle" style={{ width: '100%' }} wrap={false}>
        <Col flex="auto" style={{ minWidth: 0 }}>
          <div
            style={{
              flex: 1,
              minWidth: 0,
              display: 'inline-block',
              verticalAlign: 'middle',
              fontSize: 16,
              fontWeight: 600,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {vehicle.name}
          </div>
        </Col>
      </Row>
      {/* 第二行：Status+Tag（自动换行） */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '10px 0 0 0', width: '100%', minWidth: 0 }}>
        <StatusTag status={vehicle.status as string} />
        {vehicle.arch && <Tag icon={<LaptopOutlined />} color="default">{vehicle.arch}</Tag>}
        {vehicle.os && <Tag icon={<ToolOutlined />} color="default">{vehicle.os}</Tag>}
        {vehicle.bot_ids && <Tag icon={<UsergroupAddOutlined />} color="purple">{t('pages.vehicles.botIds')}: {vehicle.bot_ids.length}</Tag>}
        {vehicle.functions && <Tag color="cyan">{vehicle.functions}</Tag>}
      </div>
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
      <div style={{ display: 'flex', width: '100%', marginTop: 10, minWidth: 0, gap: 8 }}>
        <EnvironmentOutlined style={{ flexShrink: 0, marginTop: 2 }} />
        <span style={{
          flex: 1,
          minWidth: 0,
          color: 'rgba(255,255,255,0.65)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {vehicle.location}
        </span>
        {vehicle.currentTask && (
          <Tag color="processing" style={{ flexShrink: 0 }}>{t('pages.vehicles.currentTask')}: {vehicle.currentTask}</Tag>
        )}
      </div>
    </VehicleItemCard>
  );
};

export default VehicleItem;

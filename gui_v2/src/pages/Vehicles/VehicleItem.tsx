import React from 'react';
import { Tag, Progress, Tooltip, Row, Col } from 'antd';
import { EnvironmentOutlined, ThunderboltOutlined, ToolOutlined, LaptopOutlined, UsergroupAddOutlined, DesktopOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { keyframes } from '@emotion/react';
import type { Vehicle } from '@/types/domain/vehicle';
import StatusTag from '../../components/Common/StatusTag';
import WatchMachineButton from '../../components/Fleet/WatchMachineButton';

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
    border-color: var(--border-color);

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
    : 'var(--surface-panel)'};
  border: 1px solid ${props => props.$selected
    ? 'rgba(24, 144, 255, 0.58)'
    : 'var(--border-color)'};
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
      : 'var(--surface-subtle-hover)'};
    border-color: ${props => props.$selected
      ? 'rgba(24, 144, 255, 0.72)'
      : 'var(--border-color-hover)'};
    transform: translateY(-2px);
    box-shadow: ${props => props.$selected
      ? '0 14px 30px rgba(24, 144, 255, 0.22)'
      : 'var(--shadow-lg)'};
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

  /* StatusTag chips rendered on this fixed opaque status gradient must be
     self-contained: a translucent --*-bg tint would lose its base here and
     collapse to ~1:1. Pin an opaque on-primary chip instead. */
  .ant-tag {
    background: rgba(0, 0, 0, 0.28) !important;
    border-color: rgba(255, 255, 255, 0.32) !important;
    color: var(--text-on-primary) !important;

    .anticon {
      color: var(--text-on-primary) !important;
    }
  }
`;

const GridIconBadge = styled.div`
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--highlight-top-strong);
  border: 1px solid var(--border-color-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  .anticon {
    font-size: 18px;
    color: var(--text-on-primary);
  }
`;

const GridHeaderInfo = styled.div`
  min-width: 0;
  flex: 1;
`;

const GridName = styled.div`
  font-size: 15px;
  font-weight: 600;
  color: var(--text-on-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
`;

const GridSubtitle = styled.div`
  font-size: 12px;
  color: var(--text-on-primary);
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

/* Carries an accent colour + a matching translucent tint. Rendered in the card
   body (a theme surface), so the tint keeps its base. */
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
  border-top: 1px solid var(--border-color);
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
// Fleet role -> i18n key under `roles` (shared with the login role picker).
export const roleKey = (role?: string): string | null => {
  const r = String(role || '');
  if (r.includes('Commander')) return 'commander';
  if (r.includes('Platoon')) return 'platoon';
  if (r.includes('Staff')) return 'staff_office';
  return null;
};

const ROLE_COLOR: Record<string, string> = {
  commander: 'gold',
  platoon: 'geekblue',
  staff_office: 'purple',
};

const RoleTags: React.FC<{ vehicle: Vehicle; t: any }> = ({ vehicle, t }) => {
  const key = roleKey(vehicle.role);
  return (
    <>
      {key && <Tag color={ROLE_COLOR[key]} style={{ margin: 0 }}>{t(`roles.${key}`)}</Tag>}
      {vehicle.is_self && <Tag color="green" style={{ margin: 0 }}>{t('pages.vehicles.thisMachine', 'This machine')}</Tag>}
    </>
  );
};
/* Header gradients carried the on-primary foreground. The "-fill" ramps are
   dark enough for white text in BOTH themes; the neutral reading for
   offline/disconnected therefore needs its own theme-invariant dark slate
   ramp. --bg-tertiary/--bg-quaternary are *light* surfaces in light mode and
   collapsed the white header text to 1.23:1 there. */
const STATUS_GRADIENT: Record<string, string> = {
  active: 'var(--success-fill) 0%, var(--success-fill) 100%',
  idle: 'var(--primary-fill) 0%, var(--primary-fill-hover) 100%',
  busy: 'var(--warning-fill) 0%, var(--warning-fill) 100%',
  maintenance: 'var(--accent-fill) 0%, var(--accent-fill) 100%',
  offline: '#475569 0%, #334155 100%',
  disconnected: '#475569 0%, #334155 100%',
};

const DEFAULT_GRADIENT = 'var(--primary-fill) 0%, var(--primary-fill-hover) 100%';

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

// "Watch" -> this machine's live activity (fleet feed), keyed by its vehicle id,
// which is the id the machine reports its feed under.
const WatchButton: React.FC<{ vehicle: Vehicle }> = ({ vehicle }) => (
  <WatchMachineButton
    machineId={String(vehicle.id)}
    name={vehicle.name}
    role={vehicle.role}
    online={String(vehicle.status || '').toLowerCase() === 'active'}
  />
);

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
          <WatchButton vehicle={vehicle} />
        </GridCardHeader>

        {/* Body */}
        <GridCardBody>
          {/* Role / OS / Arch / Bot tags */}
          <GridTagRow>
            <RoleTags vehicle={vehicle} t={t} />
            {vehicle.os && (
              <GridTag $bg="var(--success-bg)" $color="var(--success-text)">
                <ToolOutlined />
                {vehicle.os}
              </GridTag>
            )}
            {vehicle.arch && (
              <GridTag $bg="var(--primary-bg)" $color="var(--primary-text)">
                <LaptopOutlined />
                {vehicle.arch}
              </GridTag>
            )}
            {vehicle.bot_ids && vehicle.bot_ids.length > 0 && (
              <GridTag $bg="var(--accent-bg)" $color="var(--accent-text)">
                <UsergroupAddOutlined />
                {vehicle.bot_ids.length}
              </GridTag>
            )}
            {vehicle.functions && (
              <GridTag $bg="var(--info-bg)" $color="var(--info-text)">
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
        <Col flex="none">
          <WatchButton vehicle={vehicle} />
        </Col>
      </Row>
      {/* 第二行：Status+Tag（自动换行） */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '10px 0 0 0', width: '100%', minWidth: 0 }}>
        <StatusTag status={vehicle.status as string} />
        <RoleTags vehicle={vehicle} t={t} />
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
          color: 'var(--text-secondary)',
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

// Custom comparator: re-render only when the bound vehicle object changes
// (by id), the selection flips, or the viewMode changes. Without this, every
// Zustand store tick re-renders every VehicleItem in the list, even though
// only one row is likely to have actually changed.
const areVehiclePropsEqual = (
  prev: VehicleItemProps,
  next: VehicleItemProps,
): boolean => {
  return (
    prev.vehicle === next.vehicle &&
    prev.selected === next.selected &&
    prev.viewMode === next.viewMode
  );
};

export default React.memo(VehicleItem, areVehiclePropsEqual);

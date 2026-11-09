import React from 'react';
import { Progress, Tooltip } from 'antd';
import {
  EnvironmentOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  LaptopOutlined,
  UsergroupAddOutlined,
  DesktopOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { keyframes, css } from '@emotion/react';
import type { Vehicle } from '@/types/domain/vehicle';
import WatchMachineButton from '../../components/Fleet/WatchMachineButton';

// ================= Animations =================
const slideInAnimation = keyframes`
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
`;

// ================= Status tokens =================
// Flat, theme-aware tokens — no full-bleed status gradient, so light and dark
// both derive their colours from the shared palette. The status hue is carried
// only by the soft-tinted icon tile and a small chip, matching the skill cards.
interface StatusInfo {
  label: string;
  icon: React.ReactNode;
  color: string;   // glyph / text token
  fill: string;    // saturated hue -> soft tile tint
  bg: string;      // translucent chip surface
  border: string;  // chip hairline
  pulse: boolean;
}

const STATUS_DEFAULT_TEXT: Record<string, string> = {
  active: '在线',
  online: '在线',
  idle: '空闲',
  busy: '忙碌',
  maintenance: '维护中',
  offline: '离线',
  disconnected: '未连接',
  inactive: '停用',
};

const STATUS_TOKEN: Record<string, Omit<StatusInfo, 'label'>> = {
  active:       { icon: <CheckCircleOutlined />, color: 'var(--success-text)', fill: 'var(--success-fill)', bg: 'var(--success-bg)', border: 'var(--success-border)', pulse: false },
  online:       { icon: <CheckCircleOutlined />, color: 'var(--success-text)', fill: 'var(--success-fill)', bg: 'var(--success-bg)', border: 'var(--success-border)', pulse: false },
  idle:         { icon: <CheckCircleOutlined />, color: 'var(--success-text)', fill: 'var(--success-fill)', bg: 'var(--success-bg)', border: 'var(--success-border)', pulse: false },
  busy:         { icon: <ClockCircleOutlined />, color: 'var(--warning-text)', fill: 'var(--warning-fill)', bg: 'var(--warning-bg)', border: 'var(--warning-border)', pulse: true },
  maintenance:  { icon: <ToolOutlined />, color: 'var(--accent-text)', fill: 'var(--accent-fill)', bg: 'var(--accent-bg)', border: 'var(--accent-border)', pulse: false },
  offline:      { icon: <CloseCircleOutlined />, color: 'var(--text-tertiary)', fill: 'var(--text-tertiary)', bg: 'var(--surface-subtle)', border: 'var(--border-color)', pulse: false },
  disconnected: { icon: <CloseCircleOutlined />, color: 'var(--text-tertiary)', fill: 'var(--text-tertiary)', bg: 'var(--surface-subtle)', border: 'var(--border-color)', pulse: false },
  inactive:     { icon: <CloseCircleOutlined />, color: 'var(--text-tertiary)', fill: 'var(--text-tertiary)', bg: 'var(--surface-subtle)', border: 'var(--border-color)', pulse: false },
};

const DEFAULT_STATUS: Omit<StatusInfo, 'label'> = {
  icon: <LaptopOutlined />,
  color: 'var(--primary-text)',
  fill: 'var(--primary-fill)',
  bg: 'var(--primary-bg)',
  border: 'var(--primary-border)',
  pulse: false,
};

const getStatus = (status: string, t: any): StatusInfo => {
  const key = String(status || '').toLowerCase();
  const base = STATUS_TOKEN[key] || DEFAULT_STATUS;
  return { ...base, label: t(`pages.vehicles.status.${key}`, STATUS_DEFAULT_TEXT[key] || key) };
};

// ================= Card shell (shared by grid + list) =================
const Card = styled.div<{ $selected?: boolean; $grid?: boolean }>`
  background: var(--bg-secondary);
  border: 1px solid ${p => (p.$selected ? 'var(--primary-border)' : 'var(--border-color)')};
  border-radius: ${p => (p.$grid ? '16px' : '14px')};
  box-shadow: ${p => (p.$selected
    ? '0 0 0 1px var(--primary-border), var(--elev-2, var(--shadow-md))'
    : 'var(--elev-2, var(--shadow-md))')};
  padding: ${p => (p.$grid ? '14px 16px' : '14px 16px')};
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease, background 0.18s ease;
  ${p => (p.$grid ? 'height: 100%;' : 'margin: 0 0 12px;')}
  ${p => (p.$grid ? css`animation: ${slideInAnimation} 0.3s ease-out;` : '')}
  ${p => (p.$selected ? 'background: var(--primary-bg);' : '')}

  &:hover {
    transform: translateY(-2px);
    background: ${p => (p.$selected ? 'var(--primary-bg-hover)' : 'var(--bg-tertiary)')};
    border-color: ${p => (p.$selected ? 'var(--primary-border)' : 'var(--border-color-hover)')};
    box-shadow: var(--elev-3, var(--shadow-lg));
  }
`;

const Header = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 12px;
`;

const IconTile = styled.div<{ $fill: string; $color: string; $grid?: boolean }>`
  width: ${p => (p.$grid ? '44px' : '40px')};
  height: ${p => (p.$grid ? '44px' : '40px')};
  border-radius: ${p => (p.$grid ? '13px' : '11px')};
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: ${p => (p.$grid ? '20px' : '18px')};
  background: ${p => `color-mix(in srgb, ${p.$fill} 15%, transparent)`};
  color: ${p => p.$color};

  /* The text tokens stay legible on both the card surface and this soft tint in
     either theme; the tile only needs a touch more presence in the dark theme. */
  body.dark & {
    background: ${p => `color-mix(in srgb, ${p.$fill} 22%, transparent)`};
  }
`;

const HeadMain = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
`;

const Name = styled.div`
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const Subline = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--text-muted);
  min-width: 0;

  .anticon {
    font-size: 12px;
  }

  .ip {
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .dot {
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: currentColor;
    opacity: 0.5;
    flex-shrink: 0;
  }
`;

const Body = styled.div`
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
`;

const TagRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
`;

// A single flat chip atom used for status, roles, os/arch/bot, and current task.
const Chip = styled.span<{ $bg: string; $color: string; $border: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 500;
  line-height: 16px;
  white-space: nowrap;
  background: ${p => p.$bg};
  color: ${p => p.$color};
  border: 1px solid ${p => p.$border};

  .anticon {
    font-size: 11px;
  }
`;

const BatteryRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;

  .ant-progress {
    flex: 1;
    min-width: 0;
  }
`;

const Footer = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
`;

const FooterMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 0;
  flex: 1;

  .anticon {
    color: var(--text-muted);
    flex-shrink: 0;
  }
`;

const LocationText = styled.span`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

// Role -> accent tokens (flat chips, not the old saturated antd Tag colours).
const ROLE_TOKEN: Record<string, { bg: string; color: string; border: string }> = {
  commander: { bg: 'var(--warning-bg)', color: 'var(--warning-text)', border: 'var(--warning-border)' },
  platoon: { bg: 'var(--primary-bg)', color: 'var(--primary-text)', border: 'var(--primary-border)' },
  staff_office: { bg: 'var(--accent-bg)', color: 'var(--accent-text)', border: 'var(--accent-border)' },
};

const RoleTags: React.FC<{ vehicle: Vehicle; t: any }> = ({ vehicle, t }) => {
  const key = roleKey(vehicle.role);
  return (
    <>
      {key && (
        <Chip $bg={ROLE_TOKEN[key].bg} $color={ROLE_TOKEN[key].color} $border={ROLE_TOKEN[key].border}>
          {t(`roles.${key}`)}
        </Chip>
      )}
      {vehicle.is_self && (
        <Chip $bg="var(--success-bg)" $color="var(--success-text)" $border="var(--success-border)">
          {t('pages.vehicles.thisMachine', 'This machine')}
        </Chip>
      )}
    </>
  );
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
  viewMode = 'grid',
  t,
}) => {
  const isGrid = viewMode === 'grid';
  const battery = vehicle.battery ?? 0;
  const st = getStatus(vehicle.status as string, t);

  return (
    <Card $selected={selected} $grid={isGrid} onClick={() => onClick(vehicle)}>
      <Header>
        <IconTile $fill={st.fill} $color={st.color} $grid={isGrid}>
          <DesktopOutlined />
        </IconTile>
        <HeadMain>
          <Name title={vehicle.name}>{vehicle.name}</Name>
          <Subline>
            <EnvironmentOutlined />
            <span className="ip" title={vehicle.ip || ''}>{vehicle.ip || '—'}</span>
            <span className="dot" />
            <Chip $bg={st.bg} $color={st.color} $border={st.border}>
              {st.icon}
              {st.label}
            </Chip>
          </Subline>
        </HeadMain>
        <WatchButton vehicle={vehicle} />
      </Header>

      <Body>
        <TagRow>
          <RoleTags vehicle={vehicle} t={t} />
          {vehicle.os && (
            <Chip $bg="var(--success-bg)" $color="var(--success-text)" $border="var(--success-border)">
              <ToolOutlined />
              {vehicle.os}
            </Chip>
          )}
          {vehicle.arch && (
            <Chip $bg="var(--primary-bg)" $color="var(--primary-text)" $border="var(--primary-border)">
              <LaptopOutlined />
              {vehicle.arch}
            </Chip>
          )}
          {vehicle.bot_ids && vehicle.bot_ids.length > 0 && (
            <Chip $bg="var(--accent-bg)" $color="var(--accent-text)" $border="var(--accent-border)">
              <UsergroupAddOutlined />
              {vehicle.bot_ids.length}
            </Chip>
          )}
          {vehicle.functions && (
            <Chip $bg="var(--info-bg)" $color="var(--info-text)" $border="var(--info-border)">
              {vehicle.functions}
            </Chip>
          )}
        </TagRow>

        {typeof vehicle.battery === 'number' && (
          <BatteryRow>
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
              />
            </Tooltip>
          </BatteryRow>
        )}
      </Body>

      <Footer>
        <FooterMeta>
          <EnvironmentOutlined />
          <LocationText title={vehicle.location}>{vehicle.location || '—'}</LocationText>
        </FooterMeta>
        {vehicle.currentTask && (
          <Chip $bg="var(--warning-bg)" $color="var(--warning-text)" $border="var(--warning-border)" title={vehicle.currentTask}>
            {t('pages.vehicles.currentTask')}: {vehicle.currentTask}
          </Chip>
        )}
      </Footer>
    </Card>
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

import React, { useRef } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Space, Button, Progress } from 'antd';
import { ClusterOutlined, CheckCircleOutlined, EnvironmentOutlined, ThunderboltOutlined, ToolOutlined, ClockCircleOutlined, PlusOutlined, HistoryOutlined } from '@ant-design/icons';
import type { Vehicle } from '@/types/domain/vehicle';
import StatusTag from '../../components/Common/StatusTag';
import DetailCard from '../../components/Common/DetailCard';
import styled from '@emotion/styled';

interface VehicleDetailsProps {
    vehicle?: Vehicle;
    onStatusChange: (id: string | number, status: Vehicle['status']) => void;
    onMaintenance: (id: string | number) => void;
    t: any;
}

const DetailContent = styled.div`
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 16px 20px 0;
  background: rgba(0, 0, 0, 0.2);

  /* Compact DetailCard overrides — dense grid for popup view */
  .ant-card {
    margin-bottom: 12px !important;
    background: rgba(255, 255, 255, 0.02) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 10px !important;
  }

  .ant-card-head {
    min-height: 36px !important;
    padding: 8px 16px !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
  }

  .ant-card-body {
    padding: 8px 16px 12px !important;
  }

  .ant-card-head-title {
    font-size: 13px !important;
    font-weight: 600 !important;
  }
`;

const CompactDetailCard = styled(DetailCard)`
  .ant-card {
    margin-bottom: 12px !important;
  }
  .ant-card-head {
    min-height: 36px !important;
    padding: 8px 16px !important;
  }
  .ant-card-head-title {
    font-size: 13px !important;
  }
  .ant-card-body {
    padding: 8px 16px 12px !important;
  }
`;

// Compact grid item override (tighter padding & line-height)
const DetailItemStyle = `
  padding: 7px 6px !important;
  font-size: 13px;
  line-height: 1.4;

  &:last-child,
  &:nth-last-child(2):nth-child(odd) {
    border-bottom: none !important;
  }
`;

// Injects style once
if (typeof document !== 'undefined' && !document.getElementById('vehicle-details-compact')) {
  const style = document.createElement('style');
  style.id = 'vehicle-details-compact';
  style.textContent = `
    .vehicle-details-compact .ant-card-body > div > div {
      ${DetailItemStyle}
    }
    .vehicle-details-compact .ant-card-body > div > div > div:nth-child(2) {
      font-size: 13px !important;
      line-height: 1.4 !important;
    }
    .vehicle-details-compact .ant-card-body > div > div > div:first-child {
      font-size: 12px !important;
      min-width: 90px !important;
    }
  `;
  document.head.appendChild(style);
}

// Compact metric — inline number + small progress
const MetricCell = styled.div`
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
`;

const MetricLabel = styled.div`
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
  display: flex;
  align-items: center;
  gap: 6px;
  text-transform: uppercase;
  letter-spacing: 0.4px;

  .anticon {
    font-size: 12px;
    color: rgba(64, 169, 255, 0.7);
  }
`;

const MetricValueRow = styled.div`
  display: flex;
  align-items: baseline;
  gap: 6px;
`;

const MetricValue = styled.span<{ $danger?: boolean }>`
  font-size: 18px;
  font-weight: 600;
  color: ${props => props.$danger ? '#ff4d4f' : '#3f8600'};
  line-height: 1.1;
`;

const MetricSuffix = styled.span`
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
`;

const MetricsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0;
`;

const MetricDivider = styled.div<{ $columns?: number }>`
  ${props => props.$columns && props.$columns > 1 ? `
    border-right: 1px solid rgba(255, 255, 255, 0.06);

    &:nth-of-type(${props.$columns}n) {
      border-right: none;
    }
  ` : ''}
`;

const ActionBar = styled.div`
  position: sticky;
  bottom: 0;
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  margin: 0 -20px;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0) 0%, rgba(15, 23, 42, 0.85) 30%, rgba(15, 23, 42, 0.95) 100%);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(8px);
  z-index: 2;
`;

const InlineTag = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.85);
`;

interface MetricItem {
  label: string;
  value: number;
  suffix?: string;
  icon: React.ReactNode;
  warn?: number; // threshold above which value shows danger color
  precision?: number;
}

const MetricBlock: React.FC<{ item: MetricItem }> = ({ item }) => {
  const isDanger = typeof item.warn === 'number' && item.value >= item.warn;
  return (
    <MetricCell>
      <MetricLabel>
        {item.icon}
        {item.label}
      </MetricLabel>
      <MetricValueRow>
        <MetricValue $danger={isDanger}>
          {item.value.toFixed(item.precision ?? 0)}
        </MetricValue>
        {item.suffix && <MetricSuffix>{item.suffix}</MetricSuffix>}
      </MetricValueRow>
      <Progress
        percent={Math.min(100, item.value)}
        size="small"
        showInfo={false}
        strokeColor={isDanger ? '#ff4d4f' : '#52c41a'}
        trailColor="rgba(255, 255, 255, 0.08)"
      />
    </MetricCell>
  );
};

const VehicleDetails: React.FC<VehicleDetailsProps> = ({ vehicle, onStatusChange, onMaintenance, t }) => {
  // ScrollPositionSave
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);

  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
  useEffectOnActive(
    () => {
      const container = scrollContainerRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
        });
      }

      return () => {
        const container = scrollContainerRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
        }
      };
    },
    []
  );

  if (!vehicle) {
    return <span style={{ color: '#888' }}>{t('pages.vehicles.selectVehicle')}</span>;
  }

  // Performance metrics — compact grid
  const performanceMetrics: MetricItem[] = [
    {
      label: t('pages.vehicles.batteryLevel'),
      value: vehicle.battery ?? 0,
      suffix: '%',
      icon: <ThunderboltOutlined />,
      warn: 0, // battery: low is bad, but we want red < 20, handled separately
      precision: 0,
    },
    {
      label: 'CPU',
      value: vehicle.cpuUsage ?? 0,
      suffix: '%',
      icon: <ClusterOutlined />,
      warn: 80,
      precision: 1,
    },
    {
      label: '内存',
      value: vehicle.memoryUsage ?? 0,
      suffix: '%',
      icon: <ClusterOutlined />,
      warn: 80,
      precision: 1,
    },
    {
      label: '磁盘',
      value: vehicle.diskUsage ?? 0,
      suffix: '%',
      icon: <ClusterOutlined />,
      warn: 90,
      precision: 1,
    },
  ];

  // Override battery danger logic
  performanceMetrics[0].warn = -1; // never warn via threshold; use red separately
  const batteryValue = vehicle.battery ?? 0;
  const batteryDanger = batteryValue < 20;

  return (
    <div className="vehicle-details-compact" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <DetailContent ref={scrollContainerRef} style={{ flex: 1, minHeight: 0 }}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          {/* Top row: Device identity + Status (single dense card) */}
          <CompactDetailCard
            title={t('pages.vehicles.vehicleInformation')}
            columns={3}
            items={[
              {
                label: t('pages.vehicles.name'),
                value: <InlineTag>{vehicle.name}</InlineTag>,
                icon: <ClusterOutlined />,
              },
              {
                label: t('pages.vehicles.statusLabel'),
                value: <StatusTag status={vehicle.status as string} />,
                icon: <CheckCircleOutlined />,
              },
              {
                label: t('pages.vehicles.type'),
                value: vehicle.type,
                icon: <ClusterOutlined />,
              },
              {
                label: 'IP',
                value: <InlineTag>{vehicle.ip || '—'}</InlineTag>,
              },
              {
                label: t('pages.vehicles.os'),
                value: vehicle.os,
                icon: <ToolOutlined />,
              },
              {
                label: t('pages.vehicles.arch'),
                value: vehicle.arch,
                icon: <ClusterOutlined />,
              },
              {
                label: t('pages.vehicles.location'),
                value: vehicle.location || '—',
                icon: <EnvironmentOutlined />,
              },
              {
                label: t('pages.vehicles.lastUpdateTime'),
                value: vehicle.last_update_time || '—',
                icon: <ClockCircleOutlined />,
              },
              {
                label: t('pages.vehicles.botIds'),
                value: vehicle.bot_ids?.length ?? 0,
              },
            ]}
          />

          {/* Performance metrics — custom 4-column compact grid */}
          <CompactDetailCard
            title={t('pages.vehicles.performanceMetrics')}
            columns={1}
            items={[]}
          >
            <MetricsGrid>
              {/* Battery — special-cased for low-danger coloring */}
              <MetricDivider $columns={4}>
                <MetricCell>
                  <MetricLabel>
                    <ThunderboltOutlined />
                    {t('pages.vehicles.batteryLevel')}
                  </MetricLabel>
                  <MetricValueRow>
                    <MetricValue $danger={batteryDanger}>{batteryValue}</MetricValue>
                    <MetricSuffix>%</MetricSuffix>
                  </MetricValueRow>
                  <Progress
                    percent={batteryValue}
                    size="small"
                    showInfo={false}
                    strokeColor={batteryDanger ? '#ff4d4f' : '#52c41a'}
                    trailColor="rgba(255, 255, 255, 0.08)"
                  />
                </MetricCell>
              </MetricDivider>
              {performanceMetrics.slice(1).map((m) => (
                <MetricDivider key={m.label} $columns={4}>
                  <MetricBlock item={m} />
                </MetricDivider>
              ))}
            </MetricsGrid>
          </CompactDetailCard>

          {/* Device status — 3 columns */}
          <CompactDetailCard
            title={t('pages.vehicles.title') === '电脑管理' ? '设备状态' : 'Device Status'}
            columns={3}
            items={[
              {
                label: '网络状态',
                value: vehicle.networkStatus === 'connected'
                  ? <InlineTag style={{ background: 'rgba(82, 196, 26, 0.15)', color: '#52c41a' }}>已连接</InlineTag>
                  : <InlineTag style={{ background: 'rgba(255, 77, 79, 0.15)', color: '#ff4d4f' }}>未连接</InlineTag>,
                icon: <EnvironmentOutlined />,
              },
              {
                label: '运行时长',
                value: vehicle.uptime
                  ? `${Math.floor(vehicle.uptime / 3600)}h ${Math.floor((vehicle.uptime % 3600) / 60)}m`
                  : '—',
                icon: <ClockCircleOutlined />,
              },
              {
                label: t('pages.vehicles.totalDistance'),
                value: vehicle.totalDistance != null ? `${vehicle.totalDistance} km` : '—',
                icon: <ClusterOutlined />,
              },
              {
                label: t('pages.vehicles.currentTask'),
                value: vehicle.currentTask || '无',
                icon: <ToolOutlined />,
              },
              {
                label: t('pages.vehicles.functions'),
                value: vehicle.functions || '—',
                icon: <ToolOutlined />,
              },
              {
                label: t('pages.vehicles.testDisabled'),
                value: vehicle.test_disabled ? t('common.yes') : t('common.no'),
                icon: <ToolOutlined />,
              },
            ]}
          />

          {/* Maintenance — 2 columns compact */}
          <CompactDetailCard
            title="维护信息"
            columns={2}
            items={[
              {
                label: t('pages.vehicles.lastMaintenance'),
                value: vehicle.lastMaintenance || '—',
                icon: <ToolOutlined />,
              },
              {
                label: t('pages.vehicles.nextMaintenance'),
                value: vehicle.nextMaintenance || '—',
                icon: <ClockCircleOutlined />,
              },
            ]}
          />

          {/* Extended metadata — single dense row */}
          <CompactDetailCard
            title="扩展元数据"
            columns={3}
            items={[
              {
                label: 'ID',
                value: <InlineTag>{vehicle.id}</InlineTag>,
              },
              {
                label: t('pages.vehicles.CAP'),
                value: vehicle.CAP ?? '—',
              },
              {
                label: t('pages.vehicles.mstats'),
                value: Array.isArray(vehicle.mstats) && vehicle.mstats.length > 0
                  ? vehicle.mstats.join(', ')
                  : '—',
              },
              {
                label: t('pages.vehicles.fieldLink'),
                value: vehicle.field_link || '—',
              },
              {
                label: t('pages.vehicles.dailyMids'),
                value: Array.isArray(vehicle.daily_mids) && vehicle.daily_mids.length > 0
                  ? vehicle.daily_mids.join(', ')
                  : '—',
              },
              {
                label: 'Hostname',
                value: vehicle.hostname || '—',
              },
            ]}
          />
        </Space>
      </DetailContent>

      <ActionBar>
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          onClick={() => onStatusChange(vehicle.id, 'active')}
          disabled={vehicle.status === 'active'}
        >
          {t('pages.vehicles.activate')}
        </Button>
        <Button
          size="small"
          icon={<ToolOutlined />}
          onClick={() => onMaintenance(vehicle.id)}
          disabled={vehicle.status === 'maintenance'}
        >
          {t('pages.vehicles.scheduleMaintenance')}
        </Button>
        <Button
          size="small"
          icon={<HistoryOutlined />}
          onClick={() => onStatusChange(vehicle.id, 'offline')}
          disabled={vehicle.status === 'offline'}
        >
          {t('pages.vehicles.setOffline')}
        </Button>
      </ActionBar>
    </div>
  );
};

export default VehicleDetails;

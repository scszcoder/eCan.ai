import React, { useRef } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Space, Button, Statistic } from 'antd';
import { ClusterOutlined, CheckCircleOutlined, EnvironmentOutlined, ThunderboltOutlined, ToolOutlined, ClockCircleOutlined, PlusOutlined, HistoryOutlined } from '@ant-design/icons';
import type { Vehicle } from '@/stores';
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
  padding: 24px;
  background: rgba(0, 0, 0, 0.2);
`;

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
    return (
        <DetailContent ref={scrollContainerRef}>
            <Space direction="vertical" style={{ width: '100%' }} size={24}>
                {/* 新增：BaseInformation卡片 */}
                <DetailCard
                    title={t('pages.vehicles.basicInfo')}
                    columns={2}
                    items={[
                        { label: 'ID', value: vehicle.id },
                        { label: 'IP', value: vehicle.ip },
                        { label: t('pages.vehicles.arch'), value: vehicle.arch },
                        { label: t('pages.vehicles.os'), value: vehicle.os },
                        { label: t('pages.vehicles.botIds'), value: vehicle.bot_ids?.length ?? 0 },
                        { label: t('pages.vehicles.functions'), value: vehicle.functions },
                        { label: t('pages.vehicles.testDisabled'), value: vehicle.test_disabled ? t('common.yes') : t('common.no') },
                        { label: t('pages.vehicles.lastUpdateTime'), value: vehicle.last_update_time },
                        { label: t('pages.vehicles.CAP'), value: vehicle.CAP },
                        { label: t('pages.vehicles.mstats'), value: Array.isArray(vehicle.mstats) ? vehicle.mstats.join(', ') : '' },
                        { label: t('pages.vehicles.fieldLink'), value: vehicle.field_link },
                        { label: t('pages.vehicles.dailyMids'), value: Array.isArray(vehicle.daily_mids) ? vehicle.daily_mids.join(', ') : '' },
                    ]}
                />
                {/* 原有车辆Information卡片 */}
                <DetailCard
                    title={t('pages.vehicles.vehicleInformation')}
                    columns={2}
                    items={[
                        {
                            label: t('pages.vehicles.name'),
                            value: vehicle.name,
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.vehicles.type'),
                            value: vehicle.type,
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.vehicles.statusLabel'),
                            value: <StatusTag status={vehicle.status} />,
                            icon: <CheckCircleOutlined />,
                        },
                        {
                            label: t('pages.vehicles.location'),
                            value: vehicle.location,
                            icon: <EnvironmentOutlined />,
                        },
                    ]}
                />
                {/* Performance指标卡片 */}
                <DetailCard
                    title={t('pages.vehicles.performanceMetrics')}
                    columns={2}
                    items={[
                        {
                            label: t('pages.vehicles.batteryLevel'),
                            value: (
                                <Statistic
                                    value={vehicle.battery ?? 0}
                                    suffix="%"
                                    prefix={<ThunderboltOutlined />}
                                    valueStyle={{ color: vehicle.battery && vehicle.battery < 20 ? '#cf1322' : '#3f8600' }}
                                />
                            ),
                            icon: <ThunderboltOutlined />,
                        },
                        {
                            label: 'CPU使用率',
                            value: (
                                <Statistic
                                    value={vehicle.cpuUsage ?? 0}
                                    suffix="%"
                                    precision={1}
                                    valueStyle={{ color: vehicle.cpuUsage && vehicle.cpuUsage > 80 ? '#cf1322' : '#3f8600' }}
                                />
                            ),
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: '内存使用率',
                            value: (
                                <Statistic
                                    value={vehicle.memoryUsage ?? 0}
                                    suffix="%"
                                    precision={1}
                                    valueStyle={{ color: vehicle.memoryUsage && vehicle.memoryUsage > 80 ? '#cf1322' : '#3f8600' }}
                                />
                            ),
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: '磁盘使用率',
                            value: (
                                <Statistic
                                    value={vehicle.diskUsage ?? 0}
                                    suffix="%"
                                    precision={1}
                                    valueStyle={{ color: vehicle.diskUsage && vehicle.diskUsage > 90 ? '#cf1322' : '#3f8600' }}
                                />
                            ),
                            icon: <ClusterOutlined />,
                        },
                    ]}
                />
                
                {/* 设备Status卡片 */}
                <DetailCard
                    title="设备Status"
                    columns={2}
                    items={[
                        {
                            label: 'NetworkStatus',
                            value: vehicle.networkStatus === 'connected' ? '已Connection' : '未Connection',
                            icon: <EnvironmentOutlined />,
                        },
                        {
                            label: 'RunTime',
                            value: vehicle.uptime ? `${Math.floor(vehicle.uptime / 3600)}小时` : '未知',
                            icon: <ClockCircleOutlined />,
                        },
                        {
                            label: t('pages.vehicles.totalDistance'),
                            value: (
                                <Statistic
                                    value={vehicle.totalDistance ?? 0}
                                    suffix="km"
                                />
                            ),
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.vehicles.currentTask'),
                            value: vehicle.currentTask || '无',
                            icon: <ToolOutlined />,
                        },
                    ]}
                />
                
                {/* MaintenanceInformation卡片 */}
                <DetailCard
                    title="MaintenanceInformation"
                    items={[
                        {
                            label: t('pages.vehicles.lastMaintenance'),
                            value: vehicle.lastMaintenance || '未记录',
                            icon: <ToolOutlined />, 
                        },
                        {
                            label: t('pages.vehicles.nextMaintenance'),
                            value: vehicle.nextMaintenance || '未安排',
                            icon: <ClockCircleOutlined />, 
                        },
                    ]}
                />
                <Space>
                    <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={() => onStatusChange(vehicle.id, 'active')}
                        disabled={vehicle.status === 'active'}
                    >
                        {t('pages.vehicles.activate')}
                    </Button>
                    <Button 
                        icon={<ToolOutlined />}
                        onClick={() => onMaintenance(vehicle.id)}
                        disabled={vehicle.status === 'maintenance'}
                    >
                        {t('pages.vehicles.scheduleMaintenance')}
                    </Button>
                    <Button 
                        icon={<HistoryOutlined />}
                        onClick={() => onStatusChange(vehicle.id, 'offline')}
                        disabled={vehicle.status === 'offline'}
                    >
                        {t('pages.vehicles.setOffline')}
                    </Button>
                </Space>
            </Space>
        </DetailContent>
    );
};

export default VehicleDetails; 
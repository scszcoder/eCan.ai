import React from 'react';
import { Space, Button, Statistic } from 'antd';
import { ClusterOutlined, CheckCircleOutlined, EnvironmentOutlined, ThunderboltOutlined, ToolOutlined, ClockCircleOutlined, PlusOutlined, HistoryOutlined } from '@ant-design/icons';
import { Vehicle } from './types';
import StatusTag from '../../components/Common/StatusTag';
import DetailCard from '../../components/Common/DetailCard';
import styled from '@emotion/styled';

interface VehicleDetailsProps {
    vehicle?: Vehicle;
    onStatusChange: (id: number, status: Vehicle['status']) => void;
    onMaintenance: (id: number) => void;
    t: any;
}

const DetailContent = styled.div`
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 16px;
`;

const VehicleDetails: React.FC<VehicleDetailsProps> = ({ vehicle, onStatusChange, onMaintenance, t }) => {
    if (!vehicle) {
        return <span style={{ color: '#888' }}>{t('pages.vehicles.selectVehicle')}</span>;
    }
    return (
        <DetailContent>
            <Space direction="vertical" style={{ width: '100%' }}>
                {/* 新增：基础信息卡片 */}
                <DetailCard
                    title={t('pages.vehicles.basicInfo')}
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
                {/* 原有车辆信息卡片 */}
                <DetailCard
                    title={t('pages.vehicles.vehicleInformation')}
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
                {/* 原有性能指标卡片 */}
                <DetailCard
                    title={t('pages.vehicles.performanceMetrics')}
                    items={[
                        {
                            label: t('pages.vehicles.batteryLevel'),
                            value: (
                                <Statistic
                                    value={vehicle.battery ?? 0}
                                    suffix="%"
                                    prefix={<ThunderboltOutlined />}
                                />
                            ),
                            icon: <ThunderboltOutlined />, 
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
                            label: t('pages.vehicles.lastMaintenance'),
                            value: vehicle.lastMaintenance,
                            icon: <ToolOutlined />, 
                        },
                        {
                            label: t('pages.vehicles.nextMaintenance'),
                            value: vehicle.nextMaintenance,
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
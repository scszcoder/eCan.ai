import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Typography, Space, Tag, Alert, Skeleton, Button } from 'antd';
import { 
    LaptopOutlined, 
    ThunderboltOutlined, 
    ScheduleOutlined, 
    ToolOutlined, 
    SettingOutlined, 
    TeamOutlined,
    RocketOutlined,
    BulbOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    ArrowRightOutlined,
    PlusOutlined,
    SyncOutlined
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppDataStore } from '../../stores/appDataStore';
import { useAgentStore } from '../../stores/agentStore';
import { useTaskStore } from '../../stores/domain/taskStore';
import { useSkillStore } from '../../stores/domain/skillStore';
import { useVehicleStore } from '../../stores/domain/vehicleStore';
import { storeSyncManager } from '../../stores/sync/syncManager';
import { useToolStore } from '../../stores/toolStore';
import { useUserStore } from '../../stores/userStore';
import { logger } from '@/utils/logger';

const { Text, Title, Paragraph } = Typography;

interface DataCardProps {
    title: string;
    value: number | string;
    icon: React.ReactNode;
    color: string;
    loading: boolean;
    gradient?: string;
    trend?: 'up' | 'down' | 'stable';
    trendValue?: string;
    onClick?: () => void;
}

const DataCard: React.FC<DataCardProps> = ({ 
    title, 
    value, 
    icon, 
    color, 
    loading, 
    gradient,
    trend,
    trendValue,
    onClick 
}) => {
    const cardStyle: React.CSSProperties = {
        background: gradient || `linear-gradient(135deg, ${color}18 0%, ${color}08 100%)`,
        border: `1px solid ${color}40`,
        borderRadius: '12px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.2s ease',
        overflow: 'hidden',
        position: 'relative',
        boxShadow: `
            0 4px 12px rgba(0, 0, 0, 0.25),
            0 8px 24px rgba(0, 0, 0, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 0.08),
            inset 0 0 0 1px ${color}10
        `,
    };

    const iconWrapperStyle: React.CSSProperties = {
        position: 'absolute',
        right: '16px',
        top: '16px',
        fontSize: '32px',
        opacity: 0.15,
        color: color,
    };

    return (
        <Card 
            hoverable={!!onClick}
            style={cardStyle}
            styles={{ body: { padding: '20px' } }}
            onClick={onClick}
        >
            <Skeleton loading={loading} active paragraph={{ rows: 1 }}>
                <div style={{ position: 'relative', zIndex: 1 }}>
                    <div style={iconWrapperStyle}>{icon}</div>
                    <div style={{ marginBottom: '8px' }}>
                        <Text style={{ fontSize: 'var(--font-size-base)', color: 'rgba(255,255,255,0.65)' }}>
                            {title}
                        </Text>
                    </div>
                    <div style={{ marginBottom: '4px' }}>
                        <Text strong style={{ fontSize: 'var(--font-size-3xl)', color: 'rgba(255,255,255,0.95)' }}>
                            {value}
                        </Text>
                    </div>
                    {trend && trendValue && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Text style={{ fontSize: 'var(--font-size-sm)', color: color }}>
                                {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'} {trendValue}
                            </Text>
                        </div>
                    )}
                </div>
            </Skeleton>
        </Card>
    );
};

// 在ComponentExternalRegister stores，只Execute一次
let storesRegistered = false;
const registerStores = () => {
    if (!storesRegistered) {
        storeSyncManager.register('agent', useAgentStore);
        storeSyncManager.register('task', useTaskStore);
        storeSyncManager.register('skill', useSkillStore);
        storeSyncManager.register('vehicle', useVehicleStore);
        storesRegistered = true;
        logger.info('[Dashboard] Stores registered:', storeSyncManager.getRegisteredStores());
    }
};

const Dashboard: React.FC = () => {
    const { t } = useTranslation();
    const username = useUserStore((state) => state.username);
    const [syncError, setSyncError] = useState<string | null>(null);
    const [isSyncing, setIsSyncing] = useState(false);

    // 从新的 stores GetData
    const agents = useAgentStore((state) => state.items);
    const agentsLoading = useAgentStore((state) => state.loading);

    const skills = useSkillStore((state) => state.items);
    const skillsLoading = useSkillStore((state) => state.loading);

    const tasks = useTaskStore((state) => state.items);
    const tasksLoading = useTaskStore((state) => state.loading);

    const vehicles = useVehicleStore((state) => state.items);
    const vehiclesLoading = useVehicleStore((state) => state.loading);

    const tools = useToolStore((state) => state.tools);
    const toolsLoading = useToolStore((state) => state.loading);

    // 从 appDataStore Get全局Status
    const appDataLoading = useAppDataStore((state) => state.isLoading);
    const initialized = useAppDataStore((state) => state.initialized);

    // 综合 loading Status
    const isLoading = isSyncing || agentsLoading || skillsLoading || tasksLoading || vehiclesLoading || toolsLoading || appDataLoading;

    useEffect(() => {
        const syncData = async () => {
            if (!username) {
                logger.debug('[Dashboard] No username, skipping sync');
                return;
            }

            // 确保 stores 已Register（只会Execute一次）
            registerStores();

            logger.info('[Dashboard] Starting data synchronization...');
            setIsSyncing(true);
            setSyncError(null);

            try {
                // 统一SyncAllData
                const results = await storeSyncManager.syncAll(username, {
                    parallel: true,  // 并行Sync，提高Performance
                    force: false,    // 使用Cache
                    timeout: 30000,  // 30秒Timeout
                });

                logger.info('[Dashboard] Sync completed:', results);

                // Check是否有Failed的Sync
                const failed = results.filter(r => !r.success);
                if (failed.length > 0) {
                    const errorMsg = `Failed to sync: ${failed.map(f => f.storeName).join(', ')}`;
                    logger.error('[Dashboard] Sync errors:', failed);
                    setSyncError(errorMsg);
                } else {
                    logger.info('[Dashboard] All stores synced successfully');
                }

                // SyncSuccess后的统计
                const successCount = results.filter(r => r.success).length;
                const totalDuration = results.reduce((sum, r) => sum + (r.duration || 0), 0);
                logger.info(`[Dashboard] Synced ${successCount}/${results.length} stores in ${totalDuration}ms`);

            } catch (err) {
                const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
                logger.error('[Dashboard] Sync error:', errorMessage);
                setSyncError(errorMessage);
            } finally {
                setIsSyncing(false);
            }
        };

        syncData();
    }, [username]);

    const dataCards = [
        { 
            title: t("pages.dashboard.agentsCount"), 
            value: (agents || []).length, 
            icon: <TeamOutlined />, 
            color: '#52c41a',
            gradient: 'linear-gradient(135deg, #52c41a20 0%, #52c41a05 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.active"),
        },
        { 
            title: t("pages.dashboard.skillsCount"), 
            value: (skills || []).length, 
            icon: <ThunderboltOutlined />, 
            color: '#1890ff',
            gradient: 'linear-gradient(135deg, #1890ff20 0%, #1890ff05 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.available"),
        },
        { 
            title: t("pages.dashboard.toolsCount"), 
            value: (tools || []).length, 
            icon: <ToolOutlined />, 
            color: '#722ed1',
            gradient: 'linear-gradient(135deg, #722ed120 0%, #722ed105 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.ready"),
        },
        { 
            title: t("pages.dashboard.tasksCount"), 
            value: (tasks || []).length, 
            icon: <ScheduleOutlined />, 
            color: '#fa8c16',
            gradient: 'linear-gradient(135deg, #fa8c1620 0%, #fa8c1605 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.pending"),
        },
        { 
            title: t("pages.dashboard.vehiclesCount"), 
            value: (vehicles || []).length, 
            icon: <LaptopOutlined />, 
            color: '#eb2f96',
            gradient: 'linear-gradient(135deg, #eb2f9620 0%, #eb2f9605 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.connected"),
        },
        { 
            title: t("pages.dashboard.systemStatus"), 
            value: initialized ? t("pages.dashboard.statusOnline") : t("pages.dashboard.statusOffline"), 
            icon: <SettingOutlined />, 
            color: initialized ? '#52c41a' : '#ff4d4f',
            gradient: initialized 
                ? 'linear-gradient(135deg, #52c41a20 0%, #52c41a05 100%)'
                : 'linear-gradient(135deg, #ff4d4f20 0%, #ff4d4f05 100%)',
            trend: 'stable' as const,
            trendValue: initialized ? t("pages.dashboard.healthy") : t("pages.dashboard.offline"),
        }
    ];

    if (syncError) {
        return (
            <Alert
                message={t("pages.dashboard.errorTitle")}
                description={syncError}
                type="error"
                showIcon
                closable
                onClose={() => setSyncError(null)}
            />
        );
    }

    return (
        <div style={{ padding: '8px' }}>
            {/* Hero Section */}
            <div style={{ 
                marginBottom: '32px',
                background: 'linear-gradient(135deg, rgba(24, 144, 255, 0.1) 0%, rgba(114, 46, 209, 0.05) 100%)',
                borderRadius: '16px',
                padding: '32px',
                border: '1px solid rgba(255, 255, 255, 0.1)'
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <Title level={2} style={{ margin: 0, color: 'rgba(255, 255, 255, 0.95)' }}>
                            <RocketOutlined style={{ marginRight: '12px', color: '#1890ff' }} />
                            {t('pages.dashboard.welcome')}, {username || t('common.agent')}
                        </Title>
                        <Paragraph style={{ margin: '8px 0 0 0', fontSize: '15px', color: 'rgba(255, 255, 255, 0.65)' }}>
                            {t('pages.dashboard.subtitle')}
                        </Paragraph>
                    </div>
                    <Space size="middle">
                        <Button 
                            type="primary" 
                            icon={<PlusOutlined />}
                            size="large"
                            style={{ borderRadius: '8px' }}
                        >
                            {t('pages.dashboard.quickStart')}
                        </Button>
                        <Button 
                            icon={<SyncOutlined spin={isSyncing} />}
                            size="large"
                            style={{ borderRadius: '8px' }}
                            onClick={() => window.location.reload()}
                        >
                            {t('common.refresh')}
                        </Button>
                    </Space>
                </div>
            </div>

            {/* Stats Grid */}
            <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
                {dataCards.map((card, index) => (
                    <Col xs={24} sm={12} lg={8} xl={4} key={index}>
                        <DataCard {...card} loading={isLoading} />
                    </Col>
                ))}
            </Row>

            {/* Main Content Grid */}
            <Row gutter={[16, 16]}>
                {/* Active Agents Section */}
                <Col xs={24} lg={12}>
                    <Card 
                        title={
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <TeamOutlined style={{ color: '#52c41a' }} />
                                <span>{t("pages.dashboard.activeAgents")}</span>
                            </div>
                        }
                        extra={
                            <Button type="link" icon={<ArrowRightOutlined />}>
                                {t('pages.dashboard.viewAll')}
                            </Button>
                        }
                        style={{ 
                            borderRadius: '12px',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            height: '100%'
                        }}
                        styles={{ body: { minHeight: '200px' } }}
                    >
                        <Skeleton loading={isLoading} active paragraph={{ rows: 3 }}>
                            {(agents || []).length > 0 ? (
                                <div>
                                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                                        {(agents || []).slice(0, 4).map((agent: any) => (
                                            <div 
                                                key={agent.card?.id || agent.id}
                                                style={{
                                                    padding: '12px',
                                                    background: 'rgba(255, 255, 255, 0.03)',
                                                    borderRadius: '8px',
                                                    border: '1px solid rgba(255, 255, 255, 0.05)',
                                                    display: 'flex',
                                                    justifyContent: 'space-between',
                                                    alignItems: 'center',
                                                    transition: 'all 0.2s',
                                                    cursor: 'pointer'
                                                }}
                                                onMouseEnter={(e) => {
                                                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                                                    e.currentTarget.style.borderColor = 'rgba(82, 196, 26, 0.3)';
                                                }}
                                                onMouseLeave={(e) => {
                                                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                                                    e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.05)';
                                                }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                                    <div style={{
                                                        width: '8px',
                                                        height: '8px',
                                                        borderRadius: '50%',
                                                        background: '#52c41a',
                                                        boxShadow: '0 0 8px rgba(82, 196, 26, 0.6)'
                                                    }} />
                                                    <Text strong style={{ color: 'rgba(255, 255, 255, 0.85)' }}>
                                                        {agent.card?.name || agent.name}
                                                    </Text>
                                                </div>
                                                <Tag color="green" style={{ margin: 0 }}>
                                                    {t('pages.dashboard.active')}
                                                </Tag>
                                            </div>
                                        ))}
                                    </Space>
                                    {(agents || []).length > 4 && (
                                        <div style={{ marginTop: '12px', textAlign: 'center' }}>
                                            <Text type="secondary">
                                                +{agents.length - 4} {t("pages.dashboard.more")}
                                            </Text>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div style={{ textAlign: 'center', padding: '40px 0' }}>
                                    <BulbOutlined style={{ fontSize: '48px', color: 'rgba(255, 255, 255, 0.25)' }} />
                                    <div style={{ marginTop: '16px', color: 'rgba(255, 255, 255, 0.45)' }}>
                                        {t('pages.dashboard.noAgents')}
                                    </div>
                                </div>
                            )}
                        </Skeleton>
                    </Card>
                </Col>

                {/* Recent Tasks Section */}
                <Col xs={24} lg={12}>
                    <Card 
                        title={
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <ScheduleOutlined style={{ color: '#fa8c16' }} />
                                <span>{t("pages.dashboard.recentTasks")}</span>
                            </div>
                        }
                        extra={
                            <Button type="link" icon={<ArrowRightOutlined />}>
                                {t('pages.dashboard.viewAll')}
                            </Button>
                        }
                        style={{ 
                            borderRadius: '12px',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            height: '100%'
                        }}
                        styles={{ body: { minHeight: '200px' } }}
                    >
                        <Skeleton loading={isLoading} active paragraph={{ rows: 3 }}>
                            {(tasks || []).length > 0 ? (
                                <div>
                                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                                        {(tasks || []).slice(0, 4).map((task) => {
                                            const isReady = task.state?.top === 'ready';
                                            const statusColor = isReady ? '#52c41a' : '#fa8c16';
                                            const StatusIcon = isReady ? CheckCircleOutlined : ClockCircleOutlined;
                                            
                                            return (
                                                <div 
                                                    key={task.id}
                                                    style={{
                                                        padding: '12px',
                                                        background: 'rgba(255, 255, 255, 0.03)',
                                                        borderRadius: '8px',
                                                        border: '1px solid rgba(255, 255, 255, 0.05)',
                                                        transition: 'all 0.2s',
                                                        cursor: 'pointer'
                                                    }}
                                                    onMouseEnter={(e) => {
                                                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                                                        e.currentTarget.style.borderColor = `${statusColor}30`;
                                                    }}
                                                    onMouseLeave={(e) => {
                                                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                                                        e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.05)';
                                                    }}
                                                >
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                                                            <StatusIcon style={{ color: statusColor, fontSize: '16px' }} />
                                                            <Text strong style={{ color: 'rgba(255, 255, 255, 0.85)' }}>
                                                                {task.skill || task.name || 'Unknown'}
                                                            </Text>
                                                        </div>
                                                        <Tag color={isReady ? 'success' : 'warning'} style={{ margin: 0 }}>
                                                            {isReady ? t('pages.dashboard.ready') : t('pages.dashboard.pending')}
                                                        </Tag>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </Space>
                                    {(tasks || []).length > 4 && (
                                        <div style={{ marginTop: '12px', textAlign: 'center' }}>
                                            <Text type="secondary">
                                                +{tasks.length - 4} {t("pages.dashboard.more")}
                                            </Text>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div style={{ textAlign: 'center', padding: '40px 0' }}>
                                    <ScheduleOutlined style={{ fontSize: '48px', color: 'rgba(255, 255, 255, 0.25)' }} />
                                    <div style={{ marginTop: '16px', color: 'rgba(255, 255, 255, 0.45)' }}>
                                        {t('pages.dashboard.noTasks')}
                                    </div>
                                </div>
                            )}
                        </Skeleton>
                    </Card>
                </Col>
            </Row>

            {/* Quick Actions */}
            <Card 
                title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <ThunderboltOutlined style={{ color: '#1890ff' }} />
                        <span>{t('pages.dashboard.quickActions')}</span>
                    </div>
                }
                style={{ 
                    marginTop: '16px',
                    borderRadius: '12px',
                    border: '1px solid rgba(255, 255, 255, 0.1)'
                }}
            >
                <Row gutter={[16, 16]}>
                    <Col xs={24} sm={12} md={6}>
                        <Button 
                            block 
                            size="large"
                            icon={<PlusOutlined />}
                            style={{ 
                                height: '60px',
                                borderRadius: '8px',
                                background: 'rgba(82, 196, 26, 0.1)',
                                borderColor: 'rgba(82, 196, 26, 0.3)',
                                color: '#52c41a'
                            }}
                        >
                            {t('pages.dashboard.createAgent')}
                        </Button>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                        <Button 
                            block 
                            size="large"
                            icon={<ThunderboltOutlined />}
                            style={{ 
                                height: '60px',
                                borderRadius: '8px',
                                background: 'rgba(24, 144, 255, 0.1)',
                                borderColor: 'rgba(24, 144, 255, 0.3)',
                                color: '#1890ff'
                            }}
                        >
                            {t('pages.dashboard.createSkill')}
                        </Button>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                        <Button 
                            block 
                            size="large"
                            icon={<ScheduleOutlined />}
                            style={{ 
                                height: '60px',
                                borderRadius: '8px',
                                background: 'rgba(250, 140, 22, 0.1)',
                                borderColor: 'rgba(250, 140, 22, 0.3)',
                                color: '#fa8c16'
                            }}
                        >
                            {t('pages.dashboard.createTask')}
                        </Button>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                        <Button 
                            block 
                            size="large"
                            icon={<SettingOutlined />}
                            style={{ 
                                height: '60px',
                                borderRadius: '8px',
                                background: 'rgba(114, 46, 209, 0.1)',
                                borderColor: 'rgba(114, 46, 209, 0.3)',
                                color: '#722ed1'
                            }}
                        >
                            {t('pages.dashboard.settings')}
                        </Button>
                    </Col>
                </Row>
            </Card>
        </div>
    );
};

export default Dashboard; 
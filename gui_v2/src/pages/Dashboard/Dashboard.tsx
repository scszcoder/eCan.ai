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
    /** Readable variant of `color` for small text; `color` tints surfaces and
        is often too bright to serve as a foreground on a light card. */
    textColor?: string;
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
    textColor,
    loading, 
    gradient,
    trend,
    trendValue,
    onClick 
}) => {
    // Tiles keep their semantic colour, but the surface itself is the card
    // token so light theme shows a real white card with a soft tint, not a
    // grey wash. The previous inline shadow was a fixed dark rgba(0,0,0,.25)
    // which read as a smudge on a light page; --shadow-md is theme-aware.
    const cardStyle: React.CSSProperties = {
        background: gradient
            || `linear-gradient(135deg, var(--surface-panel) 0%, ${color}14 45%, var(--surface-panel-alt) 100%)`,
        border: `1px solid var(--border-color)`,
        borderLeft: `3px solid ${color}`,
        borderRadius: '12px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.2s ease',
        overflow: 'hidden',
        position: 'relative',
        boxShadow: 'var(--shadow-md)',
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
                        <Text style={{ fontSize: 'var(--font-size-base)', color: 'var(--text-secondary)' }}>
                            {title}
                        </Text>
                    </div>
                    <div style={{ marginBottom: '4px' }}>
                        <Text strong style={{ fontSize: 'var(--font-size-3xl)', color: 'var(--text-primary)' }}>
                            {value}
                        </Text>
                    </div>
                    {trend && trendValue && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Text style={{ fontSize: 'var(--font-size-sm)', color: textColor || color }}>
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
            color: 'var(--success-text)',
            textColor: 'var(--success-text)',
            gradient: 'linear-gradient(135deg, rgba(34, 197, 94, 0.125) 0%, rgba(34, 197, 94, 0.02) 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.active"),
        },
        { 
            title: t("pages.dashboard.skillsCount"), 
            value: (skills || []).length, 
            icon: <ThunderboltOutlined />, 
            color: 'var(--primary-text)',
            gradient: 'linear-gradient(135deg, rgba(59, 130, 246, 0.125) 0%, rgba(59, 130, 246, 0.02) 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.available"),
        },
        { 
            title: t("pages.dashboard.toolsCount"), 
            value: (tools || []).length, 
            icon: <ToolOutlined />, 
            color: 'var(--accent-text)',
            gradient: 'linear-gradient(135deg, rgba(139, 92, 246, 0.125) 0%, rgba(139, 92, 246, 0.02) 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.ready"),
        },
        { 
            title: t("pages.dashboard.tasksCount"), 
            value: (tasks || []).length, 
            icon: <ScheduleOutlined />, 
            color: 'var(--warning-text)',
            gradient: 'linear-gradient(135deg, rgba(251, 191, 36, 0.125) 0%, rgba(251, 191, 36, 0.02) 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.pending"),
        },
        { 
            title: t("pages.dashboard.vehiclesCount"), 
            value: (vehicles || []).length, 
            icon: <LaptopOutlined />, 
            color: 'var(--accent-text)',
            gradient: 'linear-gradient(135deg, rgba(139, 92, 246, 0.125) 0%, rgba(139, 92, 246, 0.02) 100%)',
            trend: 'stable' as const,
            trendValue: t("pages.dashboard.connected"),
        },
        { 
            title: t("pages.dashboard.systemStatus"), 
            value: initialized ? t("pages.dashboard.statusOnline") : t("pages.dashboard.statusOffline"), 
            icon: <SettingOutlined />, 
            color: initialized ? 'var(--success-text)' : 'var(--error-text)',
            textColor: initialized ? 'var(--success-text)' : 'var(--error-text)',
            gradient: initialized 
                ? 'linear-gradient(135deg, rgba(34, 197, 94, 0.125) 0%, rgba(34, 197, 94, 0.02) 100%)'
                : 'linear-gradient(135deg, rgba(239, 68, 68, 0.125) 0%, rgba(239, 68, 68, 0.02) 100%)',
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
        <div className="page-shell">
            {/* Hero Section */}
            <div style={{ 
                marginBottom: '32px',
                background: 'linear-gradient(135deg, rgba(24, 144, 255, 0.1) 0%, rgba(114, 46, 209, 0.05) 100%)',
                borderRadius: '16px',
                padding: '32px',
                border: '1px solid var(--border-color)'
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <Title level={2} style={{ margin: 0, color: 'var(--text-primary)' }}>
                            <RocketOutlined style={{ marginRight: '12px', color: 'var(--primary-text)' }} />
                            {t('pages.dashboard.welcome')}, {username || t('common.agent')}
                        </Title>
                        <Paragraph style={{ margin: '8px 0 0 0', fontSize: '15px', color: 'var(--text-secondary)' }}>
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
                                <TeamOutlined style={{ color: 'var(--success-text)' }} />
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
                            border: '1px solid var(--border-color)',
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
                                                    background: 'var(--surface-panel)',
                                                    borderRadius: '8px',
                                                    border: '1px solid var(--border-color)',
                                                    display: 'flex',
                                                    justifyContent: 'space-between',
                                                    alignItems: 'center',
                                                    transition: 'all 0.2s',
                                                    cursor: 'pointer'
                                                }}
                                                onMouseEnter={(e) => {
                                                    e.currentTarget.style.background = 'var(--surface-subtle-hover)';
                                                    e.currentTarget.style.borderColor = 'var(--success-border)';
                                                }}
                                                onMouseLeave={(e) => {
                                                    e.currentTarget.style.background = 'var(--surface-panel)';
                                                    e.currentTarget.style.borderColor = 'var(--border-color)';
                                                }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                                    <div style={{
                                                        width: '8px',
                                                        height: '8px',
                                                        borderRadius: '50%',
                                                        background: 'var(--success-color)',
                                                        boxShadow: '0 0 8px var(--success-border)'
                                                    }} />
                                                    <Text strong style={{ color: 'var(--text-secondary)' }}>
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
                                    <BulbOutlined style={{ fontSize: '48px', color: 'var(--text-muted)' }} />
                                    <div style={{ marginTop: '16px', color: 'var(--text-tertiary)' }}>
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
                                <ScheduleOutlined style={{ color: 'var(--warning-text)' }} />
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
                            border: '1px solid var(--border-color)',
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
                                            const statusColor = isReady ? 'var(--success-color)' : 'var(--warning-color)';
                                            const StatusIcon = isReady ? CheckCircleOutlined : ClockCircleOutlined;
                                            
                                            return (
                                                <div 
                                                    key={task.id}
                                                    style={{
                                                        padding: '12px',
                                                        background: 'var(--surface-panel)',
                                                        borderRadius: '8px',
                                                        border: '1px solid var(--border-color)',
                                                        transition: 'all 0.2s',
                                                        cursor: 'pointer'
                                                    }}
                                                    onMouseEnter={(e) => {
                                                        e.currentTarget.style.background = 'var(--surface-subtle-hover)';
                                                        e.currentTarget.style.borderColor = `${statusColor}30`;
                                                    }}
                                                    onMouseLeave={(e) => {
                                                        e.currentTarget.style.background = 'var(--surface-panel)';
                                                        e.currentTarget.style.borderColor = 'var(--border-color)';
                                                    }}
                                                >
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                                                            <StatusIcon style={{ color: statusColor, fontSize: '16px' }} />
                                                            <Text strong style={{ color: 'var(--text-secondary)' }}>
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
                                    <ScheduleOutlined style={{ fontSize: '48px', color: 'var(--text-muted)' }} />
                                    <div style={{ marginTop: '16px', color: 'var(--text-tertiary)' }}>
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
                        <ThunderboltOutlined style={{ color: 'var(--primary-text)' }} />
                        <span>{t('pages.dashboard.quickActions')}</span>
                    </div>
                }
                style={{ 
                    marginTop: '16px',
                    borderRadius: '12px',
                    border: '1px solid var(--border-color)'
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
                                background: 'var(--success-bg)',
                                borderColor: 'var(--success-border)',
                                color: 'var(--success-text)'
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
                                color: 'var(--primary-text)'
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
                                color: 'var(--warning-text)'
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
                                color: 'var(--accent-text)'
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
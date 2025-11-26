import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Typography, Space, Tag, Alert, Skeleton } from 'antd';
import { LaptopOutlined, ThunderboltOutlined, ScheduleOutlined, ToolOutlined, SettingOutlined, TeamOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppDataStore } from '../../stores/appDataStore';
import {
  useAgentStore,
  useTaskStore,
  useSkillStore,
  useVehicleStore,
  storeSyncManager
} from '../../stores';
import { useToolStore } from '../../stores/toolStore';
import { useUserStore } from '../../stores/userStore';
import { logger } from '@/utils/logger';

const { Text } = Typography;

interface DataCardProps {
    title: string;
    value: number | string;
    icon: React.ReactNode;
    color: string;
    loading: boolean;
}

const DataCard: React.FC<DataCardProps> = ({ title, value, icon, color, loading }) => (
    <Card size="small">
        <Skeleton loading={loading} active paragraph={{ rows: 1 }}>
            <Statistic
                title={title}
                value={value}
                prefix={icon}
                valueStyle={{ color }}
            />
        </Skeleton>
    </Card>
);

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
        { title: t("pages.dashboard.agentsCount"), value: (agents || []).length, icon: <TeamOutlined />, color: '#3f8600' },
        { title: t("pages.dashboard.skillsCount"), value: (skills || []).length, icon: <ThunderboltOutlined />, color: '#1890ff' },
        { title: t("pages.dashboard.toolsCount"), value: (tools || []).length, icon: <ToolOutlined />, color: '#722ed1' },
        { title: t("pages.dashboard.tasksCount"), value: (tasks || []).length, icon: <ScheduleOutlined />, color: '#fa8c16' },
        { title: t("pages.dashboard.vehiclesCount"), value: (vehicles || []).length, icon: <LaptopOutlined />, color: '#eb2f96' },
        { title: t("pages.dashboard.systemStatus"), value: initialized ? t("pages.dashboard.statusOnline") : t("pages.dashboard.statusOffline"), icon: <SettingOutlined />, color: initialized ? '#52c41a' : '#ff4d4f' }
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
        <div>
            <div style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px', color: 'rgba(248, 250, 252, 0.95)', marginBottom: '16px' }}>
              {t('pages.dashboard.title')}
            </div>

            {/* Data概览部分 */}
            <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
                <Col span={24}>
                    <Card title={t("pages.dashboard.overviewTitle")} size="small">
                        <Row gutter={[16, 16]}>
                            {dataCards.map((card, index) => (
                                <Col span={4} key={index}>
                                    <DataCard {...card} loading={isLoading} />
                                </Col>
                            ))}
                        </Row>

                        {/* 活跃代理List */}
                        <Skeleton loading={isLoading} active paragraph={{ rows: 2 }} style={{ marginTop: '16px' }}>
                            {(agents || []).length > 0 && (
                                <div style={{ marginTop: '16px' }}>
                                    <Text strong>{t("pages.dashboard.activeAgents")}</Text>
                                    <Space wrap style={{ marginTop: '8px' }}>
                                        {(agents || []).slice(0, 5).map((agent: any) => (
                                            <Tag key={agent.card?.id || agent.id} color="blue">
                                                {agent.card?.name || agent.name}
                                            </Tag>
                                        ))}
                                        {(agents || []).length > 5 && (
                                            <Tag color="default">+{agents.length - 5} {t("pages.dashboard.more")}</Tag>
                                        )}
                                    </Space>
                                </div>
                            )}
                        </Skeleton>

                        {/* 最近任务 */}
                        <Skeleton loading={isLoading} active paragraph={{ rows: 2 }} style={{ marginTop: '16px' }}>
                            {(tasks || []).length > 0 && (
                                <div style={{ marginTop: '16px' }}>
                                    <Text strong>{t("pages.dashboard.recentTasks")}</Text>
                                    <Space wrap style={{ marginTop: '8px' }}>
                                        {(tasks || []).slice(0, 3).map((task) => (
                                            <Tag 
                                                key={task.id} 
                                                color={task.state?.top === 'ready' ? 'green' : 'orange'}
                                            >
                                                {task.skill || task.name || 'Unknown'}
                                            </Tag>
                                        ))}
                                        {(tasks || []).length > 3 && (
                                            <Tag color="default">+{tasks.length - 3} {t("pages.dashboard.more")}</Tag>
                                        )}
                                    </Space>
                                </div>
                            )}
                        </Skeleton>
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default Dashboard; 
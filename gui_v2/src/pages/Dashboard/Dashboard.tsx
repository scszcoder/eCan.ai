import React, { useEffect } from 'react';
import { Card, Row, Col, Statistic, Typography, Space, Tag, Alert, Skeleton } from 'antd';
import { CarOutlined, RobotOutlined, ScheduleOutlined, ToolOutlined, SettingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppDataStore, AppData } from '../../stores/appDataStore';
import { useUserStore } from '../../stores/userStore';
import { get_ipc_api } from '../../services/ipc_api';
import { APIResponse } from '../../services/ipc/api';
import { logger } from '@/utils/logger';
import { AppDataStoreHandler } from '@/stores/AppDataStoreHandler';

const { Title, Text } = Typography;

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

const Dashboard: React.FC = () => {
    const { t } = useTranslation();
    const username = useUserStore((state) => state.username);
    const { 
        agents, 
        skills, 
        tools, 
        tasks, 
        vehicles, 
        settings,
        isLoading,
        error,
        setLoading,
        setError,
    } = useAppDataStore();

    useEffect(() => {
        const fetchData = async () => {
            if (!username) return;

            setLoading(true);
            setError(null);
            try {
                // await new Promise(resolve => setTimeout(resolve, 6000));
                const appData = await get_ipc_api().getAll(username);
                
                // 将API返回的数据保存到store中
                console.log('appData', appData);
                if (appData?.data) {
                    logger.info('Get all system data successful');
                    AppDataStoreHandler.updateStore(appData.data as any);
                    logger.info('system data 数据已保存到store中');
                 } else {
                    logger.error('Get all system data failed');
                 }
            } catch (err) {
                setError(err instanceof Error ? err.message : 'An unknown error occurred');
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [username, setLoading, setError]);

    const dataCards = [
        { title: t("pages.dashboard.agentsCount"), value: (agents || []).length, icon: <RobotOutlined />, color: '#3f8600' },
        { title: t("pages.dashboard.skillsCount"), value: (skills || []).length, icon: <ToolOutlined />, color: '#1890ff' },
        { title: t("pages.dashboard.toolsCount"), value: (tools || []).length, icon: <SettingOutlined />, color: '#722ed1' },
        { title: t("pages.dashboard.tasksCount"), value: (tasks || []).length, icon: <ScheduleOutlined />, color: '#fa8c16' },
        { title: t("pages.dashboard.vehiclesCount"), value: (vehicles || []).length, icon: <CarOutlined />, color: '#eb2f96' },
        { title: t("pages.dashboard.systemStatus"), value: settings ? t("pages.dashboard.statusOnline") : t("pages.dashboard.statusOffline"), icon: <SettingOutlined />, color: settings ? '#52c41a' : '#ff4d4f' }
    ];

    if (error) {
        return <Alert message={t("pages.dashboard.errorTitle")} description={error} type="error" showIcon />;
    }

    return (
        <div>
            <Title level={5} style={{ color: 'white' }}>
              {t('pages.dashboard.welcome')}
            </Title>

            {/* 数据概览部分 */}
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

                        {/* 活跃代理列表 */}
                        <Skeleton loading={isLoading} active paragraph={{ rows: 2 }} style={{ marginTop: '16px' }}>
                            {(agents || []).length > 0 && (
                                <div style={{ marginTop: '16px' }}>
                                    <Text strong>{t("pages.dashboard.activeAgents")}</Text>
                                    <Space wrap style={{ marginTop: '8px' }}>
                                        {(agents || []).slice(0, 5).map((agent) => (
                                            <Tag key={agent.card.id} color="blue">
                                                {agent.card.name}
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
                                                color={task.state.top === 'ready' ? 'green' : 'orange'}
                                            >
                                                {task.skill}
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
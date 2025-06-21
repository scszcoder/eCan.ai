import React, { useState, useCallback, useEffect } from 'react';
import { Card, Row, Col, Statistic, Typography, Space, Tag } from 'antd';
import { CarOutlined, TeamOutlined, RobotOutlined, ScheduleOutlined, ToolOutlined, SettingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { IPCAPI } from '@/services/ipc/api';
import { useSystemStore } from '../../stores/systemStore';

const { Title, Text } = Typography;

// 仪表盘数据接口
export interface DashboardStats {
    overview: number;
    statistics: number;
    recentActivities: number;
    quickActions: number;
}

// 创建事件总线
const dashboardEventBus = {
    listeners: new Set<(data: DashboardStats) => void>(),
    subscribe(listener: (data: DashboardStats) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    },
    emit(data: DashboardStats) {
        this.listeners.forEach(listener => listener(data));
    }
};

// 导出更新数据的函数
export const updateDashboard = (data: DashboardStats) => {
    dashboardEventBus.emit(data);
};

const Dashboard: React.FC = () => {
    const { t } = useTranslation();
    const [stats, setStats] = useState<DashboardStats>({
        overview: 12,
        statistics: 8,
        recentActivities: 24,
        quickActions: 15
    });

    // 从store获取数据
    const { 
        agents, 
        skills, 
        tools, 
        tasks, 
        vehicles, 
        settings,
        isLoading 
    } = useSystemStore();

    // 监听数据更新
    useEffect(() => {
        const unsubscribe = dashboardEventBus.subscribe((newData) => {
            setStats(newData);
        });
        return () => {
            unsubscribe();
        };
    }, []);

    return (
        <div>
            <Title level={2} style={{ color: 'white' }}>
              {t('pages.dashboard.title')}
            </Title>
            <Title level={4} style={{ color: 'white' }}>
              {t('pages.dashboard.welcome')}
            </Title>
            
            <Row gutter={[16, 16]}>
                <Col span={6}>
                    <Card>
                        <Statistic
                            title={t('pages.dashboard.overview')}
                            value={stats.overview}
                            prefix={<CarOutlined />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic
                            title={t('pages.dashboard.statistics')}
                            value={stats.statistics}
                            prefix={<TeamOutlined />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic
                            title={t('pages.dashboard.recentActivities')}
                            value={stats.recentActivities}
                            prefix={<RobotOutlined />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic
                            title={t('pages.dashboard.quickActions')}
                            value={stats.quickActions}
                            prefix={<ScheduleOutlined />}
                        />
                    </Card>
                </Col>
            </Row>

            {/* 数据概览部分 */}
            <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
                <Col span={24}>
                    <Card title="系统数据概览" size="small">
                        <Row gutter={[16, 16]}>
                            <Col span={4}>
                                <Card size="small">
                                    <Statistic
                                        title="代理数量"
                                        value={agents.length}
                                        prefix={<RobotOutlined />}
                                        valueStyle={{ color: '#3f8600' }}
                                    />
                                </Card>
                            </Col>
                            <Col span={4}>
                                <Card size="small">
                                    <Statistic
                                        title="技能数量"
                                        value={skills.length}
                                        prefix={<ToolOutlined />}
                                        valueStyle={{ color: '#1890ff' }}
                                    />
                                </Card>
                            </Col>
                            <Col span={4}>
                                <Card size="small">
                                    <Statistic
                                        title="工具数量"
                                        value={tools.length}
                                        prefix={<SettingOutlined />}
                                        valueStyle={{ color: '#722ed1' }}
                                    />
                                </Card>
                            </Col>
                            <Col span={4}>
                                <Card size="small">
                                    <Statistic
                                        title="任务数量"
                                        value={tasks.length}
                                        prefix={<ScheduleOutlined />}
                                        valueStyle={{ color: '#fa8c16' }}
                                    />
                                </Card>
                            </Col>
                            <Col span={4}>
                                <Card size="small">
                                    <Statistic
                                        title="车辆数量"
                                        value={vehicles.length}
                                        prefix={<CarOutlined />}
                                        valueStyle={{ color: '#eb2f96' }}
                                    />
                                </Card>
                            </Col>
                            <Col span={4}>
                                <Card size="small">
                                    <Statistic
                                        title="系统状态"
                                        value={settings ? '在线' : '离线'}
                                        valueStyle={{ color: settings ? '#52c41a' : '#ff4d4f' }}
                                    />
                                </Card>
                            </Col>
                        </Row>

                        {/* 活跃代理列表 */}
                        {agents.length > 0 && (
                            <div style={{ marginTop: '16px' }}>
                                <Text strong>活跃代理:</Text>
                                <Space wrap style={{ marginTop: '8px' }}>
                                    {agents.slice(0, 5).map((agent) => (
                                        <Tag key={agent.card.id} color="blue">
                                            {agent.card.name}
                                        </Tag>
                                    ))}
                                    {agents.length > 5 && (
                                        <Tag color="default">+{agents.length - 5} 更多</Tag>
                                    )}
                                </Space>
                            </div>
                        )}

                        {/* 最近任务 */}
                        {tasks.length > 0 && (
                            <div style={{ marginTop: '16px' }}>
                                <Text strong>最近任务:</Text>
                                <Space wrap style={{ marginTop: '8px' }}>
                                    {tasks.slice(0, 3).map((task) => (
                                        <Tag 
                                            key={task.id} 
                                            color={task.state.top === 'ready' ? 'green' : 'orange'}
                                        >
                                            {task.skill}
                                        </Tag>
                                    ))}
                                    {tasks.length > 3 && (
                                        <Tag color="default">+{tasks.length - 3} 更多</Tag>
                                    )}
                                </Space>
                            </div>
                        )}
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default Dashboard; 
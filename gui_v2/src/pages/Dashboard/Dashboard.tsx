import React, { useState, useCallback, useEffect } from 'react';
import { Card, Row, Col, Statistic, Typography } from 'antd';
import { CarOutlined, TeamOutlined, RobotOutlined, ScheduleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {ipc_api} from '../../services/ipc_api';

const { Title } = Typography;

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
        </div>
    );
};

export default Dashboard; 
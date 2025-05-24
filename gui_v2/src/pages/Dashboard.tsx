import React, { useState, useCallback, useEffect } from 'react';
import { Card, Row, Col, Statistic, Typography } from 'antd';
import { CarOutlined, TeamOutlined, RobotOutlined, ScheduleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Title } = Typography;

// 仪表盘数据接口
interface DashboardStats {
    overview: number;
    statistics: number;
    recentActivities: number;
    quickActions: number;
}

// 创建全局更新函数
let updateDashboardData: ((data: DashboardStats) => void) | null = null;

const Dashboard: React.FC = () => {
    const { t } = useTranslation();
    const [stats, setStats] = useState<DashboardStats>({
        overview: 12,
        statistics: 8,
        recentActivities: 24,
        quickActions: 15
    });

    // 更新数据的函数
    const handleUpdateData = useCallback((newData: DashboardStats) => {
        setStats(newData);
    }, []);

    // 初始化 IPC 监听
    useEffect(() => {
        // 将更新函数暴露到全局
        updateDashboardData = handleUpdateData;

        // // 监听 IPC 消息
        // const handleIPCMessage = (event: MessageEvent) => {
        //     try {
        //         const data = JSON.parse(event.data);
        //         if (data.type === 'dashboard_update' && data.stats) {
        //             handleUpdateData(data.stats);
        //         }
        //     } catch (error) {
        //         console.error('Error handling IPC message:', error);
        //     }
        // };

        // // 添加消息监听器
        // window.addEventListener('message', handleIPCMessage);

        // 清理函数
        return () => {
            // window.removeEventListener('message', handleIPCMessage);
            updateDashboardData = null;
        };
    }, [handleUpdateData]);

    return (
        <div>
            <Title level={2}>{t('pages.dashboard.title')}</Title>
            <Title level={4}>{t('pages.dashboard.welcome')}</Title>
            
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

// 导出更新数据的函数
export const updateDashboard = (data: DashboardStats) => {
    if (updateDashboardData) {
        updateDashboardData(data);
    } else {
        console.warn('Dashboard update function not initialized');
    }
};

export default Dashboard; 
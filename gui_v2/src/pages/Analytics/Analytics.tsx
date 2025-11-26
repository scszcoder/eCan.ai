import React, { useState, useCallback, useEffect } from 'react';
import { Card, Row, Col, Statistic, Typography, DatePicker, Select, Space } from 'antd';
import { 
    ArrowUpOutlined, 
    ArrowDownOutlined,
    UserOutlined,
    RobotOutlined,
    LaptopOutlined,
    CheckCircleOutlined,
    ReloadOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { Line, Bar, Pie } from '@ant-design/plots';
import { useTranslation } from 'react-i18next';
import { IPCAPI } from '@/services/ipc/api';

const { Title } = Typography;
const { RangePicker } = DatePicker;
const { Option } = Select;

const AnalyticsContainer = styled.div`
    padding: 24px;
`;

const ChartCard = styled(Card)`
    margin-bottom: 24px;
`;

const StatisticCard = styled(Card)`
    height: 100%;
`;


const Analytics: React.FC = () => {
    const { t } = useTranslation();

    // Task completion data
    const taskData = [
        { date: '2024-01', value: 350 },
        { date: '2024-02', value: 420 },
        { date: '2024-03', value: 380 },
        { date: '2024-04', value: 450 },
        { date: '2024-05', value: 500 },
    ];

    // Agent performance data
    const agentData = [
        { agent: 'Alpha', tasks: 120, efficiency: 95 },
        { agent: 'Beta', tasks: 85, efficiency: 88 },
        { agent: 'Gamma', tasks: 95, efficiency: 92 },
        { agent: 'Delta', tasks: 110, efficiency: 90 },
    ];

    // Resource utilization data
    const resourceData = [
        { type: 'CPU', value: 75 },
        { type: 'Memory', value: 60 },
        { type: 'Storage', value: 45 },
        { type: 'Network', value: 80 },
    ];

    return (
        <AnalyticsContainer>
            <Space style={{ marginBottom: 24 }} size="large">
                <RangePicker />
                <Select defaultValue="week" style={{ width: 120 }}>
                    <Option value="day">{t('pages.analytics.today')}</Option>
                    <Option value="week">{t('pages.analytics.thisWeek')}</Option>
                    <Option value="month">{t('pages.analytics.thisMonth')}</Option>
                    <Option value="year">{t('pages.analytics.thisYear')}</Option>
                </Select>
            </Space>

            <Row gutter={[24, 24]}>
                <Col span={6}>
                    <StatisticCard variant="borderless">
                        <Statistic
                            title={t('pages.analytics.totalTasks')}
                            value={1560}
                            prefix={<CheckCircleOutlined />}
                            valueStyle={{ color: '#3f8600' }}
                        />
                        <div style={{ marginTop: 8 }}>
                            <span style={{ color: '#3f8600' }}>
                                <ArrowUpOutlined /> 12%
                            </span>
                            <span style={{ marginLeft: 8, color: '#999' }}>
                                {t('pages.analytics.vsLastMonth')}
                            </span>
                        </div>
                    </StatisticCard>
                </Col>
                <Col span={6}>
                    <StatisticCard variant="borderless">
                        <Statistic
                            title={t('pages.analytics.activeAgents')}
                            value={12}
                            prefix={<RobotOutlined />}
                            valueStyle={{ color: '#1890ff' }}
                        />
                        <div style={{ marginTop: 8 }}>
                            <span style={{ color: '#3f8600' }}>
                                <ArrowUpOutlined /> 8%
                            </span>
                            <span style={{ marginLeft: 8, color: '#999' }}>
                                {t('pages.analytics.vsLastMonth')}
                            </span>
                        </div>
                    </StatisticCard>
                </Col>
                <Col span={6}>
                    <StatisticCard variant="borderless">
                        <Statistic
                            title={t('pages.analytics.activeVehicles')}
                            value={8}
                            prefix={<LaptopOutlined />}
                            valueStyle={{ color: '#722ed1' }}
                        />
                        <div style={{ marginTop: 8 }}>
                            <span style={{ color: '#cf1322' }}>
                                <ArrowDownOutlined /> 3%
                            </span>
                            <span style={{ marginLeft: 8, color: '#999' }}>
                                {t('pages.analytics.vsLastMonth')}
                            </span>
                        </div>
                    </StatisticCard>
                </Col>
                <Col span={6}>
                    <StatisticCard variant="borderless">
                        <Statistic
                            title={t('pages.analytics.systemUsers')}
                            value={45}
                            prefix={<UserOutlined />}
                            valueStyle={{ color: '#fa8c16' }}
                        />
                        <div style={{ marginTop: 8 }}>
                            <span style={{ color: '#3f8600' }}>
                                <ArrowUpOutlined /> 15%
                            </span>
                            <span style={{ marginLeft: 8, color: '#999' }}>
                                {t('pages.analytics.vsLastMonth')}
                            </span>
                        </div>
                    </StatisticCard>
                </Col>
            </Row>

            <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
                <Col span={16}>
                    <ChartCard variant="borderless" title={t('pages.analytics.taskCompletionTrend')}>
                        <Line
                            data={taskData}
                            xField="date"
                            yField="value"
                            point={{
                                size: 5,
                                shape: 'diamond',
                            }}
                            smooth
                        />
                    </ChartCard>
                </Col>
                <Col span={8}>
                    <ChartCard variant="borderless" title={t('pages.analytics.resourceUtilization')}>
                        <Pie
                            data={resourceData}
                            angleField="value"
                            colorField="type"
                            radius={0.8}
                            legend={{
                                position: 'bottom',
                                itemName: {
                                    formatter: (text: string) => `${text}: ${resourceData.find(item => item.type === text)?.value}%`
                                }
                            }}
                        />
                    </ChartCard>
                </Col>
            </Row>

            <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
                <Col span={24}>
                    <ChartCard variant="borderless" title={t('pages.analytics.agentPerformance')}>
                        <Bar
                            data={agentData}
                            xField="agent"
                            yField="tasks"
                            seriesField="efficiency"
                            isStack
                            label={{
                                position: 'top',
                                style: {
                                    fill: '#fff'
                                }
                            }}
                        />
                    </ChartCard>
                </Col>
            </Row>
        </AnalyticsContainer>
    );
};

export default Analytics; 
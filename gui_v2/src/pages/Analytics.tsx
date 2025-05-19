import React from 'react';
import { Card, Row, Col, Statistic, Typography, DatePicker, Select, Space } from 'antd';
import { 
    ArrowUpOutlined, 
    ArrowDownOutlined,
    UserOutlined,
    RobotOutlined,
    CarOutlined,
    CheckCircleOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { Line, Bar, Pie } from '@ant-design/plots';

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
                    <Option value="day">Today</Option>
                    <Option value="week">This Week</Option>
                    <Option value="month">This Month</Option>
                    <Option value="year">This Year</Option>
                </Select>
            </Space>

            <Row gutter={[24, 24]}>
                <Col span={6}>
                    <StatisticCard variant="borderless">
                        <Statistic
                            title="Total Tasks"
                            value={1560}
                            prefix={<CheckCircleOutlined />}
                            valueStyle={{ color: '#3f8600' }}
                        />
                        <div style={{ marginTop: 8 }}>
                            <span style={{ color: '#3f8600' }}>
                                <ArrowUpOutlined /> 12%
                            </span>
                            <span style={{ marginLeft: 8, color: '#999' }}>
                                vs last month
                            </span>
                        </div>
                    </StatisticCard>
                </Col>
                <Col span={6}>
                    <StatisticCard variant="borderless">
                        <Statistic
                            title="Active Agents"
                            value={12}
                            prefix={<RobotOutlined />}
                            valueStyle={{ color: '#1890ff' }}
                        />
                        <div style={{ marginTop: 8 }}>
                            <span style={{ color: '#3f8600' }}>
                                <ArrowUpOutlined /> 8%
                            </span>
                            <span style={{ marginLeft: 8, color: '#999' }}>
                                vs last month
                            </span>
                        </div>
                    </StatisticCard>
                </Col>
                <Col span={6}>
                    <StatisticCard variant="borderless">
                        <Statistic
                            title="Active Vehicles"
                            value={8}
                            prefix={<CarOutlined />}
                            valueStyle={{ color: '#722ed1' }}
                        />
                        <div style={{ marginTop: 8 }}>
                            <span style={{ color: '#cf1322' }}>
                                <ArrowDownOutlined /> 3%
                            </span>
                            <span style={{ marginLeft: 8, color: '#999' }}>
                                vs last month
                            </span>
                        </div>
                    </StatisticCard>
                </Col>
                <Col span={6}>
                    <StatisticCard variant="borderless">
                        <Statistic
                            title="System Users"
                            value={45}
                            prefix={<UserOutlined />}
                            valueStyle={{ color: '#fa8c16' }}
                        />
                        <div style={{ marginTop: 8 }}>
                            <span style={{ color: '#3f8600' }}>
                                <ArrowUpOutlined /> 15%
                            </span>
                            <span style={{ marginLeft: 8, color: '#999' }}>
                                vs last month
                            </span>
                        </div>
                    </StatisticCard>
                </Col>
            </Row>

            <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
                <Col span={16}>
                    <ChartCard variant="borderless" title="Task Completion Trend">
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
                    <ChartCard variant="borderless" title="Resource Utilization">
                        <Pie
                            data={resourceData}
                            angleField="value"
                            colorField="type"
                            radius={0.8}
                            label={{
                                type: 'outer',
                            }}
                        />
                    </ChartCard>
                </Col>
            </Row>

            <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
                <Col span={24}>
                    <ChartCard variant="borderless" title="Agent Performance">
                        <Bar
                            data={agentData}
                            xField="agent"
                            yField="tasks"
                            seriesField="efficiency"
                            isStack
                            label={{
                                position: 'middle',
                                layout: [
                                    { type: 'interval-adjust-position' },
                                    { type: 'interval-hide-overlap' },
                                    { type: 'adjust-color' },
                                ],
                            }}
                        />
                    </ChartCard>
                </Col>
            </Row>
        </AnalyticsContainer>
    );
};

export default Analytics; 
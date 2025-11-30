import React, { useState } from 'react';
import { Button, Card, Col, Divider, InputNumber, Row, Space, Typography } from 'antd';
import { ReloadOutlined, DollarOutlined, ArrowRightOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

const Account: React.FC = () => {
    const [topUpAmount, setTopUpAmount] = useState<number | null>(50);

    const handleRefresh = () => {
        // TODO: Wire up IPC call to fetch account info
        console.log('Account data refresh requested');
    };

    const handleChangePlan = () => {
        // TODO: Navigate to change plan flow
        console.log('Change plan clicked');
    };

    const handleTopUp = () => {
        if (!topUpAmount || topUpAmount <= 0) {
            return;
        }
        // TODO: Wire up IPC call to top up credits
        console.log('Top up clicked with amount', topUpAmount);
    };

    return (
        <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
            <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
                <Col>
                    <Title level={3} style={{ margin: 0 }}>Account</Title>
                    <Text type="secondary">Manage your subscription and billing details.</Text>
                </Col>
                <Col>
                    <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
                        Refresh
                    </Button>
                </Col>
            </Row>

            <Row gutter={[24, 24]}>
                <Col xs={24} lg={14}>
                    <Card>
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Title level={4} style={{ margin: 0 }}>Current Plan</Title>
                            <Text type="secondary">Subscription details fetched from the cloud will appear here.</Text>
                            <Space size={32} wrap>
                                <div>
                                    <Text type="secondary">Plan</Text><br />
                                    <Text strong>Pro (placeholder)</Text>
                                </div>
                                <Divider type="vertical" style={{ height: 'auto' }} />
                                <div>
                                    <Text type="secondary">Monthly usage</Text><br />
                                    <Text strong>$120.00</Text>
                                </div>
                            </Space>
                            <Button type="primary" icon={<ArrowRightOutlined />} onClick={handleChangePlan}>
                                Change plan
                            </Button>
                        </Space>
                    </Card>
                </Col>
                <Col xs={24} lg={10}>
                    <Card>
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Title level={4} style={{ margin: 0 }}>Top up balance</Title>
                            <Text type="secondary">Add credits to your account instantly.</Text>
                            <Space>
                                <InputNumber
                                    min={0}
                                    precision={2}
                                    prefix={<DollarOutlined />}
                                    value={topUpAmount ?? undefined}
                                    onChange={(value) => setTopUpAmount(typeof value === 'number' ? value : null)}
                                    style={{ width: 160 }}
                                />
                                <Button type="primary" onClick={handleTopUp} disabled={!topUpAmount || topUpAmount <= 0}>
                                    Top up
                                </Button>
                            </Space>
                        </Space>
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default Account;

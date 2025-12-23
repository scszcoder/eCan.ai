import React, { useState, useEffect } from 'react';
import { Button, Card, Col, Divider, InputNumber, Row, Space, Typography, message } from 'antd';
import { ReloadOutlined, DollarOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAccountStore } from '../../stores';
import { ipcApi } from '../../services/ipc';

const { Title, Text } = Typography;

const Account: React.FC = () => {
    const [topUpAmount, setTopUpAmount] = useState<number | null>(50);
    const [refreshing, setRefreshing] = useState(false);
    const navigate = useNavigate();
    const accountData = useAccountStore((state) => state.accountData);
    const setAccountData = useAccountStore((state) => state.setAccountData);

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            const response = await ipcApi.invoke('get_account_info', {});
            if (response?.result?.accountInfo) {
                setAccountData(response.result.accountInfo);
                message.success('Account info refreshed');
            } else {
                message.error('Failed to fetch account info');
            }
        } catch (error) {
            console.error('Error fetching account info:', error);
            message.error('Error fetching account info');
        } finally {
            setRefreshing(false);
        }
    };

    const handleChangePlan = () => {
        navigate('/account/payment-plan');
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
                    <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={refreshing}>
                        Refresh
                    </Button>
                </Col>
            </Row>

            <Row gutter={[24, 24]}>
                <Col xs={24} lg={14}>
                    <Card>
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Title level={4} style={{ margin: 0 }}>Current Plan</Title>
                            <Text type="secondary">
                                {accountData?.acctInfo?.email || 'Subscription details will appear after refresh.'}
                            </Text>
                            <Space size={32} wrap>
                                <div>
                                    <Text type="secondary">Plan</Text><br />
                                    <Text strong>
                                        {accountData?.acctInfo?.subs && accountData.acctInfo.subs !== '[]' && accountData.acctInfo.subs.trim() !== '' 
                                            ? accountData.acctInfo.subs 
                                            : 'Free Tier'}
                                    </Text>
                                </div>
                                <Divider type="vertical" style={{ height: 'auto' }} />
                                <div>
                                    <Text type="secondary">Balance</Text><br />
                                    <Text strong>${accountData?.acctInfo?.fund ?? 0}</Text>
                                </div>
                                <Divider type="vertical" style={{ height: 'auto' }} />
                                <div>
                                    <Text type="secondary">Quota</Text><br />
                                    <Text strong>{accountData?.acctInfo?.quota ?? 0}</Text>
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

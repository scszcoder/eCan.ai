import React, { useState } from 'react';
import { Button, Card, Col, Divider, Input, InputNumber, Row, Space, Tooltip, Typography, message, Popconfirm } from 'antd';
import { ReloadOutlined, DollarOutlined, ArrowRightOutlined, KeyOutlined, CopyOutlined, EyeOutlined, EyeInvisibleOutlined, DeleteOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAccountStore } from '../../stores/accountStore';
import { ipcApi } from '../../services/ipc/api';

const { Title, Text } = Typography;

const maskApiKey = (key: string): string => {
    if (!key || key.length <= 12) return key;
    return key.slice(0, 6) + '*'.repeat(key.length - 12) + key.slice(-6);
};

const Account: React.FC = () => {
    const [topUpAmount, setTopUpAmount] = useState<number | null>(50);
    const [refreshing, setRefreshing] = useState(false);
    const [apiKey, setApiKey] = useState<string>('');
    const [apiKeyVisible, setApiKeyVisible] = useState(false);
    const [requestingKey, setRequestingKey] = useState(false);
    const [removingKey, setRemovingKey] = useState(false);
    const navigate = useNavigate();
    const accountData = useAccountStore((state) => state.accountData);
    const setAccountData = useAccountStore((state) => state.setAccountData);

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            const response = await ipcApi.executeRequest('get_account_info', {});
            if (response?.success && response.data) {
                const data = response.data as any;
                setAccountData(data.accountInfo || data);
                message.success('Account info refreshed');
            } else {
                message.error(response?.error?.message || 'Failed to fetch account info');
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

    const handleGetApiKey = async () => {
        setRequestingKey(true);
        try {
            const response = await ipcApi.executeRequest('req_api_key', { customer: 'guest' });
            if (response?.success && response.data) {
                const resp = response.data as any;
                const key = resp?.apiKey || '';
                if (key) {
                    setApiKey(key);
                    setApiKeyVisible(false);
                    message.success(resp?.message || 'API key generated successfully');
                } else {
                    message.error(resp?.message || 'Failed to get API key: empty response');
                }
            } else {
                message.error(response?.error?.message || 'Failed to get API key');
            }
        } catch (error) {
            console.error('Error requesting API key:', error);
            message.error(`Failed to get API key: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            setRequestingKey(false);
        }
    };

    const handleRemoveApiKey = async () => {
        if (!apiKey) return;
        setRemovingKey(true);
        try {
            const maskedKey = maskApiKey(apiKey);
            const response = await ipcApi.executeRequest('remove_api_key', { masked_keys: [maskedKey] });
            if (response?.success) {
                setApiKey('');
                setApiKeyVisible(false);
                message.success('API key removed');
            } else {
                message.error(response?.error?.message || 'Failed to remove API key');
            }
        } catch (error) {
            console.error('Error removing API key:', error);
            message.error(`Failed to remove API key: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            setRemovingKey(false);
        }
    };

    const handleCopyApiKey = () => {
        if (!apiKey) return;
        navigator.clipboard.writeText(apiKey).then(() => {
            message.success('API key copied to clipboard');
        }).catch(() => {
            message.error('Failed to copy API key');
        });
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

            <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
                <Col xs={24}>
                    <Card>
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Title level={4} style={{ margin: 0 }}>
                                <KeyOutlined style={{ marginRight: 8 }} />
                                API Key
                            </Title>
                            <Text type="secondary">
                                Generate an API key to access eCan services programmatically.
                            </Text>
                            {apiKey ? (
                                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <Input
                                            readOnly
                                            value={apiKeyVisible ? apiKey : maskApiKey(apiKey)}
                                            style={{ fontFamily: 'monospace', maxWidth: 480 }}
                                        />
                                        <Tooltip title={apiKeyVisible ? 'Hide' : 'Show'}>
                                            <Button
                                                type="text"
                                                icon={apiKeyVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                                                onClick={() => setApiKeyVisible(!apiKeyVisible)}
                                            />
                                        </Tooltip>
                                        <Tooltip title="Copy to clipboard">
                                            <Button
                                                type="text"
                                                icon={<CopyOutlined />}
                                                onClick={handleCopyApiKey}
                                            />
                                        </Tooltip>
                                        <Popconfirm
                                            title="Remove API key?"
                                            description="This will permanently revoke this API key."
                                            onConfirm={handleRemoveApiKey}
                                            okText="Remove"
                                            okButtonProps={{ danger: true }}
                                        >
                                            <Tooltip title="Remove API key">
                                                <Button
                                                    type="text"
                                                    danger
                                                    icon={<DeleteOutlined />}
                                                    loading={removingKey}
                                                />
                                            </Tooltip>
                                        </Popconfirm>
                                    </div>
                                </Space>
                            ) : (
                                <Button
                                    type="primary"
                                    icon={<KeyOutlined />}
                                    onClick={handleGetApiKey}
                                    loading={requestingKey}
                                >
                                    Get API Key
                                </Button>
                            )}
                        </Space>
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default Account;

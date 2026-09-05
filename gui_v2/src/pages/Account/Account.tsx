import React, { useEffect, useState } from 'react';
import { Button, Card, Col, Divider, Input, InputNumber, Row, Space, Tooltip, Typography, message, Popconfirm } from 'antd';
import { ReloadOutlined, DollarOutlined, ArrowRightOutlined, KeyOutlined, CopyOutlined, EyeOutlined, EyeInvisibleOutlined, DeleteOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAccountStore } from '../../stores/accountStore';
import { ipcApi } from '../../services/ipc/api';
import { getCachedAppConfig, useIsCN } from '../../contexts/AppConfigContext';
import { isWebPlatform } from '../../config/platform';
import { eventBus } from '../../utils/eventBus';
import TokenUsageSection from './TokenUsageSection';
import BillingDrilldown from './BillingDrilldown';
import ContactVerification from './ContactVerification';

const { Title, Text } = Typography;

const maskApiKey = (key: string): string => {
    if (!key || key.length <= 12) return key;
    return key.slice(0, 6) + '*'.repeat(key.length - 12) + key.slice(-6);
};

// Plan-id → readable tier. The subs field carries raw subscription ids
// (e.g. "2091768641895804928") which mean nothing to users. Known ids map
// explicitly; ids containing pro/custom markers map by keyword; everything
// else (including the current default id) displays as Basic.
const PLAN_ID_NAMES: Record<string, 'basic' | 'pro' | 'custom'> = {
    '2091768641895804928': 'basic',
};

const planTier = (rawId: string): 'basic' | 'pro' | 'custom' => {
    const id = (rawId || '').trim();
    if (PLAN_ID_NAMES[id]) return PLAN_ID_NAMES[id];
    const lower = id.toLowerCase();
    if (lower.includes('custom')) return 'custom';
    if (lower.includes('pro')) return 'pro';
    return 'basic';
};

const planLabel = (subs: unknown, t: any): string => {
    const raw = String(subs ?? '').trim();
    if (!raw || raw === '[]') return t('account.freeTier', 'Free Tier');
    let ids: string[];
    try {
        const parsed = JSON.parse(raw);
        ids = Array.isArray(parsed) ? parsed.map(String) : [raw];
    } catch {
        ids = raw.split(',').map((s) => s.trim()).filter(Boolean);
    }
    if (!ids.length) return t('account.freeTier', 'Free Tier');
    const names = Array.from(new Set(ids.map(planTier))).map((tier) =>
        tier === 'pro' ? t('account.planPro', 'Pro')
        : tier === 'custom' ? t('account.planCustom', 'Custom')
        : t('account.planBasic', 'Basic'));
    return names.join(' + ');
};

// CN fund is server-authoritative integer fen (billing settlement,
// 2026-09-01) — render ¥fund/100. Intl fund stays a USD amount.
const formatFund = (fund: unknown, isCN: boolean): string => {
    const n = typeof fund === 'number' && !Number.isNaN(fund) ? fund : 0;
    return isCN ? `¥${(n / 100).toFixed(2)}` : `$${n}`;
};

const Account: React.FC = () => {
    const { t } = useTranslation();
    const [topUpAmount, setTopUpAmount] = useState<number | null>(50);
    const [toppingUp, setToppingUp] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const isCN = useIsCN();
    const [apiKey, setApiKey] = useState<string>('');
    const [apiKeyVisible, setApiKeyVisible] = useState(false);
    const [requestingKey, setRequestingKey] = useState(false);
    const [testingKey, setTestingKey] = useState(false);
    const [removingKey, setRemovingKey] = useState(false);
    const navigate = useNavigate();
    const accountData = useAccountStore((state) => state.accountData);
    const setAccountData = useAccountStore((state) => state.setAccountData);

    const syncECanAIKey = async (key: string, silent = false) => {
        if (!key) return false;
        const response = await ipcApi.executeRequest('sync_ecanai_account_api_key', { api_key: key });
        if (!response?.success) {
            const error = response?.error?.message || 'Failed to synchronize eCanAI provider key';
            if (!silent) message.warning(error);
            else console.warn('[Account] eCanAI API key synchronization failed:', error);
            return false;
        }
        return true;
    };

    const clearECanAIKey = async (silent = false) => {
        // Companion to syncECanAIKey: when the user revokes the key from
        // Account page, drop the matching ECANAI_{LLM,EMBEDDING,RERANK}_API_KEY
        // slots from secure_store and the matching lightrag.env API-key
        // fields, then trigger LightRAG restart.
        const response = await ipcApi.executeRequest('remove_ecanai_account_api_key', {});
        if (!response?.success) {
            const error = response?.error?.message || 'Failed to clear eCanAI provider key';
            if (!silent) message.warning(error);
            else console.warn('[Account] eCanAI API key clear failed:', error);
            return false;
        }
        return true;
    };

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            const response = await ipcApi.executeRequest('get_account_info', {});
            if (response?.success && response.data) {
                const data = response.data as any;
                if (data.accountInfo === null) {
                    // Cloud reachable but no account row for this identity yet.
                    message.warning(t('account.noAccountRecord',
                        'No account record found yet — it is created on first login'));
                    await loadApiKey();
                    return;
                }
                setAccountData(data.accountInfo || data);
                await loadApiKey();
                message.success(t('account.refreshSuccess', 'Account info refreshed'));
            } else {
                message.error(response?.error?.message || t('account.fetchFailed', 'Failed to fetch account info'));
            }
        } catch (error) {
            console.error('Error fetching account info:', error);
            message.error(t('account.fetchError', 'Error fetching account info'));
        } finally {
            setRefreshing(false);
        }
    };

    const handleChangePlan = () => {
        navigate('/account/payment-plan');
    };

    const handleTopUp = async () => {
        if (!topUpAmount || topUpAmount <= 0) {
            return;
        }
        if (!isCN) {
            navigate('/account/payment-plan');
            return;
        }
        setToppingUp(true);
        try {
            const response = await ipcApi.executeRequest(
                'payment_topup',
                { amount: topUpAmount },
                640_000,
            );
            const data = (response?.data as any) || {};
            if (response?.success && data.status === 'SUCCESS') {
                message.success(data.message || t('account.paymentSuccess', 'Payment successful'));
                await handleRefresh();
            } else if (data.status === 'CANCELLED') {
                message.info(data.message || t('account.paymentCancelled', 'Payment cancelled'));
            } else if (response?.success) {
                message.warning(data.message || t('account.paymentPending', 'Payment pending'));
            } else {
                message.error(response?.error?.message || t('account.paymentFailed', 'Payment failed'));
            }
        } catch (error) {
            console.error('Top up error:', error);
            message.error(t('account.paymentError', 'Payment error'));
        } finally {
            setToppingUp(false);
        }
    };

    const handleGetApiKey = async () => {
        setRequestingKey(true);
        try {
            if (isCN && isWebPlatform()) {
                const envId = getCachedAppConfig()?.auth.cloudbase_env_id;
                if (!envId) throw new Error('CloudBase API key service is not configured');
                const cloudbase = (await import('@cloudbase/js-sdk')).default;
                const app = cloudbase.init({ env: envId, region: 'ap-shanghai' });
                const result = await app.callFunction({ name: 'myAPIKeygen', data: { action: 'createApiKey', customer: 'guest' } });
                const resp = (result as any)?.result || result;
                if (!resp?.apiKey) throw new Error(resp?.message || resp?.error || 'Failed to get API key: empty response');
                setApiKey(resp.apiKey);
                await syncECanAIKey(resp.apiKey);
                message.success(resp.message || t('account.apiKeySuccess', 'API key generated successfully'));
                return;
            }
            const response = await ipcApi.executeRequest('req_api_key', { customer: 'guest' });
            if (response?.success && response.data) {
                const resp = response.data as any;
                const key = resp?.apiKey || '';
                if (key) {
                    setApiKey(key);
                    await syncECanAIKey(key);
                    message.success(resp?.message || t('account.apiKeySuccess', 'API key generated successfully'));
                } else {
                    message.error(resp?.message || t('account.apiKeyEmpty', 'Failed to get API key: empty response'));
                }
            } else {
                message.error(response?.error?.message || t('account.apiKeyFailed', 'Failed to get API key'));
            }
        } catch (error) {
            console.error('Error requesting API key:', error);
            message.error(t('account.apiKeyError', 'Error requesting API key'));
        } finally {
            setRequestingKey(false);
        }
    };

    const loadApiKey = async () => {
        if (!isCN) return;
        try {
            if (isWebPlatform()) {
                const envId = getCachedAppConfig()?.auth.cloudbase_env_id;
                if (!envId) return;
                const cloudbase = (await import('@cloudbase/js-sdk')).default;
                const app = cloudbase.init({ env: envId, region: 'ap-shanghai' });
                const result = await app.callFunction({ name: 'myAPIKeygen', data: { action: 'getApiKey' } });
                const response = (result as any)?.result || result;
                const key = response?.apiKey || '';
                setApiKey(key);
                if (key) await syncECanAIKey(key, true);
                return;
            }
            // Desktop: same myAPIKeygen store via the local backend's IPC bridge.
            const response = await ipcApi.executeRequest('get_api_key', {});
            if (response?.success && response.data) {
                const key = (response.data as any)?.apiKey || '';
                setApiKey(key);
                if (key) await syncECanAIKey(key, true);
            }
        } catch (error) {
            console.error('Error loading API key:', error);
        }
    };

    const handleRemoveApiKey = async () => {
        if (!apiKey) return;
        setRemovingKey(true);
        try {
            const maskedKey = maskApiKey(apiKey);
            let backendSuccess = false;
            let backendReason = '';
            if (isCN && isWebPlatform()) {
                const envId = getCachedAppConfig()?.auth.cloudbase_env_id;
                if (!envId) throw new Error('CloudBase API key service is not configured');
                const cloudbase = (await import('@cloudbase/js-sdk')).default;
                const app = cloudbase.init({ env: envId, region: 'ap-shanghai' });
                const result = await app.callFunction({ name: 'myAPIKeygen', data: { action: 'removeApiKeys', keys: [maskedKey] } });
                const resp = (result as any)?.result || result;
                if (resp?.success) {
                    backendSuccess = true;
                } else {
                    const reason = resp?.message || resp?.error || 'unknown error';
                    console.warn('Backend API key removal failed, performing local cleanup:', reason);
                    backendReason = reason;
                }
            } else {
                const response = await ipcApi.executeRequest('remove_api_key', { masked_keys: [maskedKey] });
                if (response?.success) {
                    backendSuccess = true;
                } else {
                    const reason = response?.error?.message || response?.error?.code || 'unknown error';
                    console.warn('Backend API key removal failed, performing local cleanup:', reason);
                    backendReason = reason;
                }
            }
            // Always clear local state, even if backend deletion fails
            setApiKey('');
            // Always drop the local eCanAI credentials, even if backend
            // deletion failed — otherwise an open Knowledge → Settings tab
            // keeps showing the previous account key in the parser fields
            // until the user visits System Settings again.
            await clearECanAIKey(true);
            if (backendSuccess) {
                message.success(t('account.apiKeyRemoved', 'API key removed'));
            } else {
                // Surface the actual server-side failure reason so the user
                // can distinguish "rate-limited, retry later" from "key
                // already revoked elsewhere" — not just a vague "may have failed".
                message.warning(`${t('account.apiKeyRemovedLocal', 'API key removed from this device')}. Server: ${backendReason || 'unknown'}`);
            }
        } catch (error) {
            const reason = error instanceof Error ? error.message : String(error);
            console.error('Error removing API key:', error);
            // Still clear local state on exception
            setApiKey('');
            await clearECanAIKey(true);
            message.warning(`${t('account.apiKeyRemovedLocal', 'API key removed from this device')}. Server: ${reason}`);
        } finally {
            setRemovingKey(false);
        }
    };

    const handleCopyApiKey = () => {
        if (!apiKey) return;
        navigator.clipboard.writeText(apiKey).then(() => {
            message.success(t('account.copied', 'API key copied to clipboard'));
        }).catch(() => {
            message.error(t('account.copyFailed', 'Failed to copy API key'));
        });
    };

    useEffect(() => {
        void loadApiKey();

        // Refresh account data when billing status changes
        const handleBillingBlocked = () => {
            void loadApiKey();
        };
        eventBus.on('localws:account.billingBlocked', handleBillingBlocked);
        return () => {
            eventBus.off('localws:account.billingBlocked', handleBillingBlocked);
        };
    }, []);

    const handleTestApiKey = async () => {
        if (!apiKey) return;
        setTestingKey(true);
        try {
            if (isCN) {
                const envId = getCachedAppConfig()?.auth.cloudbase_env_id;
                if (!envId) throw new Error('CloudBase API key service is not configured');
                const result = await fetch(`https://${envId}.service.tcloudbase.com/api/llm-proxy/v1/models`, {
                    headers: { Authorization: `Bearer ${apiKey}` },
                });
                const response = await result.json().catch(() => ({}));
                if (result.ok && response?.object === 'list' && Array.isArray(response.data)) {
                    message.success(t('account.apiKeyTestSuccess', 'API key is active and valid'));
                } else {
                    throw new Error(response?.error?.message || `API key validation failed (HTTP ${result.status})`);
                }
                return;
            }
            const response = await ipcApi.executeRequest('query_api_keys', { apiKey });
            const data = response?.data as any;
            if (response?.success && data?.status === 'active') {
                message.success(t('account.apiKeyTestSuccess', 'API key is active and valid'));
            } else {
                message.error(data?.status
                    ? t('account.apiKeyTestInactive', 'API key is not active')
                    : response?.error?.message || t('account.apiKeyTestFailed', 'Unable to validate API key'));
            }
        } catch (error) {
            console.error('Error validating API key:', error);
            message.error(t('account.apiKeyTestError', 'Error validating API key'));
        } finally {
            setTestingKey(false);
        }
    };

    return (
        <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
            <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
                <Col>
                    <Title level={3} style={{ margin: 0 }}>{t('account.title', 'Account')}</Title>
                </Col>
                <Col>
                    <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={refreshing}>
                        {t('account.refresh', 'Refresh')}
                    </Button>
                </Col>
            </Row>

            <Row gutter={[24, 24]}>
                <Col xs={24} lg={14}>
                    <Card>
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Title level={4} style={{ margin: 0 }}>{t('account.currentPlan', 'Current Plan')}</Title>
                            <Text type="secondary">
                                {accountData?.acctInfo?.email || t('account.noDetails', 'Subscription details will appear after refresh.')}
                            </Text>
                            <Space size={32} wrap>
                                <div>
                                    <Text type="secondary">{t('account.plan', 'Plan')}</Text><br />
                                    <Text strong title={String(accountData?.acctInfo?.subs ?? '')}>
                                        {planLabel(accountData?.acctInfo?.subs, t)}
                                    </Text>
                                </div>
                                <Divider type="vertical" style={{ height: 'auto' }} />
                                <div>
                                    <Text type="secondary">{t('account.balance', 'Balance')}</Text><br />
                                    <Text strong style={{ fontVariantNumeric: 'tabular-nums' }}>
                                        {formatFund(accountData?.acctInfo?.fund, isCN)}
                                    </Text>
                                </div>
                                <Divider type="vertical" style={{ height: 'auto' }} />
                                <div>
                                    <Text type="secondary">{t('account.quota', 'Quota')}</Text><br />
                                    <Text strong>{accountData?.acctInfo?.quota ?? 0}</Text>
                                </div>
                            </Space>
                            <Button type="primary" icon={<ArrowRightOutlined />} onClick={handleChangePlan}>
                                {t('account.changePlan', 'Change plan')}
                            </Button>
                        </Space>
                    </Card>
                </Col>
                <Col xs={24} lg={10}>
                    <Card>
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Title level={4} style={{ margin: 0 }}>{t('account.topUp', 'Top up balance')}</Title>
                            <Text type="secondary">{t('account.topUpDesc', 'Add credits to your account instantly.')}</Text>
                            <Space>
                                <InputNumber
                                    min={0}
                                    precision={2}
                                    prefix={isCN ? <span style={{ fontWeight: 600 }}>¥</span> : <DollarOutlined />}
                                    value={topUpAmount ?? undefined}
                                    onChange={(value) => setTopUpAmount(typeof value === 'number' ? value : null)}
                                    style={{ width: 160 }}
                                />
                                <Button type="primary" onClick={handleTopUp} loading={toppingUp} disabled={!topUpAmount || topUpAmount <= 0}>
                                    {t('account.topUp', 'Top up')}
                                </Button>
                            </Space>
                        </Space>
                    </Card>
                </Col>
            </Row>

            {isCN && <ContactVerification />}

            <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
                <Col xs={24}>
                    <Card>
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Title level={4} style={{ margin: 0 }}>
                                <KeyOutlined style={{ marginRight: 8 }} />
                                {t('account.apiKey', 'API Key')}
                            </Title>
                            <Text type="secondary">
                                {t('account.apiKeyDesc', 'Generate an API key to access eCan services programmatically.')}
                            </Text>
                            {apiKey ? (
                                <Space style={{ width: '100%' }} align="center" wrap>
                                    <Input
                                        readOnly
                                        value={apiKeyVisible ? apiKey : maskApiKey(apiKey)}
                                        style={{ flex: 1, minWidth: 240, fontFamily: 'monospace' }}
                                    />
                                    <Tooltip title={apiKeyVisible ? t('account.hide', 'Hide') : t('account.show', 'Show')}>
                                        <Button
                                            type="text"
                                            icon={apiKeyVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                                            onClick={() => setApiKeyVisible(!apiKeyVisible)}
                                        />
                                    </Tooltip>
                                    <Tooltip title={t('account.copyToClipboard', 'Copy to clipboard')}>
                                        <Button
                                            type="text"
                                            icon={<CopyOutlined />}
                                            onClick={handleCopyApiKey}
                                        />
                                    </Tooltip>
                                    <Tooltip title={t('account.testApiKey', 'Test API key')}>
                                        <Button
                                            type="text"
                                            icon={<CheckCircleOutlined />}
                                            onClick={handleTestApiKey}
                                            loading={testingKey}
                                        />
                                    </Tooltip>
                                    <Popconfirm
                                        title={t('account.removeKeyTitle', 'Remove API key?')}
                                        description={t('account.removeKeyDesc', 'This will permanently revoke this API key.')}
                                        onConfirm={handleRemoveApiKey}
                                        okText={t('account.remove', 'Remove')}
                                        okButtonProps={{ danger: true }}
                                    >
                                        <Tooltip title={t('account.removeKey', 'Remove API key')}>
                                            <Button
                                                type="text"
                                                danger
                                                icon={<DeleteOutlined />}
                                                loading={removingKey}
                                            />
                                        </Tooltip>
                                    </Popconfirm>
                                </Space>
                            ) : (
                                <Button
                                    type="primary"
                                    icon={<KeyOutlined />}
                                    onClick={handleGetApiKey}
                                    loading={requestingKey}
                                >
                                    {t('account.getApiKey', 'Get API Key')}
                                </Button>
                            )}
                        </Space>
                    </Card>
                </Col>
            </Row>

            {/* Token Usage Analytics - expandable section at the bottom */}
            <TokenUsageSection />

            {/* Billing drill-down: daily → hourly → per-model, with top-ups merged */}
            <BillingDrilldown />
        </div>
    );
};

export default Account;

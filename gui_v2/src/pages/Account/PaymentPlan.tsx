import React, { useEffect, useState } from 'react';
import { Button, Card, Col, Row, Typography, message } from 'antd';
import { ArrowLeftOutlined, AlipayCircleOutlined, WechatOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ipcApi } from '../../services/ipc/api';
import { useIsCN } from '../../contexts/AppConfigContext';

const { Title, Text } = Typography;

const PaymentPlan: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const isCN = useIsCN();
    const [payingPlan, setPayingPlan] = useState<string | null>(null);

    useEffect(() => {
        if (isCN) {
            return;
        }
        const existingScript = document.querySelector('script[src="https://js.stripe.com/v3/buy-button.js"]');
        if (!existingScript) {
            const script = document.createElement('script');
            script.src = 'https://js.stripe.com/v3/buy-button.js';
            script.async = true;
            document.body.appendChild(script);
        }
    }, [isCN]);

    const handleBack = () => {
        navigate('/account');
    };

    const handleCnPay = async (planKey: string, amount: number) => {
        setPayingPlan(planKey);
        try {
            const response = await ipcApi.executeRequest(
                'payment_topup',
                { amount, purpose: 'subscription', plan: planKey },
                640_000,
            );
            const data = (response?.data as any) || {};
            if (response?.success && data.status === 'SUCCESS') {
                message.success(data.message || t('account.paymentSuccess', 'Payment successful'));
                navigate('/account');
            } else if (data.status === 'CANCELLED') {
                message.info(data.message || t('account.paymentCancelled', 'Payment cancelled'));
            } else if (response?.success) {
                message.warning(data.message || t('account.paymentPending', 'Payment pending'));
            } else {
                message.error(response?.error?.message || t('account.paymentFailed', 'Payment failed'));
            }
        } catch (error) {
            console.error('Plan payment error:', error);
            message.error(t('account.paymentError', 'Payment error'));
        } finally {
            setPayingPlan(null);
        }
    };

    return (
        <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
            <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
                <Col>
                    <Button
                        type="text"
                        icon={<ArrowLeftOutlined />}
                        onClick={handleBack}
                        style={{ marginBottom: 8 }}
                    >
                        {t('account.backToAccount', 'Back to Account')}
                    </Button>
                    <Title level={3} style={{ margin: 0 }}>{t('account.paymentPlan', 'Payment Plan')}</Title>
                    <Text type="secondary">{t('account.choosePlan', 'Choose a subscription plan that fits your needs.')}</Text>
                </Col>
            </Row>

            {isCN ? (
                <>
                    <Row gutter={[24, 24]}>
                        <Col xs={24} md={12} lg={8}>
                            <Card title={t('account.subscriptionPlan', 'Subscription Plan')} style={{ textAlign: 'center' }}>
                                <div style={{ marginBottom: 16 }}>
                                    <Text type="secondary">{t('account.subscribeDesc', 'Subscribe to unlock premium features and enhanced capabilities.')}</Text>
                                </div>
                                <Title level={3} style={{ margin: '8px 0 16px' }}>¥68 / {t('account.month', 'Month')}</Title>
                                <Button
                                    type="primary"
                                    block
                                    loading={payingPlan === 'subscription'}
                                    onClick={() => handleCnPay('subscription', 68)}
                                >
                                    {t('account.subscribe', 'Subscribe')}（{t('account.alipayWechat', 'Alipay / WeChat Pay')}）
                                </Button>
                            </Card>
                        </Col>
                        <Col xs={24} md={12} lg={8}>
                            <Card title={t('account.additionalPlan', 'Additional Plan')} style={{ textAlign: 'center' }}>
                                <div style={{ marginBottom: 16 }}>
                                    <Text type="secondary">
                                        {t('account.additionalDesc', 'Choose this plan for result-driven monthly charging, with a minimum of ¥0.50 initial top-up.')}
                                    </Text>
                                </div>
                                <Title level={3} style={{ margin: '8px 0 16px' }}>¥0.50 {t('account.from', 'from')}</Title>
                                <Button
                                    type="primary"
                                    block
                                    loading={payingPlan === 'additional'}
                                    onClick={() => handleCnPay('additional', 0.5)}
                                >
                                    {t('account.purchase', 'Purchase')}（{t('account.alipayWechat', 'Alipay / WeChat Pay')}）
                                </Button>
                            </Card>
                        </Col>
                    </Row>
                    <div style={{ marginTop: 16 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                            <AlipayCircleOutlined style={{ color: '#1677ff' }} /> {t('account.alipay', 'Alipay')}
                            &nbsp;·&nbsp;
                            <WechatOutlined style={{ color: '#07c160' }} /> {t('account.wechatPay', 'WeChat Pay')}
                        </Text>
                    </div>
                </>
            ) : (
                <Row gutter={[24, 24]}>
                    <Col xs={24} md={12} lg={8}>
                        <Card title={t('account.subscriptionPlan', 'Subscription Plan')} style={{ textAlign: 'center' }}>
                            <div style={{ marginBottom: 16 }}>
                                <Text type="secondary">
                                    {t('account.subscribeDesc', 'Subscribe to unlock premium features and enhanced capabilities.')}
                                </Text>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'center' }}>
                                {/* @ts-ignore - Stripe custom element */}
                                <stripe-buy-button
                                    buy-button-id="buy_btn_1ShEj5GyfnLwIh0ZJ5j7mysT"
                                    publishable-key="pk_live_51O0VZnGyfnLwIh0ZBo5BK0pEwfR7O3Nt1dYTCz4NidWcjVckeWiPfrNx76Bm3O7IGT0iG7Zn4ylXUBBQ9sTRLH5x00ySldd95M"
                                />
                            </div>
                        </Card>
                    </Col>
                    <Col xs={24} md={12} lg={8}>
                        <Card title={t('account.additionalPlan', 'Additional Plan')} style={{ textAlign: 'center' }}>
                            <div style={{ marginBottom: 16 }}>
                                <Text type="secondary">
                                    {t('account.additionalDesc', 'Choose this plan for result-driven monthly charging, with a minimum of $0.50 initial top-up.')}
                                </Text>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'center' }}>
                                {/* @ts-ignore - Stripe custom element */}
                                <stripe-buy-button
                                    buy-button-id="buy_btn_1ShF0qGyfnLwIh0Z8vAbvXMw"
                                    publishable-key="pk_live_51O0VZnGyfnLwIh0ZBo5BK0pEwfR7O3Nt1dYTCz4NidWcjVckeWiPfrNx76Bm3O7IGT0iG7Zn4ylXUBBQ9sTRLH5x00ySldd95M"
                                />
                            </div>
                        </Card>
                    </Col>
                </Row>
            )}
        </div>
    );
};

export default PaymentPlan;

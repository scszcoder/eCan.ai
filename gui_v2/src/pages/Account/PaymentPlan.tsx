import React, { useEffect, useState } from 'react';
import { Button, Card, Col, Row, Typography, message, Input, Space } from 'antd';
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
    // Coupon (CN top-up). The preview is advisory; the server re-validates and
    // applies the discount when the order is created.
    const [couponCode, setCouponCode] = useState('');
    const [couponChecking, setCouponChecking] = useState(false);
    const [couponInfo, setCouponInfo] = useState<{
        valid: boolean; reason?: string; pay_amount?: number; credit_amount?: number; currency?: string;
    } | null>(null);

    const previewCoupon = async (amountYuan: number) => {
        const code = couponCode.trim();
        if (!code) { setCouponInfo(null); return; }
        setCouponChecking(true);
        try {
            const res = await ipcApi.validateCoupon<any>(code, Math.round(amountYuan * 100), 'CNY', 'topup');
            const d = (res?.data as any) || {};
            if (res?.success && d.valid) {
                setCouponInfo({ valid: true, pay_amount: d.pay_amount, credit_amount: d.credit_amount, currency: d.currency || 'CNY' });
            } else {
                setCouponInfo({ valid: false, reason: d.reason || t('account.couponInvalid', 'Coupon is not valid') });
            }
        } catch {
            // Preview endpoint not available yet — allow the code through; the
            // server validates at order time.
            setCouponInfo(null);
            message.info(t('account.couponPreviewUnavailable', 'Coupon will be checked at payment'));
        } finally {
            setCouponChecking(false);
        }
    };

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
                { amount, purpose: 'subscription', plan: planKey, coupon_code: couponCode.trim() || undefined },
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
                    <Card size="small" style={{ marginBottom: 16 }}>
                        <Space wrap>
                            <Text>{t('account.couponCode', 'Coupon code')}:</Text>
                            <Input
                                placeholder={t('account.couponPlaceholder', 'Enter code (optional)')}
                                value={couponCode}
                                onChange={(e) => { setCouponCode(e.target.value); setCouponInfo(null); }}
                                style={{ width: 200 }}
                                allowClear
                            />
                            <Button loading={couponChecking} onClick={() => previewCoupon(68)}>
                                {t('account.couponApply', 'Apply')}
                            </Button>
                            {couponInfo?.valid && (
                                <Text style={{ color: '#22c55e' }}>
                                    {t('account.couponOk', 'Applied')}: {t('account.pay', 'pay')} ¥{((couponInfo.pay_amount || 0) / 100).toFixed(2)}
                                    {couponInfo.credit_amount && couponInfo.credit_amount !== couponInfo.pay_amount
                                        ? ` · ${t('account.credit', 'credit')} ¥${((couponInfo.credit_amount || 0) / 100).toFixed(2)}` : ''}
                                </Text>
                            )}
                            {couponInfo && !couponInfo.valid && (
                                <Text type="danger">{couponInfo.reason}</Text>
                            )}
                        </Space>
                        <div style={{ marginTop: 6 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                {t('account.couponServerNote', 'The discount is confirmed at payment.')}
                            </Text>
                        </div>
                    </Card>
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

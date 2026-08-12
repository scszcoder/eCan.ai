import React, { useEffect, useState } from 'react';
import { Button, Card, Col, Row, Typography, message } from 'antd';
import { ArrowLeftOutlined, AlipayCircleOutlined, WechatOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { ipcApi } from '../../services/ipc/api';
import { useIsCN } from '../../contexts/AppConfigContext';

const { Title, Text } = Typography;

const PaymentPlan: React.FC = () => {
    const navigate = useNavigate();
    const isCN = useIsCN();
    const [payingPlan, setPayingPlan] = useState<string | null>(null);

    useEffect(() => {
        // Stripe is the international path only. Don't load its script in CN
        // (blocked in China; CN uses Alipay + WeChat Pay via the in-app dialog).
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

    // CN: open the same Alipay + WeChat Pay dialog the top-up button uses.
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
                message.success(data.message || '支付成功');
                navigate('/account');
            } else if (data.status === 'CANCELLED') {
                message.info(data.message || '支付已取消');
            } else if (response?.success) {
                message.warning(data.message || '支付未完成');
            } else {
                message.error(response?.error?.message || 'Payment failed');
            }
        } catch (error) {
            console.error('Plan payment error:', error);
            message.error('Payment error');
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
                        Back to Account
                    </Button>
                    <Title level={3} style={{ margin: 0 }}>Payment Plan</Title>
                    <Text type="secondary">Choose a subscription plan that fits your needs.</Text>
                </Col>
            </Row>

            {isCN ? (
                <>
                    <Row gutter={[24, 24]}>
                        <Col xs={24} md={12} lg={8}>
                            <Card title="订阅套餐" style={{ textAlign: 'center' }}>
                                <div style={{ marginBottom: 16 }}>
                                    <Text type="secondary">订阅以解锁高级功能与增强能力。</Text>
                                </div>
                                <Title level={3} style={{ margin: '8px 0 16px' }}>¥68 / 月</Title>
                                <Button
                                    type="primary"
                                    block
                                    loading={payingPlan === 'subscription'}
                                    onClick={() => handleCnPay('subscription', 68)}
                                >
                                    订阅（支付宝 / 微信支付）
                                </Button>
                            </Card>
                        </Col>
                        <Col xs={24} md={12} lg={8}>
                            <Card title="附加套餐" style={{ textAlign: 'center' }}>
                                <div style={{ marginBottom: 16 }}>
                                    <Text type="secondary">
                                        按结果计费的月度套餐，最低 ¥0.50 起充。
                                    </Text>
                                </div>
                                <Title level={3} style={{ margin: '8px 0 16px' }}>¥0.50 起</Title>
                                <Button
                                    type="primary"
                                    block
                                    loading={payingPlan === 'additional'}
                                    onClick={() => handleCnPay('additional', 0.5)}
                                >
                                    购买（支付宝 / 微信支付）
                                </Button>
                            </Card>
                        </Col>
                    </Row>
                    <div style={{ marginTop: 16 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                            <AlipayCircleOutlined style={{ color: '#1677ff' }} /> 支付宝
                            &nbsp;·&nbsp;
                            <WechatOutlined style={{ color: '#07c160' }} /> 微信支付
                        </Text>
                    </div>
                </>
            ) : (
                <Row gutter={[24, 24]}>
                    <Col xs={24} md={12} lg={8}>
                        <Card title="Subscription Plan" style={{ textAlign: 'center' }}>
                            <div style={{ marginBottom: 16 }}>
                                <Text type="secondary">
                                    Subscribe to unlock premium features and enhanced capabilities.
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
                        <Card title="Additional Plan" style={{ textAlign: 'center' }}>
                            <div style={{ marginBottom: 16 }}>
                                <Text type="secondary">
                                    Choose this plan for result driven monthly charge, with a minimum of $0.50 initial top-up to start with.
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

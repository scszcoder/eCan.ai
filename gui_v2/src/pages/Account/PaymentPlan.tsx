import React, { useEffect } from 'react';
import { Button, Card, Col, Row, Typography } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Title, Text } = Typography;

const PaymentPlan: React.FC = () => {
    const navigate = useNavigate();

    useEffect(() => {
        // Load Stripe buy button script
        const existingScript = document.querySelector('script[src="https://js.stripe.com/v3/buy-button.js"]');
        if (!existingScript) {
            const script = document.createElement('script');
            script.src = 'https://js.stripe.com/v3/buy-button.js';
            script.async = true;
            document.body.appendChild(script);
        }
    }, []);

    const handleBack = () => {
        navigate('/account');
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

            <Row gutter={[24, 24]}>
                <Col xs={24} md={12} lg={8}>
                    <Card 
                        title="Subscription Plan"
                        style={{ textAlign: 'center' }}
                    >
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
                    <Card 
                        title="Additional Plan"
                        style={{ textAlign: 'center' }}
                    >
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
        </div>
    );
};

export default PaymentPlan;

import React, { useEffect } from 'react';
import { Button, Card, Col, Row, Typography, Divider, Space } from 'antd';
import {
    ArrowLeftOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    InfoCircleOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useIsCN } from '../../contexts/AppConfigContext';
import {
    PLAN_TERMS,
    BILLING_RULES,
    SKILL_PRICING_NOTE,
    type Bilingual,
    type PlanTerms,
} from './planTerms';

const { Title, Text, Paragraph } = Typography;

/**
 * Plan explanation page — reached from the ? icon on each plan card.
 *
 * Its whole job is removing ambiguity about what a plan consists of, so it
 * spells out the monthly minimum, the per-unit price, how the minimum is drawn
 * down, and — the part customers actually argue about — what is NOT billed.
 * Terms come from planTerms.ts so a price change is one edit in one file.
 */
const PlanDetails: React.FC = () => {
    const { t, i18n } = useTranslation();
    const navigate = useNavigate();
    const location = useLocation();
    const isCN = useIsCN();
    const zh = (i18n.language || '').toLowerCase().startsWith('zh');
    const say = (b: Bilingual) => (zh ? b.zh : b.en);

    // Deep-link from a specific plan's ? icon: /account/payment-plan/details#additional
    useEffect(() => {
        const anchor = (location.hash || '').replace('#', '');
        if (!anchor) return;
        const el = document.getElementById(anchor);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, [location.hash]);

    const renderPlan = (plan: PlanTerms) => (
        <Card
            id={plan.key}
            key={plan.key}
            title={say(plan.name)}
            style={{ marginBottom: 16 }}
            extra={<Text strong>{say(isCN ? plan.price.cn : plan.price.intl)}</Text>}
        >
            <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                {say(plan.tagline)}
            </Paragraph>

            <Text type="secondary" style={{ fontSize: 12 }}>
                {t('account.planBestFor', '适合')}:&nbsp;{say(plan.bestFor)}
            </Text>

            <Divider style={{ margin: '12px 0' }} />

            {plan.includes.map((line, idx) => (
                <Row key={idx} gutter={[12, 8]} style={{ marginBottom: 8 }}>
                    <Col xs={24} sm={8}>
                        <Text type="secondary">{say(line.label)}</Text>
                    </Col>
                    <Col xs={24} sm={16}>
                        <Text>{say(line.value)}</Text>
                    </Col>
                </Row>
            ))}

            {plan.notes.map((note, idx) => (
                <Paragraph key={idx} type="secondary" style={{ fontSize: 12, marginTop: 12, marginBottom: 0 }}>
                    <InfoCircleOutlined />&nbsp;{say(note)}
                </Paragraph>
            ))}
        </Card>
    );

    return (
        <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
            <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={() => navigate('/account/payment-plan')}
                style={{ marginBottom: 8 }}
            >
                {t('account.backToPlans', '返回套餐')}
            </Button>
            <Title level={3} style={{ margin: 0 }}>
                {t('account.planDetailsTitle', '套餐说明')}
            </Title>
            <Text type="secondary">
                {t('account.planDetailsSubtitle', '每个套餐包含什么、怎么计费、什么不计费。')}
            </Text>

            <div style={{ marginTop: 20, maxWidth: 900 }}>
                {PLAN_TERMS.map(renderPlan)}

                <Card title={say(BILLING_RULES.title)} style={{ marginBottom: 16 }}>
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        {BILLING_RULES.billed.map((line, idx) => (
                            <div key={`b${idx}`}>
                                <CheckCircleOutlined style={{ color: '#22c55e' }} />
                                &nbsp;<Text>{say(line)}</Text>
                            </div>
                        ))}
                        <Divider style={{ margin: '8px 0' }} />
                        {BILLING_RULES.notBilled.map((line, idx) => (
                            <div key={`n${idx}`}>
                                <CloseCircleOutlined style={{ color: '#94a3b8' }} />
                                &nbsp;<Text type="secondary">{say(line)}</Text>
                            </div>
                        ))}
                    </Space>
                </Card>

                <Card title={say(SKILL_PRICING_NOTE.title)}>
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        {SKILL_PRICING_NOTE.lines.map((line, idx) => (
                            <Text key={idx} type="secondary">• {say(line)}</Text>
                        ))}
                    </Space>
                </Card>
            </div>
        </div>
    );
};

export default PlanDetails;

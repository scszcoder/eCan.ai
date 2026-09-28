import React, { useEffect, useState } from 'react';
import { Card, Col, InputNumber, Row, Slider, Space, Typography, message } from 'antd';
import { BellOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAccountStore, type FundThresholds } from '../../stores/accountStore';
import { useIsCN } from '../../contexts/AppConfigContext';

const { Title, Text } = Typography;

const LOW_MAX = 200;

/** The user's own balance-alarm levels: the header banner turns into a
 *  "running low" bar at the low level and a scrolling, non-dismissible one at
 *  the critical level. Saved to settings.json on release. */
const FundAlertThresholds: React.FC = () => {
    const { t } = useTranslation();
    const isCN = useIsCN();
    const saved = useAccountStore((s) => s.fundThresholds);
    const saveFundThresholds = useAccountStore((s) => s.saveFundThresholds);
    const [draft, setDraft] = useState<FundThresholds>(saved);
    const unit = isCN ? '¥' : '$';

    useEffect(() => setDraft(saved), [saved]);

    // Critical can never sit above low.
    const withLow = (low: number): FundThresholds => ({ low, critical: Math.min(draft.critical, low) });
    const withCritical = (critical: number): FundThresholds => ({ low: draft.low, critical: Math.min(critical, draft.low) });

    const commit = async (next: FundThresholds) => {
        setDraft(next);
        if (next.low === saved.low && next.critical === saved.critical) return;
        if (await saveFundThresholds(next)) {
            message.success(t('account.fundAlertSaved', 'Balance alerts saved'));
        } else {
            setDraft(saved);
            message.error(t('account.fundAlertSaveFailed', 'Could not save the balance alerts'));
        }
    };

    const row = (label: string, hint: string, value: number, max: number,
                 make: (v: number) => FundThresholds) => (
        <div>
            <Text strong>{label}</Text>
            <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>{hint}</Text>
            <Row gutter={16} align="middle">
                <Col flex="auto">
                    <Slider
                        min={0}
                        max={max}
                        value={value}
                        onChange={(v) => setDraft(make(v))}
                        onChangeComplete={(v) => commit(make(v))}
                        tooltip={{ formatter: (v) => `${unit}${v}` }}
                    />
                </Col>
                <Col>
                    <InputNumber
                        min={0}
                        max={max}
                        precision={0}
                        prefix={unit}
                        value={value}
                        onChange={(v) => typeof v === 'number' && setDraft(make(v))}
                        onBlur={() => commit(draft)}
                        onPressEnter={() => commit(draft)}
                        style={{ width: 110 }}
                    />
                </Col>
            </Row>
        </div>
    );

    return (
        <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
            <Col xs={24}>
                <Card>
                    <Space direction="vertical" size={16} style={{ width: '100%' }}>
                        <Title level={4} style={{ margin: 0 }}>
                            <BellOutlined style={{ marginRight: 8 }} />
                            {t('account.fundAlertTitle', 'Balance alerts')}
                        </Title>
                        <Text type="secondary">
                            {t('account.fundAlertDesc', 'Choose when the top bar warns you about your balance.')}
                        </Text>
                        {row(
                            t('account.fundAlertLow', 'Running low'),
                            t('account.fundAlertLowHint', 'A red bar you can dismiss appears at or below this balance.'),
                            draft.low, LOW_MAX, withLow,
                        )}
                        {row(
                            t('account.fundAlertCritical', 'Critically low'),
                            t('account.fundAlertCriticalHint', 'A scrolling bar that cannot be dismissed appears at or below this balance.'),
                            draft.critical, draft.low, withCritical,
                        )}
                    </Space>
                </Card>
            </Col>
        </Row>
    );
};

export default FundAlertThresholds;

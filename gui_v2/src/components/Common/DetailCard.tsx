import React from 'react';
import { Card, Typography, Space, Row, Col } from 'antd';
import styled from '@emotion/styled';

const { Text } = Typography;

const StyledCard = styled(Card)`
    margin-bottom: 16px;
    .ant-card-head {
        min-height: 48px;
        padding: 0 16px;
    }
    .ant-card-body {
        padding: 16px;
    }
`;

export interface DetailItem {
    label: string;
    value: React.ReactNode;
    span?: number;
    icon?: React.ReactNode;
}

interface DetailCardProps {
    title?: string;
    items: DetailItem[];
    extra?: React.ReactNode;
    loading?: boolean;
    variant?: 'outlined' | 'borderless';
    size?: 'default' | 'small';
}

const DetailCard: React.FC<DetailCardProps> = ({
    title,
    items,
    extra,
    loading = false,
    variant = 'outlined',
    size = 'default',
}) => {
    const renderItem = (item: DetailItem) => (
        <Col span={item.span || 12} key={item.label}>
            <Space>
                {item.icon}
                <Space direction="vertical" size={0}>
                    <Text type="secondary">{item.label}</Text>
                    {typeof item.value === 'string' ? (
                        <Text>{item.value}</Text>
                    ) : (
                        item.value
                    )}
                </Space>
            </Space>
        </Col>
    );

    return (
        <StyledCard
            title={title}
            extra={extra}
            loading={loading}
            variant={variant}
            size={size}
        >
            <Row gutter={[16, 16]}>
                {items.map(renderItem)}
            </Row>
        </StyledCard>
    );
};

export default DetailCard; 
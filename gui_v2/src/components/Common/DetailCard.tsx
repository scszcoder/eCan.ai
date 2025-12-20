import React from 'react';
import { Card, Typography } from 'antd';
import styled from '@emotion/styled';

const { Text } = Typography;

const StyledCard = styled(Card)`
    margin-bottom: 24px;
    background: rgba(255, 255, 255, 0.02) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;

    .ant-card-head {
        min-height: 48px;
        padding: 16px 24px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    .ant-card-body {
        padding: 20px 24px;
    }

    .ant-card-head-title {
        color: rgba(255, 255, 255, 0.95) !important;
        font-size: 15px;
        font-weight: 600;
    }
`;

const DetailGrid = styled.div<{ columns?: number }>`
    display: grid;
    grid-template-columns: ${props => `repeat(${props.columns || 1}, 1fr)`};
    gap: 0;
`;

const DetailItemWrapper = styled.div<{ columns?: number }>`
    display: flex;
    align-items: baseline;
    gap: 16px;
    padding: 14px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    transition: all 0.2s ease;

    /* 多列Layout时的边框Process */
    ${props => props.columns && props.columns > 1 ? `
        border-right: 1px solid rgba(255, 255, 255, 0.06);

        &:nth-of-type(${props.columns}n) {
            border-right: none;
        }
    ` : ''}

    &:hover {
        background: rgba(255, 255, 255, 0.03);
        padding-left: 12px;
        padding-right: 12px;
        margin-left: -4px;
        margin-right: -4px;
        border-radius: 6px;
    }
`;

const DetailLabel = styled.div`
    font-size: 13px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.55);
    min-width: 120px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 8px;
`;

const DetailValue = styled.div`
    font-size: 14px;
    color: rgba(255, 255, 255, 0.95);
    word-break: break-word;
    flex: 1;
    line-height: 1.6;
`;

export interface DetailItem {
    label: string;
    value: React.ReactNode;
    icon?: React.ReactNode;
}

interface DetailCardProps {
    title?: string;
    items: DetailItem[];
    extra?: React.ReactNode;
    loading?: boolean;
    variant?: 'outlined' | 'borderless';
    size?: 'default' | 'small';
    columns?: number; // 列数，Default为 1
}

const DetailCard: React.FC<DetailCardProps> = ({
    title,
    items,
    extra,
    loading = false,
    variant = 'outlined',
    size = 'default',
    columns = 1,
}) => {
    const renderItem = (item: DetailItem, index: number) => (
        <DetailItemWrapper key={`${item.label}-${index}`} columns={columns}>
            <DetailLabel>
                {item.icon && (
                    <span style={{ color: 'rgba(64, 169, 255, 0.7)', fontSize: '16px' }}>
                        {item.icon}
                    </span>
                )}
                {item.label}
            </DetailLabel>
            <DetailValue>
                {typeof item.value === 'string' ? (
                    <Text style={{ color: 'rgba(255, 255, 255, 0.95)' }}>
                        {item.value || '-'}
                    </Text>
                ) : (
                    item.value || <Text type="secondary">-</Text>
                )}
            </DetailValue>
        </DetailItemWrapper>
    );

    return (
        <StyledCard
            title={title}
            extra={extra}
            loading={loading}
            variant={variant}
            size={size}
        >
            <DetailGrid columns={columns}>
                {items.map(renderItem)}
            </DetailGrid>
        </StyledCard>
    );
};

export default DetailCard; 
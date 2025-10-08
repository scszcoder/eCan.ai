import React from 'react';
import { List, Tag, Typography, Space, Progress, Tooltip, Empty, Badge, Card } from 'antd';
import {
    RobotOutlined,
    ThunderboltOutlined,
    ClockCircleOutlined,
    StarOutlined,
    CheckCircleOutlined,
    SyncOutlined,
    ExperimentOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { Skill } from '@/stores';

const { Text } = Typography;

const SkillItem = styled.div`
    padding: 14px 16px;
    cursor: pointer;
    transition: all 0.2s ease;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 8px;
    margin: 6px 0;
    border: 1.5px solid rgba(255, 255, 255, 0.08);
    position: relative;
    overflow: hidden;

    &::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        height: 100%;
        width: 3px;
        background: transparent;
        transition: all 0.2s ease;
    }

    &:hover {
        background: rgba(255, 255, 255, 0.04);
        border-color: rgba(64, 169, 255, 0.3);
        transform: translateX(2px);

        &::before {
            background: rgba(64, 169, 255, 0.6);
        }
    }

    &.selected {
        background: rgba(64, 169, 255, 0.08);
        border: 1.5px solid rgba(64, 169, 255, 0.5);

        &::before {
            background: #40a9ff;
            width: 3px;
        }

        &:hover {
            background: rgba(64, 169, 255, 0.12);
            border-color: rgba(64, 169, 255, 0.7);
        }
    }

    .ant-typography {
        color: rgba(255, 255, 255, 0.95);
    }

    .ant-tag {
        border-radius: 4px;
        font-size: 11px;
        padding: 1px 6px;
        border: none;
        font-weight: 500;
    }

    .ant-progress-text {
        color: rgba(255, 255, 255, 0.85);
        font-size: 11px;
        font-weight: 500;
    }
`;

const SkillHeader = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
`;

const SkillIcon = styled.div<{ status?: string }>`
    width: 44px;
    height: 44px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    background: ${props => {
        switch (props.status) {
            case 'active': return 'linear-gradient(135deg, #52c41a 0%, #73d13d 100%)';
            case 'learning': return 'linear-gradient(135deg, #1890ff 0%, #40a9ff 100%)';
            case 'planned': return 'linear-gradient(135deg, #8c8c8c 0%, #bfbfbf 100%)';
            default: return 'linear-gradient(135deg, #722ed1 0%, #9254de 100%)';
        }
    }};
    color: white;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    flex-shrink: 0;
`;

const SkillMeta = styled.div`
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    margin-left: 14px;
    min-width: 0;
`;

const SkillName = styled(Text)`
    font-size: 15px;
    font-weight: 600;
    display: block;
    margin-bottom: 2px;
    color: rgba(255, 255, 255, 0.95);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
`;

const SkillStats = styled.div`
    display: flex;
    align-items: center;
    gap: 16px;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
`;

const StatItem = styled.div`
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.55);

    .anticon {
        font-size: 13px;
        color: rgba(64, 169, 255, 0.7);
    }
`;

const SkillProgress = styled.div`
    margin-top: 10px;

    .ant-progress-bg {
        height: 6px !important;
    }
`;

const EmptyContainer = styled.div`
    padding: 60px 20px;
    text-align: center;
`;

const getStatusConfig = (status: Skill['status']) => {
    switch (status) {
        case 'active':
            return {
                color: 'success',
                icon: <CheckCircleOutlined />,
                text: 'Active'
            };
        case 'learning':
            return {
                color: 'processing',
                icon: <SyncOutlined spin />,
                text: 'Learning'
            };
        case 'planned':
            return {
                color: 'default',
                icon: <ExperimentOutlined />,
                text: 'Planned'
            };
        default:
            return {
                color: 'default',
                icon: <RobotOutlined />,
                text: 'Unknown'
            };
    }
};

interface SkillListProps {
    skills: Skill[];
    loading: boolean;
    onSelectSkill: (skill: Skill) => void;
    selectedSkillId?: string;
}

const SkillList: React.FC<SkillListProps> = ({ skills, loading, onSelectSkill, selectedSkillId }) => {
    const { t } = useTranslation();

    if (!loading && skills.length === 0) {
        return (
            <EmptyContainer>
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                        <Space direction="vertical" size={4}>
                            <Text style={{ color: 'var(--text-secondary)' }}>
                                {t('pages.skills.noSkills', 'No skills yet')}
                            </Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                {t('pages.skills.clickAddToCreate', 'Click the + button to create your first skill')}
                            </Text>
                        </Space>
                    }
                />
            </EmptyContainer>
        );
    }

    return (
        <List
            dataSource={skills}
            loading={loading}
            renderItem={skill => {
                const statusConfig = getStatusConfig(skill.status);
                // 确保两边都是字符串类型进行比较
                const skillIdStr = String(skill.id);
                const isSelected = selectedSkillId !== undefined && selectedSkillId === skillIdStr;
                const levelValue = typeof skill.level === 'string' ? parseInt(skill.level, 10) : (skill.level || 0);

                return (
                    <SkillItem
                        onClick={() => onSelectSkill(skill)}
                        className={isSelected ? 'selected' : ''}
                    >
                        <SkillHeader>
                            <Space align="start" style={{ flex: 1 }}>
                                <SkillIcon status={skill.status}>
                                    <RobotOutlined />
                                </SkillIcon>
                                <SkillMeta>
                                    <SkillName>{skill.name}</SkillName>
                                    <Space size={6} wrap>
                                        <Tag color={statusConfig.color} icon={statusConfig.icon}>
                                            {t(`pages.skills.status.${skill.status || 'unknown'}`, statusConfig.text)}
                                        </Tag>
                                        {skill.category && (
                                            <Tag color="blue">
                                                {t(`pages.skills.categories.${skill.category}`, skill.category)}
                                            </Tag>
                                        )}
                                    </Space>
                                </SkillMeta>
                            </Space>
                        </SkillHeader>

                        <SkillProgress>
                            <Progress
                                percent={levelValue}
                                size="small"
                                status={skill.status === 'learning' ? 'active' : 'normal'}
                                strokeColor={{
                                    '0%': '#1890ff',
                                    '100%': '#52c41a',
                                }}
                                showInfo={true}
                                format={percent => `${percent}%`}
                            />
                        </SkillProgress>

                        {((skill as any).usageCount !== undefined || (skill as any).lastUsed) && (
                            <SkillStats>
                                {(skill as any).usageCount !== undefined && (
                                    <StatItem>
                                        <StarOutlined />
                                        <span>{t('pages.skills.usageCount', 'Used')}: {(skill as any).usageCount}</span>
                                    </StatItem>
                                )}
                                {(skill as any).lastUsed && (
                                    <StatItem>
                                        <ClockCircleOutlined />
                                        <span>{t('pages.skills.lastUsed', 'Last')}: {(skill as any).lastUsed}</span>
                                    </StatItem>
                                )}
                            </SkillStats>
                        )}
                    </SkillItem>
                );
            }}
        />
    );
};

export default SkillList;
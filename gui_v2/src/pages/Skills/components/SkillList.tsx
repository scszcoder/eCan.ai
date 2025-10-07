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
    padding: 16px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: var(--bg-secondary);
    border-radius: 12px;
    margin: 8px 0;
    border: 2px solid transparent;
    position: relative;
    overflow: hidden;

    &::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        height: 100%;
        width: 4px;
        background: transparent;
        transition: all 0.3s ease;
    }

    &:hover {
        background: var(--bg-tertiary);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);

        &::before {
            width: 3px;
            background: var(--primary-color);
        }
    }

    &.selected {
        background: linear-gradient(135deg, rgba(24, 144, 255, 0.15) 0%, rgba(24, 144, 255, 0.05) 100%);
        border: 2px solid var(--primary-color);

        &::before {
            background: var(--primary-color);
        }

        &:hover {
            background: linear-gradient(135deg, rgba(24, 144, 255, 0.2) 0%, rgba(24, 144, 255, 0.08) 100%);

            &::before {
                width: 4px;
            }
        }
    }

    .ant-typography {
        color: var(--text-primary);
    }

    .ant-tag {
        border-radius: 6px;
        font-size: 12px;
        padding: 2px 8px;
        border: none;
    }

    .ant-progress-text {
        color: var(--text-primary);
        font-size: 12px;
        font-weight: 500;
    }
`;

const SkillHeader = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
`;

const SkillIcon = styled.div<{ status?: string }>`
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    background: ${props => {
        switch (props.status) {
            case 'active': return 'linear-gradient(135deg, #52c41a 0%, #73d13d 100%)';
            case 'learning': return 'linear-gradient(135deg, #1890ff 0%, #40a9ff 100%)';
            case 'planned': return 'linear-gradient(135deg, #8c8c8c 0%, #bfbfbf 100%)';
            default: return 'linear-gradient(135deg, #722ed1 0%, #9254de 100%)';
        }
    }};
    color: white;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
`;

const SkillMeta = styled.div`
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    margin-left: 12px;
`;

const SkillName = styled(Text)`
    font-size: 15px;
    font-weight: 600;
    display: block;
    margin-bottom: 4px;
`;

const SkillStats = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border-color);
`;

const StatItem = styled.div`
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--text-secondary);

    .anticon {
        font-size: 14px;
    }
`;

const SkillProgress = styled.div`
    margin-top: 12px;
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
                            <Tooltip title={t('pages.skills.levelTooltip', { level: levelValue })}>
                                <Progress
                                    percent={levelValue}
                                    size="small"
                                    status={skill.status === 'learning' ? 'active' : 'normal'}
                                    strokeColor={{
                                        '0%': '#1890ff',
                                        '100%': '#52c41a',
                                    }}
                                />
                            </Tooltip>
                        </SkillProgress>

                        <SkillStats>
                            <StatItem>
                                <ThunderboltOutlined />
                                <span>{t('pages.skills.level')}: {levelValue}%</span>
                            </StatItem>
                            {(skill as any).usageCount !== undefined && (
                                <StatItem>
                                    <StarOutlined />
                                    <span>{(skill as any).usageCount}</span>
                                </StatItem>
                            )}
                            {(skill as any).lastUsed && (
                                <StatItem>
                                    <ClockCircleOutlined />
                                    <span>{(skill as any).lastUsed}</span>
                                </StatItem>
                            )}
                        </SkillStats>
                    </SkillItem>
                );
            }}
        />
    );
};

export default SkillList;
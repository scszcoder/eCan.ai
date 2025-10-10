import React from 'react';
import { List, Tag, Typography, Space, Empty } from 'antd';
import {
    RobotOutlined,
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
    padding: 12px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: var(--bg-secondary);
    border-radius: 12px;
    margin: 8px 0;
    border: 1px solid rgba(255, 255, 255, 0.05);
    position: relative;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);

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
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        border-color: rgba(255, 255, 255, 0.1);

        &::before {
            width: 3px;
            background: var(--primary-color);
        }
    }

    &.selected {
        background: linear-gradient(135deg, rgba(24, 144, 255, 0.15) 0%, rgba(24, 144, 255, 0.05) 100%);
        border: 1px solid rgba(24, 144, 255, 0.4);
        box-shadow: 0 2px 8px rgba(24, 144, 255, 0.2);

        &::before {
            background: var(--primary-color);
        }

        &:hover {
            background: linear-gradient(135deg, rgba(24, 144, 255, 0.2) 0%, rgba(24, 144, 255, 0.08) 100%);
            border-color: rgba(24, 144, 255, 0.6);
            box-shadow: 0 4px 16px rgba(24, 144, 255, 0.3);

            &::before {
                width: 4px;
            }
        }
    }

    .ant-typography {
        color: var(--text-primary);
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
    flex-shrink: 0;
`;

const SkillMeta = styled.div`
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    margin-left: 12px;
    min-width: 0;
`;

const SkillName = styled.div`
    font-size: 15px;
    font-weight: 600;
    display: block;
    margin-bottom: 4px;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
    margin-top: 10px;

    @keyframes pulse {
        0%, 100% {
            opacity: 1;
        }
        50% {
            opacity: 0.8;
        }
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
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                                <span style={{ fontSize: '11px', color: 'rgba(255, 255, 255, 0.45)' }}>
                                    {t('pages.skills.proficiency', 'Proficiency')}
                                </span>
                                <span style={{ 
                                    fontSize: '13px', 
                                    color: '#1890ff', 
                                    fontWeight: 700,
                                    fontFamily: 'monospace'
                                }}>
                                    {isNaN(levelValue) ? 0 : levelValue}%
                                </span>
                            </div>
                            {/* Gradient Progress Bar */}
                            <div style={{ 
                                width: '100%', 
                                height: '8px', 
                                background: 'rgba(255, 255, 255, 0.08)',
                                borderRadius: '4px',
                                overflow: 'hidden',
                                position: 'relative'
                            }}>
                                <div style={{
                                    width: `${isNaN(levelValue) ? 0 : levelValue}%`,
                                    height: '100%',
                                    background: 'linear-gradient(90deg, #1890ff 0%, #40a9ff 50%, #52c41a 100%)',
                                    borderRadius: '4px',
                                    transition: 'width 0.3s ease',
                                    boxShadow: skill.status === 'learning' 
                                        ? '0 0 8px rgba(24, 144, 255, 0.6)' 
                                        : 'none',
                                    animation: skill.status === 'learning' 
                                        ? 'pulse 2s ease-in-out infinite' 
                                        : 'none'
                                }} />
                            </div>
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
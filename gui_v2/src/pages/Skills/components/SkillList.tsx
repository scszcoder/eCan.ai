import React, { useState, useMemo, useRef } from 'react';
import { List, Tag, Typography, Space, Empty } from 'antd';
import { useEffectOnActive } from 'keepalive-for-react';
import {
    RobotOutlined,
    ClockCircleOutlined,
    StarOutlined,
    CheckCircleOutlined,
    SyncOutlined,
    ExperimentOutlined,
    ThunderboltOutlined,
    BulbOutlined,
    ApiOutlined,
    BranchesOutlined,
    RadarChartOutlined,
    MessageOutlined,
    CodeOutlined,
    EyeOutlined,
    CloudOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { Skill } from '@/stores';
import { SkillFilters, SkillFilterOptions } from './SkillFilters';

const { Text } = Typography;

const ListContainer = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
`;

const SkillsScrollArea = styled.div`
  flex: 1;
  padding: 0 8px 8px;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
`;

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
    width: 48px;
    height: 48px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    flex-shrink: 0;
    position: relative;
    background: ${props => {
        switch (props.status) {
            case 'active': 
                return 'linear-gradient(135deg, #10b981 0%, #34d399 50%, #6ee7b7 100%)';
            case 'learning': 
                return 'linear-gradient(135deg, #3b82f6 0%, #60a5fa 50%, #93c5fd 100%)';
            case 'planned': 
                return 'linear-gradient(135deg, #6b7280 0%, #9ca3af 50%, #d1d5db 100%)';
            case 'inactive':
                return 'linear-gradient(135deg, #ef4444 0%, #f87171 50%, #fca5a5 100%)';
            default: 
                return 'linear-gradient(135deg, #8b5cf6 0%, #a78bfa 50%, #c4b5fd 100%)';
        }
    }};
    color: white;
    box-shadow: 0 4px 20px ${props => {
        switch (props.status) {
            case 'active': return 'rgba(16, 185, 129, 0.4)';
            case 'learning': return 'rgba(59, 130, 246, 0.5)';
            case 'planned': return 'rgba(107, 114, 128, 0.3)';
            case 'inactive': return 'rgba(239, 68, 68, 0.3)';
            default: return 'rgba(139, 92, 246, 0.4)';
        }
    }};
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    
    /* AI科技感光晕效果 */
    &::before {
        content: '';
        position: absolute;
        inset: -2px;
        border-radius: 16px;
        padding: 2px;
        background: linear-gradient(135deg, 
            rgba(255, 255, 255, 0.6), 
            rgba(255, 255, 255, 0.1), 
            rgba(255, 255, 255, 0.4)
        );
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask-composite: exclude;
        opacity: 0.8;
        animation: ${props => props.status === 'learning' ? 'rotate 3s linear infinite' : 'none'};
    }
    
    /* 内部高光效果 */
    &::after {
        content: '';
        position: absolute;
        inset: 4px;
        border-radius: 11px;
        background: linear-gradient(135deg, 
            rgba(255, 255, 255, 0.25) 0%, 
            transparent 50%
        );
        opacity: 0.6;
    }
    
    .anticon {
        position: relative;
        z-index: 1;
        filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.25));
    }
    
    &:hover {
        transform: scale(1.1) translateY(-2px);
        box-shadow: 0 8px 28px ${props => {
            switch (props.status) {
                case 'active': return 'rgba(16, 185, 129, 0.6)';
                case 'learning': return 'rgba(59, 130, 246, 0.7)';
                case 'planned': return 'rgba(107, 114, 128, 0.5)';
                case 'inactive': return 'rgba(239, 68, 68, 0.5)';
                default: return 'rgba(139, 92, 246, 0.6)';
            }
        }};
    }
    
    @keyframes rotate {
        from {
            transform: rotate(0deg);
        }
        to {
            transform: rotate(360deg);
        }
    }
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

// Infer category from skill name, description, and tags
const inferCategory = (skill: Skill): string => {
    const searchText = `${skill.name} ${skill.description || ''} ${(skill.tags || []).join(' ')}`.toLowerCase();
    
    // Pattern matching for different categories
    if (/automat|workflow|process|batch|schedule/i.test(searchText)) return 'automation';
    if (/analy[sz]|data|chart|report|metric|statistic/i.test(searchText)) return 'analysis';
    if (/chat|message|email|communication|talk|conversation/i.test(searchText)) return 'communication';
    if (/code|program|develop|script|function|debug/i.test(searchText)) return 'coding';
    if (/vision|image|photo|visual|ocr|detect|recognize/i.test(searchText)) return 'vision';
    if (/api|rest|http|integration|webhook|endpoint/i.test(searchText)) return 'api';
    if (/logic|reason|think|decision|rule|condition/i.test(searchText)) return 'logic';
    if (/cloud|aws|azure|gcp|server|deploy|network/i.test(searchText)) return 'cloud';
    if (/search|find|query|lookup|browse/i.test(searchText)) return 'analysis';
    if (/test|debug|check|verify|validate/i.test(searchText)) return 'development';
    
    return 'general';
};

// Get AI skill icon based on inferred category
const getCategoryIcon = (skill: Skill, status?: Skill['status']) => {
    const isLearning = status === 'learning';
    const category = skill.category || inferCategory(skill);
    
    switch (category) {
        case 'automation':
            return isLearning ? <SyncOutlined spin /> : <ThunderboltOutlined />;
        case 'analysis':
            return isLearning ? <SyncOutlined spin /> : <RadarChartOutlined />;
        case 'communication':
            return isLearning ? <SyncOutlined spin /> : <MessageOutlined />;
        case 'coding':
        case 'development':
            return isLearning ? <SyncOutlined spin /> : <CodeOutlined />;
        case 'vision':
        case 'image':
            return isLearning ? <SyncOutlined spin /> : <EyeOutlined />;
        case 'api':
        case 'integration':
            return isLearning ? <SyncOutlined spin /> : <ApiOutlined />;
        case 'logic':
        case 'reasoning':
            return isLearning ? <SyncOutlined spin /> : <BranchesOutlined />;
        case 'cloud':
        case 'network':
            return isLearning ? <SyncOutlined spin /> : <CloudOutlined />;
        case 'general':
        default:
            if (status === 'planned') return <ExperimentOutlined />;
            return isLearning ? <SyncOutlined spin /> : <BulbOutlined />;
    }
};

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
    const [filters, setFilters] = useState<SkillFilterOptions>({
        sortBy: 'name',
    });

    // Scroll position preservation for keepalive
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const savedScrollPositionRef = useRef<number>(0);

    // Restore scroll position when component becomes active
    useEffectOnActive(
        () => {
            const container = scrollContainerRef.current;
            if (container && savedScrollPositionRef.current > 0) {
                requestAnimationFrame(() => {
                    if (container) {
                        container.scrollTop = savedScrollPositionRef.current;
                    }
                });
            }
            
            return () => {
                const container = scrollContainerRef.current;
                if (container) {
                    savedScrollPositionRef.current = container.scrollTop;
                }
            };
        },
        []
    );

    // Save scroll position when scrolling
    const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
        savedScrollPositionRef.current = e.currentTarget.scrollTop;
    };

    // 筛选和Sort技能
    const filteredAndSortedSkills = useMemo(() => {
        let result = [...skills];

        // 1. 先按StatusFilter（If有SelectStatus）
        // 没SelectStatus时，filters.status 为 undefined，DefaultDisplayAllStatus
        if (filters.status) {
            result = result.filter(skill => skill.status === filters.status);
        }

        // 2. 在StatusFilterResult中，再按Search关键字匹配Name、Description和类别
        if (filters.search) {
            const searchLower = filters.search.toLowerCase();
            result = result.filter(skill => {
                const category = skill.category || inferCategory(skill);
                return skill.name?.toLowerCase().includes(searchLower) ||
                    skill.description?.toLowerCase().includes(searchLower) ||
                    category.toLowerCase().includes(searchLower);
            });
        }

        // Sort
        result.sort((a, b) => {
            switch (filters.sortBy) {
                case 'name': {
                    const nameA = a.name || '';
                    const nameB = b.name || '';
                    return nameA.localeCompare(nameB);
                }
                case 'status': {
                    const statusA = a.status || '';
                    const statusB = b.status || '';
                    return statusA.localeCompare(statusB);
                }
                case 'level': {
                    const levelA = typeof a.level === 'string' ? parseInt(a.level, 10) : (a.level || 0);
                    const levelB = typeof b.level === 'string' ? parseInt(b.level, 10) : (b.level || 0);
                    return levelB - levelA; // 高Level在前
                }
                default:
                    return 0;
            }
        });

        return result;
    }, [skills, filters]);

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
        <ListContainer>
            <SkillFilters filters={filters} onChange={setFilters} />
            
            <SkillsScrollArea ref={scrollContainerRef} onScroll={handleScroll}>
                {filteredAndSortedSkills.length === 0 ? (
                    <EmptyContainer>
                        <Empty
                            image={Empty.PRESENTED_IMAGE_SIMPLE}
                            description={t('pages.skills.noMatchingSkills', '未找到匹配的技能')}
                        />
                    </EmptyContainer>
                ) : (
                    <List
                        dataSource={filteredAndSortedSkills}
                        loading={loading}
                        renderItem={skill => {
                const statusConfig = getStatusConfig(skill.status);
                // 确保两边都是字符串Type进行比较
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
                                    {getCategoryIcon(skill, skill.status)}
                                </SkillIcon>
                                <SkillMeta>
                                    <SkillName>{skill.name}</SkillName>
                                    <Space size={6} wrap>
                                        <Tag color={statusConfig.color} icon={statusConfig.icon}>
                                            {t(`pages.skills.status.${skill.status || 'unknown'}`, statusConfig.text)}
                                        </Tag>
                                        {(() => {
                                            const displayCategory = skill.category || inferCategory(skill);
                                            return (
                                                <Tag color="blue">
                                                    {t(`pages.skills.categories.${displayCategory}`, displayCategory)}
                                                </Tag>
                                            );
                                        })()}
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
                )}
            </SkillsScrollArea>
        </ListContainer>
    );
};

export default SkillList;
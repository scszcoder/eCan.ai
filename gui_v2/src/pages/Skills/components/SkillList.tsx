import React, { useState, useMemo, useRef, useEffect } from 'react';
import { List, Tag, Typography, Space, Empty, Collapse } from 'antd';
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
    CloudOutlined,
    CloudFilled,
    DollarCircleFilled,
    StarFilled,
    TeamOutlined,
    CopyOutlined,
    DownloadOutlined,
} from '@ant-design/icons';

import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { Skill } from '@/types/domain/skill';
import { SkillFilters, SkillFilterOptions } from './SkillFilters';
import { logger } from '@/utils/logger';

const { Text } = Typography;

const ListContainer = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
`;

const GridContainer = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 12px;
    padding: 8px 0;
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

const GridSkillItem = styled(SkillItem)`
    margin: 0;
    height: 100%;
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

const SkillRatingRow = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
`;

const StarRating = styled.span`
    display: inline-flex;
    gap: 2px;
    .anticon {
        font-size: 14px;
        color: #faad14;
    }
`;

const SubsLabel = styled.span`
    font-size: 12px;
    color: rgba(255, 255, 255, 0.45);
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    .anticon {
        font-size: 13px;
    }
`;

const EmptyContainer = styled.div`
    padding: 60px 20px;
    text-align: center;
`;

const SkillActionBar = styled.div`
    display: flex;
    gap: 6px;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
`;

const ActionBtn = styled.button`
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 500;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
    &:hover {
        background: rgba(24, 144, 255, 0.15);
        border-color: rgba(24, 144, 255, 0.4);
        color: #1890ff;
    }
`;

const MiniBadge = styled.div<{ $variant: 'free' | 'paid' }>`
    position: absolute;
    top: 4px;
    right: 4px;
    font-size: 7px;
    font-weight: 600;
    padding: 1px 3px;
    border-radius: 4px;
    color: ${props => props.$variant === 'free' ? 'rgba(255, 255, 255, 0.95)' : 'rgba(250, 204, 21, 0.95)'};
    background: ${props => props.$variant === 'free' ? 'rgba(239, 68, 68, 0.9)' : 'rgba(17, 24, 39, 0.65)'};
    border: 1px solid ${props => props.$variant === 'free' ? 'rgba(239, 68, 68, 0.9)' : 'rgba(250, 204, 21, 0.55)'};
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
    line-height: 1;
`;

const ExecBadge = styled.div`
    position: absolute;
    top: -3px;
    left: -3px;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2;
    .anticon {
        font-size: 15px;
        filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.5));
    }
`;

const HalfCloudIcon: React.FC<{ size?: number }> = ({ size = 15 }) => (
    <svg width={size} height={size} viewBox="0 0 1024 1024" style={{ display: 'block' }}>
        <defs>
            <clipPath id="half-left">
                <rect x="0" y="0" width="512" height="1024" />
            </clipPath>
            <clipPath id="half-right">
                <rect x="512" y="0" width="512" height="1024" />
            </clipPath>
        </defs>
        {/* Cloud path from Ant Design CloudFilled */}
        <path
            clipPath="url(#half-left)"
            d="M811.4 418.7C765.6 297.9 648.9 212 512.2 212S258.8 297.8 213 418.6C127.3 441.1 64 519.1 64 612c0 110.5 89.5 200 200 200h496c110.5 0 200-89.5 200-200 0-92.8-63.3-170.7-148.6-193.3z"
            fill="rgba(255,255,255,0.35)"
        />
        <path
            clipPath="url(#half-right)"
            d="M811.4 418.7C765.6 297.9 648.9 212 512.2 212S258.8 297.8 213 418.6C127.3 441.1 64 519.1 64 612c0 110.5 89.5 200 200 200h496c110.5 0 200-89.5 200-200 0-92.8-63.3-170.7-148.6-193.3z"
            fill="#1890ff"
        />
    </svg>
);

const getExecMode = (skill: Skill): 'local' | 'cloud' | 'hybrid' => {
    // 1. Check explicit exec_mode / execMode field first
    const mode = ((skill as any).exec_mode || (skill as any).execMode || '').toLowerCase();
    if (mode === 'cloud') return 'cloud';
    if (mode === 'hybrid') return 'hybrid';
    if (mode === 'local') return 'local';

    // 2. Fall back to config stored in DB: config.run_in_cloud / config.hybrid_cloud_mode
    const cfg = (skill as any).config;
    if (cfg && typeof cfg === 'object') {
        const runInCloud = cfg.run_in_cloud === true || cfg.run_in_cloud === 'true';
        const hybridCloud = cfg.hybrid_cloud_mode === true || cfg.hybrid_cloud_mode === 'true';
        if (runInCloud && hybridCloud) return 'hybrid';
        if (runInCloud) return 'cloud';
    }

    // 3. Also check top-level run_in_cloud (in case backend flattens it)
    if ((skill as any).run_in_cloud === true) {
        if ((skill as any).hybrid_cloud_mode === true) return 'hybrid';
        return 'cloud';
    }

    return 'local';
};

/** Safely coerce tags to string[] – handles JSON strings, arrays, and nullish values */
const safeTags = (tags: unknown): string[] => {
    if (Array.isArray(tags)) return tags;
    if (typeof tags === 'string') {
        try { const parsed = JSON.parse(tags); if (Array.isArray(parsed)) return parsed; } catch { /* ignore */ }
        return tags ? [tags] : [];
    }
    return [];
};

// Infer category from skill name, description, and tags
const inferCategory = (skill: Skill): string => {
    const searchText = `${skill.name} ${skill.description || ''} ${safeTags(skill.tags).join(' ')}`.toLowerCase();
    
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

const normalizeValue = (value: unknown): string => String(value ?? '').trim();

const isResourceMySkillsPath = (path?: string | null): boolean => {
    if (!path) return false;
    const norm = String(path).replace(/\\/g, '/');
    return norm.includes('/resource/my_skills/') || norm.startsWith('resource/my_skills/');
};

const isCodeSkill = (skill: Skill): boolean => normalizeValue((skill as any)?.source).toLowerCase() === 'code';

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
                icon: <CheckCircleOutlined />
            };
        case 'learning':
            return {
                color: 'processing',
                icon: <SyncOutlined spin />
            };
        case 'planned':
            return {
                color: 'default',
                icon: <ExperimentOutlined />
            };
        default:
            return {
                color: 'default',
                icon: <RobotOutlined />
            };
    }
};

interface SkillListProps {
    skills: Skill[];
    publicSkills?: Skill[];
    loading: boolean;
    onSelectSkill: (skill: Skill) => void;
    selectedSkillId?: string;
    viewMode: 'list' | 'grid';
    username: string;
    subscribedSkillIds?: string[];
}

const SkillList: React.FC<SkillListProps> = ({
    skills,
    publicSkills,
    loading,
    onSelectSkill,
    selectedSkillId,
    viewMode,
    username,
    subscribedSkillIds,
}) => {
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

    const applyFiltersAndSort = (rows: Skill[]) => {
        let result = [...rows];

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
    };

    const mySkills = useMemo(() => {
        const me = normalizeValue(username).toLowerCase();
        const candidates = (skills || []).filter((skill) => {
            const owner = normalizeValue((skill as any)?.owner).toLowerCase();
            const path = normalizeValue((skill as any)?.path);
            const source = normalizeValue((skill as any)?.source).toLowerCase();
            const skillId = normalizeValue((skill as any)?.id).toLowerCase();
            const isOwnedByOwner = !!owner && !!me && owner === me;
            const isOwnedByPath = isResourceMySkillsPath(path);
            const isLocalCodeSkill = source === 'code' || skillId.startsWith('code-skill-');
            return isOwnedByOwner || isOwnedByPath || isLocalCodeSkill;
        });

        logger.debug('[SkillList][mySkills] skills count:', skills?.length, 'candidates count:', candidates.length);

        const localPreferredNames = new Set(
            candidates
                .filter((skill) => {
                    const path = normalizeValue((skill as any)?.path);
                    const source = normalizeValue((skill as any)?.source).toLowerCase();
                    const skillId = normalizeValue((skill as any)?.id).toLowerCase();
                    return isResourceMySkillsPath(path) || source === 'code' || skillId.startsWith('code-skill-');
                })
                .map((skill) => normalizeValue(skill.name).toLowerCase())
                .filter(Boolean)
        );

        const rows = candidates.filter((skill) => {
            const skillName = normalizeValue(skill.name).toLowerCase();
            if (!skillName || !localPreferredNames.has(skillName)) {
                return true;
            }

            const path = normalizeValue((skill as any)?.path);
            const source = normalizeValue((skill as any)?.source).toLowerCase();
            const skillId = normalizeValue((skill as any)?.id).toLowerCase();
            return isResourceMySkillsPath(path) || source === 'code' || skillId.startsWith('code-skill-');
        });

        // Deduplicate by ID to prevent stale store entries from showing twice
        const seenIds = new Set<string>();
        const dedupedRows = rows.filter((skill) => {
            const id = String((skill as any)?.id ?? '');
            if (!id || seenIds.has(id)) return false;
            seenIds.add(id);
            return true;
        });

        return applyFiltersAndSort(dedupedRows);
    }, [skills, filters, username]);
    const storeSkills = useMemo(() => applyFiltersAndSort(publicSkills || []), [publicSkills, filters]);

    useEffect(() => {
        logger.debug(
            '[SkillList][diag] incoming skills:',
            (skills || []).map((skill) => `${skill.name}#${skill.id}`)
        );
        logger.debug(
            '[SkillList][diag] filtered mySkills:',
            mySkills.map((skill) => `${skill.name}#${skill.id}`)
        );
        logger.debug(
            '[SkillList][diag] incoming publicSkills:',
            (publicSkills || []).map((skill) => `${skill.name}#${skill.id}`)
        );
        logger.debug(
            '[SkillList][diag] filtered storeSkills:',
            storeSkills.map((skill) => `${skill.name}#${skill.id}`)
        );
        logger.debug(
            '[SkillList][diag] basic_chatter_xxx incoming/filtered:',
            {
                incoming: (skills || []).some((skill) => skill.name === 'basic_chatter_xxx'),
                filtered: mySkills.some((skill) => skill.name === 'basic_chatter_xxx'),
                filters,
            }
        );
    }, [skills, mySkills, publicSkills, storeSkills, filters]);

    const isSkillSubscribed = (skill: Skill) => {
        const subscribedSet = new Set((subscribedSkillIds || []).map((id) => String(id)));
        const skillId = String((skill as any)?.id ?? '').trim();
        const skillAskid = String((skill as any)?.askid ?? '').trim();
        return !!(
            (skillId && subscribedSet.has(skillId))
            || (skillAskid && skillAskid !== '0' && subscribedSet.has(skillAskid))
        );
    };

    const isPaidSkill = (skill: Skill): boolean => {
        const price = (skill as any)?.price;
        if (typeof price === 'number') return price > 0;
        if (typeof price === 'string') {
            const v = Number(price);
            return Number.isFinite(v) && v > 0;
        }
        return false;
    };

    if (!loading && (skills.length === 0) && ((publicSkills || []).length === 0)) {
        return (
            <EmptyContainer>
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                        <Space direction="vertical" size={4}>
                            <Text style={{ color: 'var(--text-secondary)' }}>
                                {t('pages.skills.noSkills')}
                            </Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                {t('pages.skills.clickAddToCreate')}
                            </Text>
                        </Space>
                    }
                />
            </EmptyContainer>
        );
    }

    const renderSkillCard = (skill: Skill, opts: { grid: boolean }) => {
        const statusConfig = getStatusConfig(skill.status);
        const skillIdStr = String(skill.id);
        const isSelected = selectedSkillId !== undefined && selectedSkillId === skillIdStr;
        const paid = isPaidSkill(skill);
        const isSubscribedSkill = isSkillSubscribed(skill);

        const CardComp: any = opts.grid ? GridSkillItem : SkillItem;

        return (
            <CardComp
                key={skillIdStr}
                onClick={() => onSelectSkill(skill)}
                className={isSelected ? 'selected' : ''}
            >
                <SkillHeader>
                    <Space align="start" style={{ flex: 1 }}>
                        <SkillIcon status={skill.status}>
                            <ExecBadge title={t(`pages.skills.execMode.${getExecMode(skill)}`, `${getExecMode(skill)} execution`)}>
                                {getExecMode(skill) === 'cloud' ? (
                                    <CloudFilled style={{ color: '#1890ff' }} />
                                ) : getExecMode(skill) === 'hybrid' ? (
                                    <HalfCloudIcon />
                                ) : (
                                    <CloudOutlined style={{ color: 'rgba(255,255,255,0.35)' }} />
                                )}
                            </ExecBadge>
                            {paid ? (
                                <MiniBadge $variant="paid">
                                    <DollarCircleFilled />
                                </MiniBadge>
                            ) : (
                                <MiniBadge $variant="free">{t('pages.skills.free')}</MiniBadge>
                            )}
                            {getCategoryIcon(skill, skill.status)}
                        </SkillIcon>
                        <SkillMeta>
                            <SkillName>{skill.name}</SkillName>
                            <Space size={6} wrap>
                                <Tag color={statusConfig.color} icon={statusConfig.icon}>
                                    {t(`pages.skills.status.${skill.status || 'unknown'}`)}
                                </Tag>
                                {isCodeSkill(skill) && (
                                    <Tag color="geekblue">
                                        {t('pages.skills.codeSkill', 'Code')}
                                    </Tag>
                                )}
                                {!isCodeSkill(skill) && !isResourceMySkillsPath(String((skill as any)?.path || '')) && (() => {
                                    const skillOwner = normalizeValue((skill as any)?.owner).toLowerCase();
                                    const me = normalizeValue(username).toLowerCase();
                                    if (!skillOwner || skillOwner === me) return null;
                                    return (
                                        <Tag color="purple">
                                            {t('pages.skills.storeSkill', 'Store')}
                                        </Tag>
                                    );
                                })()}
                                {(() => {
                                    const displayCategory = skill.category || inferCategory(skill);
                                    return (
                                        <Tag color="blue">{t(`pages.skills.categories.${displayCategory}`, displayCategory)}</Tag>
                                    );
                                })()}
                                {(() => {
                                    const owner = normalizeValue((skill as any)?.owner);
                                    if (!owner) return null;
                                    return <Tag>{owner}</Tag>;
                                })()}
                                {isSubscribedSkill && (
                                    <Tag color="green">{t('pages.skills.subscribed')}</Tag>
                                )}
                            </Space>
                        </SkillMeta>
                    </Space>
                </SkillHeader>

                <SkillRatingRow>
                    <StarRating>
                        {[1, 2, 3, 4, 5].map((star) => {
                            const rating = (skill as any).rating ?? 0;
                            return star <= rating
                                ? <StarFilled key={star} />
                                : <StarOutlined key={star} style={{ color: 'rgba(255,255,255,0.2)' }} />;
                        })}
                    </StarRating>
                    <SubsLabel>
                        <TeamOutlined />
                        {(skill as any).subscribers ?? 0} {t('pages.skills.subscribers')}
                    </SubsLabel>
                </SkillRatingRow>

                {((skill as any).usageCount !== undefined || (skill as any).lastUsed) && (
                    <SkillStats>
                        {(skill as any).usageCount !== undefined && (
                            <StatItem>
                                <StarOutlined />
                                <span>
                                    {t('pages.skills.usageCount')}: {(skill as any).usageCount}
                                </span>
                            </StatItem>
                        )}
                        {(skill as any).lastUsed && (
                            <StatItem>
                                <ClockCircleOutlined />
                                <span>
                                    {t('pages.skills.lastUsed')}: {(skill as any).lastUsed}
                                </span>
                            </StatItem>
                        )}
                    </SkillStats>
                )}

                {/* Copy / Download buttons -- only for non-owned FREE skills */}
                {(() => {
                    const skillOwner = ((skill as any).owner || '').trim().toLowerCase();
                    const me = (username || '').trim().toLowerCase();
                    const isNotMine = skillOwner && skillOwner !== me;
                    if (!isNotMine) return null;
                    if (paid) return null;
                    return (
                        <SkillActionBar onClick={(e: React.MouseEvent) => e.stopPropagation()}>
                            <ActionBtn
                                title={t('pages.skills.copySkill', 'Copy Skill')}
                                onClick={(e: React.MouseEvent) => {
                                    e.stopPropagation();
                                    window.dispatchEvent(new CustomEvent('ecan:copy-skill', { detail: { skill } }));
                                }}
                            >
                                <CopyOutlined /> {t('common.copy', 'Copy')}
                            </ActionBtn>
                            <ActionBtn
                                title={t('pages.skills.downloadJson', 'Download JSON')}
                                onClick={(e: React.MouseEvent) => {
                                    e.stopPropagation();
                                    const blob = new Blob([JSON.stringify(skill, null, 2)], { type: 'application/json' });
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = `${skill.name || 'skill'}.json`;
                                    a.click();
                                    URL.revokeObjectURL(url);
                                }}
                            >
                                <DownloadOutlined /> {t('pages.skills.download', 'Download')}
                            </ActionBtn>
                        </SkillActionBar>
                    );
                })()}
            </CardComp>
        );
    };

    const renderSection = (rows: Skill[], opts: { grid: boolean }) => {
        if (rows.length === 0) {
            return (
                <EmptyContainer>
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('pages.skills.noMatchingSkills')} />
                </EmptyContainer>
            );
        }

        if (opts.grid) {
            return <GridContainer>{rows.map((s) => renderSkillCard(s, { grid: true }))}</GridContainer>;
        }

        return (
            <List
                dataSource={rows}
                loading={loading}
                renderItem={(skill) => renderSkillCard(skill, { grid: false }) as any}
            />
        );
    };

    const collapseItems = [
        {
            key: 'my',
            label: t('pages.skills.sections.mySkills'),
            children: renderSection(mySkills, { grid: viewMode === 'grid' }),
        },
        {
            key: 'store',
            label: t('pages.skills.sections.skillStore'),
            children: renderSection(storeSkills, { grid: viewMode === 'grid' }),
        },
    ];

    return (
        <ListContainer>
            <SkillFilters filters={filters} onChange={setFilters} />

            <SkillsScrollArea ref={scrollContainerRef} onScroll={handleScroll}>
                <Collapse
                    ghost
                    defaultActiveKey={['my', 'store']}
                    items={collapseItems as any}
                />
            </SkillsScrollArea>
        </ListContainer>
    );
};

export default SkillList;
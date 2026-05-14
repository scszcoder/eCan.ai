import React, { useState, useMemo, useRef, useEffect } from 'react';
import { Tag, Typography, Space, Empty, Drawer, Button, Spin } from 'antd';
import { useEffectOnActive } from 'keepalive-for-react';
import {
    RobotOutlined,
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
    CloseOutlined,
    EditOutlined,
    PlayCircleOutlined,
    UserOutlined,
    ShopOutlined,
} from '@ant-design/icons';

import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { Skill } from '@/types/domain/skill';
import { SkillFilters, SkillFilterOptions } from './SkillFilters';
import { logger } from '@/utils/logger';

const { Paragraph } = Typography;

const ListContainer = styled.div`
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
`;

const GridContainer = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
    padding: 12px;
    flex: 1;
    overflow-y: auto;
    align-content: start;
    height: 100%;
    box-sizing: border-box;

    &::-webkit-scrollbar {
        width: 6px;
    }
    &::-webkit-scrollbar-track {
        background: transparent;
    }
    &::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.15);
        border-radius: 3px;
    }
`;

const ListViewContainer = styled.div`
    flex: 1;
    overflow-y: auto;
    padding: 0 8px 8px;

    &::-webkit-scrollbar {
        width: 6px;
    }
    &::-webkit-scrollbar-track {
        background: transparent;
    }
    &::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.15);
        border-radius: 3px;
    }
`;

// 网格卡片样式 - 紧凑水平布局
const GridCard = styled.div<{ $selected?: boolean }>`
    background: var(--bg-secondary);
    border-radius: 12px;
    padding: 14px;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid ${props => props.$selected ? 'var(--primary-color)' : 'rgba(255, 255, 255, 0.06)'};
    position: relative;
    overflow: visible;
    min-height: 72px;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 12px;

    &:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        border-color: rgba(24, 144, 255, 0.3);
    }

    ${props => props.$selected && `
        border-color: var(--primary-color);
        box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.25);
    `}
`;

// 图标容器 - 小圆点徽章
const CardIconWrapper = styled.div`
    width: 38px;
    height: 38px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    flex-shrink: 0;

    .anticon {
        color: white;
    }
`;

// 免费/付费徽章 - 柔和胶囊样式
const PriceBadge = styled.div<{ $isFree: boolean }>`
    position: absolute;
    top: 12px;
    right: 12px;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    z-index: 2;

    ${props => props.$isFree ? `
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
    ` : `
        background: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.3);
    `}
`;

// 卡片标题
const CardTitle = styled.div`
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    letter-spacing: -0.01em;
    min-width: 0;
`;

// 标签区域 - 柔和胶囊标签
const CardTags = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
    min-height: 20px;
`;

// 统计信息
const CardStats = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 6px;
    flex-shrink: 0;
`;

const CardContent = styled.div`
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
`;

const StatItem = styled.div`
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--text-secondary);

    .anticon {
        font-size: 11px;
        opacity: 0.7;
    }
`;

// 列表视图样式 - 现代卡片风格
const SkillItem = styled.div`
    padding: 14px 16px;
    cursor: pointer;
    transition: all 0.15s ease;
    background: var(--bg-secondary);
    border-radius: 12px;
    margin-bottom: 6px;
    border: 1px solid rgba(255, 255, 255, 0.05);
    display: flex;
    align-items: center;
    gap: 14px;

    &:hover {
        background: var(--bg-tertiary);
        border-color: rgba(24, 144, 255, 0.2);
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
    }

    &.selected {
        background: rgba(24, 144, 255, 0.08);
        border-color: rgba(24, 144, 255, 0.4);
    }
`;

const ListItemIcon = styled.div`
    width: 42px;
    height: 42px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    background: linear-gradient(145deg, var(--primary-color), #8b5cf6);
    box-shadow: 0 3px 10px rgba(139, 92, 246, 0.3);

    .anticon {
        color: white;
        font-size: 18px;
    }
`;

const ListItemContent = styled.div`
    flex: 1;
    min-width: 0;
`;

const ListItemTitle = styled.div`
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
`;

const ListItemMeta = styled.div`
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 2px;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
`;

const ListItemOwner = styled.div`
    font-size: 11px;
    color: var(--text-tertiary, rgba(255, 255, 255, 0.4));
    margin-top: 3px;
    display: flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    .anticon {
        font-size: 11px;
        flex-shrink: 0;
        opacity: 0.6;
    }
`;

const PriceTag = styled.span<{ $isFree: boolean }>`
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 20px;
    text-transform: uppercase;

    ${props => props.$isFree ? `
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.25);
    ` : `
        background: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.25);
    `}
`;

const StatGroup = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
`;

const EmptyContainer = styled.div`
    padding: 60px 20px;
    text-align: center;
`;

// 详情抽屉样式
const DetailHeader = styled.div`
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 16px;
`;

const DetailIconArea = styled.div`
    width: 72px;
    height: 72px;
    border-radius: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 36px;
    background: linear-gradient(135deg, var(--primary-color), #8b5cf6);
    box-shadow: 0 8px 24px rgba(139, 92, 246, 0.4);

    .anticon {
        color: white;
    }
`;

const DetailTitle = styled.div`
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 8px;
`;

const DetailTags = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
`;

const DetailSection = styled.div`
    margin-bottom: 20px;
`;

const DetailSectionTitle = styled.div`
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
`;

const DetailDescription = styled(Paragraph)`
    color: var(--text-primary);
    margin-bottom: 0;
    line-height: 1.6;
`;

const DetailStats = styled.div`
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.03);
    border-radius: 12px;
    margin-bottom: 20px;
`;

const DetailStatItem = styled.div`
    text-align: center;
`;

const DetailStatValue = styled.div`
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
`;

const DetailStatLabel = styled.div`
    font-size: 11px;
    color: var(--text-secondary);
    margin-top: 4px;
`;

const DetailActions = styled.div`
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-top: 16px;
    border-top: 1px solid var(--border-color);
`;

// Helper functions
const getExecMode = (skill: Skill): 'local' | 'cloud' | 'hybrid' => {
    const mode = ((skill as any).exec_mode || (skill as any).execMode || '').toLowerCase();
    if (mode === 'cloud') return 'cloud';
    if (mode === 'hybrid') return 'hybrid';
    if (mode === 'local') return 'local';

    const cfg = (skill as any).config;
    if (cfg && typeof cfg === 'object') {
        const runInCloud = cfg.run_in_cloud === true || cfg.run_in_cloud === 'true';
        const hybridCloud = cfg.hybrid_cloud_mode === true || cfg.hybrid_cloud_mode === 'true';
        if (runInCloud && hybridCloud) return 'hybrid';
        if (runInCloud) return 'cloud';
    }

    if ((skill as any).run_in_cloud === true) {
        if ((skill as any).hybrid_cloud_mode === true) return 'hybrid';
        return 'cloud';
    }

    return 'local';
};

const safeTags = (tags: unknown): string[] => {
    if (Array.isArray(tags)) return tags;
    if (typeof tags === 'string') {
        try { const parsed = JSON.parse(tags); if (Array.isArray(parsed)) return parsed; } catch { /* ignore */ }
        return tags ? [tags] : [];
    }
    return [];
};

// Helper: consistent pseudo-random from string (for icon/color assignment)
const strHash = (s: string): number => {
    let h = 0;
    for (let i = 0; i < s.length; i++) {
        h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
    }
    return Math.abs(h);
};

// Pool of icons for visual variety — each skill gets one based on name hash
const ICON_POOL = [
    { icon: <BulbOutlined />, label: 'bulb' },
    { icon: <RobotOutlined />, label: 'robot' },
    { icon: <ThunderboltOutlined />, label: 'bolt' },
    { icon: <RadarChartOutlined />, label: 'chart' },
    { icon: <MessageOutlined />, label: 'msg' },
    { icon: <CodeOutlined />, label: 'code' },
    { icon: <EyeOutlined />, label: 'eye' },
    { icon: <ApiOutlined />, label: 'api' },
    { icon: <BranchesOutlined />, label: 'branch' },
    { icon: <CloudOutlined />, label: 'cloud' },
    { icon: <ExperimentOutlined />, label: 'lab' },
    { icon: <SyncOutlined />, label: 'sync' },
    { icon: <PlayCircleOutlined />, label: 'play' },
    { icon: <DollarCircleFilled />, label: 'dollar' },
    { icon: <TeamOutlined />, label: 'team' },
    { icon: <StarOutlined />, label: 'star' },
];

// Color palettes for icon backgrounds — pairs with icon pool
const BG_PALETTES = [
    ['#8b5cf6', '#6366f1'], // purple-indigo
    ['#06b6d4', '#0891b2'], // cyan
    ['#f59e0b', '#d97706'], // amber
    ['#ec4899', '#db2777'], // pink
    ['#10b981', '#059669'], // emerald
    ['#3b82f6', '#2563eb'], // blue
    ['#ef4444', '#dc2626'], // red
    ['#14b8a6', '#0d9488'], // teal
    ['#f97316', '#ea580c'], // orange
    ['#8b5cf6', '#7c3aed'], // violet
    ['#06b6d4', '#0284c7'], // sky
    ['#a855f7', '#9333ea'], // purple
    ['#22c55e', '#16a34a'], // green
    ['#eab308', '#ca8a04'], // yellow
    ['#64748b', '#475569'], // slate
    ['#f43f5e', '#e11d48'], // rose
];

const getSkillIcon = (skill: Skill): { icon: React.ReactNode; bg: string[] } => {
    // Code skill always gets code icon with blue palette
    if (isCodeSkill(skill)) {
        return { icon: <CodeOutlined />, bg: ['#3b82f6', '#2563eb'] };
    }

    const name = skill.name || '';
    const hash = strHash(name);

    // Try category-based icon first if category is set
    const category = skill.category || inferCategory(skill);
    if (category && category !== 'general') {
        switch (category) {
            case 'automation': return { icon: <ThunderboltOutlined />, bg: ['#f59e0b', '#d97706'] };
            case 'analysis': return { icon: <RadarChartOutlined />, bg: ['#8b5cf6', '#7c3aed'] };
            case 'communication': return { icon: <MessageOutlined />, bg: ['#06b6d4', '#0891b2'] };
            case 'coding':
            case 'development': return { icon: <CodeOutlined />, bg: ['#3b82f6', '#2563eb'] };
            case 'vision':
            case 'image': return { icon: <EyeOutlined />, bg: ['#ec4899', '#db2777'] };
            case 'api':
            case 'integration': return { icon: <ApiOutlined />, bg: ['#14b8a6', '#0d9488'] };
            case 'logic':
            case 'reasoning': return { icon: <BranchesOutlined />, bg: ['#a855f7', '#9333ea'] };
            case 'cloud':
            case 'network': return { icon: <CloudOutlined />, bg: ['#64748b', '#475569'] };
            case 'search': return { icon: <BulbOutlined />, bg: ['#f97316', '#ea580c'] };
            case 'file': return { icon: <DollarCircleFilled />, bg: ['#22c55e', '#16a34a'] };
            case 'browser': return { icon: <RobotOutlined />, bg: ['#f43f5e', '#e11d48'] };
            default: break;
        }
    }

    // Fall back to pool for variety
    const poolIdx = hash % ICON_POOL.length;
    return { icon: ICON_POOL[poolIdx].icon, bg: BG_PALETTES[poolIdx] };
};

const inferCategory = (skill: Skill): string => {
    const searchText = `${skill.name} ${skill.description || ''} ${safeTags(skill.tags).join(' ')}`.toLowerCase();

    if (/automat|workflow|process|batch|schedule/i.test(searchText)) return 'automation';
    if (/analy[sz]|data|chart|report|metric|statistic/i.test(searchText)) return 'analysis';
    if (/chat|message|email|communication|talk|conversation/i.test(searchText)) return 'communication';
    if (/code|program|develop|script|function|debug/i.test(searchText)) return 'coding';
    if (/vision|image|photo|visual|ocr|detect|recognize/i.test(searchText)) return 'vision';
    if (/api|rest|http|integration|webhook|endpoint/i.test(searchText)) return 'api';
    if (/logic|reason|think|decision|rule|condition/i.test(searchText)) return 'logic';
    if (/cloud|aws|azure|gcp|server|deploy|network/i.test(searchText)) return 'cloud';
    if (/test|debug|check|verify|validate/i.test(searchText)) return 'development';
    if (/search|find|lookup|query|retrieve/i.test(searchText)) return 'search';
    if (/file|document|upload|download|export|import/i.test(searchText)) return 'file';
    if (/browser|web|page|click|scroll|navigate/i.test(searchText)) return 'browser';
    return 'general';
};

const normalizeValue = (value: unknown): string => String(value ?? '').trim();

const isResourceMySkillsPath = (path?: string | null): boolean => {
    if (!path) return false;
    const norm = String(path).replace(/\\/g, '/');
    return norm.includes('/resource/my_skills/') || norm.startsWith('resource/my_skills/');
};

const isCodeSkill = (skill: Skill): boolean => normalizeValue((skill as any)?.source).toLowerCase() === 'code';

const getDisplayOwner = (skill: Skill): string | null => {
    const owner = ((skill as any)?.owner || '').trim();
    if (!owner || owner.toLowerCase() === 'unknown') return null;
    return owner;
};

const getStatusConfig = (status: Skill['status']) => {
    switch (status) {
        case 'active': return { color: 'success', icon: <CheckCircleOutlined /> };
        case 'learning': return { color: 'processing', icon: <SyncOutlined spin /> };
        case 'planned': return { color: 'default', icon: <ExperimentOutlined /> };
        default: return { color: 'default', icon: <RobotOutlined /> };
    }
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

interface SkillListProps {
    skills: Skill[];
    publicSkills?: Skill[];
    loading: boolean;
    onSelectSkill: (skill: Skill) => void;
    selectedSkillId?: string;
    viewMode: 'list' | 'grid';
    username: string;
    subscribedSkillIds?: string[];
    onEditInGrid?: () => void;
    onSubscribe?: (skillId: string) => Promise<void>;
    onUnsubscribe?: (skillId: string) => Promise<void>;
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
    onEditInGrid,
    onSubscribe,
    onUnsubscribe,
}) => {
    const { t } = useTranslation();
    const [filters, setFilters] = useState<SkillFilterOptions>({ sortBy: 'name' });
    const [detailDrawer, setDetailDrawer] = useState<{ open: boolean; skill: Skill | null }>({
        open: false,
        skill: null,
    });

    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const savedScrollPositionRef = useRef<number>(0);

    useEffectOnActive(
        () => {
            const container = scrollContainerRef.current;
            if (container && savedScrollPositionRef.current > 0) {
                requestAnimationFrame(() => {
                    if (container) container.scrollTop = savedScrollPositionRef.current;
                });
            }
            return () => {
                const container = scrollContainerRef.current;
                if (container) savedScrollPositionRef.current = container.scrollTop;
            };
        },
        []
    );

    const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
        savedScrollPositionRef.current = e.currentTarget.scrollTop;
    };

    const applyFiltersAndSort = (rows: Skill[]) => {
        let result = [...rows];

        if (filters.status) {
            result = result.filter(skill => skill.status === filters.status);
        }

        if (filters.search) {
            const searchLower = filters.search.toLowerCase();
            result = result.filter(skill => {
                const category = skill.category || inferCategory(skill);
                return skill.name?.toLowerCase().includes(searchLower) ||
                    skill.description?.toLowerCase().includes(searchLower) ||
                    category.toLowerCase().includes(searchLower);
            });
        }

        result.sort((a, b) => {
            switch (filters.sortBy) {
                case 'name': return (a.name || '').localeCompare(b.name || '');
                case 'status': return (a.status || '').localeCompare(b.status || '');
                case 'level': {
                    const levelA = typeof a.level === 'string' ? parseInt(a.level, 10) : (a.level || 0);
                    const levelB = typeof b.level === 'string' ? parseInt(b.level, 10) : (b.level || 0);
                    return levelB - levelA;
                }
                default: return 0;
            }
        });

        return result;
    };

    const mySkills = useMemo(() => {
        const me = normalizeValue(username).toLowerCase();
        const candidates = (skills || []).filter((skill) => {
            const owner = normalizeValue((skill as any)?.owner).toLowerCase();
            if (owner === 'unknown' || owner === '') return false; // skip unknown/empty owners
            const path = normalizeValue((skill as any)?.path);
            const source = normalizeValue((skill as any)?.source).toLowerCase();
            const skillId = normalizeValue((skill as any)?.id).toLowerCase();
            return owner === me || isResourceMySkillsPath(path) || source === 'code' || skillId.startsWith('code-skill-');
        });

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
            if (!skillName || !localPreferredNames.has(skillName)) return true;
            const path = normalizeValue((skill as any)?.path);
            const source = normalizeValue((skill as any)?.source).toLowerCase();
            const skillId = normalizeValue((skill as any)?.id).toLowerCase();
            return isResourceMySkillsPath(path) || source === 'code' || skillId.startsWith('code-skill-');
        });

        const seenIds = new Set<string>();
        return rows.filter((skill) => {
            const id = String((skill as any)?.id ?? '');
            if (!id || seenIds.has(id)) return false;
            seenIds.add(id);
            return true;
        });
    }, [skills, username]);

    const storeSkills = useMemo(() => applyFiltersAndSort(publicSkills || []), [publicSkills]);

    const isSkillSubscribed = (skill: Skill) => {
        const subscribedSet = new Set((subscribedSkillIds || []).map((id) => String(id)));
        const skillId = String((skill as any)?.id ?? '').trim();
        const skillAskid = String((skill as any)?.askid ?? '').trim();
        return !!(skillId && subscribedSet.has(skillId)) ||
            (skillAskid && skillAskid !== '0' && subscribedSet.has(skillAskid));
    };

    const handleCardClick = (skill: Skill) => {
        onSelectSkill(skill);
        if (viewMode === 'grid') {
            setDetailDrawer({ open: true, skill });
        }
    };

    const renderGridCard = (skill: Skill) => {
        const skillIdStr = String(skill.id);
        const isSelected = selectedSkillId !== undefined && selectedSkillId === skillIdStr;
        const isFree = !isPaidSkill(skill);
        const execMode = getExecMode(skill);
        const isSubscribed = isSkillSubscribed(skill);
        const { icon: skillIcon, bg: skillBg } = getSkillIcon(skill);

        return (
            <GridCard
                key={skillIdStr}
                $selected={isSelected}
                onClick={() => handleCardClick(skill)}
            >
                <PriceBadge $isFree={isFree}>
                    {isFree ? t('pages.skills.free', 'Free') : <DollarCircleFilled />}
                </PriceBadge>

                <CardIconWrapper style={{ background: `linear-gradient(145deg, ${skillBg[0]}, ${skillBg[1]})` }}>
                    {skillIcon}
                </CardIconWrapper>

                <CardContent>
                    <CardTitle title={skill.name}>{skill.name}</CardTitle>

                    <CardTags>
                        <Tag
                            color={getStatusConfig(skill.status).color}
                            style={{
                                margin: 0,
                                fontSize: 10,
                                padding: '2px 8px',
                                borderRadius: 20,
                                border: 'none',
                                fontWeight: 500,
                            }}
                        >
                            {t(`pages.skills.status.${skill.status || 'unknown'}`)}
                        </Tag>
                        {execMode === 'cloud' && (
                            <Tag
                                color="blue"
                                style={{ margin: 0, fontSize: 10, padding: '2px 8px', borderRadius: 20, border: 'none', fontWeight: 500 }}
                            >
                                <CloudFilled />
                            </Tag>
                        )}
                        {isCodeSkill(skill) && (
                            <Tag
                                color="geekblue"
                                style={{ margin: 0, fontSize: 10, padding: '2px 8px', borderRadius: 20, border: 'none', fontWeight: 500 }}
                            >
                                <CodeOutlined />
                            </Tag>
                        )}
                        {isSubscribed && (
                            <Tag
                                color="green"
                                style={{ margin: 0, fontSize: 10, padding: '2px 8px', borderRadius: 20, border: 'none', fontWeight: 500 }}
                            >
                                ✓
                            </Tag>
                        )}
                    </CardTags>

                    <CardStats>
                        <StarRatingSmall rating={(skill as any).rating ?? 0} />
                        <StatItem>
                            <TeamOutlined />
                            <span>{(skill as any).subscribers ?? 0}</span>
                        </StatItem>
                    </CardStats>
                </CardContent>
            </GridCard>
        );
    };

    const renderListItem = (skill: Skill) => {
        const skillIdStr = String(skill.id);
        const isSelected = selectedSkillId !== undefined && selectedSkillId === skillIdStr;
        const execMode = getExecMode(skill);
        const category = skill.category || inferCategory(skill);
        const isFree = !isPaidSkill(skill);
        const { icon: skillIcon, bg: skillBg } = getSkillIcon(skill);

        return (
            <SkillItem
                key={skillIdStr}
                className={isSelected ? 'selected' : ''}
                onClick={() => onSelectSkill(skill)}
            >
                <ListItemIcon style={{ background: `linear-gradient(145deg, ${skillBg[0]}, ${skillBg[1]})` }}>
                    {skillIcon}
                </ListItemIcon>
                <ListItemContent>
                    <ListItemTitle>{skill.name}</ListItemTitle>
                    <ListItemMeta>
                        <PriceTag $isFree={isFree}>
                            {isFree ? t('pages.skills.free', 'Free') : t('pages.skills.paid', 'Paid')}
                        </PriceTag>
                        {t(`pages.skills.status.${skill.status || 'unknown'}`)} · {t(`pages.skills.categories.${category}`, category)}
                        {execMode === 'cloud' && ' · Cloud'}
                    </ListItemMeta>
                    {(() => {
                        const owner = getDisplayOwner(skill);
                        return owner ? (
                            <ListItemOwner>
                                <UserOutlined />
                                <span>{owner}</span>
                            </ListItemOwner>
                        ) : null;
                    })()}
                </ListItemContent>
                <StatGroup>
                    <StarRatingSmall rating={(skill as any).rating ?? 0} />
                    <StatItem>
                        <TeamOutlined />
                        <span>{(skill as any).subscribers ?? 0}</span>
                    </StatItem>
                </StatGroup>
            </SkillItem>
        );
    };

    const renderDetailDrawer = () => {
        const skill = detailDrawer.skill;
        if (!skill) return null;

        const execMode = getExecMode(skill);
        const category = skill.category || inferCategory(skill);
        const isOwned = (() => {
            const owner = getDisplayOwner(skill);
            return !!owner && owner.toLowerCase() === normalizeValue(username).toLowerCase();
        })();
        const isSubscribed = isSkillSubscribed(skill);
        const isFree = !isPaidSkill(skill);
        const { icon: skillIcon, bg: skillBg } = getSkillIcon(skill);

        return (
            <Drawer
                title={null}
                placement="right"
                width={400}
                onClose={() => setDetailDrawer({ open: false, skill: null })}
                open={detailDrawer.open}
                closable={false}
                styles={{
                    body: { padding: 20, background: 'var(--bg-primary)' },
                    header: { display: 'none' },
                }}
            >
                <DetailHeader>
                    <Space align="start" size={16}>
                        <DetailIconArea style={{ background: `linear-gradient(135deg, ${skillBg[0]}, ${skillBg[1]})` }}>
                            {skillIcon}
                        </DetailIconArea>
                        <div>
                            <DetailTitle>{skill.name}</DetailTitle>
                            <DetailTags>
                                <Tag color={getStatusConfig(skill.status).color} style={{ borderRadius: 20, border: 'none', fontWeight: 500 }}>
                                    {t(`pages.skills.status.${skill.status || 'unknown'}`)}
                                </Tag>
                                <Tag color="blue" style={{ borderRadius: 20, border: 'none', fontWeight: 500 }}>
                                    {t(`pages.skills.categories.${category}`, category)}
                                </Tag>
                                <Tag color={isFree ? 'success' : 'warning'} style={{ borderRadius: 20, border: 'none', fontWeight: 500 }}>
                                    {isFree ? t('pages.skills.free', 'Free') : t('pages.skills.paid', 'Paid')}
                                </Tag>
                                {execMode === 'cloud' && (
                                    <Tag color="cyan" style={{ borderRadius: 20, border: 'none', fontWeight: 500 }}>
                                        {t(`pages.skills.execMode.${execMode}`, execMode)}
                                    </Tag>
                                )}
                            </DetailTags>
                        </div>
                    </Space>
                    <Button
                        type="text"
                        icon={<CloseOutlined />}
                        onClick={() => setDetailDrawer({ open: false, skill: null })}
                    />
                </DetailHeader>

                {skill.description && (
                    <DetailSection>
                        <DetailSectionTitle>{t('pages.skills.description', 'Description')}</DetailSectionTitle>
                        <DetailDescription ellipsis={{ rows: 3, expandable: true }}>
                            {skill.description}
                        </DetailDescription>
                    </DetailSection>
                )}

                {(() => {
                    const owner = getDisplayOwner(skill);
                    return owner ? (
                        <DetailSection>
                            <DetailSectionTitle>{t('pages.skills.owner', 'Owner')}</DetailSectionTitle>
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: 8,
                                padding: '8px 12px',
                                background: 'rgba(255, 255, 255, 0.04)',
                                borderRadius: 8,
                                fontSize: 13,
                            }}>
                                <UserOutlined style={{ color: 'var(--primary-color)', fontSize: 14 }} />
                                <span style={{ color: 'var(--text-primary)', wordBreak: 'break-all' }}>{owner}</span>
                            </div>
                        </DetailSection>
                    ) : null;
                })()}

                <DetailStats>
                    <DetailStatItem>
                        <DetailStatValue>{(skill as any).rating ?? 0}</DetailStatValue>
                        <DetailStatLabel>{t('pages.skills.rating', 'Rating')}</DetailStatLabel>
                    </DetailStatItem>
                    <DetailStatItem>
                        <DetailStatValue>{(skill as any).subscribers ?? 0}</DetailStatValue>
                        <DetailStatLabel>{t('pages.skills.subscribers', 'Subscribers')}</DetailStatLabel>
                    </DetailStatItem>
                    <DetailStatItem>
                        <DetailStatValue>{(skill as any).usageCount ?? 0}</DetailStatValue>
                        <DetailStatLabel>{t('pages.skills.usageCount', 'Usage')}</DetailStatLabel>
                    </DetailStatItem>
                </DetailStats>

                {(skill as any).tags && (
                    <DetailSection>
                        <DetailSectionTitle>{t('pages.skills.tags', 'Tags')}</DetailSectionTitle>
                        <Space size={6} wrap>
                            {safeTags((skill as any).tags).map((tag, idx) => (
                                <Tag key={idx} style={{ borderRadius: 6 }}>{tag}</Tag>
                            ))}
                        </Space>
                    </DetailSection>
                )}

                <DetailActions>
                    {isOwned ? (
                        <>
                            <Button
                                type="primary"
                                icon={<EditOutlined />}
                                block
                                onClick={() => {
                                    setDetailDrawer({ open: false, skill: null });
                                    onSelectSkill(skill);
                                    if (onEditInGrid) {
                                        onEditInGrid();
                                    }
                                }}
                            >
                                {t('pages.skills.edit', 'Edit Skill')}
                            </Button>
                            <Button icon={<PlayCircleOutlined />} block>
                                {t('pages.skills.run', 'Run Skill')}
                            </Button>
                        </>
                    ) : (
                        <>
                            {isSubscribed ? (
                                <Button
                                    block
                                    onClick={async () => {
                                        try {
                                            await onUnsubscribe?.(String((skill as any)?.id));
                                            // Refresh the drawer state
                                            setDetailDrawer({ open: true, skill });
                                        } catch (e) {
                                            console.error('Unsubscribe error:', e);
                                        }
                                    }}
                                >
                                    {t('pages.skills.unsubscribe', 'Unsubscribe')}
                                </Button>
                            ) : (
                                <Button
                                    type="primary"
                                    icon={<DownloadOutlined />}
                                    block
                                    onClick={async () => {
                                        try {
                                            await onSubscribe?.(String((skill as any)?.id));
                                            // Refresh the drawer state
                                            setDetailDrawer({ open: true, skill });
                                        } catch (e) {
                                            console.error('Subscribe error:', e);
                                        }
                                    }}
                                >
                                    {t('pages.skills.subscribe', 'Subscribe')}
                                </Button>
                            )}
                            {isFree && (
                                <Button icon={<CopyOutlined />} block>
                                    {t('pages.skills.copy', 'Copy to My Skills')}
                                </Button>
                            )}
                        </>
                    )}
                </DetailActions>
            </Drawer>
        );
    };

    if (loading) {
        return (
            <ListContainer style={{ justifyContent: 'center', alignItems: 'center' }}>
                <Spin size="large" />
            </ListContainer>
        );
    }

    if ((skills.length === 0) && ((publicSkills || []).length === 0)) {
        return (
            <EmptyContainer>
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                        <Space direction="vertical" size={4}>
                            <span style={{ color: 'var(--text-secondary)' }}>
                                {t('pages.skills.noSkills')}
                            </span>
                            <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                                {t('pages.skills.clickAddToCreate')}
                            </span>
                        </Space>
                    }
                />
            </EmptyContainer>
        );
    }

    const allSkills = applyFiltersAndSort([...mySkills, ...storeSkills]);

    return (
        <ListContainer>
            <SkillFilters filters={filters} onChange={setFilters} />

            {viewMode === 'grid' ? (
                <GridContainer ref={scrollContainerRef as any} onScroll={handleScroll}>
                    {allSkills.length === 0 ? (
                        <EmptyContainer style={{ gridColumn: '1 / -1' }}>
                            <Empty description={t('pages.skills.noMatchingSkills')} />
                        </EmptyContainer>
                    ) : (
                        <>
                            {mySkills.length > 0 && (
                                <>
                                    <GridSectionTitle>
                                        <UserOutlined /> {t('pages.skills.sections.mySkills', 'My Skills')}
                                    </GridSectionTitle>
                                    {mySkills.map(renderGridCard)}
                                </>
                            )}
                            {storeSkills.length > 0 && (
                                <>
                                    <GridSectionTitle>
                                        <ShopOutlined /> {t('pages.skills.sections.skillStore', 'Skill Store')}
                                    </GridSectionTitle>
                                    {storeSkills.map(renderGridCard)}
                                </>
                            )}
                        </>
                    )}
                </GridContainer>
            ) : (
                <ListViewContainer ref={scrollContainerRef as any} onScroll={handleScroll}>
                    {mySkills.length > 0 && (
                        <>
                            <SectionTitle>{t('pages.skills.sections.mySkills', 'My Skills')}</SectionTitle>
                            {mySkills.map(renderListItem)}
                        </>
                    )}
                    {storeSkills.length > 0 && (
                        <>
                            <SectionTitle>{t('pages.skills.sections.skillStore', 'Skill Store')}</SectionTitle>
                            {storeSkills.map(renderListItem)}
                        </>
                    )}
                    {allSkills.length === 0 && (
                        <EmptyContainer>
                            <Empty description={t('pages.skills.noMatchingSkills')} />
                        </EmptyContainer>
                    )}
                </ListViewContainer>
            )}

            {renderDetailDrawer()}
        </ListContainer>
    );
};

// Helper components
const StarRatingSmall: React.FC<{ rating: number }> = ({ rating }) => (
    <Space size={2}>
        {[1, 2, 3, 4, 5].map((star) => (
            <span key={star} style={{ color: star <= rating ? '#faad14' : 'rgba(255,255,255,0.2)', fontSize: 12 }}>
                ★
            </span>
        ))}
    </Space>
);

const SectionTitle = styled.div`
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 16px 16px 8px;
`;

const GridSectionTitle = styled.div`
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    padding: 16px 0 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    grid-column: 1 / -1;

    &::after {
        content: '';
        flex: 1;
        height: 1px;
        background: var(--border-color);
        margin-left: 8px;
    }

    .anticon {
        font-size: 16px;
        color: var(--primary-color);
    }
`;

export default SkillList;

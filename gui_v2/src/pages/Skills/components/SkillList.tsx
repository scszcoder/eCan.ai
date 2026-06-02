import React, { useState, useMemo, useRef, useCallback } from 'react';
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
    TeamOutlined,
    CopyOutlined,
    DownloadOutlined,
    CloseOutlined,
    EditOutlined,
    PlayCircleOutlined,
    UserOutlined,
    ShopOutlined,
    ClockCircleOutlined,
} from '@ant-design/icons';

import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { Skill } from '@/types/domain/skill';
import { SkillFilters, SkillFilterOptions } from './SkillFilters';

const { Paragraph } = Typography;

const ListContainer = styled.div`
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
`;

const GridContainer = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
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

// ===================== 网格卡片样式 =====================
// 紧凑型卡片：左侧图标 + 右侧信息列
const GridCard = styled.div<{ $selected?: boolean }>`
    background: var(--bg-secondary);
    border-radius: 10px;
    padding: 12px;
    cursor: pointer;
    transition: all 0.15s ease;
    border: 1px solid ${props => props.$selected ? 'var(--primary-color)' : 'rgba(255, 255, 255, 0.06)'};
    display: flex;
    gap: 10px;
    align-items: stretch;
    position: relative;

    &:hover {
        border-color: rgba(24, 144, 255, 0.4);
        background: var(--bg-tertiary);
    }

    ${props => props.$selected && `
        border-color: var(--primary-color);
        box-shadow: 0 0 0 1px rgba(24, 144, 255, 0.25);
    `}
`;

// 左侧图标 - 固定宽度
const CardIconWrap = styled.div`
    position: relative;
    width: 36px;
    height: 36px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    align-self: flex-start;

    .anticon {
        font-size: 18px;
        color: white;
    }
`;

// 状态角标 - 叠加在图标右上角
const StatusBadge = styled.div<{ $color: string }>`
    position: absolute;
    top: -2px;
    right: -2px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: ${props => props.$color};
    border: 1.5px solid var(--bg-secondary);
`;

// 右侧信息列
const CardBody = styled.div`
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
`;

// 标题行：名称 + 价格
const TitleLine = styled.div`
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 6px;
    line-height: 1.3;
`;

const CardTitle = styled.span`
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
`;

const PriceBadge = styled.span<{ $isFree: boolean }>`
    font-size: 10px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 20px;
    text-transform: uppercase;
    flex-shrink: 0;

    ${props => props.$isFree ? `
        background: rgba(16, 185, 129, 0.85);
        color: white;
    ` : `
        background: rgba(245, 158, 11, 0.85);
        color: white;
    `}
`;

// 元信息行：版本 | 等级 | 执行环境
const MetaLine = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: var(--text-secondary);
    line-height: 1;
`;

const MetaItem = styled.span`
    display: inline-flex;
    align-items: center;
    gap: 3px;
    white-space: nowrap;

    .anticon {
        font-size: 11px;
        opacity: 0.7;
    }
`;

const MetaSep = styled.span`
    color: rgba(255, 255, 255, 0.15);
    font-size: 10px;
    line-height: 1;
`;

// 描述 - 2行截断
const CardDesc = styled.div`
    font-size: 11px;
    line-height: 1.4;
    color: var(--text-secondary);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
`;

// 标签行
const TagLine = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
`;

// 底部统计行
const StatLine = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding-top: 5px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    margin-top: 2px;
`;

const StatLeft = styled.div`
    display: flex;
    align-items: center;
    gap: 10px;
`;

const GridStatItem = styled.div`
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    color: var(--text-secondary);

    .anticon {
        font-size: 11px;
        opacity: 0.65;
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

const StatItem = styled.div`
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--text-secondary);

    .anticon {
        font-size: 12px;
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

const ListStatsBar = styled.div`
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

const getSkillSource = (skill: Skill): string => {
    return normalizeValue((skill as any)?.source).toLowerCase() || '';
};

const isCodeSkill = (skill: Skill): boolean => getSkillSource(skill) === 'code';

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
    onCopy?: (skill: Skill) => Promise<void>;
    onRun?: (skill: Skill) => void;
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
    onCopy,
    onRun,
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

    const isSkillSubscribed = useCallback((skill: Skill) => {
        const subscribedSet = new Set((subscribedSkillIds || []).map((id) => String(id)));
        const skillId = String((skill as any)?.id ?? '').trim();
        const skillAskid = String((skill as any)?.askid ?? '').trim();
        return !!(skillId && subscribedSet.has(skillId)) ||
            (skillAskid && skillAskid !== '0' && subscribedSet.has(skillAskid));
    }, [subscribedSkillIds]);

    const applyFiltersAndSort = useCallback((rows: Skill[]) => {
        let result = [...rows];

        if (filters.status) {
            result = result.filter(skill => skill.status === filters.status);
        }

        // Source filter: ui = my skills, code = code skills, subscribed = subscribed skills
        if (filters.source) {
            const me = normalizeValue(username).toLowerCase();
            result = result.filter(skill => {
                const source = getSkillSource(skill);
                const owner = normalizeValue((skill as any)?.owner).toLowerCase();

                if (filters.source === 'ui') {
                    // My Skills: owned by me OR code skills
                    if (source === 'code') return true;
                    return owner === me;
                }
                if (filters.source === 'code') {
                    return source === 'code';
                }
                if (filters.source === 'subscribed') {
                    return isSkillSubscribed(skill);
                }
                return true;
            });
        }

        if (filters.level) {
            result = result.filter(skill => skill.level === filters.level);
        }

        if (filters.priceType) {
            result = result.filter(skill => {
                const price = (skill as any)?.price;
                const isFree = typeof price === 'number' ? price <= 0 : !price;
                return filters.priceType === 'free' ? isFree : !isFree;
            });
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
    }, [filters, username, isSkillSubscribed]);

    const mySkills = useMemo(() => {
        const me = normalizeValue(username).toLowerCase();
        const ownedSkills = (skills || []).filter((skill) => {
            const source = getSkillSource(skill);
            const owner = normalizeValue((skill as any)?.owner).toLowerCase();
            // code skills always belong to "my skills"
            if (source === 'code') return true;
            // For all other skills, check ownership
            if (owner === me) return true;
            return false;
        });
        return ownedSkills;
    }, [skills, username]);

    const storeSkills = useMemo(() => {
        const me = normalizeValue(username).toLowerCase();
        return (publicSkills || []).filter((skill) => {
            const owner = normalizeValue((skill as any)?.owner).toLowerCase();
            // Don't show my own skills in the store
            if (owner === me) return false;
            // Only show public skills
            if (!(skill as any)?.public) return false;
            return true;
        });
    }, [publicSkills, username]);

    // Apply source filter and get filtered skill lists
    const filteredMySkills = useMemo(() => {
        const me = normalizeValue(username).toLowerCase();
        if (filters.source === 'subscribed') {
            // Subscribed tab: show subscribed skills from both sources
            return mySkills.filter(skill => isSkillSubscribed(skill));
        }
        if (filters.source === 'code') {
            return mySkills.filter(skill => getSkillSource(skill) === 'code');
        }
        if (filters.source === 'ui') {
            // UI source = my owned skills (not code skills)
            return mySkills.filter(skill => {
                const source = getSkillSource(skill);
                const owner = normalizeValue((skill as any)?.owner).toLowerCase();
                return source !== 'code' && owner === me;
            });
        }
        return mySkills;
    }, [mySkills, filters.source, username, isSkillSubscribed]);

    const filteredStoreSkills = useMemo(() => {
        if (filters.source === 'subscribed') {
            // Subscribed tab: show subscribed skills from store
            return storeSkills.filter(skill => isSkillSubscribed(skill));
        }
        if (filters.source === 'code') {
            return [];
        }
        if (filters.source === 'ui') {
            return [];
        }
        return storeSkills;
    }, [storeSkills, filters.source, isSkillSubscribed]);

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
        const me = normalizeValue(username).toLowerCase();
        const owner = normalizeValue((skill as any)?.owner).toLowerCase();
        const isOwnedByMe = owner === me;
        const isSubscribedSkill = getSkillSource(skill) === 'subscribed' && !isOwnedByMe;
        const statusColor = getStatusConfig(skill.status).color;

        return (
            <GridCard
                key={skillIdStr}
                $selected={isSelected}
                onClick={() => handleCardClick(skill)}
            >
                {/* 左侧图标 + 状态角标 */}
                <CardIconWrap>
                    <div style={{
                        width: 36,
                        height: 36,
                        borderRadius: 8,
                        background: `linear-gradient(135deg, ${skillBg[0]}, ${skillBg[1]})`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                    }}>
                        {skillIcon}
                    </div>
                    <StatusBadge $color={statusColor} title={t(`pages.skills.status.${skill.status || 'unknown'}`)} />
                </CardIconWrap>

                <CardBody>
                    {/* 行1: 名称 + 价格 */}
                    <TitleLine>
                        <CardTitle title={skill.name}>{skill.name}</CardTitle>
                        <PriceBadge $isFree={isFree}>
                            {isFree ? t('pages.skills.free') : t('pages.skills.paid')}
                        </PriceBadge>
                    </TitleLine>

                    {/* 行2: 元信息横排 */}
                    <MetaLine>
                        {skill.version && (
                            <>
                                <MetaItem title={`v${skill.version}`}>
                                    <CodeOutlined />{skill.version}
                                </MetaItem>
                                <MetaSep>·</MetaSep>
                            </>
                        )}
                        {skill.level && (
                            <>
                                <MetaItem>
                                    <RadarChartOutlined />{t(`pages.skills.levels.${skill.level}`, String(skill.level))}
                                </MetaItem>
                                <MetaSep>·</MetaSep>
                            </>
                        )}
                        <MetaItem>
                            {execMode === 'cloud' ? <CloudOutlined /> : <ThunderboltOutlined />}
                            {t(`pages.skills.execMode.${execMode}`, execMode)}
                        </MetaItem>
                    </MetaLine>

                    {/* 行3: 描述 2行 */}
                    {skill.description && (
                        <CardDesc title={skill.description}>{skill.description}</CardDesc>
                    )}

                    {/* 行4: 标签行 */}
                    <TagLine>
                        <Tag
                            color={getStatusConfig(skill.status).color}
                            style={{
                                margin: 0,
                                fontSize: 10,
                                padding: '1px 6px',
                                borderRadius: 20,
                                border: 'none',
                                fontWeight: 500,
                                lineHeight: 1.6,
                            }}
                        >
                            {t(`pages.skills.status.${skill.status || 'unknown'}`)}
                        </Tag>
                        {isCodeSkill(skill) && (
                            <Tag color="geekblue" style={{ margin: 0, fontSize: 10, padding: '1px 6px', borderRadius: 20, border: 'none', fontWeight: 500, lineHeight: 1.6 }}>
                                <CodeOutlined />
                            </Tag>
                        )}
                        {isSubscribedSkill && (
                            <Tag color="purple" style={{ margin: 0, fontSize: 10, padding: '1px 6px', borderRadius: 20, border: 'none', fontWeight: 500, lineHeight: 1.6 }}>
                                <CloudOutlined />
                            </Tag>
                        )}
                        {isSubscribed && (
                            <Tag color="green" style={{ margin: 0, fontSize: 10, padding: '1px 6px', borderRadius: 20, border: 'none', fontWeight: 500, lineHeight: 1.6 }}>
                                <CheckCircleOutlined />
                            </Tag>
                        )}
                        {getDisplayOwner(skill) && (
                            <MetaItem title={t('pages.skills.owner', 'Owner')}>
                                <UserOutlined />{getDisplayOwner(skill)}
                            </MetaItem>
                        )}
                    </TagLine>

                    {/* 行5: 底部统计 */}
                    <StatLine>
                        <StatLeft>
                            <StarRatingSmall rating={(skill as any).rating ?? 0} />
                            <GridStatItem>
                                <TeamOutlined />{(skill as any).subscribers ?? 0}
                            </GridStatItem>
                            {(skill as any).usageCount !== undefined && (
                                <GridStatItem>
                                    <SyncOutlined />{(skill as any).usageCount}
                                </GridStatItem>
                            )}
                            {(skill as any).updatedAt && (
                                <GridStatItem>
                                    <ClockCircleOutlined />{String((skill as any).updatedAt).slice(0, 10)}
                                </GridStatItem>
                            )}
                        </StatLeft>
                    </StatLine>
                </CardBody>
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
                <ListStatsBar>
                    <StarRatingSmall rating={(skill as any).rating ?? 0} />
                    <StatItem>
                        <TeamOutlined />
                        <span>{(skill as any).subscribers ?? 0}</span>
                    </StatItem>
                </ListStatsBar>
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
                            <Button icon={<PlayCircleOutlined />} block onClick={() => {
                                setDetailDrawer({ open: false, skill: null });
                                onSelectSkill(skill);
                                onRun?.(skill);
                            }}>
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
                                <Button
                                    icon={<CopyOutlined />}
                                    block
                                    onClick={async () => {
                                        try {
                                            await onCopy?.(skill);
                                        } catch (e) {
                                            console.error('Copy error:', e);
                                        }
                                    }}
                                >
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

    // Calculate filtered totals for empty state
    const filteredMySkillsTotal = applyFiltersAndSort(filteredMySkills);
    const filteredStoreSkillsTotal = applyFiltersAndSort(filteredStoreSkills);
    const allSkills = [...filteredMySkillsTotal, ...filteredStoreSkillsTotal];

    // Determine which sections to show based on filter
    const showMySkillsSection = filteredMySkills.length > 0;
    const showStoreSection = filteredStoreSkills.length > 0 && filters.source !== 'ui' && filters.source !== 'code';

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
                            {showMySkillsSection && (
                                <>
                                    <GridSectionTitle>
                                        <UserOutlined /> {t('pages.skills.sections.mySkills', 'My Skills')}
                                    </GridSectionTitle>
                                    {filteredMySkillsTotal.map(renderGridCard)}
                                </>
                            )}
                            {showStoreSection && (
                                <>
                                    <GridSectionTitle>
                                        <ShopOutlined /> {t('pages.skills.sections.skillStore', 'Skill Store')}
                                    </GridSectionTitle>
                                    {filteredStoreSkillsTotal.map(renderGridCard)}
                                </>
                            )}
                        </>
                    )}
                </GridContainer>
            ) : (
                <ListViewContainer ref={scrollContainerRef as any} onScroll={handleScroll}>
                    {showMySkillsSection && (
                        <>
                            <SectionTitle>{t('pages.skills.sections.mySkills', 'My Skills')}</SectionTitle>
                            {filteredMySkillsTotal.map(renderListItem)}
                        </>
                    )}
                    {showStoreSection && (
                        <>
                            <SectionTitle>{t('pages.skills.sections.skillStore', 'Skill Store')}</SectionTitle>
                            {filteredStoreSkillsTotal.map(renderListItem)}
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

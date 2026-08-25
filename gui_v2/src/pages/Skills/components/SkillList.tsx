import React, { useState, useMemo, useRef, useCallback } from 'react';
import { Tag, Typography, Space, Empty, Button, Spin, Drawer } from 'antd';
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
    display: flex;
    flex-direction: column;
`;

const GridContainer = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
    padding: 16px;
    align-content: start;

    &::-webkit-scrollbar {
        width: 6px;
    }
    &::-webkit-scrollbar-track {
        background: transparent;
    }
    &::-webkit-scrollbar-thumb {
        background: transparent;
        border-radius: 3px;
        transition: background 0.3s ease;
    }
    &:hover::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.15);
    }
`;

const ListViewContainer = styled.div`
    flex: 1;
    padding: 0 8px 8px;

    &::-webkit-scrollbar {
        width: 6px;
    }
    &::-webkit-scrollbar-track {
        background: transparent;
    }
    &::-webkit-scrollbar-thumb {
        background: transparent;
        border-radius: 3px;
        transition: background 0.3s ease;
    }
    &:hover::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.15);
    }
`;

// ===================== 网格卡片样式 =====================
// 新设计：垂直布局，层次分明
const GridCard = styled.div<{ $selected?: boolean }>`
    background: var(--bg-secondary);
    border-radius: 12px;
    cursor: pointer;
    transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    border: 1px solid rgba(255, 255, 255, 0.06);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
    min-height: 280px;

    &:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    }

    ${props => props.$selected ? `
        border-color: rgba(24, 144, 255, 0.4);
        box-shadow: 0 0 0 1px rgba(24, 144, 255, 0.2), 0 4px 16px rgba(24, 144, 255, 0.1);
    ` : ''}
`;

// 卡片头部：渐变图标区
const CardHeader = styled.div<{ $bg: string[] }>`
    background: linear-gradient(135deg, ${props => props.$bg[0]}, ${props => props.$bg[1]});
    padding: 14px 16px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    position: relative;
    min-height: 60px;
`;

const CardIconArea = styled.div`
    display: flex;
    align-items: center;
    gap: 10px;

    .anticon {
        font-size: 24px;
        color: rgba(255, 255, 255, 0.9);
    }
`;

const StatusBadge = styled.div<{ $color: string }>`
    background: ${props => props.$color};
    color: white;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 20px;
    display: flex;
    align-items: center;
    gap: 4px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);

    .anticon {
        font-size: 11px;
    }
`;

// 卡片主体内容
const CardContent = styled.div`
    flex: 1;
    padding: 14px 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 110px;
`;

const CardTitle = styled.div`
    font-size: 16px;
    font-weight: 600;
    color: rgba(241, 245, 249, 0.92);
    line-height: 1.35;
    display: flex;
    align-items: center;
    gap: 8px;
    justify-content: space-between;
`;

const PriceTag = styled.span<{ $isFree: boolean }>`
    font-size: 11px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 20px;
    text-transform: uppercase;
    flex-shrink: 0;

    ${props => props.$isFree ? `
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
    ` : `
        background: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
    `}
`;

const CardDesc = styled.div`
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-secondary);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
`;

const CardMeta = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
`;

const MetaTag = styled.span`
    font-size: 11px;
    color: var(--text-tertiary, rgba(255, 255, 255, 0.55));
    background: rgba(255,255,255,0.04);
    padding: 3px 8px;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    gap: 4px;

    .anticon {
        font-size: 11px;
        opacity: 0.6;
    }
`;

const CardStats = styled.div`
    display: flex;
    gap: 12px;
    padding: 8px 0 4px;
`;

// 卡片统计项
const CardStatItem = styled.div`
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--text-secondary);

    .anticon {
        font-size: 12px;
        opacity: 0.5;
    }

    .stat-value {
        color: var(--text-secondary);
        font-weight: 500;
    }
`;

// 卡片操作按钮区
const CardActions = styled.div`
    padding: 10px 16px 12px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: auto;
`;

const ActionButton = styled.button<{ $variant?: 'primary' | 'secondary' | 'danger' | 'success' }>`
    flex: 1;
    min-width: 80px;
    max-width: 140px;
    padding: 8px 12px;
    border-radius: 8px;
    border: none;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: all 0.2s ease;

    ${props => {
        switch (props.$variant) {
            case 'primary':
                return `
                    background: linear-gradient(135deg, #1890ff, #40a9ff);
                    color: white;
                    &:hover {
                        background: linear-gradient(135deg, #40a9ff, #69c0ff);
                        transform: translateY(-1px);
                    }
                `;
            case 'danger':
                return `
                    background: rgba(245, 34, 45, 0.15);
                    color: #ff4d4f;
                    border: 1px solid rgba(245, 34, 45, 0.3);
                    &:hover {
                        background: rgba(245, 34, 45, 0.25);
                    }
                `;
            case 'success':
                return `
                    background: rgba(82, 196, 26, 0.15);
                    color: #52c41a;
                    border: 1px solid rgba(82, 196, 26, 0.3);
                    &:hover {
                        background: rgba(82, 196, 26, 0.25);
                    }
                `;
            default:
                return `
                    background: rgba(255,255,255,0.08);
                    color: var(--text-primary);
                    border: 1px solid rgba(255,255,255,0.1);
                    &:hover {
                        background: rgba(255,255,255,0.12);
                    }
                `;
        }
    }}

    .anticon {
        font-size: 14px;
    }

    &:active {
        transform: scale(0.98);
    }
`;

// 标签行（保留）
const TagLine = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 3px;
`;

// 底部统计行（保留）
const StatLine = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    padding-top: 6px;
    border-top: 1px solid rgba(255, 255, 255, 0.04);
`;

const GridStatItem = styled.div`
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

// 订阅管理视图卡片
const SubscriptionCard = styled.div`
    padding: 14px 16px;
    cursor: pointer;
    transition: all 0.15s ease;
    background: var(--bg-secondary);
    border-radius: 12px;
    margin-bottom: 6px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    display: flex;
    align-items: center;
    gap: 14px;

    &:hover {
        background: var(--bg-tertiary);
        border-color: rgba(24, 144, 255, 0.2);
    }
`;

const SubCardIcon = styled.div<{ $bg: string[] }>`
    width: 42px;
    height: 42px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    background: linear-gradient(145deg, ${props => props.$bg[0]}, ${props => props.$bg[1]});
    box-shadow: 0 3px 10px rgba(0, 0, 0, 0.2);

    .anticon {
        color: white;
        font-size: 18px;
    }
`;

const SubCardInfo = styled.div`
    flex: 1;
    min-width: 0;
`;

const SubCardTitle = styled.div`
    font-size: 13.5px;
    font-weight: 500;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
`;

const SubCardMeta = styled.div`
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 3px;
    display: flex;
    gap: 12px;

    > span {
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }

    .anticon {
        font-size: 12px;
        opacity: 0.7;
    }
`;

const SubCardProficiency = styled.div`
    min-width: 120px;
    display: flex;
    flex-direction: column;
    gap: 4px;
`;

const SubCardProficiencyLabel = styled.div`
    font-size: 11px;
    color: var(--text-secondary);
    font-weight: 500;
`;

const SubCardProficiencyBar = styled.div`
    height: 4px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    overflow: hidden;
`;

const SubCardProficiencyFill = styled.div<{ $percent: number }>`
    height: 100%;
    width: ${props => props.$percent}%;
    background: linear-gradient(90deg, #1890ff, #52c41a);
    border-radius: 4px;
    transition: width 0.3s ease;
`;

const SubCardRating = styled.div`
    min-width: 80px;
    display: flex;
    align-items: center;
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
    font-size: 13.5px;
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

// 列表统计项
const ListStatItem = styled.div`
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

const ListPriceTag = styled.span<{ $isFree: boolean }>`
    font-size: 11px;
    font-weight: 600;
    padding: 2px 10px;
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
    viewMode: 'list' | 'grid' | 'subscriptions';
    username: string;
    subscribedSkillIds?: string[];
    onEditInGrid?: () => void;
    onSubscribe?: (skillId: string) => Promise<void>;
    onUnsubscribe?: (skillId: string) => Promise<void>;
    onCopy?: (skill: Skill) => Promise<void>;
    onRun?: (skill: Skill) => void;
    filters?: SkillFilterOptions;
    renderFilters?: boolean;
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
    filters: externalFilters,
    renderFilters = false,
}) => {
    const { t } = useTranslation();
    const [internalFilters, setInternalFilters] = useState<SkillFilterOptions>({ sortBy: 'name' });
    const filters = externalFilters || internalFilters;
    const setFilters = externalFilters ? () => {} : setInternalFilters;
    const [detailDrawer, setDetailDrawer] = useState<{ open: boolean; skill: Skill | null }>({ open: false, skill: null });

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

        if (filters.category) {
            const categoryLower = filters.category.toLowerCase();
            result = result.filter(skill => {
                const skillCategory = (skill.category || inferCategory(skill) || '').toLowerCase();
                return skillCategory === categoryLower;
            });
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
                    const levelMap: Record<string, number> = { entry: 1, intermediate: 2, advanced: 3 };
                    const levelA = typeof a.level === 'string' ? (levelMap[a.level.toLowerCase()] ?? 0) : (Number(a.level) || 0);
                    const levelB = typeof b.level === 'string' ? (levelMap[b.level.toLowerCase()] ?? 0) : (Number(b.level) || 0);
                    return levelB - levelA;
                }
                case 'rating': {
                    const ratingA = Number((a as any).rating ?? 5);
                    const ratingB = Number((b as any).rating ?? 5);
                    return ratingB - ratingA;
                }
                case 'newest': {
                    const dateA = (a as any).updatedAt || (a as any).createdAt || '';
                    const dateB = (b as any).updatedAt || (b as any).createdAt || '';
                    return dateB.localeCompare(dateA);
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
        if (filters.source === 'marketplace') {
            return mySkills.filter(skill => (skill as any)?.public === true);
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
        if (filters.source === 'marketplace') {
            return storeSkills;
        }
        return storeSkills;
    }, [storeSkills, filters.source, isSkillSubscribed]);

    const handleCardClick = (skill: Skill) => {
        setDetailDrawer({ open: true, skill });
        onSelectSkill(skill);
    };

    const handleSubscribe = async (e: React.MouseEvent, skillId: string) => {
        e.stopPropagation();
        try {
            await onSubscribe?.(skillId);
        } catch (err) {
            console.error('Subscribe error:', err);
        }
    };

    const handleUnsubscribe = async (e: React.MouseEvent, skillId: string) => {
        e.stopPropagation();
        try {
            await onUnsubscribe?.(skillId);
        } catch (err) {
            console.error('Unsubscribe error:', err);
        }
    };

    const handleCopy = async (e: React.MouseEvent, skill: Skill) => {
        e.stopPropagation();
        try {
            await onCopy?.(skill);
        } catch (err) {
            console.error('Copy error:', err);
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
        const category = skill.category || inferCategory(skill);

        const statusColorMap: Record<string, string> = {
            active: '#52c41a',
            learning: '#1890ff',
            planned: '#8c8c8c',
        };
        const statusColor = statusColorMap[skill.status || ''] || '#8c8c8c';
        const statusBgMap: Record<string, string> = {
            active: 'rgba(82, 196, 26, 0.2)',
            learning: 'rgba(24, 144, 255, 0.2)',
            planned: 'rgba(140, 140, 140, 0.2)',
        };
        const statusBg = statusBgMap[skill.status || ''] || 'rgba(140, 140, 140, 0.2)';

        return (
            <GridCard
                key={skillIdStr}
                $selected={isSelected}
                onClick={() => handleCardClick(skill)}
            >
                {/* 卡片头部：渐变图标区 */}
                <CardHeader $bg={skillBg}>
                    <CardIconArea>
                        {skillIcon}
                    </CardIconArea>
                    <StatusBadge $color={statusBg}>
                        <span style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: statusColor,
                            display: 'inline-block'
                        }} />
                        {t(`pages.skills.status.${skill.status || 'unknown'}`)}
                    </StatusBadge>
                </CardHeader>

                {/* 卡片主体 */}
                <CardContent>
                    {/* 标题 + 价格 */}
                    <CardTitle>
                        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {skill.name}
                        </span>
                        <PriceTag $isFree={isFree}>
                            {isFree ? t('pages.skills.free') : t('pages.skills.paid')}
                        </PriceTag>
                    </CardTitle>

                    {/* 描述 */}
                    {skill.description && (
                        <CardDesc>{skill.description}</CardDesc>
                    )}

                    {/* 元信息标签 */}
                    <CardMeta>
                        <MetaTag>
                            <RadarChartOutlined />
                            {t(`pages.skills.levels.${skill.level || 'entry'}`, String(skill.level || 'entry'))}
                        </MetaTag>
                        <MetaTag>
                            {execMode === 'cloud' ? <CloudOutlined /> : <ThunderboltOutlined />}
                            {t(`pages.skills.execMode.${execMode}`, execMode)}
                        </MetaTag>
                        {isCodeSkill(skill) && (
                            <MetaTag>
                                <CodeOutlined />
                                {t('pages.skills.code', 'Code')}
                            </MetaTag>
                        )}
                        {isSubscribed && (
                            <MetaTag style={{ background: 'rgba(82, 196, 26, 0.15)', color: '#52c41a' }}>
                                <CheckCircleOutlined />
                                {t('pages.skills.subscribed', 'Subscribed')}
                            </MetaTag>
                        )}
                        {/* Publish status on the summary card: public / rentable */}
                        {(skill as any).public && (
                            <MetaTag style={{ background: 'rgba(24, 144, 255, 0.15)', color: '#1890ff' }}>
                                <CloudOutlined />
                                {t('pages.skills.public', 'Public')}
                            </MetaTag>
                        )}
                        {(skill as any).rentable && (
                            <MetaTag style={{ background: 'rgba(250, 173, 20, 0.15)', color: '#faad14' }}>
                                <ThunderboltOutlined />
                                {t('pages.skills.rentable', 'Rentable')}
                            </MetaTag>
                        )}
                    </CardMeta>

                    {/* 统计信息 */}
                    <CardStats>
                        <CardStatItem>
                            <StarOutlined style={{ color: '#faad14' }} />
                            <span className="stat-value">{Number((skill as any).rating ?? 5).toFixed(1)}</span>
                        </CardStatItem>
                        <CardStatItem>
                            <TeamOutlined />
                            <span className="stat-value">{(skill as any).subscribers ?? 0}</span>
                        </CardStatItem>
                        <CardStatItem>
                            <SyncOutlined />
                            <span className="stat-value">{(skill as any).usageCount ?? 0}</span>
                        </CardStatItem>
                    </CardStats>
                </CardContent>

                    {/* 操作按钮 */}
                <CardActions>
                    {isOwnedByMe ? (
                        <>
                            <ActionButton
                                $variant="primary"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onSelectSkill(skill);
                                    if (onEditInGrid) onEditInGrid();
                                }}
                            >
                                <EditOutlined />
                                {t('pages.skills.edit', 'Edit')}
                            </ActionButton>
                        </>
                    ) : isSubscribed ? (
                        <>
                            <ActionButton
                                $variant="secondary"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleCardClick(skill);
                                }}
                            >
                                <EyeOutlined />
                                {t('pages.skills.actions.view', 'View')}
                            </ActionButton>
                            <ActionButton
                                $variant="danger"
                                onClick={(e) => handleUnsubscribe(e, skillIdStr)}
                            >
                                <CloseOutlined />
                                {t('pages.skills.unsubscribe', 'Unsubscribe')}
                            </ActionButton>
                        </>
                    ) : (
                        <>
                            <ActionButton
                                $variant="secondary"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleCardClick(skill);
                                }}
                            >
                                <EyeOutlined />
                                {t('pages.skills.actions.view', 'View')}
                            </ActionButton>
                            {isFree ? (
                                <ActionButton
                                    $variant="success"
                                    onClick={(e) => handleCopy(e, skill)}
                                >
                                    <CopyOutlined />
                                    {t('common.copy', 'Copy')}
                                </ActionButton>
                            ) : null}
                            <ActionButton
                                $variant="primary"
                                onClick={(e) => handleSubscribe(e, skillIdStr)}
                            >
                                <DownloadOutlined />
                                {t('pages.skills.subscribe', 'Subscribe')}
                            </ActionButton>
                        </>
                    )}
                </CardActions>
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
                        <ListPriceTag $isFree={isFree}>
                            {isFree ? t('pages.skills.free', 'Free') : t('pages.skills.paid', 'Paid')}
                        </ListPriceTag>
                        {t(`pages.skills.status.${skill.status || 'unknown'}`)} · {t(`pages.skills.categories.${category}`, category)}
                        {execMode === 'cloud' && ` · ${t('pages.skills.cloud', 'Cloud')}`}
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
                    <StarRatingSmall rating={(skill as any).rating ?? 5} />
                    <ListStatItem>
                        <TeamOutlined />
                        <span>{(skill as any).subscribers ?? 0}</span>
                    </ListStatItem>
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
                        <DetailSectionTitle>{t('common.description', 'Description')}</DetailSectionTitle>
                        <DetailDescription ellipsis={{ rows: 3, expandable: true }}>
                            {skill.description}
                        </DetailDescription>
                    </DetailSection>
                )}

                {(() => {
                    const owner = getDisplayOwner(skill);
                    return owner ? (
                        <DetailSection>
                            <DetailSectionTitle>{t('common.owner', 'Owner')}</DetailSectionTitle>
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
                        <DetailStatValue>{(skill as any).rating ?? 5}</DetailStatValue>
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
                                        <UserOutlined /> {t('pages.skills.filter.mySkills', 'My Skills')}
                                    </GridSectionTitle>
                                    {filteredMySkillsTotal.map(renderGridCard)}
                                </>
                            )}
                            {showStoreSection && (
                                <>
                                    <GridSectionTitle>
                                        <ShopOutlined /> {t('pages.skills.heroTitle', 'Skill Store')}
                                    </GridSectionTitle>
                                    {filteredStoreSkillsTotal.map(renderGridCard)}
                                </>
                            )}
                        </>
                    )}
                </GridContainer>
            ) : viewMode === 'subscriptions' ? (
                <ListViewContainer ref={scrollContainerRef as any} onScroll={handleScroll}>
                    <SectionTitle>{t('pages.skills.subscriptions.title', 'My Subscriptions')}</SectionTitle>
                    {(() => {
                        const subscribedSkills = skills.filter(s => isSkillSubscribed(s));
                        if (subscribedSkills.length === 0) {
                            return (
                                <EmptyContainer style={{ padding: '40px 0' }}>
                                    <Empty description={t('pages.skills.subscriptions.empty', 'No subscriptions yet. Browse the Skill Store to subscribe.')} />
                                </EmptyContainer>
                            );
                        }
                        return subscribedSkills.map(skill => {
                            const levelMap: Record<string, number> = { entry: 33, intermediate: 66, advanced: 100 };
                            const rawLevel = (skill as any)?.level;
                            const levelPercent = typeof rawLevel === 'string' ? (levelMap[rawLevel.toLowerCase()] ?? 0) : (Number(rawLevel) || 0);
                            const usageCount = (skill as any)?.usageCount ?? 0;
                            const rating = Number((skill as any).rating ?? 5);
                            return (
                                <SubscriptionCard
                                    key={String(skill.id)}
                                    onClick={() => handleCardClick(skill)}
                                >
                                    <SubCardIcon $bg={getSkillIcon(skill).bg}>
                                        {getSkillIcon(skill).icon}
                                    </SubCardIcon>
                                    <SubCardInfo>
                                        <SubCardTitle>{skill.name}</SubCardTitle>
                                        <SubCardMeta>
                                            <span><RadarChartOutlined /> {t(`pages.skills.levels.${skill.level || 'entry'}`, String(skill.level || 'entry'))}</span>
                                            <span><SyncOutlined spin /> {usageCount} {t('pages.skills.uses', 'uses')}</span>
                                        </SubCardMeta>
                                    </SubCardInfo>
                                    <SubCardProficiency>
                                        <SubCardProficiencyLabel>
                                            {levelPercent === 100 ? t('pages.skills.levelExpert', 'Expert')
                                                : levelPercent >= 66 ? t('pages.skills.levelAdvanced', 'Advanced')
                                                : levelPercent >= 33 ? t('pages.skills.levelIntermediate', 'Intermediate')
                                                : t('pages.skills.levelBeginner', 'Beginner')}
                                        </SubCardProficiencyLabel>
                                        <SubCardProficiencyBar>
                                            <SubCardProficiencyFill $percent={levelPercent} />
                                        </SubCardProficiencyBar>
                                    </SubCardProficiency>
                                    <SubCardRating>
                                        <StarRatingSmall rating={rating} />
                                    </SubCardRating>
                                </SubscriptionCard>
                            );
                        });
                    })()}
                </ListViewContainer>
            ) : (
                <ListViewContainer ref={scrollContainerRef as any} onScroll={handleScroll}>
                    {renderFilters && (
                        <SkillFilters
                            filters={filters}
                            onChange={(newFilters) => setFilters(newFilters)}
                        />
                    )}
                    {showMySkillsSection && (
                        <>
                            <SectionTitle>{t('pages.skills.filter.mySkills', 'My Skills')}</SectionTitle>
                            {filteredMySkillsTotal.map(renderListItem)}
                        </>
                    )}
                    {showStoreSection && (
                        <>
                            <SectionTitle>{t('pages.skills.heroTitle', 'Skill Store')}</SectionTitle>
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
    <Space size={3}>
        {[1, 2, 3, 4, 5].map((star) => (
            <span key={star} style={{ color: star <= rating ? '#faad14' : 'rgba(255,255,255,0.2)', fontSize: 13 }}>
                ★
            </span>
        ))}
    </Space>
);

const SectionTitle = styled.div`
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 18px 16px 10px;
`;

const GridSectionTitle = styled.div`
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    padding: 18px 0 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    grid-column: 1 / -1;

    &::after {
        content: '';
        flex: 1;
        height: 1px;
        background: linear-gradient(90deg, var(--border-color), transparent);
        margin-left: 10px;
    }

    .anticon {
        font-size: 16px;
        color: var(--primary-color);
    }
`;

export default SkillList;

/**
 * SkillAnalyticsDashboard: Overview statistics and insights for the Skills page.
 * Shows: total skills, status/level/category breakdown, top skills, recent activity.
 * Integrated in Skills.tsx as a summary bar above the list.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Typography, Spin, Space, Tag } from 'antd';
import {
    BarChartOutlined,
    ClockCircleOutlined,
    CheckCircleOutlined,
    SyncOutlined,
    TrophyOutlined,
    ThunderboltOutlined,
    ShopOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { logger } from '@/utils/logger';

const { Text, Title } = Typography;

interface SkillAnalyticsProps {
    username: string;
    skillCount?: number;
}

interface AnalyticsData {
    total_skills: number;
    total_public_skills: number;
    by_status: Record<string, number>;
    by_level: Record<string, number>;
    by_category: Record<string, number>;
    top_by_usage: { id: string; name: string; usageCount: number; owner: string }[];
    top_by_rating: { id: string; name: string; rating: number; owner: string }[];
    recent_skills: { id: string; name: string; updatedAt: string; owner: string }[];
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: React.ReactNode }> = {
    active: { color: '#52c41a', bg: 'rgba(82, 196, 26, 0.12)', icon: <CheckCircleOutlined /> },
    learning: { color: '#1890ff', bg: 'rgba(24, 144, 255, 0.12)', icon: <SyncOutlined /> },
    planned: { color: '#8c8c8c', bg: 'rgba(140, 140, 140, 0.12)', icon: <ClockCircleOutlined /> },
};

const LEVEL_CONFIG: Record<string, { color: string; bg: string }> = {
    advanced: { color: '#52c41a', bg: 'rgba(82, 196, 26, 0.12)' },
    intermediate: { color: '#1890ff', bg: 'rgba(24, 144, 255, 0.12)' },
    entry: { color: '#8c8c8c', bg: 'rgba(140, 140, 140, 0.12)' },
};

const CATEGORY_CONFIG: Record<string, { color: string; bg: string }> = {
    agent: { color: '#722ed1', bg: 'rgba(114, 46, 209, 0.12)' },
    data: { color: '#13c2c2', bg: 'rgba(19, 194, 194, 0.12)' },
    web: { color: '#fa8c16', bg: 'rgba(250, 140, 22, 0.12)' },
    code: { color: '#1890ff', bg: 'rgba(24, 144, 255, 0.12)' },
    file: { color: '#eb2f96', bg: 'rgba(235, 47, 150, 0.12)' },
    social: { color: '#52c41a', bg: 'rgba(82, 196, 26, 0.12)' },
    analysis: { color: '#faad14', bg: 'rgba(250, 173, 20, 0.12)' },
    automation: { color: '#f5222d', bg: 'rgba(245, 34, 45, 0.12)' },
    communication: { color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.12)' },
    general: { color: '#8c8c8c', bg: 'rgba(140, 140, 140, 0.12)' },
};

const SectionCard: React.FC<{
    title: React.ReactNode;
    children: React.ReactNode;
    accent?: string;
    compact?: boolean;
}> = ({ title, children, accent, compact }) => (
    <div style={{
        background: 'var(--bg-secondary)',
        borderRadius: 12,
        padding: compact ? '12px 16px' : '16px 20px',
        border: '1px solid rgba(255,255,255,0.08)',
        display: 'flex',
        flexDirection: 'column',
        gap: compact ? 8 : 12,
        position: 'relative',
        overflow: 'hidden',
    }}>
        {accent && (
            <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: 3,
                background: accent,
                borderRadius: '12px 12px 0 0',
            }} />
        )}
        <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 0,
        }}>
            {title}
        </div>
        {children}
    </div>
);

const MiniBar: React.FC<{
    value: number;
    max: number;
    color: string;
    label: string;
    count: number;
}> = ({ value, max, color, label, count }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', width: 70, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {label}
        </Text>
        <div style={{ flex: 1, height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
                width: `${max > 0 ? (value / max * 100) : 0}%`,
                height: '100%',
                background: `linear-gradient(90deg, ${color}cc, ${color})`,
                borderRadius: 3,
                transition: 'width 0.5s cubic-bezier(0.4, 0, 0.2, 1)',
                minWidth: value > 0 ? 3 : 0,
            }} />
        </div>
        <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', width: 20, textAlign: 'right', flexShrink: 0 }}>
            {count}
        </Text>
    </div>
);

export const SkillAnalyticsDashboard: React.FC<SkillAnalyticsProps> = ({ username }) => {
    const { t } = useTranslation();
    const [data, setData] = useState<AnalyticsData | null>(null);
    const [loading, setLoading] = useState(false);

    const fetchAnalytics = useCallback(async () => {
        setLoading(true);
        try {
            const api = get_ipc_api();
            const resp = await api?.getSkillAnalytics(username) as any;
            if (resp?.success && resp?.data?.data) {
                setData(resp.data.data);
            }
        } catch (e) {
            logger.error('[SkillAnalytics] fetch error:', e);
        } finally {
            setLoading(false);
        }
    }, [username]);

    useEffect(() => { fetchAnalytics(); }, [fetchAnalytics]);

    if (loading) {
        return (
            <div style={{ textAlign: 'center', padding: 20 }}>
                <Spin size="small" />
            </div>
        );
    }

    if (!data) return null;

    const maxStatus = Math.max(...Object.values(data.by_status || {}), 1);
    const maxLevel = Math.max(...Object.values(data.by_level || {}), 1);

    const totalActive = data.by_status?.active || 0;

    return (
        <div style={{
            padding: '12px 16px',
            background: 'var(--bg-secondary)',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
        }}>
            {/* Compact Stats Row */}
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 32,
                marginBottom: 10,
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <BarChartOutlined style={{ color: 'rgba(255,255,255,0.4)', fontSize: 16 }} />
                    <Text style={{ fontSize: 14, color: 'rgba(255,255,255,0.5)' }}>
                        {t('pages.skills.analytics.mySkills', 'My Skills')}
                    </Text>
                    <Text style={{ fontSize: 18, color: '#fff', fontWeight: 600 }}>{data.total_skills}</Text>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
                    <Text style={{ fontSize: 14, color: 'rgba(255,255,255,0.5)' }}>
                        {t('pages.skills.analytics.active', 'Active')}
                    </Text>
                    <Text style={{ fontSize: 18, color: '#52c41a', fontWeight: 600 }}>{totalActive}</Text>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ShopOutlined style={{ color: '#faad14', fontSize: 16 }} />
                    <Text style={{ fontSize: 14, color: 'rgba(255,255,255,0.5)' }}>
                        {t('pages.skills.analytics.public', 'Public')}
                    </Text>
                    <Text style={{ fontSize: 18, color: '#faad14', fontWeight: 600 }}>{data.total_public_skills}</Text>
                </div>
            </div>

            {/* Compact Progress Bars */}
            <div style={{ display: 'flex', gap: 32 }}>
                {/* Status breakdown */}
                <div style={{ flex: 1 }}>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginBottom: 8, display: 'block' }}>
                        {t('pages.skills.analytics.byStatus', 'By Status')}
                    </Text>
                    <div style={{ display: 'flex', gap: 16 }}>
                        {Object.entries(data.by_status || {}).map(([status, count]) => {
                            const cfg = STATUS_CONFIG[status] || { color: '#8c8c8c', bg: 'rgba(140,140,140,0.12)', icon: null };
                            return (
                                <div key={status} style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                                    <Text style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', width: 60, flexShrink: 0 }}>
                                        {t(`pages.skills.status.${status}`, status)}
                                    </Text>
                                    <div style={{ flex: 1, height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3 }}>
                                        <div style={{
                                            width: `${maxStatus > 0 ? (count / maxStatus * 100) : 0}%`,
                                            height: '100%',
                                            background: cfg.color,
                                            borderRadius: 3,
                                        }} />
                                    </div>
                                    <Text style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', width: 20 }}>{count}</Text>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Level breakdown */}
                <div style={{ flex: 1 }}>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginBottom: 8, display: 'block' }}>
                        {t('pages.skills.analytics.byLevel', 'By Level')}
                    </Text>
                    <div style={{ display: 'flex', gap: 16 }}>
                        {Object.entries(data.by_level || {}).map(([level, count]) => {
                            const cfg = LEVEL_CONFIG[level] || { color: '#8c8c8c', bg: 'rgba(140,140,140,0.12)' };
                            return (
                                <div key={level} style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                                    <Text style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', width: 60, flexShrink: 0 }}>
                                        {t(`pages.skills.levels.${level}`, level)}
                                    </Text>
                                    <div style={{ flex: 1, height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3 }}>
                                        <div style={{
                                            width: `${maxLevel > 0 ? (count / maxLevel * 100) : 0}%`,
                                            height: '100%',
                                            background: cfg.color,
                                            borderRadius: 3,
                                        }} />
                                    </div>
                                    <Text style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', width: 20 }}>{count}</Text>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Top skill */}
                {data.top_by_usage?.length > 0 && (
                    <div style={{ flex: 1 }}>
                        <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginBottom: 8, display: 'block' }}>
                            <TrophyOutlined style={{ marginRight: 4 }} />
                            {t('pages.skills.analytics.topSkill', 'Top Skill')}
                        </Text>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Text style={{ fontSize: 13, color: 'rgba(255,255,255,0.8)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {data.top_by_usage[0].name}
                            </Text>
                            <Tag style={{
                                background: 'rgba(250,173,20,0.1)',
                                border: 'none',
                                color: '#faad14',
                                borderRadius: 4,
                                fontSize: 12,
                                padding: '2px 8px',
                                margin: 0,
                            }}>
                                {data.top_by_usage[0].usageCount}×
                            </Tag>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

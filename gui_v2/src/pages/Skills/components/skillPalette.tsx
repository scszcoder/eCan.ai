import React from 'react';
import {
    CodeOutlined,
    ApiOutlined,
    BranchesOutlined,
    CloudSyncOutlined,
    BulbOutlined,
    RocketOutlined,
    RiseOutlined,
    MessageOutlined,
    EyeOutlined,
    FileTextOutlined,
    ExperimentOutlined,
} from '@ant-design/icons';
import type { Skill } from '@/types/domain/skill';

export const CATEGORY_PALETTE: Record<string, { icon: React.ReactNode; bg: [string, string] }> = {
    automation: { icon: <RocketOutlined />, bg: ['#f59e0b', '#d97706'] },
    analysis: { icon: <RiseOutlined />, bg: ['#8b5cf6', '#7c3aed'] },
    communication: { icon: <MessageOutlined />, bg: ['#06b6d4', '#0891b2'] },
    coding: { icon: <CodeOutlined />, bg: ['#3b82f6', '#2563eb'] },
    development: { icon: <CodeOutlined />, bg: ['#3b82f6', '#2563eb'] },
    vision: { icon: <EyeOutlined />, bg: ['#ec4899', '#db2777'] },
    image: { icon: <EyeOutlined />, bg: ['#ec4899', '#db2777'] },
    api: { icon: <ApiOutlined />, bg: ['#14b8a6', '#0d9488'] },
    integration: { icon: <ApiOutlined />, bg: ['#14b8a6', '#0d9488'] },
    logic: { icon: <BranchesOutlined />, bg: ['#a855f7', '#9333ea'] },
    reasoning: { icon: <BranchesOutlined />, bg: ['#a855f7', '#9333ea'] },
    cloud: { icon: <CloudSyncOutlined />, bg: ['#64748b', '#475569'] },
    network: { icon: <CloudSyncOutlined />, bg: ['#64748b', '#475569'] },
    search: { icon: <BulbOutlined />, bg: ['#f97316', '#ea580c'] },
    file: { icon: <FileTextOutlined />, bg: ['#22c55e', '#16a34a'] },
    browser: { icon: <RocketOutlined />, bg: ['#f43f5e', '#e11d48'] },
    general: { icon: <ExperimentOutlined />, bg: ['#64748b', '#475569'] },
    unknown: { icon: <ExperimentOutlined />, bg: ['#64748b', '#475569'] },
};

export function inferCategory(s: Skill): string {
    const tags = (Array.isArray((s as any)?.tags) ? (s as any).tags : []) as string[];
    const text = `${s.name || ''} ${s.description || ''} ${tags.join(' ')}`.toLowerCase();
    if (/automat|workflow|process|batch|schedule/i.test(text)) return 'automation';
    if (/analy[sz]|data|chart|report|metric|statistic/i.test(text)) return 'analysis';
    if (/chat|message|email|communication|talk|conversation/i.test(text)) return 'communication';
    if (/code|program|develop|script|function|debug/i.test(text)) return 'coding';
    if (/vision|image|photo|visual|ocr|detect|recognize/i.test(text)) return 'vision';
    if (/api|rest|http|integration|webhook|endpoint/i.test(text)) return 'api';
    if (/logic|reason|think|decision|rule|condition/i.test(text)) return 'logic';
    if (/cloud|aws|azure|gcp|server|deploy|network/i.test(text)) return 'cloud';
    if (/search|find|lookup|query|retrieve/i.test(text)) return 'search';
    if (/file|document|upload|download|export|import/i.test(text)) return 'file';
    if (/browser|web|page|click|scroll|navigate/i.test(text)) return 'browser';
    return 'general';
}

export function getSkillPalette(s: Skill): { icon: React.ReactNode; bg: [string, string] } {
    if ((s as any)?.source === 'code') return CATEGORY_PALETTE.coding;
    const cat = (s as any)?.category || inferCategory(s);
    return CATEGORY_PALETTE[cat] || CATEGORY_PALETTE.general;
}

export function formatNumber(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n || 0);
}

export function isPaidSkill(s: Skill): boolean {
    const price = (s as any)?.price;
    if (typeof price === 'number') return price > 0;
    if (typeof price === 'string') {
        const v = Number(price);
        return Number.isFinite(v) && v > 0;
    }
    return false;
}

export function safeTags(tags: unknown): string[] {
    if (Array.isArray(tags)) return tags.map(String);
    if (typeof tags === 'string') {
        try {
            const parsed = JSON.parse(tags);
            if (Array.isArray(parsed)) return parsed.map(String);
        } catch { /* ignore */ }
        return tags ? [tags] : [];
    }
    return [];
}

export function getInitials(text?: string | null): string {
    if (!text) return '?';
    const cleaned = String(text).trim();
    if (!cleaned) return '?';
    const at = cleaned.indexOf('@');
    const local = at > 0 ? cleaned.slice(0, at) : cleaned;
    const parts = local.split(/[\s._-]+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return cleaned.slice(0, 2).toUpperCase();
}

export function colorFromString(s?: string | null): string {
    if (!s) return '#1890ff';
    let hash = 0;
    for (let i = 0; i < s.length; i++) hash = s.charCodeAt(i) + ((hash << 5) - hash);
    const palette = ['#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2', '#eb2f96', '#fa541c'];
    return palette[Math.abs(hash) % palette.length];
}

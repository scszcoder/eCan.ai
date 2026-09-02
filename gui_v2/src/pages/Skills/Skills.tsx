import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, message, Modal, Tooltip, Space, Tabs, Tag } from 'antd';
import {
    ReloadOutlined,
    AppstoreOutlined,
    UnorderedListOutlined,
    PlusOutlined,
    HeartOutlined,
    ShopOutlined,
    StarOutlined,
    RiseOutlined,
    ThunderboltOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';

import { useSkillStore } from '../../stores/domain/skillStore';
import { useUserStore } from '../../stores/userStore';
import { get_ipc_api } from '../../services/ipc_api';
import { logger } from '@/utils/logger';
import type { Skill } from '@/types/domain/skill';

import SkillMarketplaceGrid from './components/SkillMarketplaceGrid';
import SkillMarketplaceList from './components/SkillMarketplaceList';
import SkillMarketplaceHero from './components/SkillMarketplaceHero';
import SkillCategoryNav from './components/SkillCategoryNav';
import SkillDetails from './components/SkillDetails';
import { SkillFilters, SkillFilterOptions } from './components/SkillFilters';
import { SkillAnalyticsDashboard } from './components/SkillAnalyticsDashboard';
import './Skills.css';

const PageContainer = styled.div`
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--bg-primary);
`;

const TopBar = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 24px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
    gap: 12px;

    @media (max-width: 900px) {
        padding: 8px 14px;
    }
`;

const ScrollArea = styled.div`
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
    position: relative;

    &::-webkit-scrollbar {
        width: 8px;
    }
    &::-webkit-scrollbar-track {
        background: transparent;
    }
    &::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.08);
        border-radius: 4px;
        transition: background 0.3s ease;
    }
    &:hover::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.18);
    }
`;

const StickyFilters = styled.div`
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--bg-primary);
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
`;

const CategoryStrip = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 24px 4px;
    overflow-x: auto;
    background: var(--bg-primary);

    &::-webkit-scrollbar {
        height: 0;
    }
`;

const PageTitleBlock = styled.div`
    display: flex;
    flex-direction: column;
    min-width: 0;
`;

const PageTitle = styled.div`
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
    letter-spacing: -0.2px;
`;

const PageSubtitle = styled.div`
    font-size: 11px;
    color: var(--text-secondary);
    margin-top: 1px;
`;

const SectionHeading = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 24px 6px;

    .heading-left {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .heading-icon {
        font-size: 18px;
        color: var(--primary-color);
    }
    .heading-text {
        font-size: 15px;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: -0.2px;
    }
    .heading-meta {
        font-size: 12px;
        color: var(--text-secondary);
        margin-left: 6px;
    }
    .heading-right {
        display: flex;
        align-items: center;
        gap: 6px;
    }
`;

type ViewMode = 'grid' | 'list' | 'subscriptions' | 'favorites';
type ScopeTab = 'mine' | 'store';

const Skills: React.FC = () => {
    const { t } = useTranslation();
    const username = useUserStore((s) => s.username) || '';

    const skills = useSkillStore((s) => s.items) as Skill[];
    const isLoading = useSkillStore((s) => s.loading);
    const fetchItems = useSkillStore((s) => s.fetchItems);
    const forceRefresh = useSkillStore((s) => s.forceRefresh);
    const setFavoriteSkillIds = useSkillStore((s) => s.setFavoriteSkillIds);
    const setMarketplaceStats = useSkillStore((s) => s.setMarketplaceStats);
    const updateItem = useSkillStore((s) => s.updateItem);

    const [scope, setScope] = useState<ScopeTab>('store');
    const [viewMode, setViewMode] = useState<ViewMode>('grid');
    const [filters, setFilters] = useState<SkillFilterOptions>({ sortBy: 'trending' });
    const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
    const [isAddingNew, setIsAddingNew] = useState(false);
    const [editingSkill, setEditingSkill] = useState<Skill | null>(null);

    const [publicSkills, setPublicSkills] = useState<Skill[]>([]);
    const [subscribedSkillIds, setSubscribedSkillIds] = useState<string[]>([]);
    const [activeCategory, setActiveCategory] = useState<string>('all');

    const normalizeSubscribedIds = useCallback((rawIds: any[]): string[] => {
        const set = new Set<string>();
        for (const raw of rawIds || []) {
            const v = String(raw ?? '').trim();
            if (!v || v === '0') continue;
            set.add(v);
        }
        return Array.from(set);
    }, []);

    const fetchAll = useCallback(async () => {
        if (!username) return;
        try {
            await fetchItems(username);
            const api = get_ipc_api();

            const [publicResp, subscribedResp, favoritesResp] = await Promise.all([
                api.getPublicSkills<any>(username),
                api.getSubscribedSkillIds<any>(username),
                api.listFavoriteSkills<any>(username).catch(() => ({ success: false, data: [] })),
            ]);

            if (publicResp?.success) {
                const data = publicResp.data as any;
                const rows = Array.isArray(data) ? data : (data?.skills || []);
                setPublicSkills(rows);
            } else {
                setPublicSkills([]);
            }

            if (subscribedResp?.success) {
                const data = subscribedResp.data as any;
                const ids = Array.isArray(data) ? data : [];
                setSubscribedSkillIds(normalizeSubscribedIds(ids));
            } else {
                setSubscribedSkillIds([]);
            }

            if (favoritesResp?.success) {
                const ids = (favoritesResp.data as any)?.data ?? favoritesResp.data;
                if (Array.isArray(ids)) setFavoriteSkillIds(ids.map(String));
            }
        } catch (error) {
            logger.error('[Skills] Error fetching skills:', error);
            message.error(t('pages.skills.fetchError', { defaultValue: 'Failed to fetch skills' }));
        }
    }, [username, fetchItems, t, normalizeSubscribedIds, setFavoriteSkillIds]);

    useEffect(() => {
        if (username) fetchAll();
    }, [username, fetchAll]);

    // ============ Derived skill lists ============
    const meLower = (username || '').toLowerCase();
    const isOwnedByMe = useCallback(
        (s: Skill) => {
            const owner = String((s as any)?.owner || '').toLowerCase();
            const source = String((s as any)?.source || '').toLowerCase();
            if (source === 'code') return true;
            return owner === meLower;
        },
        [meLower]
    );

    const mySkills = useMemo(
        () => (skills || []).filter(isOwnedByMe),
        [skills, isOwnedByMe]
    );

    const storeSkills = useMemo(() => {
        const ids = new Set((subscribedSkillIds || []).map(String));
        return (publicSkills || []).filter((s) => {
            const owner = String((s as any)?.owner || '').toLowerCase();
            if (owner === meLower) return false;
            if ((s as any)?.public === false) return false;
            // Hide skills that the user already owns locally
            if (mySkills.some((m) => String(m.id) === String((s as any).id))) return false;
            return true;
        }).map((s) => ({
            ...s,
            _subscribed: ids.has(String((s as any).id)) || ids.has(String((s as any).askid)),
        } as any));
    }, [publicSkills, mySkills, subscribedSkillIds, meLower]);

    // ============ Marketplace Stats Prefetch (cache-aware, debounced, batched) ============
    const prefetchedIdsRef = React.useRef<Set<string>>(new Set());
    const prefetchTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        if (!username) return;
        if (prefetchTimerRef.current) clearTimeout(prefetchTimerRef.current);

        prefetchTimerRef.current = setTimeout(async () => {
            const api = get_ipc_api();
            const target = scope === 'store' ? storeSkills : mySkills;
            const toFetch: Array<{ id: string }> = [];

            // Only fetch skills that haven't been prefetched yet (first 24)
            target.forEach((s, idx) => {
                const id = String((s as any)?.id || '');
                if (id && !prefetchedIdsRef.current.has(id) && idx < 24) {
                    toFetch.push({ id });
                    prefetchedIdsRef.current.add(id);
                }
            });

            if (toFetch.length === 0) return;

            // Fetch in batches of 4 to avoid overwhelming the server
            const BATCH_SIZE = 4;
            for (let i = 0; i < toFetch.length; i += BATCH_SIZE) {
                const batch = toFetch.slice(i, i + BATCH_SIZE);
                await Promise.allSettled(
                    batch.map(async ({ id }) => {
                        try {
                            const resp = await api.getSkillMarketplaceStats<any>(id);
                            if (resp?.success && (resp.data as any)?.data) {
                                setMarketplaceStats(id, (resp.data as any).data);
                            }
                        } catch { /* ignore individual failures */ }
                    })
                );
            }
        }, 600); // debounce 600ms after skill list stabilises

        return () => {
            if (prefetchTimerRef.current) clearTimeout(prefetchTimerRef.current);
        };
    }, [username, scope, storeSkills, mySkills]);

    // ============ Handlers ============
    const handleRefresh = useCallback(async () => {
        if (!username) return;
        try {
            await forceRefresh(username);
            await fetchAll();
        } catch (error) {
            logger.error('[Skills] Error refreshing skills:', error);
            message.error(t('pages.skills.fetchError', { defaultValue: 'Failed to refresh skills' }));
        }
    }, [username, forceRefresh, fetchAll, t]);

    const handleSubscribe = async (skillId: string) => {
        if (!username) return;

        // Paid-skill confirmation: free skills subscribe instantly; paid
        // skills confirm the recurring monthly charge first. The backend
        // additionally rejects with INSUFFICIENT_FUNDS when the account
        // balance is known to be below the price.
        const target: any = (publicSkills || []).find(
            (s: any) => String(s?.id) === String(skillId) || String(s?.askid) === String(skillId)
        );
        const price = Number(target?.price || 0);
        if (price > 0) {
            const confirmed = await new Promise<boolean>((resolve) => {
                Modal.confirm({
                    title: t('pages.skills.paidSubscribeTitle', '订阅付费技能'),
                    content: t('pages.skills.paidSubscribeContent',
                        `该技能为付费技能：订阅后将按月从您的账户扣费 ¥${price}/月。余额不足时订阅将被拒绝。确认订阅？`),
                    okText: t('common.confirm', '确认'),
                    cancelText: t('common.cancel', '取消'),
                    onOk: () => resolve(true),
                    onCancel: () => resolve(false),
                });
            });
            if (!confirmed) return;
        }

        const api = get_ipc_api();
        const resp = await api.subscribeToSkill(username, skillId);
        if (!resp?.success) {
            const err: any = resp?.error;
            if (err?.code === 'INSUFFICIENT_FUNDS') {
                message.error(err?.message || t('pages.skills.insufficientFunds', '账户余额不足，请先充值后再订阅'));
                return;
            }
            throw new Error(err?.message || t('pages.skills.subscribeFailed', 'Subscribe failed'));
        }
        const result = resp.data as any;
        if (result && result.success === false) throw new Error(result.error || t('pages.skills.subscribeFailed', 'Subscribe failed'));
        setSubscribedSkillIds((prev) => {
            const next = new Set((prev || []).map(String));
            if (skillId) next.add(String(skillId));
            if (result?.id) next.add(String(result.id));
            if (result?.askid !== undefined && result?.askid !== null && String(result.askid).trim() && String(result.askid).trim() !== '0') {
                next.add(String(result.askid));
            }
            return Array.from(next);
        });
        // Bump download count locally for instant feedback
        try {
            await api.incrementSkillDownload(String(skillId), 1);
            const statsResp = await api.getSkillMarketplaceStats(String(skillId));
            if (statsResp?.success && (statsResp.data as any)?.data) {
                setMarketplaceStats(String(skillId), (statsResp.data as any).data);
            }
        } catch { /* ignore */ }

        // Refresh to verify the subscribed skill appears in "My Skills"
        await handleRefresh();

        // Warn user if cloud sync failed (subscription saved locally but may not sync to other devices)
        if (result && result.cloud_sync_success === false) {
            message.warning(t('pages.skills.subscribeCloudSyncWarning', 'Subscribed successfully. Note: sync to cloud failed — subscription may not appear on other devices.'));
        }
    };

    const handleUnsubscribe = async (skillId: string) => {
        if (!username) return;
        const api = get_ipc_api();
        const resp = await api.unsubscribeFromSkill(username, skillId);
        if (!resp?.success) throw new Error((resp?.error as any)?.message || t('pages.skills.unsubscribeFailed', 'Unsubscribe failed'));
        const result = resp.data as any;
        if (result && result.success === false) throw new Error(result.error || t('pages.skills.unsubscribeFailed', 'Unsubscribe failed'));
        setSubscribedSkillIds((prev) => {
            const removeIds = new Set<string>();
            if (skillId) removeIds.add(String(skillId));
            if (result?.id) removeIds.add(String(result.id));
            if (result?.askid !== undefined && result?.askid !== null && String(result.askid).trim() && String(result.askid).trim() !== '0') {
                removeIds.add(String(result.askid));
            }
            return (prev || []).filter((id) => !removeIds.has(String(id)));
        });
    };

    const handleFavoriteToggle = useCallback(
        async (skill: Skill) => {
            if (!username) return;
            const api = get_ipc_api();
            const id = String((skill as any)?.id || '');
            if (!id) return;
            const resp = await api.toggleSkillFavorite(username, id);
            if (!resp?.success) {
                message.error(t('pages.skills.favoriteToggleFailed', 'Failed to update favorite'));
                return;
            }
            const data = (resp.data as any)?.data ?? resp.data;
            const favorited = !!data?.favorited;
            setFavoriteSkillIds(
                favorited
                    ? Array.from(new Set([...(useSkillStore.getState().favoriteSkillIds || []), id]))
                    : (useSkillStore.getState().favoriteSkillIds || []).filter((x) => String(x) !== id)
            );
            if (data) setMarketplaceStats(id, data);
            message.success(
                favorited
                    ? t('pages.skills.favorited', 'Added to favorites')
                    : t('pages.skills.unfavorited', 'Removed from favorites')
            );
        },
        [username, setFavoriteSkillIds, setMarketplaceStats, t]
    );

    const handleCopy = useCallback(
        async (sourceSkill: Skill) => {
            if (!username) return;
            const copyName = `${sourceSkill.name} (Copy)`;
            const copySkill: Skill = {
                ...sourceSkill,
                id: '',
                name: copyName,
                owner: username,
                description: sourceSkill.description || '',
                version: '0.0.0',
                public: false,
                rentable: false,
                source: 'ui',
                askid: undefined,
                cloud_id: undefined,
            };
            delete (copySkill as any).subscribedAt;
            delete (copySkill as any).subscribedBy;
            try {
                const api = get_ipc_api();
                const newAgentResp = await api.newAgentSkill<any>(username, copySkill as any);
                if (newAgentResp?.success) {
                    const newId = (newAgentResp.data as any)?.skill_id || (newAgentResp.data as any)?.id;
                    message.success(t('pages.skills.copied', 'Skill copied successfully'));
                    await handleRefresh();
                    if (newId) {
                        const fresh = (useSkillStore.getState().items as Skill[]).find((s) => String(s.id) === String(newId));
                        if (fresh) setSelectedSkill(fresh);
                    }
                } else {
                    throw new Error(newAgentResp?.error?.message || 'Copy failed');
                }
            } catch (e) {
                if (e instanceof Error) message.error(e.message);
                else message.error(t('pages.skills.copyFailed', 'Failed to copy skill'));
            }
        },
        [username, handleRefresh, t]
    );

    const handleRun = (_skill: Skill) => {
        message.info(t('pages.skills.runComingSoon', 'Skill execution coming soon'));
    };

    const handleReport = useCallback(
        async (skill: Skill, reason: string, note: string) => {
            if (!username) return;
            const api = get_ipc_api();
            const id = String((skill as any)?.id || '');
            const resp = await api.reportSkill(id, username, reason, note);
            if (resp?.success) {
                message.success(t('pages.skills.reportSubmitted', 'Report submitted. Thank you.'));
            } else {
                message.error(t('pages.skills.reportFailed', 'Failed to submit report'));
            }
        },
        [username, t]
    );

    const handleSelect = useCallback((skill: Skill) => {
        setSelectedSkill(skill);
        setEditingSkill(skill);
    }, []);

    const handleEditInDrawer = useCallback((skill: Skill) => {
        setEditingSkill(skill);
        setSelectedSkill(skill);
    }, []);

    const handleCloseDrawer = useCallback(() => {
        setEditingSkill(null);
        setSelectedSkill(null);
    }, []);

    const handleSkillSave = useCallback(() => {
        setIsAddingNew(false);
        setEditingSkill(null);
        setSelectedSkill(null);
        handleRefresh();
    }, [handleRefresh]);

    // ============ Filtered lists ============
    const filterAndSort = useCallback(
        (rows: Skill[]) => {
            let result = [...rows];
            if (filters.search) {
                const q = filters.search.toLowerCase();
                result = result.filter((s) =>
                    s.name?.toLowerCase().includes(q) ||
                    s.description?.toLowerCase().includes(q) ||
                    (Array.isArray(s.tags) ? s.tags : []).some((tag) => String(tag).toLowerCase().includes(q))
                );
            }
            if (filters.status) result = result.filter((s) => s.status === filters.status);
            if (filters.level) result = result.filter((s) => s.level === filters.level);
            if (filters.priceType) {
                result = result.filter((s) => {
                    const price = (s as any)?.price;
                    const isFree = typeof price === 'number' ? price <= 0 : !price;
                    return filters.priceType === 'free' ? isFree : !isFree;
                });
            }
            if (activeCategory && activeCategory !== 'all') {
                const cat = activeCategory.toLowerCase();
                result = result.filter((s) => {
                    const skillCat = ((s as any).category || '').toLowerCase();
                    return skillCat === cat;
                });
            }
            result.sort((a, b) => {
                switch (filters.sortBy) {
                    case 'trending':
                        return ((b as any).trendingScore || 0) - ((a as any).trendingScore || 0)
                            || ((b as any).downloadCount || 0) - ((a as any).downloadCount || 0);
                    case 'downloads':
                        return ((b as any).downloadCount || 0) - ((a as any).downloadCount || 0);
                    case 'rating':
                        return ((b as any).rating || 0) - ((a as any).rating || 0);
                    case 'name':
                        return (a.name || '').localeCompare(b.name || '');
                    case 'newest':
                        return String((b as any).updatedAt || '').localeCompare(String((a as any).updatedAt || ''));
                    case 'level': {
                        const order: Record<string, number> = { entry: 1, intermediate: 2, advanced: 3, expert: 4 };
                        return (order[String((b as any).level || '').toLowerCase()] || 0)
                            - (order[String((a as any).level || '').toLowerCase()] || 0);
                    }
                    default:
                        return 0;
                }
            });
            return result;
        },
        [filters, activeCategory]
    );

    const mySkillsView = useMemo(() => {
        if (viewMode !== 'subscriptions' && viewMode !== 'favorites') {
            return filterAndSort(mySkills);
        }
        if (viewMode === 'subscriptions') {
            const subIds = new Set(subscribedSkillIds.map(String));
            // Include both mySkills (running locally) and public store items that the user subscribed to
            const merged = [...mySkills, ...storeSkills];
            const unique = new Map<string, Skill>();
            for (const s of merged) {
                const id = String((s as any).id);
                if (subIds.has(id) || subIds.has(String((s as any).askid))) {
                    if (!unique.has(id)) unique.set(id, s);
                }
            }
            return filterAndSort(Array.from(unique.values()));
        }
        if (viewMode === 'favorites') {
            const favIds = new Set(useSkillStore.getState().favoriteSkillIds.map(String));
            const merged = [...mySkills, ...storeSkills];
            const unique = new Map<string, Skill>();
            for (const s of merged) {
                const id = String((s as any).id);
                if (favIds.has(id)) {
                    if (!unique.has(id)) unique.set(id, s);
                }
            }
            return filterAndSort(Array.from(unique.values()));
        }
        return [];
    }, [viewMode, mySkills, storeSkills, subscribedSkillIds, filterAndSort]);

    const storeSkillsView = useMemo(() => filterAndSort(storeSkills), [storeSkills, filterAndSort]);

    // Aggregate top-level numbers for the marketplace stats strip
    const heroStats = useMemo(() => {
        const all = [...mySkills, ...storeSkills];
        const totalDownloads = all.reduce((acc, s) => acc + Number((s as any).downloadCount || 0), 0);
        const totalAuthors = new Set(all.map((s) => String((s as any).owner || '').toLowerCase()).filter(Boolean)).size;
        const newThisWeek = all.filter((s) => {
            const ts = (s as any).updatedAt || (s as any).createdAt;
            if (!ts) return false;
            const d = new Date(ts);
            if (isNaN(d.getTime())) return false;
            return Date.now() - d.getTime() < 7 * 24 * 60 * 60 * 1000;
        }).length;
        return {
            totalSkills: all.length,
            totalDownloads,
            totalAuthors,
            newThisWeek,
        };
    }, [mySkills, storeSkills]);

    // For "My Library" tab — show analytics only
    const myLibraryContent = (
        <>
            <SkillAnalyticsDashboard username={username} />
            <StickyFilters>
                <SkillFilters filters={filters} onChange={setFilters} />
            </StickyFilters>
            {viewMode === 'grid' && (
                <SkillMarketplaceGrid
                    skills={mySkillsView}
                    loading={isLoading}
                    onSelectSkill={handleSelect}
                    selectedSkillId={selectedSkill ? String(selectedSkill.id) : undefined}
                    username={username}
                    subscribedSkillIds={subscribedSkillIds}
                    onSubscribe={handleSubscribe}
                    onUnsubscribe={handleUnsubscribe}
                    onCopy={handleCopy}
                    onRun={handleRun}
                    onReport={handleReport}
                    onFavoriteToggle={handleFavoriteToggle}
                    onEditInGrid={handleEditInDrawer}
                />
            )}
            {viewMode === 'list' && (
                <SkillMarketplaceList
                    skills={mySkillsView}
                    loading={isLoading}
                    onSelectSkill={handleSelect}
                    selectedSkillId={selectedSkill ? String(selectedSkill.id) : undefined}
                    username={username}
                    subscribedSkillIds={subscribedSkillIds}
                    onSubscribe={handleSubscribe}
                    onUnsubscribe={handleUnsubscribe}
                    onCopy={handleCopy}
                    onRun={handleRun}
                    onReport={handleReport}
                    onFavoriteToggle={handleFavoriteToggle}
                    onEditInGrid={handleEditInDrawer}
                />
            )}
            {(viewMode === 'subscriptions' || viewMode === 'favorites') && (
                <SkillMarketplaceList
                    skills={mySkillsView}
                    loading={isLoading}
                    onSelectSkill={handleSelect}
                    selectedSkillId={selectedSkill ? String(selectedSkill.id) : undefined}
                    username={username}
                    subscribedSkillIds={subscribedSkillIds}
                    onSubscribe={handleSubscribe}
                    onUnsubscribe={handleUnsubscribe}
                    onCopy={handleCopy}
                    onRun={handleRun}
                    onReport={handleReport}
                    onFavoriteToggle={handleFavoriteToggle}
                    onEditInGrid={handleEditInDrawer}
                    variant={viewMode === 'favorites' ? 'favorites' : 'subscriptions'}
                />
            )}
        </>
    );

    // For "App Store" tab — show stats strip + category nav + filters + grid
    const storeContent = (
        <>
            <SkillMarketplaceHero stats={heroStats} />
            <CategoryStrip>
                <SkillCategoryNav
                    active={activeCategory}
                    onChange={setActiveCategory}
                />
            </CategoryStrip>
            <StickyFilters>
                <SkillFilters filters={filters} onChange={setFilters} />
            </StickyFilters>

            <SectionHeading>
                <div className="heading-left">
                    <RiseOutlined className="heading-icon" />
                    <span className="heading-text">
                        {t('pages.skills.sections.trending', 'Trending Now')}
                    </span>
                    <span className="heading-meta">
                        {storeSkillsView.length} {t('pages.skills.skills', 'skills')}
                    </span>
                </div>
            </SectionHeading>

            {viewMode === 'grid' ? (
                <SkillMarketplaceGrid
                    skills={storeSkillsView}
                    loading={isLoading}
                    onSelectSkill={handleSelect}
                    selectedSkillId={selectedSkill ? String(selectedSkill.id) : undefined}
                    username={username}
                    subscribedSkillIds={subscribedSkillIds}
                    onSubscribe={handleSubscribe}
                    onUnsubscribe={handleUnsubscribe}
                    onCopy={handleCopy}
                    onRun={handleRun}
                    onReport={handleReport}
                    onFavoriteToggle={handleFavoriteToggle}
                    onEditInGrid={handleEditInDrawer}
                />
            ) : (
                <SkillMarketplaceList
                    skills={storeSkillsView}
                    loading={isLoading}
                    onSelectSkill={handleSelect}
                    selectedSkillId={selectedSkill ? String(selectedSkill.id) : undefined}
                    username={username}
                    subscribedSkillIds={subscribedSkillIds}
                    onSubscribe={handleSubscribe}
                    onUnsubscribe={handleUnsubscribe}
                    onCopy={handleCopy}
                    onRun={handleRun}
                    onReport={handleReport}
                    onFavoriteToggle={handleFavoriteToggle}
                    onEditInGrid={handleEditInDrawer}
                />
            )}
        </>
    );

    const scopeTabs = [
        {
            key: 'store',
            label: (
                <Space size={6}>
                    <ShopOutlined />
                    {t('pages.skills.heroTitle', 'Skill Store')}
                    <Tag color="blue" style={{ marginLeft: 4, fontSize: 10 }}>{storeSkills.length}</Tag>
                </Space>
            ),
        },
        {
            key: 'mine',
            label: (
                <Space size={6}>
                    <StarOutlined />
                    {t('pages.skills.scope.mine', 'My Library')}
                    <Tag style={{ marginLeft: 4, fontSize: 10 }}>{mySkills.length}</Tag>
                </Space>
            ),
        },
    ];

    return (
        <PageContainer>
            <TopBar>
                <PageTitleBlock>
                    <PageTitle>
                        <Space size={8}>
                            <ShopOutlined style={{ color: 'var(--primary-color)' }} />
                            {t('pages.skills.title', 'Skill Store')}
                        </Space>
                    </PageTitle>
                    <PageSubtitle>
                        {t('pages.skills.subtitle', 'Discover, install and manage reusable skills for your agents.')}
                    </PageSubtitle>
                </PageTitleBlock>

                <Tabs
                    activeKey={scope}
                    onChange={(k) => setScope(k as ScopeTab)}
                    items={scopeTabs}
                    size="small"
                    tabBarStyle={{ marginBottom: 0 }}
                />

                <Space>
                    {scope === 'mine' && (
                        <Tooltip title={t('pages.skills.addSkill', 'Add Skill')}>
                            <Button
                                type="primary"
                                icon={<PlusOutlined />}
                                onClick={() => setIsAddingNew(true)}
                            >
                                {t('pages.skills.newSkill', 'New Skill')}
                            </Button>
                        </Tooltip>
                    )}
                    <Tooltip title={t('pages.skills.viewList', 'List view')}>
                        <Button
                            type="text"
                            shape="circle"
                            icon={<UnorderedListOutlined />}
                            onClick={() => setViewMode('list')}
                            style={{
                                background: viewMode === 'list' ? 'rgba(255,255,255,0.08)' : 'transparent',
                                color: 'rgba(203, 213, 225, 0.9)',
                            }}
                        />
                    </Tooltip>
                    <Tooltip title={t('pages.skills.viewGrid', 'Grid view')}>
                        <Button
                            type="text"
                            shape="circle"
                            icon={<AppstoreOutlined />}
                            onClick={() => setViewMode('grid')}
                            style={{
                                background: viewMode === 'grid' ? 'rgba(255,255,255,0.08)' : 'transparent',
                                color: 'rgba(203, 213, 225, 0.9)',
                            }}
                        />
                    </Tooltip>
                    <Tooltip title={t('pages.skills.viewSubscriptions', 'Subscriptions')}>
                        <Button
                            type="text"
                            shape="circle"
                            icon={<HeartOutlined />}
                            onClick={() => setViewMode('subscriptions')}
                            style={{
                                background: viewMode === 'subscriptions' ? 'rgba(245, 34, 45, 0.12)' : 'transparent',
                                color: viewMode === 'subscriptions' ? '#ff7875' : 'rgba(203, 213, 225, 0.9)',
                            }}
                        />
                    </Tooltip>
                    <Tooltip title={t('common.refresh', 'Refresh')}>
                        <Button
                            type="text"
                            shape="circle"
                            icon={<ReloadOutlined />}
                            onClick={handleRefresh}
                            loading={isLoading}
                            style={{
                                background: 'transparent',
                                color: 'rgba(203, 213, 225, 0.9)',
                            }}
                        />
                    </Tooltip>
                </Space>
            </TopBar>

            <ScrollArea>
                {scope === 'store' ? storeContent : myLibraryContent}
            </ScrollArea>

            {/* Click-outside overlay to close drawer */}
            {(editingSkill || isAddingNew) && (
                <div
                    onClick={handleCloseDrawer}
                    style={{
                        position: 'fixed',
                        inset: 0,
                        zIndex: 999,
                        background: 'rgba(0,0,0,0.3)',
                        cursor: 'pointer',
                    }}
                />
            )}

            {/* Detail / Editor Drawer */}
            {(editingSkill || isAddingNew) && (
                <div
                    onClick={(e) => e.stopPropagation()}
                    style={{
                        position: 'fixed',
                        top: 0,
                        right: 0,
                        bottom: 0,
                        width: 'min(1080px, 92vw)',
                        zIndex: 1000,
                        background: 'var(--bg-primary)',
                        borderLeft: '1px solid rgba(255,255,255,0.06)',
                        boxShadow: '-16px 0 60px rgba(0,0,0,0.6)',
                        display: 'flex',
                        flexDirection: 'column',
                    }}
                >
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 16px',
                        borderBottom: '1px solid rgba(255,255,255,0.08)',
                        flexShrink: 0,
                    }}>
                        <Space size={6}>
                            <ThunderboltOutlined style={{ color: 'var(--primary-color)' }} />
                            <strong style={{ color: 'var(--text-primary)', fontSize: 13 }}>
                                {isAddingNew ? t('pages.skills.newSkill', 'New Skill') : t('common.edit', 'Edit')}
                            </strong>
                        </Space>
                        <Space>
                            <Button size="small" onClick={handleCloseDrawer}>{t('common.cancel', 'Cancel')}</Button>
                        </Space>
                    </div>
                    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                        <SkillDetails
                            skill={isAddingNew ? null : editingSkill}
                            isNew={isAddingNew}
                            onRefresh={handleRefresh}
                            onSave={handleSkillSave}
                            onSkillChange={(updated) => {
                                setEditingSkill(updated);
                                setSelectedSkill(updated);
                                updateItem(String(updated.id), updated);
                            }}
                            onCancel={handleCloseDrawer}
                            onDelete={() => {
                                handleCloseDrawer();
                                handleRefresh();
                            }}
                            subscribedSkillIds={subscribedSkillIds}
                            onSubscribe={handleSubscribe}
                            onUnsubscribe={handleUnsubscribe}
                        />
                    </div>
                </div>
            )}
        </PageContainer>
    );
};

export default Skills;

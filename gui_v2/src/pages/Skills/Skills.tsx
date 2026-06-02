import React, { useCallback, useEffect, useState } from 'react';
import { Button, message, Tooltip, Space, Drawer } from 'antd';
import { ReloadOutlined, AppstoreOutlined, UnorderedListOutlined, PlusOutlined } from '@ant-design/icons';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useTranslation } from 'react-i18next';
import { useSkillStore } from '../../stores/domain/skillStore';
import { useUserStore } from '../../stores/userStore';
import SkillList from './components/SkillList';
import SkillDetails from './components/SkillDetails';
import { logger } from '@/utils/logger';
import type { Skill } from '@/types/domain/skill';
import { SkillAPI } from '@/services/api/skillApi';
import { get_ipc_api } from '../../services/ipc_api';
import styled from '@emotion/styled';
import './Skills.css';

const FullWidthContainer = styled.div`
    height: 100%;
    display: flex;
    flex-direction: column;
`;

const HeaderBar = styled.div`
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
`;

// Edit Drawer样式 - 右侧滑出全功能编辑面板
const EditDrawer = styled(Drawer)`
    .ant-drawer-body {
        padding: 0;
        height: 100%;
        display: flex;
        flex-direction: column;
    }
`;

const Skills: React.FC = () => {
    const { t } = useTranslation();

    const normalizeSubscribedIds = useCallback((rawIds: any[]): string[] => {
        const next = new Set<string>();
        for (const raw of rawIds || []) {
            const value = String(raw ?? '').trim();
            if (!value || value === '0') continue;
            next.add(value);
        }
        return Array.from(next);
    }, []);

    const skills = useSkillStore((state) => state.items);
    const isLoading = useSkillStore((state) => state.loading);
    const fetchItems = useSkillStore((state) => state.fetchItems);
    const forceRefresh = useSkillStore((state) => state.forceRefresh);

    const username = useUserStore((state) => state.username);
    const [isAddingNew, setIsAddingNew] = React.useState(false);
    const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
    const [publicSkills, setPublicSkills] = useState<Skill[]>([]);
    const [subscribedSkillIds, setSubscribedSkillIds] = useState<string[]>([]);

    const [viewMode, setViewMode] = useState<'list' | 'grid'>('list');
    const [isEditingInGrid, setIsEditingInGrid] = useState(false);

    const selectItem = useCallback((skill: Skill) => {
        setSelectedSkill(skill);
    }, []);

    const fetchSkills = useCallback(async () => {
        if (!username) return;

        try {
            await fetchItems(username);
            const api = get_ipc_api();

            const [publicResp, subscribedResp] = await Promise.all([
                api.getPublicSkills<any>(username),
                api.getSubscribedSkillIds<any>(username),
            ]);

            if (publicResp.success) {
                const publicData = publicResp.data as any;
                const rows = Array.isArray(publicData) ? publicData : (publicData?.skills || []);
                setPublicSkills(rows);
            } else {
                setPublicSkills([]);
            }

            if (subscribedResp.success) {
                const subscribedData = subscribedResp.data as any;
                const ids = Array.isArray(subscribedData) ? subscribedData : [];
                setSubscribedSkillIds(normalizeSubscribedIds(ids));
            } else {
                setSubscribedSkillIds([]);
            }
        } catch (error) {
            logger.error('[Skills] Error fetching skills:', error);
            message.error(t('pages.skills.fetchError', { defaultValue: 'Failed to fetch skills' }));
        }
    }, [username, fetchItems, t, normalizeSubscribedIds]);

    useEffect(() => {
        if (username) {
            fetchSkills();
        }
    }, [username, fetchSkills]);

    const handleRefresh = useCallback(async () => {
        if (!username) return;

        try {
            await forceRefresh(username);
            const api = get_ipc_api();

            const [publicResp, subscribedResp] = await Promise.all([
                api.getPublicSkills<any>(username),
                api.getSubscribedSkillIds<any>(username),
            ]);

            if (publicResp.success) {
                const publicData = publicResp.data as any;
                const rows = Array.isArray(publicData) ? publicData : (publicData?.skills || []);
                setPublicSkills(rows);
            } else {
                setPublicSkills([]);
            }

            if (subscribedResp.success) {
                const subscribedData = subscribedResp.data as any;
                const ids = Array.isArray(subscribedData) ? subscribedData : [];
                setSubscribedSkillIds(normalizeSubscribedIds(ids));
            } else {
                setSubscribedSkillIds([]);
            }
        } catch (error) {
            logger.error('[Skills] Error refreshing skills:', error);
            message.error(t('pages.skills.fetchError', { defaultValue: 'Failed to refresh skills' }));
        }
    }, [username, forceRefresh, t, normalizeSubscribedIds]);

    const HeaderControls = () => (
        <Space>
            <Tooltip title={t('pages.skills.viewList', 'List view')}>
                <Button
                    type="text"
                    shape="circle"
                    icon={<UnorderedListOutlined />}
                    onClick={() => {
                        setViewMode('list');
                        setIsEditingInGrid(false);
                        try { localStorage.setItem('skills:list_view_mode', 'list'); } catch { /* ignore */ }
                    }}
                    style={{
                        background: viewMode === 'list' ? 'rgba(255, 255, 255, 0.06)' : 'transparent',
                        border: 'none',
                        color: 'rgba(203, 213, 225, 0.9)',
                    }}
                />
            </Tooltip>
            <Tooltip title={t('pages.skills.viewGrid', 'Grid view')}>
                <Button
                    type="text"
                    shape="circle"
                    icon={<AppstoreOutlined />}
                    onClick={() => {
                        setViewMode('grid');
                        setIsEditingInGrid(false);
                        try { localStorage.setItem('skills:list_view_mode', 'grid'); } catch { /* ignore */ }
                    }}
                    style={{
                        background: viewMode === 'grid' ? 'rgba(255, 255, 255, 0.06)' : 'transparent',
                        border: 'none',
                        color: 'rgba(203, 213, 225, 0.9)',
                    }}
                />
            </Tooltip>
            <Tooltip title={t('pages.skills.refresh')}>
                <Button
                    type="text"
                    shape="circle"
                    icon={<ReloadOutlined />}
                    onClick={handleRefresh}
                    loading={isLoading}
                    style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'rgba(203, 213, 225, 0.9)',
                    }}
                />
            </Tooltip>
        </Space>
    );

    const listTitle = (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <span style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px' }}>{t('pages.skills.title')}</span>
            <HeaderControls />
        </div>
    );

    const handleSkillSave = () => {
        setIsAddingNew(false);
        handleRefresh();
    };

    const handleSkillCancel = () => {
        if (isAddingNew) {
            setIsAddingNew(false);
            setSelectedSkill(null);
        }
    };

    const handleSkillDelete = () => {
        setSelectedSkill(null);
        setIsEditingInGrid(false);
    };

    const handleSelectedSkillChange = useCallback((updatedSkill: Skill) => {
        setSelectedSkill(updatedSkill);
    }, []);

    const handleSubscribe = async (skillId: string) => {
        if (!username) return;
        const api = get_ipc_api();
        const resp = await api.subscribeToSkill(username, skillId);
        if (!resp.success) throw new Error((resp.error as any)?.message || t('pages.skills.subscribeFailed', 'Subscribe failed'));
        const result = resp.data as any;
        if (result && result.success === false) throw new Error(result.error || t('pages.skills.subscribeFailed', 'Subscribe failed'));
        setSubscribedSkillIds(prev => {
            const next = new Set((prev || []).map((id) => String(id)));
            if (skillId) next.add(String(skillId));
            if (result?.id) next.add(String(result.id));
            if (result?.askid !== undefined && result?.askid !== null && String(result.askid).trim() && String(result.askid).trim() !== '0') {
                next.add(String(result.askid));
            }
            return normalizeSubscribedIds(Array.from(next));
        });
    };

    const handleUnsubscribe = async (skillId: string) => {
        if (!username) return;
        const api = get_ipc_api();
        const resp = await api.unsubscribeFromSkill(username, skillId);
        if (!resp.success) throw new Error((resp.error as any)?.message || t('pages.skills.unsubscribeFailed', 'Unsubscribe failed'));
        const result = resp.data as any;
        if (result && result.success === false) throw new Error(result.error || t('pages.skills.unsubscribeFailed', 'Unsubscribe failed'));
        setSubscribedSkillIds(prev => {
            const removeIds = new Set<string>();
            if (skillId) removeIds.add(String(skillId));
            if (result?.id) removeIds.add(String(result.id));
            if (result?.askid !== undefined && result?.askid !== null && String(result.askid).trim() && String(result.askid).trim() !== '0') {
                removeIds.add(String(result.askid));
            }
            return normalizeSubscribedIds((prev || []).filter((id) => !removeIds.has(String(id))));
        });
    };

    const handleCopy = async (sourceSkill: Skill) => {
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
            const api = new SkillAPI();
            const resp = await api.create(username, copySkill);
            if (resp.success && resp.data) {
                message.success(t('pages.skills.copied', 'Skill copied successfully'));
                handleRefresh();
                setSelectedSkill(resp.data);
                if (viewMode === 'grid') {
                    setIsEditingInGrid(true);
                }
            } else {
                throw new Error(resp.error?.message || 'Copy failed');
            }
        } catch (e) {
            if (e instanceof Error) message.error(e.message);
            else message.error(t('pages.skills.copyFailed', 'Failed to copy skill'));
        }
    };

    const handleRun = (_skill: Skill) => {
        message.info(t('pages.skills.runComingSoon', 'Skill execution coming soon'));
    };

    // Grid view with detail drawer (Drawer style for full editing experience)
    if (viewMode === 'grid') {
        return (
            <FullWidthContainer>
                <HeaderBar>
                    <span style={{ fontSize: '16px', fontWeight: 600 }}>{t('pages.skills.title')}</span>
                    <Space>
                        <Tooltip title={t('pages.skills.addSkill', 'Add Skill')}>
                            <Button
                                type="primary"
                                icon={<PlusOutlined />}
                                onClick={() => {
                                    setIsAddingNew(true);
                                    setSelectedSkill(null);
                                }}
                                style={{
                                    background: 'rgba(24, 144, 255, 0.8)',
                                    border: '1px solid rgba(24, 144, 255, 0.6)',
                                    borderRadius: '8px',
                                    height: '34px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px',
                                }}
                            />
                        </Tooltip>
                        <HeaderControls />
                    </Space>
                </HeaderBar>
                <SkillList
                    skills={skills}
                    publicSkills={publicSkills}
                    loading={isLoading}
                    onSelectSkill={selectItem}
                    selectedSkillId={selectedSkill ? String(selectedSkill.id) : undefined}
                    viewMode={viewMode}
                    username={username || ''}
                    subscribedSkillIds={subscribedSkillIds}
                    onEditInGrid={() => setIsEditingInGrid(true)}
                    onSubscribe={handleSubscribe}
                    onUnsubscribe={handleUnsubscribe}
                    onCopy={handleCopy}
                    onRun={handleRun}
                />
                <EditDrawer
                    title={null}
                    placement="right"
                    width={800}
                    open={isEditingInGrid && !!selectedSkill}
                    onClose={() => {
                        setIsEditingInGrid(false);
                        setSelectedSkill(null);
                    }}
                    closable={false}
                    styles={{
                        body: { padding: 0, background: 'var(--bg-primary)' },
                        header: { display: 'none' },
                    }}
                >
                    {selectedSkill && (
                        <SkillDetails
                            skill={selectedSkill}
                            isNew={false}
                            onRefresh={handleRefresh}
                            onSave={handleSkillSave}
                            onSkillChange={handleSelectedSkillChange}
                            onCancel={() => {
                                setIsEditingInGrid(false);
                                setSelectedSkill(null);
                            }}
                            onDelete={handleSkillDelete}
                            subscribedSkillIds={subscribedSkillIds}
                            onSubscribe={handleSubscribe}
                            onUnsubscribe={handleUnsubscribe}
                        />
                    )}
                </EditDrawer>
            </FullWidthContainer>
        );
    }

    // List view: detail layout
    return (
        <DetailLayout
            listTitle={listTitle}
            detailsTitle={t('pages.skills.details')}
            resizableList
            listWidthStorageKey="skills:list_panel_width"
            defaultListWidth={360}
            minListWidth={300}
            maxListWidth={640}
            listContent={
                <SkillList
                    skills={skills}
                    publicSkills={publicSkills}
                    loading={isLoading}
                    onSelectSkill={selectItem}
                    selectedSkillId={selectedSkill ? String(selectedSkill.id) : undefined}
                    viewMode={viewMode}
                    username={username || ''}
                    subscribedSkillIds={subscribedSkillIds}
                    onSubscribe={handleSubscribe}
                    onUnsubscribe={handleUnsubscribe}
                    onCopy={handleCopy}
                    onRun={handleRun}
                />
            }
            detailsContent={
                (selectedSkill || isAddingNew) ? (
                    <SkillDetails
                        skill={isAddingNew ? null : selectedSkill}
                        isNew={isAddingNew}
                        onRefresh={handleRefresh}
                        onSave={handleSkillSave}
                        onSkillChange={handleSelectedSkillChange}
                        onCancel={handleSkillCancel}
                        onDelete={handleSkillDelete}
                        subscribedSkillIds={subscribedSkillIds}
                        onSubscribe={handleSubscribe}
                        onUnsubscribe={handleUnsubscribe}
                    />
                ) : undefined
            }
        />
    );
};

export default Skills;

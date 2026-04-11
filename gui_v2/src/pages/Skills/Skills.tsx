import React, { useCallback, useEffect, useState } from 'react';
import { Button, message, Tooltip, Space } from 'antd';
import { ReloadOutlined, AppstoreOutlined, UnorderedListOutlined } from '@ant-design/icons';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useTranslation } from 'react-i18next';
import { useSkillStore } from '../../stores/domain/skillStore';
import { useUserStore } from '../../stores/userStore';
import SkillList from './components/SkillList';
import SkillDetails from './components/SkillDetails';
import { logger } from '@/utils/logger';
import type { Skill } from '@/types/domain/skill';
import { get_ipc_api } from '../../services/ipc_api';
import './Skills.css';

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

    // Use new skillStore
    const skills = useSkillStore((state) => state.items);
    const isLoading = useSkillStore((state) => state.loading);
    const fetchItems = useSkillStore((state) => state.fetchItems);
    const forceRefresh = useSkillStore((state) => state.forceRefresh);

    const username = useUserStore((state) => state.username);
    const [isAddingNew, setIsAddingNew] = React.useState(false);

    // Directly manage selected status
    const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
    const [publicSkills, setPublicSkills] = useState<Skill[]>([]);
    const [subscribedSkillIds, setSubscribedSkillIds] = useState<string[]>([]);

    const [viewMode, setViewMode] = useState<'list' | 'grid'>(() => {
        try {
            const raw = localStorage.getItem('skills:list_view_mode');
            return raw === 'grid' ? 'grid' : 'list';
        } catch {
            return 'list';
        }
    });

    const selectItem = useCallback((skill: Skill) => {
        setSelectedSkill(skill);
    }, []);

    const fetchSkills = useCallback(async () => {
        if (!username) return;

        try {
            await fetchItems(username);
            const fetchedSkills = useSkillStore.getState().items || [];
            logger.info(
                '[Skills][diag] store items after fetch:',
                fetchedSkills.map((skill) => `${skill.name}#${skill.id}`)
            );
            logger.info(
                '[Skills][diag] basic_chatter_xxx in store after fetch:',
                fetchedSkills.some((skill) => skill.name === 'basic_chatter_xxx')
            );
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

    useEffect(() => {
        logger.debug(
            '[Skills][diag] render skills:',
            (skills || []).map((skill) => `${skill.name}#${skill.id}`)
        );
        logger.debug(
            '[Skills][diag] basic_chatter_xxx in render skills:',
            (skills || []).some((skill) => skill.name === 'basic_chatter_xxx')
        );
    }, [skills]);

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

    const listTitle = (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <span style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px' }}>{t('pages.skills.title')}</span>
            <Space>
                <Tooltip title={t('pages.skills.viewList', 'List view')}>
                    <Button
                        type="text"
                        shape="circle"
                        icon={<UnorderedListOutlined />}
                        onClick={() => {
                            setViewMode('list');
                            try {
                                localStorage.setItem('skills:list_view_mode', 'list');
                            } catch {
                                // ignore
                            }
                        }}
                        style={{
                            background: viewMode === 'list' ? 'rgba(255, 255, 255, 0.06)' : 'transparent',
                            border: 'none',
                            color: 'rgba(203, 213, 225, 0.9)',
                            boxShadow: 'none'
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
                            try {
                                localStorage.setItem('skills:list_view_mode', 'grid');
                            } catch {
                                // ignore
                            }
                        }}
                        style={{
                            background: viewMode === 'grid' ? 'rgba(255, 255, 255, 0.06)' : 'transparent',
                            border: 'none',
                            color: 'rgba(203, 213, 225, 0.9)',
                            boxShadow: 'none'
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
                            boxShadow: 'none'
                        }}
                    />
                </Tooltip>
                {/* Add button removed - skills are created from skill_editor */}
            </Space>
        </div>
    );

    const handleSkillSave = () => {
        setIsAddingNew(false);
        handleRefresh();
    };

    const handleSkillCancel = () => {
        // Cancel process:
        // - If in new mode, close details panel
        // - If in edit mode, no extra processing needed (SkillDetails handles internally)
        if (isAddingNew) {
            setIsAddingNew(false);
            setSelectedSkill(null);
        }
        // In edit mode, SkillDetails will automatically restore data and exit edit mode, no need to close panel
    };

    const handleSkillDelete = () => {
        // After delete, clear selected status and close details page
        logger.info('[Skills] handleSkillDelete called, selectedSkill before:', selectedSkill ? `${selectedSkill.name}#${selectedSkill.id}` : null);
        setSelectedSkill(null);
        logger.info('[Skills] handleSkillDelete completed, selectedSkill after:', null);
    };

    const handleSelectedSkillChange = useCallback((updatedSkill: Skill) => {
        setSelectedSkill(updatedSkill);
    }, []);

    const handleSubscribe = async (skillId: string) => {
        if (!username) return;
        const api = get_ipc_api();
        const resp = await api.subscribeToSkill(username, skillId);
        if (!resp.success) throw new Error((resp.error as any)?.message || t('pages.skills.subscribeFailed', 'Subscribe failed'));
        // Also check the mutation result's success field
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
        // Also check the mutation result's success field
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
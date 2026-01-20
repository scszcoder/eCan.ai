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

    // 使用新的 skillStore
    const skills = useSkillStore((state) => state.items);
    const isLoading = useSkillStore((state) => state.loading);
    const fetchItems = useSkillStore((state) => state.fetchItems);
    const forceRefresh = useSkillStore((state) => state.forceRefresh);

    const username = useUserStore((state) => state.username);
    const [isAddingNew, setIsAddingNew] = React.useState(false);

    // 直接管理选中Status
    const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
    const [publicSkills, setPublicSkills] = useState<Skill[]>([]);

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
        } catch (error) {
            logger.error('[Skills] Error fetching skills:', error);
            message.error(t('pages.skills.fetchError') || 'Failed to fetch skills');
        }
    }, [username, fetchItems, t]);

    useEffect(() => {
        if (username) {
            fetchSkills();
        }
    }, [username, fetchSkills]);

    useEffect(() => {
        if (!username) return;
        let cancelled = false;

        (async () => {
            try {
                const resp = await get_ipc_api().getPublicSkills<{ skills?: Skill[] }>(username);
                if (!resp.success) return;
                const rows = (resp.data as any)?.skills;
                const next = Array.isArray(rows) ? rows : [];
                if (!cancelled) setPublicSkills(next);
            } catch (e) {
                // ignore - store is optional
            }
        })();

        return () => {
            cancelled = true;
        };
    }, [username]);

    const handleRefresh = useCallback(async () => {
        if (!username) return;

        try {
            await forceRefresh(username);
        } catch (error) {
            logger.error('[Skills] Error refreshing skills:', error);
            message.error(t('pages.skills.fetchError') || 'Failed to refresh skills');
        }
    }, [username, forceRefresh, t]);

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
        // Cancel时的Process：
        // - If是新建模式，CloseDetails面板
        // - If是Edit模式，不Need额外Process（SkillDetails Internal会Process）
        if (isAddingNew) {
            setIsAddingNew(false);
            setSelectedSkill(null);
        }
        // Edit模式下，SkillDetails 会自动RestoreData并退出Edit模式，不NeedClose面板
    };

    const handleSkillDelete = () => {
        // Delete后清空选中Status，CloseDetails页
        setSelectedSkill(null);
        handleRefresh();
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
                />
            }
            detailsContent={
                (selectedSkill || isAddingNew) ? (
                    <SkillDetails
                        skill={isAddingNew ? null : selectedSkill}
                        isNew={isAddingNew}
                        onRefresh={handleRefresh}
                        onSave={handleSkillSave}
                        onCancel={handleSkillCancel}
                        onDelete={handleSkillDelete}
                    />
                ) : undefined
            }
        />
    );
};

export default Skills;
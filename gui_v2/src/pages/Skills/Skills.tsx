import React, { useCallback, useEffect, useState } from 'react';
import { Button, Space, message } from 'antd';
import { ReloadOutlined, PlusOutlined } from '@ant-design/icons';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useTranslation } from 'react-i18next';
import { useSkillStore } from '../../stores';
import { useUserStore } from '../../stores/userStore';
import SkillList from './components/SkillList';
import SkillDetails from './components/SkillDetails';
import { IPCWCClient } from '@/services/ipc/ipcWCClient';
import { logger } from '@/utils/logger';
import type { Skill } from '@/stores';
import './Skills.css';

const Skills: React.FC = () => {
    const { t } = useTranslation();

    // 使用新的 skillStore
    const skills = useSkillStore((state) => state.items);
    const isLoading = useSkillStore((state) => state.loading);
    const fetchItems = useSkillStore((state) => state.fetchItems);
    const forceRefresh = useSkillStore((state) => state.forceRefresh);
    const updateItem = useSkillStore((state) => state.updateItem);

    const username = useUserStore((state) => state.username);
    const [isAddingNew, setIsAddingNew] = React.useState(false);

    // 直接管理选中状态
    const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);

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


    const handleRefresh = useCallback(async () => {
        if (!username) return;

        try {
            await forceRefresh(username);
        } catch (error) {
            logger.error('[Skills] Error refreshing skills:', error);
            message.error(t('pages.skills.fetchError') || 'Failed to refresh skills');
        }
    }, [username, forceRefresh, t]);

    const handleLevelUp = (id: number) => {
        const skill = skills.find(s => String(s.id) === String(id));
        if (skill && skill.level) {
            // 将 level 转换为数字进行比较
            const currentLevel = typeof skill.level === 'string' ? parseInt(skill.level, 10) : skill.level;
            if (currentLevel < 100) {
                const newLevel = Math.min(currentLevel + 5, 100);
                const updates = {
                    level: typeof skill.level === 'string' ? String(newLevel) : newLevel,
                    lastUsed: t('pages.skills.time.justNow'),
                    usageCount: (skill.usageCount || 0) + 1,
                };

                // 更新本地状态
                updateItem(String(id), updates as any);

                logger.info('[Skills] Level up skill:', id, updates);
            }
        }
    };

    const listTitle = (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{t('pages.skills.title')}</span>
            <Space>
                <Button
                    type="text"
                    icon={<ReloadOutlined style={{ color: 'white' }} />}
                    onClick={handleRefresh}
                    loading={isLoading}
                    title={t('pages.skills.refresh')}
                />
                <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={async () => {
                        // Scaffold a code-based skill on backend
                        const defaultName = `skill_${Date.now()}`;
                        try {
                            const resp: any = await IPCWCClient.getInstance().sendRequest('skills.scaffold', { name: defaultName, kind: 'code' });
                            if (resp?.status !== 'success') {
                                // eslint-disable-next-line no-console
                                console.warn('[Skills] scaffold code skill failed', resp);
                            }
                        } catch (e) {
                            // eslint-disable-next-line no-console
                            console.warn('[Skills] scaffold code skill exception', e);
                        }
                        setIsAddingNew(true);
                        // Refresh list to include the new scaffold
                        await fetchSkills();
                    }}
                    title={t('pages.skills.addSkill')}
                />
            </Space>
        </div>
    );

    const handleSkillSave = () => {
        setIsAddingNew(false);
        handleRefresh();
    };

    const handleSkillDelete = () => {
        // 删除后清空选中状态，关闭详情页
        setSelectedSkill(null);
        handleRefresh();
    };

    return (
        <DetailLayout
            listTitle={listTitle}
            detailsTitle={t('pages.skills.details')}
            listContent={
                <SkillList
                    skills={skills}
                    loading={isLoading}
                    onSelectSkill={selectItem}
                    selectedSkillId={selectedSkill ? String(selectedSkill.id) : undefined}
                />
            }
            detailsContent={
                (selectedSkill || isAddingNew) ? (
                    <SkillDetails
                        skill={isAddingNew ? null : selectedSkill}
                        isNew={isAddingNew}
                        onLevelUp={handleLevelUp}
                        onRefresh={handleRefresh}
                        onSave={handleSkillSave}
                        onCancel={() => setIsAddingNew(false)}
                        onDelete={handleSkillDelete}
                    />
                ) : undefined
            }
        />
    );
};

export default Skills;
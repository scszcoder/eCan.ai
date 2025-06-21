import React, { useCallback, useEffect } from 'react';
import { Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import { useTranslation } from 'react-i18next';
import { useAppDataStore } from '../../stores/appDataStore';
import { useUserStore } from '../../stores/userStore';
import { IPCAPI } from '@/services/ipc/api';
import { SkillsAPIResponseData } from './types';
import SkillList from './components/SkillList';
import SkillDetails from './components/SkillDetails';

const Skills: React.FC = () => {
    const { t } = useTranslation();
    
    const skills = useAppDataStore((state) => state.skills);
    const isLoading = useAppDataStore((state) => state.isLoading);
    const setLoading = useAppDataStore((state) => state.setLoading);
    const setError = useAppDataStore((state) => state.setError);
    const setSkills = useAppDataStore((state) => state.setSkills);
    
    const username = useUserStore((state) => state.username);

    const {
        selectedItem: selectedSkill,
        selectItem,
    } = useDetailView(skills);

    const fetchSkills = useCallback(async () => {
        if (!username) {
            console.error("Username is not available.");
            return;
        }

        try {
            setLoading(true);
            setError(null);
            const response = await IPCAPI.getInstance().getSkills(username, []);
            if (response && response.success && response.data) {
                const responseData = response.data as SkillsAPIResponseData;
                if (responseData.skills && Array.isArray(responseData.skills)) {
                    setSkills(responseData.skills);
                } else {
                    console.error("Fetched skills data is not in the expected format:", response.data);
                    setError("Fetched skills data is not in the expected format.");
                }
            } else {
                setError((response as any).message || 'Failed to fetch skills.');
            }
        } catch (error) {
            console.error('Error fetching skills:', error);
            setError((error as Error).message);
        } finally {
            setLoading(false);
        }
    }, [username, setLoading, setError, setSkills]);

    useEffect(() => {
        if (username) {
            fetchSkills();
        }
    }, [username, fetchSkills]);

    const handleRefresh = useCallback(async () => {
        await fetchSkills();
    }, [fetchSkills]);

    const handleLevelUp = (id: number) => {
        const skill = skills.find(s => s.id === id);
        if (skill && skill.level < 100) {
            const updatedSkill = {
                ...skill,
                level: Math.min(skill.level + 5, 100),
                lastUsed: t('pages.skills.time.justNow'),
                usageCount: skill.usageCount + 1,
            };
            const updatedSkills = skills.map(s => s.id === id ? updatedSkill : s);
            setSkills(updatedSkills);
        }
    };

    const listTitle = (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>{t('pages.skills.title')}</span>
            <Button
                type="text"
                icon={<ReloadOutlined style={{ color: 'white' }} />}
                onClick={handleRefresh}
                loading={isLoading}
                title={t('pages.skills.refresh')}
            />
        </div>
    );

    return (
        <DetailLayout
            listTitle={listTitle}
            detailsTitle={t('pages.skills.details')}
            listContent={
                <SkillList 
                    skills={skills} 
                    loading={isLoading} 
                    onSelectSkill={selectItem} 
                />
            }
            detailsContent={
                <SkillDetails 
                    skill={selectedSkill} 
                    onLevelUp={handleLevelUp}
                    onRefresh={handleRefresh}
                />
            }
        />
    );
};

export default Skills;
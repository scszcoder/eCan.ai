import React, { useEffect, useCallback } from 'react';
import VirtualPlatform from './VirtualPlatform';
import { useAppDataStore } from '../../stores/appDataStore';
import { useUserStore } from '../../stores/userStore';
import { Agent } from './types';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';
import { useTranslation } from 'react-i18next';

const Agents: React.FC = () => {
    const { t } = useTranslation();
    const setAgents = useAppDataStore((state) => state.setAgents);
    const setError = useAppDataStore((state) => state.setError);
    const username = useUserStore((state) => state.username);

    const fetchAgents = useCallback(async () => {
        if (!username) return;

        // 强制获取最新数据，在后台静默更新，不显示loading状态避免页面闪烁
        setError(null);
        try {
            const response = await get_ipc_api().getAgents<{ agents: Agent[] }>(username, []);
            console.log(t('pages.agents.fetched_agents') || 'Fetched agents:', response.data);
            if (response.success && response.data) {
                // 总是更新store中的agents数据，即使是空数组也更新
                setAgents(response.data.agents || []);
                logger.info(t('pages.agents.updated_data_from_api') || 'Updated agents data from API:', response.data.agents?.length || 0, t('common.agents') || 'agents');
            } else {
                logger.error(t('pages.agents.fetch_failed') || 'Failed to fetch agents:', response.error?.message);
                // 可以选择显示错误消息，但不影响页面显示
                // messageApi.error(`${t('common.failed')}: ${response.error?.message || 'Unknown error'}`);
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : t('common.unknown_error') || 'Unknown error';
            setError(errorMessage);
            logger.error(t('pages.agents.error_fetching') || 'Error fetching agents:', errorMessage);
            // 可以选择显示错误消息，但不影响页面显示
            // messageApi.error(`${t('common.failed')}: ${errorMessage}`);
        }
    }, [username, setError, setAgents, t]);

    useEffect(() => {
        fetchAgents();
    }, [fetchAgents]);

  return <VirtualPlatform />;
};

export default Agents;
import React, { useEffect, useCallback } from 'react';
import VirtualPlatform from './VirtualPlatform';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Spin, message, App } from 'antd';
import { useAgents } from './hooks/useAgents';
import { useAppDataStore } from '../../stores/appDataStore';
import { useUserStore } from '../../stores/userStore';
import { Agent } from './types';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';


const Agents: React.FC = () => {
  const { t } = useTranslation();
    const navigate = useNavigate();
    const { message: messageApi } = App.useApp();
    // const { selectedAgent, selectItem, isSelected } = useAgents();
    
    const agents = useAppDataStore((state) => state.agents);
    const isLoading = useAppDataStore((state) => state.isLoading);
    const setLoading = useAppDataStore((state) => state.setLoading);
    const setAgents = useAppDataStore((state) => state.setAgents);
    const setError = useAppDataStore((state) => state.setError);
    const username = useUserStore((state) => state.username);

    const fetchAgents = useCallback(async () => {
        if (!username) return;

        setLoading(true);
        setError(null);
        try {
            const response = await get_ipc_api().getAgents<{ agents: Agent[] }>(username, []);
            console.log('[Agents] Fetched agents:', response.data);
            if (response.success && response.data) {
                setAgents(response.data.agents);
                // messageApi.success(t('common.success'));
            } else {
                throw new Error(response.error?.message || 'Failed to fetch agents');
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            setError(errorMessage);
            messageApi.error(`${t('common.failed')}: ${errorMessage}`);
            logger.error('[Agents] Error fetching agents:', errorMessage);
        } finally {
            setLoading(false);
        }
    }, [username, setLoading, setError, setAgents, messageApi, t]);

    useEffect(() => {
        fetchAgents();
    }, [fetchAgents]);

  return <VirtualPlatform />;
};

export default Agents;
import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Spin, message, App } from 'antd';
import DetailLayout from '../../components/Layout/DetailLayout';
import ActionButtons from '../../components/Common/ActionButtons';
import { useAgents } from './hooks/useAgents';
import { AgentList } from './components/AgentList';
import { AgentDetail } from './components/AgentDetail';
import { useSystemStore } from '../../stores/systemStore';
import { useUserStore } from '../../stores/userStore';
import { IPCAPI } from '../../services/ipc/api';
import { Agent } from './types';

const Agents: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { message: messageApi } = App.useApp();
    const { selectedAgent, selectItem, isSelected } = useAgents();
    
    const agents = useSystemStore((state) => state.agents);
    const isLoading = useSystemStore((state) => state.isLoading);
    const setLoading = useSystemStore((state) => state.setLoading);
    const setAgents = useSystemStore((state) => state.setAgents);
    const setError = useSystemStore((state) => state.setError);
    const username = useUserStore((state) => state.username);

    const handleAddAgent = () => {
        navigate('/agents/new');
    };

    const handleRefresh = async () => {
        if (!username) return;
        
        setLoading(true);
        setError(null);
        try {
            const response = await IPCAPI.getInstance().getAgents(username, []);
            if (response.success && response.data) {
                setAgents(response.data.agents as Agent[]);
                messageApi.success(t('common.refreshSuccess'));
            } else {
                throw new Error(response.error?.message || 'Failed to fetch agents');
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            setError(errorMessage);
            messageApi.error(`${t('common.refreshFailed')}: ${errorMessage}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <DetailLayout
            listTitle={t('pages.agents.title')}
            detailsTitle={t('pages.agents.details')}
            listContent={
                <>
                    <ActionButtons
                        onAdd={handleAddAgent}
                        onRefresh={handleRefresh}
                        addText={t('pages.agents.addAgent')}
                        refreshText={t('common.refresh')}
                        visibleButtons={['add', 'refresh']}
                    />
                    <Spin spinning={isLoading}>
                        <AgentList
                            agents={Array.isArray(agents) ? agents : []}
                            onSelectAgent={selectItem}
                            isSelected={isSelected}
                        />
                    </Spin>
                </>
            }
            detailsContent={
                <AgentDetail agent={selectedAgent} />
            }
        />
    );
};

export default Agents;
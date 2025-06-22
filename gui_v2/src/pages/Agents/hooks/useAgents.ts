import { useEffect } from 'react';
import { useDetailView } from '@/hooks/useDetailView';
import { useAppDataStore } from '@/stores/appDataStore';
import { Agent } from '../types';

export const useAgents = () => {
    const storeAgents = useAppDataStore((state) => state.agents);

    const {
        items: agents,
        setItems,
        selectedItem: selectedAgent,
        selectItem,
        isSelected,
    } = useDetailView<Agent>([], (agent) => agent.card.id);

    useEffect(() => {
        if (Array.isArray(storeAgents)) {
            setItems(storeAgents);
        }
    }, [storeAgents, setItems]);

    return {
        agents,
        selectedAgent,
        selectItem,
        isSelected,
    };
}; 
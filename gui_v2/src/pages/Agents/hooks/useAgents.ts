import { useEffect } from 'react';
import { useDetailView } from '@/hooks/useDetailView';
import { useSystemStore } from '@/stores/systemStore';
import { Agent } from '../types';

export const useAgents = () => {
    const storeAgents = useSystemStore((state) => state.agents);

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
import { useDetailView } from '../../../hooks/useDetailView';
import { Agent } from '../types';

export const useAgents = () => {
    const {
        selectedItem: selectedAgent,
        selectItem: selectAgent,
        unselectItem,
        isSelected,
    } = useDetailView<Agent>((agent) => agent.card.id);

    return {
        selectedAgent,
        selectAgent,
        unselectItem,
        isSelected,
    };
}; 
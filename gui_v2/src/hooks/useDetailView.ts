import { useState } from 'react';

interface DetailViewState<T> {
    selectedItem: T | null;
    items: T[];
}

export function useDetailView<T>(initialItems: T[]) {
    const [state, setState] = useState<DetailViewState<T>>({
        selectedItem: null,
        items: initialItems,
    });

    const selectItem = (item: T) => {
        setState(prev => ({
            ...prev,
            selectedItem: item,
        }));
    };

    const updateItems = (items: T[]) => {
        setState(prev => ({
            ...prev,
            items: Array.isArray(items) ? items : [],
        }));
    };

    const addItem = (item: T) => {
        setState(prev => ({
            ...prev,
            items: [...prev.items, item],
        }));
    };

    const removeItem = (id: number) => {
        setState(prev => ({
            ...prev,
            items: prev.items.filter((item: any) => item.id !== id),
            selectedItem: prev.selectedItem && (prev.selectedItem as any).id === id ? null : prev.selectedItem,
        }));
    };

    const updateItem = (id: number, updatedItem: Partial<T>) => {
        setState(prev => ({
            ...prev,
            items: prev.items.map((item: any) => 
                item.id === id ? { ...item, ...updatedItem } : item
            ),
            selectedItem: prev.selectedItem && (prev.selectedItem as any).id === id 
                ? { ...prev.selectedItem, ...updatedItem }
                : prev.selectedItem,
        }));
    };

    return {
        selectedItem: state.selectedItem,
        items: state.items,
        selectItem,
        updateItems,
        addItem,
        removeItem,
        updateItem,
    };
} 
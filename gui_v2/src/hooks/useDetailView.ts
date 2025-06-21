import { useState, useCallback } from 'react';

interface DetailViewState<T> {
    selectedItem: T | null;
}

export function useDetailView<T>(
    getKey: (item: T) => string | number = (item: any) => item.id
) {
    const [selectedItem, setSelectedItem] = useState<T | null>(null);

    const selectItem = useCallback((item: T) => {
        setSelectedItem(item);
    }, []);

    const unselectItem = useCallback(() => {
        setSelectedItem(null);
    }, []);

    const isSelected = useCallback((item: T) => {
        return selectedItem ? getKey(selectedItem) === getKey(item) : false;
    }, [selectedItem, getKey]);

    return {
        selectedItem,
        selectItem,
        unselectItem,
        isSelected,
    };
} 
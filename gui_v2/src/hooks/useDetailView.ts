import { useState, useCallback } from 'react';

export function useDetailView<T>(
    initialItems: T[],
    getKey: (item: T) => string | number = (item: any) => item.id
) {
    const [items, setItems] = useState<T[]>(initialItems);
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

    const addItem = useCallback(
        (item: T) => {
            setItems((prevItems) => [...prevItems, item]);
        },
        [setItems],
    );

    const removeItem = useCallback(
        (key: string | number) => {
            setItems((prevItems) => prevItems.filter((item) => getKey(item) !== key));
        },
        [getKey, setItems],
    );

    const updateItem = useCallback(
        (key: string | number, updates: Partial<T>) => {
            setItems((prevItems) =>
                prevItems.map((item) => (getKey(item) === key ? { ...item, ...updates } : item)),
            );
        },
        [getKey, setItems],
    );

    return {
        items,
        setItems,
        selectedItem,
        selectItem,
        unselectItem,
        isSelected,
        addItem,
        removeItem,
        updateItem,
    };
} 
/**
 * PageStatus管理 Store
 * 
 * Used forSave和RestorePageStatus，替代 KeepAlive 方案
 * Support：ScrollPosition、Search文本、选中项、CustomStatus
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface PageState {
    // ScrollPosition { pagePath: scrollPosition }
    scrollPositions: Record<string, number>;
    // Search关键词 { pagePath: searchText }
    searchTexts: Record<string, string>;
    // 选中项 { pagePath: selectedIds[] }
    selectedItems: Record<string, string[]>;
    // CustomStatus { pagePath: { key: value } }
    customStates: Record<string, Record<string, any>>;
}

interface PageStateStore extends PageState {
    // ScrollPosition管理
    saveScrollPosition: (page: string, position: number) => void;
    getScrollPosition: (page: string) => number;
    
    // Search文本管理
    saveSearchText: (page: string, text: string) => void;
    getSearchText: (page: string) => string;
    
    // 选中项管理
    saveSelectedItems: (page: string, items: string[]) => void;
    getSelectedItems: (page: string) => string[];
    
    // CustomStatus管理
    saveCustomState: (page: string, key: string, value: any) => void;
    getCustomState: (page: string, key: string) => any;
    
    // 清除Operation
    clearPageState: (page: string) => void;
    clearAllStates: () => void;
}

export const usePageStateStore = create<PageStateStore>()(
    persist(
        (set, get) => ({
            // 初始Status
            scrollPositions: {},
            searchTexts: {},
            selectedItems: {},
            customStates: {},
            
            // ScrollPosition
            saveScrollPosition: (page, position) => {
                console.log(`[Store] SaveScrollPosition - Page: ${page}, Position: ${position}`);
                set((state) => {
                    const newState = { ...state.scrollPositions, [page]: position };
                    console.log(`[Store] 新的 scrollPositions:`, newState);
                    return { scrollPositions: newState };
                });
            },
            
            getScrollPosition: (page) => {
                const position = get().scrollPositions[page] || 0;
                console.log(`[Store] GetScrollPosition - Page: ${page}, Position: ${position}`);
                return position;
            },
            
            // Search文本
            saveSearchText: (page, text) =>
                set((state) => ({
                    searchTexts: { ...state.searchTexts, [page]: text }
                })),
            
            getSearchText: (page) => get().searchTexts[page] || '',
            
            // 选中项
            saveSelectedItems: (page, items) =>
                set((state) => ({
                    selectedItems: { ...state.selectedItems, [page]: items }
                })),
            
            getSelectedItems: (page) => get().selectedItems[page] || [],
            
            // CustomStatus
            saveCustomState: (page, key, value) =>
                set((state) => ({
                    customStates: {
                        ...state.customStates,
                        [page]: { ...(state.customStates[page] || {}), [key]: value }
                    }
                })),
            
            getCustomState: (page, key) => get().customStates[page]?.[key],
            
            // 清除单个PageStatus
            clearPageState: (page) =>
                set((state) => {
                    const { [page]: _, ...restScroll } = state.scrollPositions;
                    const { [page]: __, ...restSearch } = state.searchTexts;
                    const { [page]: ___, ...restSelected } = state.selectedItems;
                    const { [page]: ____, ...restCustom } = state.customStates;
                    return {
                        scrollPositions: restScroll,
                        searchTexts: restSearch,
                        selectedItems: restSelected,
                        customStates: restCustom
                    };
                }),
            
            // 清除AllStatus
            clearAllStates: () =>
                set({
                    scrollPositions: {},
                    searchTexts: {},
                    selectedItems: {},
                    customStates: {}
                })
        }),
        {
            name: 'page-state-storage',
            // 显式使用 localStorage
            storage: createJSONStorage(() => localStorage),
            // 只持久化部分Status到 localStorage
            partialize: (state) => ({
                scrollPositions: state.scrollPositions,
                searchTexts: state.searchTexts,
                selectedItems: state.selectedItems
                // customStates 不持久化，仅会话期间有效
            })
        }
    )
);

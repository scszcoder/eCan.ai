/**
 * 页面状态管理 Store
 * 
 * 用于保存和恢复页面状态，替代 KeepAlive 方案
 * 支持：滚动位置、搜索文本、选中项、自定义状态
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface PageState {
    // 滚动位置 { pagePath: scrollPosition }
    scrollPositions: Record<string, number>;
    // 搜索关键词 { pagePath: searchText }
    searchTexts: Record<string, string>;
    // 选中项 { pagePath: selectedIds[] }
    selectedItems: Record<string, string[]>;
    // 自定义状态 { pagePath: { key: value } }
    customStates: Record<string, Record<string, any>>;
}

interface PageStateStore extends PageState {
    // 滚动位置管理
    saveScrollPosition: (page: string, position: number) => void;
    getScrollPosition: (page: string) => number;
    
    // 搜索文本管理
    saveSearchText: (page: string, text: string) => void;
    getSearchText: (page: string) => string;
    
    // 选中项管理
    saveSelectedItems: (page: string, items: string[]) => void;
    getSelectedItems: (page: string) => string[];
    
    // 自定义状态管理
    saveCustomState: (page: string, key: string, value: any) => void;
    getCustomState: (page: string, key: string) => any;
    
    // 清除操作
    clearPageState: (page: string) => void;
    clearAllStates: () => void;
}

export const usePageStateStore = create<PageStateStore>()(
    persist(
        (set, get) => ({
            // 初始状态
            scrollPositions: {},
            searchTexts: {},
            selectedItems: {},
            customStates: {},
            
            // 滚动位置
            saveScrollPosition: (page, position) => {
                console.log(`[Store] 保存滚动位置 - 页面: ${page}, 位置: ${position}`);
                set((state) => {
                    const newState = { ...state.scrollPositions, [page]: position };
                    console.log(`[Store] 新的 scrollPositions:`, newState);
                    return { scrollPositions: newState };
                });
            },
            
            getScrollPosition: (page) => {
                const position = get().scrollPositions[page] || 0;
                console.log(`[Store] 获取滚动位置 - 页面: ${page}, 位置: ${position}`);
                return position;
            },
            
            // 搜索文本
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
            
            // 自定义状态
            saveCustomState: (page, key, value) =>
                set((state) => ({
                    customStates: {
                        ...state.customStates,
                        [page]: { ...(state.customStates[page] || {}), [key]: value }
                    }
                })),
            
            getCustomState: (page, key) => get().customStates[page]?.[key],
            
            // 清除单个页面状态
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
            
            // 清除所有状态
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
            // 只持久化部分状态到 localStorage
            partialize: (state) => ({
                scrollPositions: state.scrollPositions,
                searchTexts: state.searchTexts,
                selectedItems: state.selectedItems
                // customStates 不持久化，仅会话期间有效
            })
        }
    )
);

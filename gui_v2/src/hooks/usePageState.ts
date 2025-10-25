/**
 * 页面状态管理 Hooks
 * 
 * 提供便捷的 Hooks 来自动保存和恢复页面状态
 */

import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { usePageStateStore } from '../stores/pageStateStore';

/**
 * 自动保存和恢复滚动位置
 * 
 * @param containerRef 可选的滚动容器引用，默认为 window
 * @returns void
 * 
 * @example
 * const containerRef = useRef<HTMLDivElement>(null);
 * useScrollPosition(containerRef);
 */
export const useScrollPosition = (containerRef?: React.RefObject<HTMLElement>) => {
    const location = useLocation();
    const pageName = location.pathname;
    const { saveScrollPosition, getScrollPosition } = usePageStateStore();
    
    // 恢复滚动位置
    useEffect(() => {
        const savedPosition = getScrollPosition(pageName);
        const container = containerRef?.current || window;
        
        console.log(`[useScrollPosition] 恢复滚动位置 - 页面: ${pageName}, 位置: ${savedPosition}`);
        
        if (savedPosition > 0) {
            // 延迟恢复，确保内容已渲染
            const timer = setTimeout(() => {
                if (container === window) {
                    window.scrollTo(0, savedPosition);
                    console.log(`[useScrollPosition] ✅ 已恢复到位置: ${savedPosition}`);
                } else {
                    (container as HTMLElement).scrollTop = savedPosition;
                    console.log(`[useScrollPosition] ✅ 已恢复容器滚动到位置: ${savedPosition}`);
                }
            }, 100);
            
            return () => clearTimeout(timer);
        }
    }, [pageName, containerRef, getScrollPosition]);
    
    // 保存滚动位置
    useEffect(() => {
        const container = containerRef?.current || window;
        
        const handleScroll = () => {
            const position = container === window 
                ? window.scrollY 
                : (container as HTMLElement).scrollTop;
            console.log(`[useScrollPosition] 保存滚动位置 - 页面: ${pageName}, 位置: ${position}`);
            saveScrollPosition(pageName, position);
        };
        
        if (container === window) {
            window.addEventListener('scroll', handleScroll, { passive: true });
            return () => window.removeEventListener('scroll', handleScroll);
        } else {
            container.addEventListener('scroll', handleScroll, { passive: true });
            return () => container.removeEventListener('scroll', handleScroll);
        }
    }, [pageName, containerRef, saveScrollPosition]);
};

/**
 * 自动保存和恢复搜索文本
 * 
 * @param initialValue 初始值
 * @returns [text, setText] 类似 useState 的返回值
 * 
 * @example
 * const [searchText, setSearchText] = useSearchText();
 */
export const useSearchText = (initialValue = '') => {
    const location = useLocation();
    const pageName = location.pathname;
    const { saveSearchText, getSearchText } = usePageStateStore();
    
    const [text, setText] = useState(() => getSearchText(pageName) || initialValue);
    
    useEffect(() => {
        saveSearchText(pageName, text);
    }, [text, pageName, saveSearchText]);
    
    return [text, setText] as const;
};

/**
 * 自动保存和恢复选中项
 * 
 * @param initialValue 初始值
 * @returns [items, setItems] 类似 useState 的返回值
 * 
 * @example
 * const [selectedIds, setSelectedIds] = useSelectedItems();
 */
export const useSelectedItems = (initialValue: string[] = []) => {
    const location = useLocation();
    const pageName = location.pathname;
    const { saveSelectedItems, getSelectedItems } = usePageStateStore();
    
    const [items, setItems] = useState(() => getSelectedItems(pageName) || initialValue);
    
    useEffect(() => {
        saveSelectedItems(pageName, items);
    }, [items, pageName, saveSelectedItems]);
    
    return [items, setItems] as const;
};

/**
 * 通用的页面状态管理
 * 
 * @param key 状态键名
 * @param initialValue 初始值
 * @returns [state, setState] 类似 useState 的返回值
 * 
 * @example
 * const [filterOptions, setFilterOptions] = usePageCustomState('filters', { status: 'all' });
 */
export const usePageCustomState = <T,>(key: string, initialValue: T) => {
    const location = useLocation();
    const pageName = location.pathname;
    const { saveCustomState, getCustomState } = usePageStateStore();
    
    const [state, setState] = useState<T>(() => {
        const saved = getCustomState(pageName, key);
        return saved !== undefined ? saved : initialValue;
    });
    
    useEffect(() => {
        saveCustomState(pageName, key, state);
    }, [state, pageName, key, saveCustomState]);
    
    return [state, setState] as const;
};

/**
 * 清除当前页面的所有状态
 * 
 * @example
 * const clearState = useClearPageState();
 * // 在某个操作后清除状态
 * clearState();
 */
export const useClearPageState = () => {
    const location = useLocation();
    const pageName = location.pathname;
    const { clearPageState } = usePageStateStore();
    
    return () => clearPageState(pageName);
};

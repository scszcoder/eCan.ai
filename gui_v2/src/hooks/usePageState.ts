/**
 * PageStatus管理 Hooks
 * 
 * 提供便捷的 Hooks 来自动Save和RestorePageStatus
 */

import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { usePageStateStore } from '../stores/pageStateStore';

/**
 * 自动Save和RestoreScrollPosition
 * 
 * @param containerRef Optional的ScrollContainerReference，Default为 window
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
    
    // RestoreScrollPosition
    useEffect(() => {
        const savedPosition = getScrollPosition(pageName);
        const container = containerRef?.current || window;
        
        console.log(`[useScrollPosition] RestoreScrollPosition - Page: ${pageName}, Position: ${savedPosition}`);
        
        if (savedPosition > 0) {
            // DelayRestore，确保Content已Render
            const timer = setTimeout(() => {
                if (container === window) {
                    window.scrollTo(0, savedPosition);
                    console.log(`[useScrollPosition] ✅ 已Restore到Position: ${savedPosition}`);
                } else {
                    (container as HTMLElement).scrollTop = savedPosition;
                    console.log(`[useScrollPosition] ✅ 已RestoreContainerScroll到Position: ${savedPosition}`);
                }
            }, 100);
            
            return () => clearTimeout(timer);
        }
    }, [pageName, containerRef, getScrollPosition]);
    
    // SaveScrollPosition
    useEffect(() => {
        const container = containerRef?.current || window;
        
        const handleScroll = () => {
            const position = container === window 
                ? window.scrollY 
                : (container as HTMLElement).scrollTop;
            console.log(`[useScrollPosition] SaveScrollPosition - Page: ${pageName}, Position: ${position}`);
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
 * 自动Save和RestoreSearch文本
 * 
 * @param initialValue 初始Value
 * @returns [text, setText] 类似 useState 的Return value
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
 * 自动Save和Restore选中项
 * 
 * @param initialValue 初始Value
 * @returns [items, setItems] 类似 useState 的Return value
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
 * General的PageStatus管理
 * 
 * @param key Status键名
 * @param initialValue 初始Value
 * @returns [state, setState] 类似 useState 的Return value
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
 * 清除When前Page的AllStatus
 * 
 * @example
 * const clearState = useClearPageState();
 * // 在某个Operation后清除Status
 * clearState();
 */
export const useClearPageState = () => {
    const location = useLocation();
    const pageName = location.pathname;
    const { clearPageState } = usePageStateStore();
    
    return () => clearPageState(pageName);
};

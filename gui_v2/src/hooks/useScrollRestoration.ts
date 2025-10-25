import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * 通用的滚动位置保存和恢复 Hook
 * 
 * 使用场景：
 * - 详情页：从列表进入详情，返回时恢复滚动位置
 * - 列表页：在 KeepAlive 场景下自动保持滚动位置
 * 
 * @param containerRef - 滚动容器的 ref
 * @param enabled - 是否启用滚动恢复（默认 true）
 */
export function useScrollRestoration(
  containerRef: React.RefObject<HTMLElement>,
  enabled: boolean = true
) {
  const location = useLocation();
  const savedScrollPosition = useRef<number>(0);
  const isFirstMount = useRef(true);

  // 保存滚动位置
  useEffect(() => {
    if (!enabled) return;
    
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      savedScrollPosition.current = container.scrollTop;
    };

    // 使用防抖，避免频繁更新
    let scrollTimeout: NodeJS.Timeout;
    const debouncedHandleScroll = () => {
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(handleScroll, 100);
    };

    container.addEventListener('scroll', debouncedHandleScroll);
    
    return () => {
      container.removeEventListener('scroll', debouncedHandleScroll);
      clearTimeout(scrollTimeout);
    };
  }, [containerRef, enabled]);

  // 恢复滚动位置（仅在组件首次挂载时）
  useEffect(() => {
    if (!enabled) return;
    
    const container = containerRef.current;
    if (!container) return;

    // 只在首次挂载时恢复滚动位置
    if (isFirstMount.current && savedScrollPosition.current > 0) {
      requestAnimationFrame(() => {
        container.scrollTop = savedScrollPosition.current;
      });
      isFirstMount.current = false;
    }
  }, [containerRef, enabled, location.pathname]);

  // 提供手动重置滚动位置的方法
  const resetScroll = () => {
    const container = containerRef.current;
    if (container) {
      container.scrollTop = 0;
      savedScrollPosition.current = 0;
    }
  };

  return { resetScroll };
}

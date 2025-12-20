import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * General的ScrollPositionSave和Restore Hook
 * 
 * 使用场景：
 * - Details页：从List进入Details，返回时RestoreScrollPosition
 * - List页：在 KeepAlive 场景下自动保持ScrollPosition
 * 
 * @param containerRef - ScrollContainer的 ref
 * @param enabled - 是否EnabledScrollRestore（Default true）
 */
export function useScrollRestoration(
  containerRef: React.RefObject<HTMLElement>,
  enabled: boolean = true
) {
  const location = useLocation();
  const savedScrollPosition = useRef<number>(0);
  const isFirstMount = useRef(true);

  // SaveScrollPosition
  useEffect(() => {
    if (!enabled) return;
    
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      savedScrollPosition.current = container.scrollTop;
    };

    // 使用防抖，避免频繁Update
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

  // RestoreScrollPosition（仅在Component首次Mount时）
  useEffect(() => {
    if (!enabled) return;
    
    const container = containerRef.current;
    if (!container) return;

    // 只在首次Mount时RestoreScrollPosition
    if (isFirstMount.current && savedScrollPosition.current > 0) {
      requestAnimationFrame(() => {
        container.scrollTop = savedScrollPosition.current;
      });
      isFirstMount.current = false;
    }
  }, [containerRef, enabled, location.pathname]);

  // 提供手动ResetScrollPosition的Method
  const resetScroll = () => {
    const container = containerRef.current;
    if (container) {
      container.scrollTop = 0;
      savedScrollPosition.current = 0;
    }
  };

  return { resetScroll };
}

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { List, Card, Skeleton } from 'antd';

interface VirtualListProps<T> {
  data: T[];
  height: number;
  itemHeight: number;
  renderItem: (item: T, index: number) => React.ReactNode;
  loading?: boolean;
}

const VirtualList = <T extends any>({
  data,
  height,
  itemHeight,
  renderItem,
  loading = false
}: VirtualListProps<T>) => {
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(height);
  const containerRef = useRef<HTMLDivElement>(null);

  // 计算可见区域的项目
  const visibleCount = Math.ceil(containerHeight / itemHeight);
  const startIndex = Math.floor(scrollTop / itemHeight);
  const endIndex = Math.min(startIndex + visibleCount + 1, data.length);

  // 可见的项目
  const visibleItems = data.slice(startIndex, endIndex);

  // 计算偏移量
  const offsetY = startIndex * itemHeight;

  // 处理滚动事件
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  // 监听容器大小变化
  useEffect(() => {
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height);
      }
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  // 滚动到指定项目
  const scrollToItem = useCallback((index: number) => {
    if (containerRef.current) {
      const scrollTop = index * itemHeight;
      containerRef.current.scrollTop = scrollTop;
    }
  }, [itemHeight]);

  // 滚动到顶部
  const scrollToTop = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, []);

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        height: containerHeight,
        overflow: 'auto',
        position: 'relative',
      }}
      onScroll={handleScroll}
    >
      {/* 占位符，用于保持正确的滚动高度 */}
      <div style={{ height: data.length * itemHeight }}>
        {/* 可见项目容器 */}
        <div
          style={{
            position: 'absolute',
            top: offsetY,
            left: 0,
            right: 0,
          }}
        >
          {loading ? (
            // 加载状态
            Array.from({ length: visibleCount }).map((_, index) => (
              <div key={`skeleton-${index}`} style={{ height: itemHeight, padding: 8 }}>
                <Skeleton active paragraph={{ rows: 2 }} />
              </div>
            ))
          ) : (
            // 实际内容
            visibleItems.map((item, index) => (
              <div key={`item-${startIndex + index}`} style={{ height: itemHeight }}>
                {renderItem(item, startIndex + index)}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default VirtualList; 
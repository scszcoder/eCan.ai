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

  // ProcessScrollEvent
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  // ListenContainerSize变化
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

  // Scroll到指定项目
  const scrollToItem = useCallback((index: number) => {
    if (containerRef.current) {
      const scrollTop = index * itemHeight;
      containerRef.current.scrollTop = scrollTop;
    }
  }, [itemHeight]);

  // Scroll到Top
  const scrollToTop = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, []);

  // Scroll到Bottom
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
        overflowX: 'hidden',
        overflowY: 'auto',
        position: 'relative',
      }}
      onScroll={handleScroll}
    >
      {/* 占位符，Used for保持正确的ScrollHeight */}
      <div style={{ height: data.length * itemHeight }}>
        {/* 可见项目Container */}
        <div
          style={{
            position: 'absolute',
            top: offsetY,
            left: 0,
            right: 0,
          }}
        >
          {loading ? (
            // LoadStatus
            Array.from({ length: visibleCount }).map((_, index) => (
              <div key={`skeleton-${index}`} style={{ height: itemHeight, padding: 8 }}>
                <Skeleton active paragraph={{ rows: 2 }} />
              </div>
            ))
          ) : (
            // 实际Content
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
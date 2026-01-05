/**
 * ResizableDivider - Draggable divider for resizing panels
 */

import React, { useCallback, useRef, useEffect } from 'react';
import styled from 'styled-components';

interface ResizableDividerProps {
  onResize: (delta: number) => void;
  isVisible: boolean;
}

const DividerContainer = styled.div<{ $visible: boolean }>`
  width: 6px;
  height: 100%;
  background: transparent;
  cursor: col-resize;
  position: relative;
  flex-shrink: 0;
  display: ${props => props.$visible ? 'block' : 'none'};
  
  &::before {
    content: '';
    position: absolute;
    left: 2px;
    top: 0;
    bottom: 0;
    width: 2px;
    background: rgba(148, 163, 184, 0.2);
    transition: background 0.2s ease;
  }
  
  &:hover::before,
  &:active::before {
    background: #3b82f6;
  }
`;

const DividerHandle = styled.div`
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 4px;
  height: 40px;
  border-radius: 2px;
  background: rgba(148, 163, 184, 0.3);
  opacity: 0;
  transition: opacity 0.2s ease;
  
  ${DividerContainer}:hover & {
    opacity: 1;
  }
`;

export const ResizableDivider: React.FC<ResizableDividerProps> = ({
  onResize,
  isVisible,
}) => {
  const isDragging = useRef(false);
  const startX = useRef(0);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    startX.current = e.clientX;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      
      const delta = e.clientX - startX.current;
      startX.current = e.clientX;
      onResize(delta);
    };

    const handleMouseUp = () => {
      if (isDragging.current) {
        isDragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [onResize]);

  return (
    <DividerContainer $visible={isVisible} onMouseDown={handleMouseDown}>
      <DividerHandle />
    </DividerContainer>
  );
};

export default ResizableDivider;

import React from 'react';
import { IconButton, Tooltip } from '@douyinfe/semi-ui';
import { IconChevronLeft, IconChevronRight, IconClose, IconPlus } from '@douyinfe/semi-icons';
import styled from 'styled-components';
import { useSheetsStore } from '../../stores/sheets-store';

const Bar = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 12px;
  background: #0f172a;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
`;

const ScrollArea = styled.div`
  position: relative;
  display: flex;
  align-items: center;
  overflow: hidden;
  flex: 1 1 auto;
  height: 36px;
`;

const TabsRow = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  height: 100%;
`;

const Tab = styled.div.withConfig({
  shouldForwardProp: (prop) => prop !== 'active',
})<{ active?: boolean }>`
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 200px;
  min-width: 80px;
  height: 32px;
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
  border-radius: 6px 6px 0 0;
  padding: 6px 12px;
  font-size: 13px;
  font-weight: ${(p) => (p.active ? '600' : '500')};
  color: ${(p) => (p.active ? '#ffffff' : 'rgba(255, 255, 255, 0.6)')};
  background: ${(p) => (p.active 
    ? '#1e293b' 
    : 'transparent')};
  border: 1px solid ${(p) => (p.active 
    ? 'rgba(255, 255, 255, 0.08)' 
    : 'transparent')};
  border-bottom: ${(p) => (p.active 
    ? '3px solid #3b82f6' 
    : 'none')};
  cursor: pointer;
  user-select: none;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  
  &:hover {
    background: ${(p) => (p.active 
      ? '#1e293b' 
      : 'rgba(59, 130, 246, 0.12)')};
    color: ${(p) => (p.active ? '#ffffff' : 'rgba(255, 255, 255, 0.85)')};
    transform: ${(p) => (p.active ? 'none' : 'translateY(-1px)')};
  }
  
  &:active {
    transform: translateY(0);
  }
  
  /* Active tab shadow */
  ${(p) => p.active && `
    box-shadow: 0 -1px 4px rgba(0, 0, 0, 0.2),
                0 2px 8px rgba(0, 0, 0, 0.15);
    z-index: 1;
  `}
`;

const TabLabel = styled.span`
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.2s ease;
`;

const TabCloseButton = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.5);
  transition: all 0.2s ease;
  
  &:hover {
    color: rgba(255, 255, 255, 0.9);
    background: rgba(255, 255, 255, 0.1);
    transform: scale(1.1);
  }
  
  &:active {
    background: rgba(255, 255, 255, 0.15);
    transform: scale(0.95);
  }
  
  .semi-icon {
    font-size: 12px;
  }
`;

const TabInput = styled.input`
  flex: 1;
  background: #3d4a5d;
  border: 1px solid #4d53e8;
  border-radius: 4px;
  color: #ffffff;
  padding: 2px 6px;
  font-size: 13px;
  outline: none;
  transition: all 0.2s ease;
  
  &:focus {
    box-shadow: 0 0 0 2px rgba(77, 83, 232, 0.3);
    background: #2d3a4d;
  }
`;

export const SheetsTabBar: React.FC = () => {
  const sheets = useSheetsStore((s) => s.sheets);
  const openTabs = useSheetsStore((s) => s.openTabs);
  const activeId = useSheetsStore((s) => s.activeSheetId);
  const setActive = useSheetsStore((s) => s.setActiveSheet);
  const closeSheet = useSheetsStore((s) => s.closeSheet);
  const newSheet = useSheetsStore((s) => s.newSheet);
  const openSheet = useSheetsStore((s) => s.openSheet);
  const reorderTabs = useSheetsStore((s) => s.reorderTabs);
  const renameSheet = useSheetsStore((s) => s.renameSheet);

  const [offset, setOffset] = React.useState(0);
  const tabsRef = React.useRef<HTMLDivElement>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const scrollLeft = () => setOffset((o) => Math.min(o + 160, 0));
  const scrollRight = () => {
    const row = tabsRef.current;
    if (!row) return;
    const totalWidth = Array.from(row.children).reduce((acc, el) => acc + (el as HTMLElement).offsetWidth + 6, 0);
    const viewport = row.parentElement?.clientWidth ?? 0;
    const maxLeft = -(Math.max(0, totalWidth - viewport));
    setOffset((o) => Math.max(o - 160, maxLeft));
  };

  const handleNew = () => {
    const name = prompt('New sheet name?') || undefined;
    const id = newSheet(name, null);
    openSheet(id);
  };

  // DnD handlers
  const dragOverIndex = React.useRef<number | null>(null);
  const [hoverIndex, setHoverIndex] = React.useState<number | null>(null);

  const onDragStart = (e: React.DragEvent, id: string) => {
    e.dataTransfer.setData('text/tab-id', id);
    e.dataTransfer.effectAllowed = 'move';
  };
  const computeMaxLeft = () => {
    const row = tabsRef.current;
    const viewport = scrollRef.current?.clientWidth ?? 0;
    if (!row) return 0;
    const totalWidth = Array.from(row.children).reduce((acc, el) => acc + (el as HTMLElement).offsetWidth + 6, 0);
    return -(Math.max(0, totalWidth - viewport));
  };

  const onDragOver = (e: React.DragEvent, overIndex: number) => {
    e.preventDefault();
    dragOverIndex.current = overIndex;
    setHoverIndex(overIndex);
    // Edge autoscroll when dragging near edges of the scroll area
    const area = scrollRef.current;
    if (area) {
      const rect = area.getBoundingClientRect();
      const edge = 30; // px from edge to trigger scroll
      const maxLeft = computeMaxLeft();
      if (e.clientX < rect.left + edge) {
        setOffset((o) => Math.min(o + 20, 0));
      } else if (e.clientX > rect.right - edge) {
        setOffset((o) => Math.max(o - 20, maxLeft));
      }
    }
  };
  const onDragLeave = () => {
    dragOverIndex.current = null;
    setHoverIndex(null);
  };
  const onDrop = (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    const id = e.dataTransfer.getData('text/tab-id');
    const currentOrder = [...openTabs];
    const from = currentOrder.indexOf(id);
    if (from === -1) return;
    const item = currentOrder.splice(from, 1)[0];
    currentOrder.splice(dropIndex, 0, item);
    reorderTabs(currentOrder);
    setHoverIndex(null);
  };

  // Inline rename state
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingName, setEditingName] = React.useState<string>('');
  const startRename = (id: string, current: string) => {
    setEditingId(id);
    setEditingName(current);
  };
  const commitRename = () => {
    if (editingId) {
      const name = editingName.trim();
      if (name) renameSheet(editingId, name);
    }
    setEditingId(null);
    setEditingName('');
  };
  const cancelRename = () => {
    setEditingId(null);
    setEditingName('');
  };

  return (
    <Bar>
      <Tooltip content="Scroll tabs left"><IconButton icon={<IconChevronLeft />} onClick={scrollLeft} /></Tooltip>
      <ScrollArea ref={scrollRef}>
        <TabsRow ref={tabsRef} style={{ transform: `translateX(${offset}px)` }}>
          {openTabs.map((id, idx) => {
            const sh = sheets[id];
            if (!sh) return null;
            return (
              <Tab
                key={id}
                active={id === activeId}
                onClick={() => setActive(id)}
                draggable
                onDragStart={(e) => onDragStart(e, id)}
                onDragOver={(e) => onDragOver(e, idx)}
                onDragLeave={onDragLeave}
                onDrop={(e) => onDrop(e, idx)}
                style={hoverIndex === idx ? { 
                  outline: '2px dashed var(--semi-color-primary)',
                  outlineOffset: '-2px'
                } : undefined}
              >
                {editingId === id ? (
                  <TabInput
                    autoFocus
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    onKeyDown={(e) => { 
                      if (e.key === 'Enter') commitRename(); 
                      if (e.key === 'Escape') cancelRename(); 
                    }}
                    onBlur={commitRename}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <TabLabel
                    title={sh.name}
                    onDoubleClick={(e) => { 
                      e.stopPropagation(); 
                      startRename(id, sh.name); 
                    }}
                  >
                    {sh.name}
                  </TabLabel>
                )}
                {id !== 'main' && (
                  <TabCloseButton
                    onClick={(e) => { 
                      e.stopPropagation(); 
                      closeSheet(id); 
                    }}
                  >
                    <IconClose />
                  </TabCloseButton>
                )}
              </Tab>
            );
          })}
        </TabsRow>
      </ScrollArea>
      <Tooltip content="New sheet"><IconButton icon={<IconPlus />} onClick={handleNew} /></Tooltip>
      <Tooltip content="Scroll tabs right"><IconButton icon={<IconChevronRight />} onClick={scrollRight} /></Tooltip>
    </Bar>
  );
};

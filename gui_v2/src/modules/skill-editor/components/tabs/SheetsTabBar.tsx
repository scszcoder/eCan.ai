import React from 'react';
import { IconButton, Tooltip } from '@douyinfe/semi-ui';
import { IconChevronLeft, IconChevronRight, IconClose, IconPlus } from '@douyinfe/semi-icons';
import styled from 'styled-components';
import { useSheetsStore } from '../../stores/sheets-store';

const Bar = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
`;

const ScrollArea = styled.div`
  position: relative;
  display: flex;
  align-items: center;
  overflow: hidden;
  flex: 1 1 auto;
`;

const TabsRow = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  transition: transform 0.15s ease;
`;

const Tab = styled.div<{ active?: boolean }>`
  display: flex;
  align-items: center;
  max-width: 180px;
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
  border-radius: 6px;
  padding: 4px 8px;
  background: ${(p) => (p.active ? 'var(--semi-color-fill-1)' : 'transparent')};
  border: 1px solid var(--semi-color-border);
  cursor: pointer;
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
                style={hoverIndex === idx ? { outline: '2px dashed var(--semi-color-primary)' } : undefined}
              >
                {editingId === id ? (
                  <input
                    autoFocus
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') cancelRename(); }}
                    onBlur={commitRename}
                    style={{
                      marginRight: 8,
                      background: 'transparent',
                      border: '1px solid var(--semi-color-border)',
                      borderRadius: 4,
                      color: 'inherit',
                      padding: '0 4px',
                      width: 120,
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span
                    title={sh.name}
                    style={{ marginRight: 8 }}
                    onDoubleClick={(e) => { e.stopPropagation(); startRename(id, sh.name); }}
                  >
                    {sh.name}
                  </span>
                )}
                {id !== 'main' && (
                  <IconButton
                    size="small"
                    theme="borderless"
                    icon={<IconClose />}
                    onClick={(e) => { e.stopPropagation(); closeSheet(id); }}
                  />
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

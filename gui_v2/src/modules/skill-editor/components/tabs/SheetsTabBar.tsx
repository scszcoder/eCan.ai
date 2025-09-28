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

  const [offset, setOffset] = React.useState(0);
  const tabsRef = React.useRef<HTMLDivElement>(null);
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

  return (
    <Bar>
      <Tooltip content="Scroll tabs left"><IconButton icon={<IconChevronLeft />} onClick={scrollLeft} /></Tooltip>
      <ScrollArea>
        <TabsRow ref={tabsRef} style={{ transform: `translateX(${offset}px)` }}>
          {openTabs.map((id) => {
            const sh = sheets[id];
            if (!sh) return null;
            return (
              <Tab key={id} active={id === activeId} onClick={() => setActive(id)}>
                <span title={sh.name} style={{ marginRight: 8 }}>{sh.name}</span>
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

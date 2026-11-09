import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { Spin, Empty, Tooltip, Button } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../../stores/userStore';
import { useToolStore } from '../../stores/toolStore';
import { Tool } from './types';
import ToolDetail from './ToolDetail';
import ToolCard from './components/ToolCard';
import ToolsSidebar from './components/ToolsSidebar';
import { buildCategoryBuckets, toolMatches } from './toolTaxonomy';
import RefreshButton from '../../components/Common/RefreshButton';
import SplitPane, { Pane as SplitChild } from 'split-pane-react';
import 'split-pane-react/esm/themes/default.css';

/**
 * Tools page — three panes:
 *
 *   [ category rail ] [ tool card grid ] [ detail ]
 *
 * Why not the previous `DetailLayout` list+detail: the list was a 332-row
 * un-virtualised column (~58k px of DOM) whose `.ant-spin-nested-loading`
 * wrapper is a plain `block` div, so it broke the flex chain and the panel
 * collapsed to a 53px scroll window. A bounded card grid removes both
 * problems without adding a virtualiser, and it surfaces the real taxonomy
 * (26 categories parsed from the description tag block) that the old
 * `system`/`custom` dropdown never matched.
 */

const Shell = styled.div`
  display: flex;
  gap: var(--space-md);
  height: 100%;
  min-height: 0;

  /* The category rail is a fixed column; the list and the detail pane share
     the remaining width and are separated by a draggable sash. */
  > :first-child {
    flex: 0 0 240px;
    min-width: 0;

    @media (max-width: 1600px) {
      flex-basis: 216px;
    }

    @media (max-width: 1200px) {
      flex-basis: 200px;
    }
  }
`;

/* Host for the list | detail split. It owns the free width the rail leaves. */
const SplitHost = styled.div`
  flex: 1;
  min-width: 0;
  height: 100%;
  min-height: 0;

  .react-split {
    height: 100%;
  }

  /* Vertical sash: 8px hit area with a 1px visible rule, matching the
     editor/preview sash inside the detail pane. */
  .react-split__sash--vertical {
    background: transparent;

    &::after {
      content: '';
      position: absolute;
      top: 0;
      bottom: 0;
      left: 3px;
      width: 2px;
      border-radius: 1px;
      background: var(--border-color);
    }

    &:hover::after,
    &.react-split__sash--active::after {
      background: var(--primary-color);
    }
  }
`;
const Pane = styled.section`
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: hidden;
`;

const PaneHeader = styled.header`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  flex-shrink: 0;
  min-height: 48px;
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
`;

const PaneTitle = styled.h2`
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  line-height: 1.4;
  color: var(--text-primary);
`;

const HeaderMeta = styled.span`
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
`;

const ActiveFilters = styled.div`
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  flex-shrink: 0;
  padding: var(--space-xs) var(--space-md);
  border-bottom: 1px solid var(--border-color);
  background: var(--surface-subtle);
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  overflow-x: auto;
`;

const FilterChip = styled.button`
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 8px;
  font-family: inherit;
  font-size: var(--font-size-xs);
  cursor: pointer;
  color: var(--primary-text);
  background: var(--primary-bg);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-full);
  white-space: nowrap;

  &:hover {
    color: var(--text-on-primary);
    background: var(--primary-fill);
  }
`;

/* Scroll owner for the card grid. It must be the flex child that shrinks,
   hence `flex: 1; min-height: 0` on both this and its ancestors. */
const GridScroll = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-md);
`;

const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-md);
  align-content: start;
`;

const CenterState = styled.div`
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-lg);
`;

const DetailScroll = styled.div`
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

/* Wide windows: a normal third grid column, always visible.
   Narrow windows: it leaves the grid and becomes a full-screen overlay.

   The wide `display: flex` below is load-bearing — the media query only
   applies *below* the breakpoint, so if the base declaration were
   `display: none` the pane would be invisible at every width above it. */
const DetailOverlay = styled.section`
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  background: var(--bg-secondary);

  @media (max-width: 1200px) {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 1000;
    height: auto;
    padding: var(--space-md);
    background: var(--bg-primary);
    gap: var(--space-sm);

    &[data-open='true'] {
      display: flex;
    }
  }
`;

const BREAKPOINT = 1200;

/** True when the window is too narrow for the three-pane layout. */
const useNarrowLayout = () => {
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= BREAKPOINT
  );

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${BREAKPOINT}px)`);
    const onChange = (e: MediaQueryListEvent) => setNarrow(e.matches);
    setNarrow(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  return narrow;
};

/* Width split for the list | detail sash, persisted so the chosen proportion
   survives navigation. Stored as percentages so the split keeps its shape when
   the window is resized; falls back to a 60/40 list-heavy default. */
const LIST_RATIO_KEY = 'tools.listRatio';
const DEFAULT_LIST_RATIO: [number, number] = [60, 40];

const readListRatio = (): number[] => {
  if (typeof window === 'undefined') return [...DEFAULT_LIST_RATIO];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(LIST_RATIO_KEY) ?? '');
    if (
      Array.isArray(parsed) &&
      parsed.length === 2 &&
      parsed.every((n) => typeof n === 'number' && Number.isFinite(n) && n > 0)
    ) {
      return parsed;
    }
  } catch {
    /* Corrupt or unavailable storage — fall through to the default. */
  }
  return [...DEFAULT_LIST_RATIO];
};

const Tools: React.FC = () => {
  const { t } = useTranslation();
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [query, setQuery] = useState('');
  const [activeBucket, setActiveBucket] = useState<string | null>(null);
  // In narrow layout the detail pane leaves the split and becomes an overlay,
  // so selecting a card has to open it explicitly.
  const narrow = useNarrowLayout();
  const [detailOpen, setDetailOpen] = useState(false);
  const [listRatio, setListRatio] = useState<number[]>(readListRatio);
  const username = useUserStore((state) => state.username);
  const { tools, loading, fetchTools, forceRefresh } = useToolStore();
  const hasFetchedRef = React.useRef(false);

  // Auto-load tools when component mounts or username changes
  useEffect(() => {
    if (username && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchTools(username).catch(console.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username]);

  const uncategorizedLabel = t('pages.tools.uncategorized', 'Uncategorized');

  const buckets = useMemo(
    () => buildCategoryBuckets(tools, uncategorizedLabel),
    [tools, uncategorizedLabel]
  );

  const filtered = useMemo(
    () => tools.filter((tool) => toolMatches(tool, query, activeBucket, uncategorizedLabel)),
    [tools, query, activeBucket, uncategorizedLabel]
  );

  // Keep the detail pane meaningful: when the current selection is filtered
  // out, fall back to the first visible tool instead of showing a stale one
  // that is not in the grid any more.
  useEffect(() => {
    if (isAddingNew) return;
    if (filtered.length === 0) {
      if (selectedTool !== null) setSelectedTool(null);
      return;
    }
    const stillVisible = selectedTool && filtered.some((tool) => tool.id === selectedTool.id);
    if (!stillVisible) setSelectedTool(filtered[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, isAddingNew]);

  const handleRefresh = useCallback(async () => {
    if (username) {
      await forceRefresh(username);
    }
  }, [username, forceRefresh]);

  /* split-pane-react reports pixel sizes; store the ratio so the split keeps
     its shape when the window (and therefore the pane total) changes. */
  const handleListResize = useCallback((next: number[]) => {
    const total = next.reduce((a, b) => a + b, 0);
    if (!total) return;
    const ratio = next.map((n) => (n / total) * 100);
    setListRatio(ratio);
    try {
      window.localStorage.setItem(LIST_RATIO_KEY, JSON.stringify(ratio));
    } catch {
      /* Storage unavailable — the split still works, it just will not persist. */
    }
  }, []);
  const handleCancelAdd = useCallback(() => {
    setIsAddingNew(false);
  }, []);

  const handleToolSaved = useCallback(() => {
    setIsAddingNew(false);
  }, []);

  const handleSelectTool = useCallback((tool: Tool) => {
    setIsAddingNew(false);
    setSelectedTool(tool);
    // In narrow layout the detail pane is an overlay; opening it here is what
    // the card tap means to the user.
    if (window.innerWidth <= BREAKPOINT) setDetailOpen(true);
  }, []);

  const handleClearFilters = useCallback(() => {
    setQuery('');
    setActiveBucket(null);
  }, []);

  const hasFilters = query.trim().length > 0 || activeBucket !== null;
  const isInitialLoad = loading && tools.length === 0;

  return (
    <div className="page-shell page-shell--fill">
      <Shell>
        {/* ── Pane 1: category rail ─────────────────────────────────── */}
        <Pane>
          <ToolsSidebar
            buckets={buckets}
            totalCount={tools.length}
            query={query}
            onQueryChange={setQuery}
            activeBucket={activeBucket}
            onBucketChange={setActiveBucket}
          />
        </Pane>

        {/* ── Panes 2 + 3: tool grid and detail, separated by a sash ─── */}
        <SplitHost>
          <SplitPane
            split="vertical"
            sizes={
              narrow
                ? ['100%', '0%']
                : listRatio.map((n) => `${n}%`)
            }
            allowResize={!narrow}
            onChange={handleListResize}
            sashRender={() => undefined}
          >
            <SplitChild minSize={narrow ? 0 : 320}>
              <Pane>
              <PaneHeader>
                <PaneTitle>{t('pages.tools.title')}</PaneTitle>
                <Tooltip title={t('pages.tools.refresh')}>
                  <RefreshButton
                    title={t('pages.tools.refresh')}
                    onClick={handleRefresh}
                    loading={loading}
                  />
                </Tooltip>
              </PaneHeader>

              {hasFilters && (
                <ActiveFilters>
                  <span>{t('pages.tools.showingCount', { shown: filtered.length, total: tools.length })}</span>
                  {activeBucket && (
                    <FilterChip type="button" onClick={() => setActiveBucket(null)}>
                      {activeBucket} ✕
                    </FilterChip>
                  )}
                  {query.trim() && (
                    <FilterChip type="button" onClick={() => setQuery('')}>
                      “{query.trim()}” ✕
                    </FilterChip>
                  )}
                  <FilterChip type="button" onClick={handleClearFilters}>
                    {t('pages.tools.clearFilters')}
                  </FilterChip>
                </ActiveFilters>
              )}

              {isInitialLoad ? (
                <CenterState>
                  <Spin />
                </CenterState>
              ) : tools.length === 0 ? (
                <CenterState>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span>{t('pages.tools.noTools')}</span>
                        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
                          {t('pages.tools.noToolsHint')}
                        </span>
                      </div>
                    }
                  />
                </CenterState>
              ) : filtered.length === 0 ? (
                <CenterState>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span>{t('pages.tools.noMatchingTools')}</span>
                        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
                          {t('pages.tools.noMatchingToolsHint')}
                        </span>
                      </div>
                    }
                  />
                </CenterState>
              ) : (
                <GridScroll>
                  <Grid>
                    {filtered.map((tool) => (
                      <ToolCard
                        key={tool.id || tool.name}
                        tool={tool}
                        selected={!isAddingNew && selectedTool?.id === tool.id}
                        onClick={() => handleSelectTool(tool)}
                      />
                    ))}
                  </Grid>
                </GridScroll>
              )}
              </Pane>
            </SplitChild>

            {/* Pane 3: detail.
                Wide: the second sash pane, always visible.
                Narrow: leaves the split as a fixed-position overlay. */}
            <SplitChild minSize={narrow ? 0 : 280}>
              <DetailOverlay data-open={narrow && detailOpen ? 'true' : 'false'}>
                <PaneHeader>
                  {narrow && (
                    <Button
                      size="small"
                      type="text"
                      icon={<ArrowLeftOutlined />}
                      onClick={() => setDetailOpen(false)}
                    >
                      {t('pages.tools.backToList', '返回列表')}
                    </Button>
                  )}
                  <PaneTitle>{t('pages.tools.details')}</PaneTitle>
                  {selectedTool && !isAddingNew && <HeaderMeta>{selectedTool.name}</HeaderMeta>}
                </PaneHeader>
                <DetailScroll>
                  <ToolDetail
                    tool={selectedTool}
                    isAddingNew={isAddingNew}
                    onSaved={handleToolSaved}
                    onCancelAdd={handleCancelAdd}
                  />
                </DetailScroll>
              </DetailOverlay>
            </SplitChild>
          </SplitPane>
        </SplitHost>
      </Shell>
    </div>
  );
};

export default Tools;

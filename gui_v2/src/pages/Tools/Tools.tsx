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
  display: grid;
  /* The card grid is the primary surface, so it takes the lion's share of the
     free space; the detail pane only needs enough width for one editor column. */
  grid-template-columns: 240px minmax(0, 1.6fr) minmax(320px, 1fr);
  gap: var(--space-md);
  height: 100%;
  min-height: 0;
  /* Keep all three panes down to ~1200px: the rail is fixed and the detail
     pane is clamped, so the grid absorbs the remainder. */
  @media (max-width: 1600px) {
    grid-template-columns: 216px minmax(0, 1.2fr) minmax(300px, 1fr);
  }

  /* Below that even two card columns stop fitting next to a usable editor. The
     detail pane leaves the grid entirely (it is rendered as a fixed-position
     overlay instead), so the template needs just two columns. */
  @media (max-width: 1200px) {
    grid-template-columns: 200px minmax(0, 1fr);
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

/* Narrow windows cannot fit a usable editor next to the card grid, so the
   detail pane becomes a full-screen overlay opened by tapping a card.
   `position: fixed` keeps it out of the 2-column grid so it never has to wrap
   into a second row the way a third grid child would.

   Visibility is driven by a `data-open` attribute rather than a styled prop:
   an interpolated value nested inside a media query is not re-evaluated per
   prop by emotion, which silently emitted a single `display: none` rule. */
const DetailOverlay = styled.section`
  display: none;

  @media (max-width: 1200px) {
    position: fixed;
    inset: 0;
    z-index: 1000;
    flex-direction: column;
    min-width: 0;
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

const Tools: React.FC = () => {
  const { t } = useTranslation();
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [query, setQuery] = useState('');
  const [activeBucket, setActiveBucket] = useState<string | null>(null);
  // Narrow windows render the detail pane as an overlay instead of a third
  // grid column, so selecting a card must also open it.
  const narrow = useNarrowLayout();
  const [detailOpen, setDetailOpen] = useState(false);
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

        {/* ── Pane 2: tool grid ─────────────────────────────────────── */}
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

        {/* ── Pane 3: detail ───────────────────────────────────────────
            Wide: a normal third grid column.
            Narrow: a fixed-position overlay, opened by tapping a card. */}
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
      </Shell>
    </div>
  );
};

export default Tools;

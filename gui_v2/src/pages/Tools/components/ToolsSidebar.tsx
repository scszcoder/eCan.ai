import React, { useMemo } from 'react';
import { Input, Empty } from 'antd';
import styled from '@emotion/styled';
import { SearchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { CategoryBucket } from '../toolTaxonomy';

/**
 * Left rail of the Tools page: one search box over a scrollable list of the
 * real categories (parsed from tool descriptions). Replaces the old icon-only
 * dropdown whose two hard-coded options ("system"/"custom") matched no shipped
 * tool at all.
 *
 * The list must be the only scrolling element in the rail, so the root is a
 * flex column with `min-height: 0` and the scroll area carries `flex: 1`.
 */

const Rail = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
`;

const SearchWrap = styled.div`
  padding: var(--space-sm);
  /* Was a fixed dark-slate literal in the old filter bar; token keeps it
     correct in both themes. */
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
`;

const ScrollArea = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--space-sm);
`;

const SectionLabel = styled.div`
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  padding: var(--space-xs) var(--space-sm);
  margin-bottom: var(--space-xs);
`;

const Row = styled.button<{ $active: boolean }>`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  width: 100%;
  min-height: var(--control-height-md);
  padding: 0 var(--space-sm);
  margin-bottom: var(--space-xs);
  border: 1px solid transparent;
  border-radius: var(--radius-xs-tight);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-md);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color var(--transition-fast), color var(--transition-fast),
    border-color var(--transition-fast);

  &:hover {
    background: var(--surface-subtle-hover);
    color: var(--text-primary);
  }

  &:focus-visible {
    outline: none;
    border-color: var(--border-color-focus);
    box-shadow: var(--shadow-focus);
  }

  ${props =>
    props.$active &&
    `
    background: var(--primary-fill);
    border-color: var(--primary-color);
    color: var(--text-on-primary);
    font-weight: var(--font-weight-medium);

    &:hover {
      background: var(--primary-fill-hover);
      color: var(--text-on-primary);
    }
  `}
`;

const RowName = styled.span`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const Count = styled.span<{ $active: boolean }>`
  flex-shrink: 0;
  min-width: 24px;
  padding: 0 6px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-variant-numeric: tabular-nums;
  text-align: center;
  background: ${props => (props.$active ? 'transparent' : 'var(--surface-subtle)')};
  border: 1px solid ${props => (props.$active ? 'var(--primary-border)' : 'transparent')};
  color: ${props => (props.$active ? 'var(--text-on-primary)' : 'var(--text-tertiary)')};
`;

const EmptyWrap = styled.div`
  padding: var(--space-lg) 0;
`;

interface ToolsSidebarProps {
  buckets: CategoryBucket[];
  totalCount: number;
  query: string;
  onQueryChange: (q: string) => void;
  activeBucket: string | null;
  onBucketChange: (name: string | null) => void;
}

const ToolsSidebar: React.FC<ToolsSidebarProps> = ({
  buckets,
  totalCount,
  query,
  onQueryChange,
  activeBucket,
  onBucketChange,
}) => {
  const { t } = useTranslation();

  const visible = useMemo(
    () => buckets.filter(b => !b.isUncategorized || b.count > 0),
    [buckets]
  );

  return (
    <Rail>
      <SearchWrap>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder={t('pages.tools.searchPlaceholder', 'Search by name or description…')}
          value={query}
          onChange={e => onQueryChange(e.target.value)}
          style={{ height: 'var(--control-height-md)' }}
        />
      </SearchWrap>

      <ScrollArea>
        {visible.length === 0 ? (
          <EmptyWrap>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('pages.tools.noTools', 'No tools yet')}
            />
          </EmptyWrap>
        ) : (
          <>
            <SectionLabel>
              {t('pages.tools.categoryLabel', 'Category')}
            </SectionLabel>

            <Row
              type="button"
              $active={activeBucket === null}
              onClick={() => onBucketChange(null)}
              aria-pressed={activeBucket === null}
            >
              <RowName>{t('pages.tools.allTools', 'All Tools')}</RowName>
              <Count $active={activeBucket === null}>{totalCount}</Count>
            </Row>

            {visible.map(bucket => {
              const active = activeBucket === bucket.name;
              return (
                <Row
                  key={bucket.name}
                  type="button"
                  $active={active}
                  onClick={() => onBucketChange(active ? null : bucket.name)}
                  aria-pressed={active}
                  title={bucket.name}
                >
                  <RowName>{bucket.name}</RowName>
                  <Count $active={active}>{bucket.count}</Count>
                </Row>
              );
            })}
          </>
        )}
      </ScrollArea>
    </Rail>
  );
};

export default ToolsSidebar;

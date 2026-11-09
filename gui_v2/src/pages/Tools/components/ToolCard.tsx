import React from 'react';
import styled from '@emotion/styled';
import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { Tool } from '../types';
import { parseToolTaxonomy } from '../toolTaxonomy';

/**
 * One tool tile in the middle grid.
 *
 * The old list rendered `tool.description` verbatim, so 296 of the 332 shipped
 * tools showed a literal `<category>RPA</category><sub-category>…</sub-category>`
 * prefix and untruncated paragraphs (rows measured 120–165px tall). Here the
 * tag block is split out into chips and the prose is clamped to two lines.
 */

const Card = styled.button<{ $selected: boolean }>`
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  width: 100%;
  padding: var(--space-md);
  text-align: left;
  font-family: inherit;
  cursor: pointer;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--elev-1, none);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast),
    transform var(--transition-fast), background-color var(--transition-fast);

  &:hover {
    transform: translateY(-1px);
    border-color: var(--border-color-hover);
    box-shadow: var(--elev-2, var(--shadow-md));
  }

  &:focus-visible {
    outline: none;
    border-color: var(--border-color-focus);
    box-shadow: var(--shadow-focus);
  }

  ${props =>
    props.$selected &&
    `
    border-color: var(--primary-border);
    background: var(--surface-subtle);
    box-shadow: 0 0 0 1px var(--primary-border), var(--elev-2, var(--shadow-md));
  `}
`;

const Head = styled.div`
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  min-width: 0;
`;

const Name = styled.div`
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  line-height: 1.35;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
`;

const Version = styled.span`
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
  padding: 1px 6px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
`;

const Description = styled.div`
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-secondary);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  min-height: calc(var(--font-size-sm) * 1.5 * 2);
`;

const NoDescription = styled(Description)`
  color: var(--text-tertiary);
  font-style: italic;
`;

const Chips = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-top: auto;
`;

const Chip = styled.span<{ $primary?: boolean }>`
  font-size: var(--font-size-xs);
  line-height: 1.6;
  padding: 1px 8px;
  border-radius: var(--radius-xs-tight);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;

  ${props =>
    props.$primary
      ? `
    background: var(--primary-bg);
    color: var(--primary-text);
    border: 1px solid var(--primary-border);
  `
      : `
    background: var(--surface-subtle);
    color: var(--text-tertiary);
    border: 1px solid var(--border-color);
  `}
`;

const ParamCount = styled.span`
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
`;

interface ToolCardProps {
  tool: Tool;
  selected: boolean;
  onClick: () => void;
}

const ToolCard: React.FC<ToolCardProps> = ({ tool, selected, onClick }) => {
  const { t } = useTranslation();
  const { category, subcategory, description } = parseToolTaxonomy(tool);

  const required: string[] = Array.isArray(tool.inputSchema?.required)
    ? tool.inputSchema.required
    : [];
  const properties = tool.inputSchema?.properties;
  const paramCount =
    properties && typeof properties === 'object' ? Object.keys(properties).length : 0;

  const title = tool.title || tool.name;

  return (
    <Card $selected={selected} type="button" onClick={onClick} aria-pressed={selected}>
      <Head>
        <Name title={title}>{title}</Name>
        {tool.version ? <Version>v{tool.version}</Version> : null}
      </Head>

      {description ? (
        <Description title={description}>{description}</Description>
      ) : (
        <NoDescription>{t('pages.tools.noDescription', 'No description')}</NoDescription>
      )}

      <Chips>
        {category ? (
          <Tooltip title={category}>
            <Chip $primary>{category}</Chip>
          </Tooltip>
        ) : null}
        {subcategory ? (
          <Tooltip title={subcategory}>
            <Chip>{subcategory}</Chip>
          </Tooltip>
        ) : null}
        {paramCount > 0 ? (
          <ParamCount>
            {t('pages.tools.parameters', 'Parameters')}: {paramCount}
            {required.length > 0 ? ` · ${required.length} ${t('pages.tools.required', 'required')}` : ''}
          </ParamCount>
        ) : null}
      </Chips>
    </Card>
  );
};

export default ToolCard;

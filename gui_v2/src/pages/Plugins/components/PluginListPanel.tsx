/**
 * PluginListPanel — left pane: search + filter chips + plugin rows.
 *
 * Each row shows name, version, tier badge, source badge, enable switch.
 * Selecting a row notifies the parent via onSelect.
 */

import React, { useMemo, useState } from 'react';
import { Input, List, Space, Tag, Typography, Button, Switch, Empty, Tooltip, App as AntApp } from 'antd';
import { SearchOutlined, AppstoreOutlined, FilterOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import type { PluginEntry, InstallSource } from '@/services/api/pluginApi';
import { enablePlugin, disablePlugin } from '@/services/api/pluginApi';

const { Text } = Typography;

const ListContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
`;

const Header = styled.div`
  padding: 12px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
`;

const ScrollArea = styled.div`
  flex: 1;
  overflow-y: auto;
`;

const RowBox = styled.div<{ $selected: boolean }>`
  padding: 10px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  cursor: pointer;
  background: ${({ $selected }) =>
    $selected ? 'var(--ant-color-bg-text-active)' : 'transparent'};
  transition: background 0.15s;
  &:hover {
    background: var(--ant-color-bg-text-hover);
  }
`;

export interface PluginListPanelProps {
  items: PluginEntry[];
  loading: boolean;
  selectedName: string | null;
  onSelect: (name: string) => void;
  onInstallClick: () => void;
  onMutated: () => void;
}

const sourceColor = (src: InstallSource): string => {
  switch (src) {
    case 'builtin':
      return 'default';
    case 'local':
      return 'blue';
    case 'catalog':
      return 'purple';
    default:
      return 'default';
  }
};

export const PluginListPanel: React.FC<PluginListPanelProps> = ({
  items,
  loading,
  selectedName,
  onSelect,
  onInstallClick,
  onMutated,
}) => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState<InstallSource | 'all'>('all');

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((e) => {
      if (sourceFilter !== 'all' && e.install_source !== sourceFilter) return false;
      if (!q) return true;
      return (
        e.name.toLowerCase().includes(q) ||
        (e.manifest_summary?.description || '').toLowerCase().includes(q) ||
        (e.manifest_summary?.author || '').toLowerCase().includes(q)
      );
    });
  }, [items, search, sourceFilter]);

  const handleToggle = async (entry: PluginEntry, next: boolean) => {
    if (entry.install_source === 'builtin') {
      message.info(
        t('plugins.list.builtinNoToggle', 'Built-in plugins cannot be disabled here.')
      );
      return;
    }
    try {
      const resp = next ? await enablePlugin(entry.name) : await disablePlugin(entry.name);
      if (resp.success) {
        onMutated();
      } else {
        message.error(resp.error?.message || 'Failed to update enabled state');
      }
    } catch (e: any) {
      message.error(String(e?.message || e));
    }
  };

  const filterChip = (key: InstallSource | 'all', label: string) => (
    <Tag
      color={sourceFilter === key ? 'blue' : 'default'}
      style={{ cursor: 'pointer' }}
      onClick={() => setSourceFilter(key)}
    >
      {label}
    </Tag>
  );

  return (
    <ListContainer>
      <Header>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Text strong>
              <AppstoreOutlined /> {t('plugins.list.title', 'Plugins')}
            </Text>
            <Button type="primary" size="small" onClick={onInstallClick}>
              {t('plugins.list.install', 'Install…')}
            </Button>
          </Space>
          <Input
            prefix={<SearchOutlined />}
            placeholder={t('plugins.list.searchPlaceholder', 'Search plugins…')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
            size="small"
          />
          <Space size={4} wrap>
            <FilterOutlined style={{ color: 'var(--ant-color-text-quaternary)' }} />
            {filterChip('all', t('plugins.list.filterAll', 'All'))}
            {filterChip('builtin', t('plugins.list.filterBuiltin', 'Built-in'))}
            {filterChip('local', t('plugins.list.filterLocal', 'Installed'))}
          </Space>
        </Space>
      </Header>
      <ScrollArea>
        {filtered.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              loading
                ? t('plugins.list.loading', 'Loading…')
                : t('plugins.list.empty', 'No plugins installed. Use Install… to add one.')
            }
            style={{ marginTop: 64 }}
          />
        ) : (
          <List
            dataSource={filtered}
            renderItem={(entry) => (
              <RowBox
                $selected={entry.name === selectedName}
                onClick={() => onSelect(entry.name)}
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Space size={6}>
                      <Text strong>{entry.name}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        v{entry.version}
                      </Text>
                    </Space>
                    <Tooltip
                      title={
                        entry.install_source === 'builtin'
                          ? t('plugins.list.builtinNoToggle', 'Built-in plugins cannot be disabled here.')
                          : entry.enabled
                          ? t('plugins.list.disable', 'Disable')
                          : t('plugins.list.enable', 'Enable')
                      }
                    >
                      <Switch
                        size="small"
                        checked={entry.enabled}
                        disabled={entry.install_source === 'builtin'}
                        onChange={(checked, e) => {
                          e?.stopPropagation?.();
                          handleToggle(entry, checked);
                        }}
                        onClick={(_checked, e) => e?.stopPropagation?.()}
                      />
                    </Tooltip>
                  </Space>
                  <Space size={4}>
                    <Tag color={sourceColor(entry.install_source)} style={{ margin: 0 }}>
                      {entry.install_source}
                    </Tag>
                    {entry.manifest_summary?.hooks?.length ? (
                      <Tag style={{ margin: 0 }}>
                        {t('plugins.list.hookCount', '{{n}} hook(s)', {
                          n: entry.manifest_summary.hooks.length,
                        })}
                      </Tag>
                    ) : null}
                    {entry.signature_status && entry.signature_status !== 'n/a' ? (
                      <Tag style={{ margin: 0 }}>{entry.signature_status}</Tag>
                    ) : null}
                  </Space>
                  {entry.manifest_summary?.description ? (
                    <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                      {entry.manifest_summary.description}
                    </Text>
                  ) : null}
                </Space>
              </RowBox>
            )}
          />
        )}
      </ScrollArea>
    </ListContainer>
  );
};

export default PluginListPanel;

import React from 'react';
import { List, Input, Badge, Typography, Button, Dropdown, Tooltip } from 'antd';
import { SearchOutlined, PlusOutlined, MoreOutlined, ReloadOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import type { Prompt } from './types';
import { useTranslation } from 'react-i18next';

interface PromptsListProps {
  prompts: Prompt[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  search: string;
  onSearchChange: (val: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

const PromptsList: React.FC<PromptsListProps> = ({ prompts, selectedId, onSelect, search, onSearchChange, onAdd, onDelete, onRefresh }) => {
  const { t } = useTranslation();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: 12, display: 'flex', gap: 8 }}>
        <Input
          allowClear
          placeholder={t('pages.prompts.searchPlaceholder', { defaultValue: 'Search prompts' })}
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>{t('common.add')}</Button>
        <Tooltip title={t('common.refresh', { defaultValue: 'Refresh' })}>
          <Button icon={<ReloadOutlined />} onClick={onRefresh} />
        </Tooltip>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <List
          dataSource={prompts}
          renderItem={(item) => (
            <List.Item
              onClick={() => onSelect(item.id)}
              style={{ cursor: 'pointer', paddingLeft: 16, paddingRight: 8, background: selectedId === item.id ? 'rgba(255,255,255,0.06)' : 'transparent' }}
              actions={[
                <Dropdown
                  key="menu"
                  menu={{ items: [{ key: 'delete', label: t('common.delete'), danger: true }] as MenuProps['items'], onClick: ({ key }) => { if (key === 'delete') onDelete(item.id); } }}
                  trigger={["click"]}
                  placement="bottomRight"
                >
                  <Button type="text" size="small" onClick={(e) => e.stopPropagation()} icon={<MoreOutlined />} />
                </Dropdown>
              ]}
            >
              <List.Item.Meta
                title={<span style={{ color: '#fff' }}>
                  {(() => {
                    const rawTitle = (item.title || '').trim();
                    if (rawTitle) return rawTitle;
                    const slug = (item.topic || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
                    const titleKey = `pages.prompts.examples.${slug}.title`;
                    const titleText = t(titleKey, { defaultValue: '' });
                    if (titleText && titleText !== titleKey) return titleText;
                    return t(`pages.prompts.examples.${slug}`, { defaultValue: item.topic });
                  })()}
                </span>}
                description={
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'rgba(255,255,255,0.65)' }}>
                    <div>
                      <Badge count={item.usageCount} style={{ backgroundColor: '#3b82f6' }} />
                      <Typography.Text style={{ marginLeft: 8, color: 'rgba(255,255,255,0.65)' }}>{t('pages.prompts.uses', { defaultValue: 'uses' })}</Typography.Text>
                    </div>
                    <Typography.Text style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>
                      {(() => {
                        if (!item.lastModified) return '';
                        const date = new Date(item.lastModified);
                        if (Number.isNaN(date.getTime())) return item.lastModified;
                        return date.toLocaleString();
                      })()}
                    </Typography.Text>
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </div>
    </div>
  );
};

export default PromptsList;

import React from 'react';
import { List, Input, Badge, Typography, Button, Dropdown, Tooltip, Tag, Space } from 'antd';
import { SearchOutlined, PlusOutlined, MoreOutlined, ReloadOutlined, CopyOutlined } from '@ant-design/icons';
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
  onClone: (prompt: Prompt) => void;
}

const PromptsList: React.FC<PromptsListProps> = ({ prompts, selectedId, onSelect, search, onSearchChange, onAdd, onDelete, onRefresh, onClone }) => {
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
            <Tooltip
              key={item.id}
              placement="right"
              title={item.source === 'sample_prompts'
                ? t('pages.prompts.sampleSource', { defaultValue: 'Sample library prompt (read-only)' })
                : t('pages.prompts.mySource', { defaultValue: 'My prompts directory' })}
            >
              <List.Item
                onClick={() => onSelect(item.id)}
                style={{ cursor: 'pointer', paddingLeft: 16, paddingRight: 8, background: selectedId === item.id ? 'rgba(255,255,255,0.06)' : 'transparent' }}
                actions={(() => {
                  const menuItems: MenuProps['items'] = [
                    { key: 'copy', label: t('pages.prompts.copyCreate', { defaultValue: 'Copy & create' }), icon: <CopyOutlined /> },
                    {
                      key: 'delete',
                      label: t('common.delete'),
                      danger: true,
                      disabled: !!item.readOnly,
                    },
                  ];
                  return [
                    <Dropdown
                      key="menu"
                      menu={{
                        items: menuItems,
                        onClick: ({ key }) => {
                          if (key === 'delete') {
                            if (item.readOnly) return;
                            onDelete(item.id);
                          } else if (key === 'copy') {
                            onClone(item);
                          }
                        },
                      }}
                      trigger={['click']}
                      placement="bottomRight"
                    >
                      <Button type="text" size="small" onClick={(e) => e.stopPropagation()} icon={<MoreOutlined />} />
                    </Dropdown>,
                  ];
                })()}
              >
                <List.Item.Meta
                  title={
                    <div
                      style={{
                        color: '#fff',
                        marginBottom: 4,
                        display: 'flex',
                        alignItems: 'baseline',
                        gap: 6,
                        width: '100%',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {(() => {
                        const rawTitle = (item.title || '').trim();
                        const resolvedTitle = (() => {
                          if (rawTitle) return rawTitle;
                          const slug = (item.topic || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
                          const titleKey = `pages.prompts.examples.${slug}.title`;
                          const titleText = t(titleKey, { defaultValue: '' });
                          if (titleText && titleText !== titleKey) return titleText;
                          const fallback = t(`pages.prompts.examples.${slug}`, { defaultValue: item.topic });
                          return fallback || item.id;
                        })();
                        const trimmedId = (item.id || '').trim();
                        const displayId = trimmedId.replace(/^pr-/, '');
                        return (
                          <>
                            <span style={{ fontWeight: 600 }}>{resolvedTitle}</span>
                            {displayId ? (
                              <span style={{ fontWeight: 400, color: 'rgba(255,255,255,0.7)' }}>
                                ({displayId})
                              </span>
                            ) : null}
                          </>
                        );
                      })()}
                    </div>
                  }
                  description={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12, whiteSpace: 'nowrap' }}>
                      <Space size={4} align="center" style={{ whiteSpace: 'nowrap' }}>
                        <Badge count={item.usageCount} style={{ backgroundColor: '#3b82f6' }} showZero />
                        <Typography.Text style={{ color: 'rgba(255,255,255,0.55)', fontSize: 12, whiteSpace: 'nowrap' }}>
                          {t('pages.prompts.uses', { defaultValue: 'uses' })}
                        </Typography.Text>
                      </Space>
                      <Typography.Text style={{ color: 'rgba(255,255,255,0.55)', fontSize: 12, whiteSpace: 'nowrap', minWidth: 50 }}>
                        {item.source === 'sample_prompts' 
                          ? t('pages.prompts.sampleLabel', { defaultValue: 'sample' })
                          : t('pages.prompts.myLabel', { defaultValue: 'my' })}
                      </Typography.Text>
                      <Typography.Text style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, marginLeft: 'auto', whiteSpace: 'nowrap', paddingRight: 8 }}>
                        {(() => {
                          if (!item.lastModified) return '';
                          const date = new Date(item.lastModified);
                          if (Number.isNaN(date.getTime())) return item.lastModified;
                          return date.toLocaleString(undefined, { 
                            year: '2-digit', 
                            month: '2-digit', 
                            day: '2-digit', 
                            hour: '2-digit', 
                            minute: '2-digit' 
                          });
                        })()}
                      </Typography.Text>
                    </div>
                  }
                />
              </List.Item>
            </Tooltip>
          )}
        />
      </div>
    </div>
  );
};

export default PromptsList;

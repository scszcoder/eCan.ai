import React from 'react';
import { List, Input, Badge, Typography, Button, Dropdown } from 'antd';
import { SearchOutlined, PlusOutlined, MoreOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import type { Prompt } from './types';

interface PromptsListProps {
  prompts: Prompt[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  search: string;
  onSearchChange: (val: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
}

const PromptsList: React.FC<PromptsListProps> = ({ prompts, selectedId, onSelect, search, onSearchChange, onAdd, onDelete }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: 12, display: 'flex', gap: 8 }}>
        <Input
          allowClear
          placeholder="Search prompts"
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>Add</Button>
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
                  menu={{ items: [{ key: 'delete', label: 'Delete', danger: true }] as MenuProps['items'], onClick: ({ key }) => { if (key === 'delete') onDelete(item.id); } }}
                  trigger={["click"]}
                  placement="bottomRight"
                >
                  <Button type="text" size="small" onClick={(e) => e.stopPropagation()} icon={<MoreOutlined />} />
                </Dropdown>
              ]}
            >
              <List.Item.Meta
                title={<span style={{ color: '#fff' }}>{item.topic}</span>}
                description={
                  <div style={{ color: 'rgba(255,255,255,0.65)' }}>
                    <Badge count={item.usageCount} style={{ backgroundColor: '#3b82f6' }} />
                    <Typography.Text style={{ marginLeft: 8, color: 'rgba(255,255,255,0.65)' }}>uses</Typography.Text>
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

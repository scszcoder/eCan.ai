import React from 'react';
import { List } from 'antd';
import ToolListItem from './ToolListItem';
import { Tool } from './types';

interface ToolsListProps {
  tools: Tool[];
  selectedTool: Tool | null;
  onSelect: (tool: Tool) => void;
  loading: boolean;
}

const ToolsList: React.FC<ToolsListProps> = ({ tools, selectedTool, onSelect, loading }) => (
  <List
    loading={loading}
    dataSource={tools}
    renderItem={tool => (
      <ToolListItem
        key={tool.name}
        tool={tool}
        selected={selectedTool?.name === tool.name}
        onClick={() => onSelect(tool)}
      />
    )}
    bordered
  />
);

export default ToolsList; 
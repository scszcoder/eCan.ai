import React, { useState, useMemo } from 'react';
import { List, Empty } from 'antd';
import styled from '@emotion/styled';
import ToolListItem from './ToolListItem';
import { Tool } from './types';
import { ToolFilters, ToolFilterOptions } from './components/ToolFilters';

const ListContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
`;

const ListScrollArea = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
`;

interface ToolsListProps {
  tools: Tool[];
  selectedTool: Tool | null;
  onSelect: (tool: Tool) => void;
  loading: boolean;
}

const ToolsList: React.FC<ToolsListProps> = ({ tools, selectedTool, onSelect, loading }) => {
  const [filters, setFilters] = useState<ToolFilterOptions>({
    search: '',
    category: undefined,
  });

  // 过滤和排序工具列表
  const filteredTools = useMemo(() => {
    let result = [...tools];

    // 按类别筛选
    if (filters.category) {
      result = result.filter(tool => {
        // 这里可以根据实际的工具类别字段进行筛选
        // 假设工具有一个 category 或 type 字段
        const toolCategory = (tool as any).category || (tool as any).type || 'custom';
        return toolCategory === filters.category;
      });
    }

    // 按搜索关键字筛选（匹配名称和描述）
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      result = result.filter(tool =>
        tool.name?.toLowerCase().includes(searchLower) ||
        tool.description?.toLowerCase().includes(searchLower)
      );
    }

    return result;
  }, [tools, filters]);

  return (
    <ListContainer>
      {/* Filter Section */}
      <ToolFilters filters={filters} onChange={setFilters} />

      {/* Scrollable List */}
      <ListScrollArea>
        {filteredTools.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="没有找到匹配的工具"
            style={{ marginTop: 40 }}
          />
        ) : (
          <List
            loading={loading}
            dataSource={filteredTools}
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
        )}
      </ListScrollArea>
    </ListContainer>
  );
};

export default ToolsList; 
import React, { useState, useEffect } from 'react';
import { Input, Empty, Spin } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useContextStore } from '@/stores/contextStore';
import { ContextCard } from './ContextCard';

const Container = styled.div`
  display: block;
  width: 100%;
  background: transparent;
  overflow: visible;
  box-sizing: border-box;
  position: relative;
`;

const SearchContainer = styled.div`
  padding: 12px 16px;
  border-bottom: 1px solid var(--text-primary);
  flex-shrink: 0;
`;

const StyledInput = styled(Input)`
  background: #1a1a1a;
  border: 1px solid var(--text-primary);
  border-radius: 6px;
  
  &:hover, &:focus {
    border-color: var(--text-secondary);
    background: #222;
  }
  
  .ant-input {
    background: transparent;
  }
`;

const ContextList = styled.div`
  display: block;
  overflow: visible; /* let Card body handle scrolling */
  padding: 12px;
  position: relative;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
  
  &::-webkit-scrollbar-thumb {
    background: var(--text-primary);
    border-radius: 3px;
    
    &:hover {
      background: var(--text-secondary);
    }
  }
`;

const EmptyContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
`;

export const ContextPanel: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const { contexts, searchQuery, setSearchQuery, getFilteredContexts, setContexts } = useContextStore();

  useEffect(() => {
    // Request initial contexts from backend
    const loadContexts = async () => {
      try {
        setLoading(true);
        await ipcInvoke('refresh_contexts');
      } catch (error) {
        console.error('Failed to load contexts:', error);
      } finally {
        setLoading(false);
      }
    };

    loadContexts();
  }, []);

  const filteredContexts = getFilteredContexts();

  // Sort by most recent timestamp
  const sortedContexts = [...filteredContexts].sort((a, b) => {
    return new Date(b.mostRecentTimestamp).getTime() - new Date(a.mostRecentTimestamp).getTime();
  });

  return (
    <Container>
      <SearchContainer>
        <StyledInput
          placeholder="Search contexts..."
          prefix={<SearchOutlined style={{ color: 'var(--text-tertiary)' }} />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          allowClear
        />
      </SearchContainer>
      
      <ContextList>
        {loading ? (
          <EmptyContainer>
            <Spin />
          </EmptyContainer>
        ) : sortedContexts.length === 0 ? (
          <EmptyContainer>
            <Empty
              description={searchQuery ? 'No matching contexts' : 'No contexts yet'}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          </EmptyContainer>
        ) : (
          sortedContexts.map((context) => (
            <ContextCard key={context.uid} context={context} />
          ))
        )}
      </ContextList>
    </Container>
  );
};

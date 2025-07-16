import React from 'react';
import { Typography } from 'antd';
import styled from '@emotion/styled';
import { Tool } from './types';

interface ToolListItemProps {
  tool: Tool;
  selected: boolean;
  onClick: () => void;
}

const StyledToolItem = styled.div<{ $selected: boolean }>`
  padding: 12px;
  border-bottom: 1px solid var(--border-color);
  &:last-child { border-bottom: none; }
  cursor: pointer;
  transition: all 0.3s ease;
  background-color: ${props => props.$selected ? 'var(--bg-tertiary)' : 'var(--bg-secondary)'};
  border-radius: 8px;
  margin: 4px 0;
  box-shadow: ${props => props.$selected ? '0 2px 8px rgba(0,0,0,0.10)' : 'none'};
  &:hover {
    background-color: var(--bg-tertiary);
    transform: translateX(4px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.10);
  }
  .ant-typography { color: var(--text-primary); }
`;

const ToolListItem: React.FC<ToolListItemProps> = ({ tool, selected, onClick }) => (
  <StyledToolItem $selected={selected} onClick={onClick}>
    <Typography.Text strong>{tool.name}</Typography.Text>
    <div style={{ fontSize: 12, color: '#888' }}>{tool.description}</div>
  </StyledToolItem>
);

export default ToolListItem; 
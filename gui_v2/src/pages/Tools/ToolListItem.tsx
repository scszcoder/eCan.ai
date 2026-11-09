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
  cursor: pointer;
  transition: all 0.3s ease;
  background: var(--bg-secondary);
  border-radius: 12px;
  margin: 6px 0;
  border: 1px solid var(--border-color);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    width: 4px;
    background: transparent;
    transition: all 0.3s ease;
  }

  &:hover {
    background: var(--bg-tertiary);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
    border-color: var(--border-color);

    &::before {
      width: 3px;
      background: var(--primary-color);
    }
  }
  
  ${props => props.$selected && `
    background: linear-gradient(135deg, rgba(var(--primary-color-rgb), 0.15) 0%, rgba(var(--primary-color-rgb), 0.05) 100%);
    border: 1px solid rgba(var(--primary-color-rgb), 0.4);
    box-shadow: 0 2px 8px rgba(var(--primary-color-rgb), 0.2);
    
    &::before {
      background: var(--primary-color);
    }
    
    &:hover {
      background: linear-gradient(135deg, rgba(var(--primary-color-rgb), 0.2) 0%, rgba(var(--primary-color-rgb), 0.08) 100%);
      border-color: rgba(var(--primary-color-rgb), 0.6);
      box-shadow: 0 4px 16px rgba(var(--primary-color-rgb), 0.3);
      
      &::before {
        width: 4px;
      }
    }
  `}
  
  .ant-typography { color: var(--text-primary); }
`;

const ToolListItem: React.FC<ToolListItemProps> = ({ tool, selected, onClick }) => (
  <StyledToolItem $selected={selected} onClick={onClick}>
    <Typography.Text strong>{tool.name}</Typography.Text>
    <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-tertiary)' }}>{tool.description}</div>
  </StyledToolItem>
);

export default ToolListItem; 
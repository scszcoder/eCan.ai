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
  border: 1px solid transparent;
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
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    border-color: rgba(255, 255, 255, 0.1);

    &::before {
      width: 3px;
      background: var(--primary-color);
    }
  }
  
  ${props => props.$selected && `
    background: linear-gradient(135deg, rgba(24, 144, 255, 0.15) 0%, rgba(24, 144, 255, 0.05) 100%);
    border: 1px solid rgba(24, 144, 255, 0.4);
    box-shadow: 0 2px 8px rgba(24, 144, 255, 0.2);
    
    &::before {
      background: var(--primary-color);
    }
    
    &:hover {
      background: linear-gradient(135deg, rgba(24, 144, 255, 0.2) 0%, rgba(24, 144, 255, 0.08) 100%);
      border-color: rgba(24, 144, 255, 0.6);
      box-shadow: 0 4px 16px rgba(24, 144, 255, 0.3);
      
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
    <div style={{ fontSize: 12, color: '#888' }}>{tool.description}</div>
  </StyledToolItem>
);

export default ToolListItem; 
import React, { useState } from 'react';
import { Card, Dropdown, Modal, Input, message } from 'antd';
import type { MenuProps } from 'antd';
import { MoreOutlined, DownOutlined, RightOutlined, MessageOutlined, ClockCircleOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import type { ChatContext } from '../types/context';
import { ContextItemCard } from './ContextItemCard';
import { useContextStore } from '@/stores/contextStore';
import { ipcInvoke } from '@/services/ipc/ipcWCClient';

const StyledCard = styled(Card)`
  margin: 8px 0;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  transition: all 0.2s;
  width: 100%;
  box-sizing: border-box;
  
  &.collapsed {
    .ant-card-head {
      padding-top: 18px; /* nudge header down when collapsed */
    }
  }
  
  &:first-of-type {
    margin-top: 0;
  }
  
  &:hover {
    border-color: #555;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }
  
  .ant-card-head {
    padding: 12px 16px;
    min-height: 56px;
    border-bottom: none;
    background: transparent;
    display: flex;
    align-items: center;
  }
  
  .ant-card-head-title {
    padding: 0;
    overflow: visible;
    display: flex;
    align-items: center;
  }
  
  .ant-card-body {
    padding: 0 16px 12px;
  }
`;

const CardHeader = styled.div`
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  width: 100%;
`;

const HeaderWrap = styled.div<{ collapsed: boolean }>`
  display: flex;
  align-items: stretch;
  gap: 8px;
  padding: ${(props) => (props.collapsed ? '12px 16px' : '12px 16px')};
`;

const TitleRow = styled.div`
  display: flex;
  align-items: baseline;
  gap: 8px;
  width: 100%;
`;

const RightSide = styled.div`
  margin-left: auto;
  align-self: baseline;
`;

const ExpandIcon = styled.div`
  color: #888;
  cursor: pointer;
  flex-shrink: 0;
  min-width: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  
  &:hover {
    color: #fff;
  }
`;

const HeaderContent = styled.div`
  flex: 1;
  min-width: 0;
  cursor: pointer;
  overflow: hidden;
`;

const Title = styled.div`
  font-size: 14px;
  font-weight: 500;
  color: #fff;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const MetaInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
  flex-wrap: wrap;
`;

const MetaItem = styled.span`
  display: flex;
  align-items: center;
  gap: 4px;
`;

const RecentMessage = styled.div`
  font-size: 12px;
  color: #aaa;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const MenuButton = styled.div`
  color: #888;
  cursor: pointer;
  flex-shrink: 0;
  padding: 4px;
  border-radius: 4px;
  
  &:hover {
    color: #fff;
    background: #333;
  }
`;

const ItemsList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const ItemsScroll = styled.div`
  max-height: 50vh;
  overflow-y: auto;
  overflow-x: hidden;
  margin-top: 8px;
  padding-right: 4px;
`;

interface ContextCardProps {
  context: ChatContext;
}

export const ContextCard: React.FC<ContextCardProps> = ({ context }) => {
  const [expanded, setExpanded] = useState(false);
  const [renameModalVisible, setRenameModalVisible] = useState(false);
  const [newTitle, setNewTitle] = useState(context.title);
  const { updateContext, deleteContext } = useContextStore();

  const handleRename = async () => {
    if (!newTitle.trim()) {
      message.error('Title cannot be empty');
      return;
    }
    
    updateContext(context.uid, { title: newTitle.trim() });
    setRenameModalVisible(false);
    message.success('Context renamed');
  };

  const handleArchive = async () => {
    updateContext(context.uid, { isArchived: true });
    message.success('Context archived');
  };

  const handleDelete = async () => {
    Modal.confirm({
      title: 'Delete Context',
      content: 'Are you sure you want to delete this context? This action cannot be undone.',
      okText: 'Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          await ipcInvoke('delete_context', { contextId: context.uid });
          deleteContext(context.uid);
          message.success('Context deleted');
        } catch (error) {
          console.error('Failed to delete context:', error);
          message.error('Failed to delete context');
        }
      },
    });
  };

  const menuItems: MenuProps['items'] = [
    {
      key: 'rename',
      label: 'Rename',
      onClick: () => {
        setNewTitle(context.title);
        setRenameModalVisible(true);
      },
    },
    {
      key: 'archive',
      label: 'Archive',
      onClick: handleArchive,
    },
    {
      type: 'divider',
    },
    {
      key: 'delete',
      label: 'Delete',
      danger: true,
      onClick: handleDelete,
    },
  ];

  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString();
    } catch {
      return timestamp;
    }
  };

  return (
    <>
      <StyledCard className={expanded ? '' : 'collapsed'}>
        <HeaderWrap collapsed={!expanded}>
          <CardHeader>
            <TitleRow>
              <ExpandIcon onClick={() => setExpanded(!expanded)}>
                {expanded ? <DownOutlined /> : <RightOutlined />}
              </ExpandIcon>
              <Title onClick={() => setExpanded(!expanded)}>{context.title}</Title>
              <RightSide>
                <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
                  <MenuButton onClick={(e) => e.stopPropagation()}>
                    <MoreOutlined />
                  </MenuButton>
                </Dropdown>
              </RightSide>
            </TitleRow>
            <MetaInfo>
              <MetaItem>
                <MessageOutlined />
                {context.messageCount} {context.messageCount === 1 ? 'message' : 'messages'}
              </MetaItem>
              <MetaItem>
                <ClockCircleOutlined />
                {formatTimestamp(context.mostRecentTimestamp)}
              </MetaItem>
            </MetaInfo>
            {!expanded && <RecentMessage>{context.mostRecentMessage}</RecentMessage>}
          </CardHeader>
        </HeaderWrap>
        {expanded && (
          <ItemsList>
            {context.items.map((item) => (
              <ContextItemCard key={item.uid} item={item} />
            ))}
          </ItemsList>
        )}
      </StyledCard>

      <Modal
        title="Rename Context"
        open={renameModalVisible}
        onOk={handleRename}
        onCancel={() => setRenameModalVisible(false)}
        okText="Rename"
      >
        <Input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="Enter new title"
          onPressEnter={handleRename}
          autoFocus
        />
      </Modal>
    </>
  );
};

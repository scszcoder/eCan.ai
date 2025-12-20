import React, { useMemo, useState, useEffect } from 'react';
import { Modal, Tree, Input, Empty, Space } from 'antd';
import { SearchOutlined, ApartmentOutlined, UserOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { DataNode } from 'antd/es/tree';
import { useAgentStore } from '@/stores/agentStore';
import { useOrgStore } from '@/stores/orgStore';
import { useUserStore } from '@/stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';

interface AgentFilterModalProps {
  visible: boolean;
  selectedAgentId: string | null;
  onSelect: (agentId: string | null) => void;
  onCancel: () => void;
}

const AgentFilterModal: React.FC<AgentFilterModalProps> = ({
  visible,
  selectedAgentId,
  onSelect,
  onCancel,
}) => {
  const { t } = useTranslation();
  const agents = useAgentStore((state) => state.agents);
  const treeOrgs = useOrgStore((state) => state.treeOrgs);
  const setAllOrgAgents = useOrgStore((state) => state.setAllOrgAgents);
  const username = useUserStore((state) => state.username);
  const getMyTwinAgent = useAgentStore((state) => state.getMyTwinAgent);
  const [searchText, setSearchText] = useState('');
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  
  // Get MyTwin agent
  const myTwinAgent = getMyTwinAgent();
  const myTwinAgentId = myTwinAgent?.card?.id;

  // When Modal Open时Load组织Data
  useEffect(() => {
    if (visible && treeOrgs.length === 0 && username) {
      const loadOrgData = async () => {
        try {
          const response = await get_ipc_api().getAllOrgAgents(username);
          if (response.success && response.data) {
            setAllOrgAgents(response.data as any);
          }
        } catch (error) {
          console.error('[AgentFilterModal] Failed to load org data:', error);
        }
      };
      
      loadOrgData();
    }
  }, [visible, treeOrgs.length, username, setAllOrgAgents]);


  // Build tree data from organization structure
  const treeData = useMemo(() => {
    const buildTreeNode = (orgNode: any): DataNode => {
      // 计算该组织及其子组织的代理总数
      const countAgents = (node: any): number => {
        let count = 0;
        if (node.agents && Array.isArray(node.agents)) {
          // If有Search文本，只计算匹配的代理
          if (searchText) {
            count = node.agents.filter((agent: any) => {
              const agentName = agent.name || agent.card?.name || '';
              return agentName.toLowerCase().includes(searchText.toLowerCase());
            }).length;
          } else {
            count = node.agents.length;
          }
        }
        if (node.children && Array.isArray(node.children)) {
          count += node.children.reduce((sum: number, child: any) => sum + countAgents(child), 0);
        }
        return count;
      };

      const agentCount = countAgents(orgNode);
      const children: DataNode[] = [];

      // 1. 先Add直属代理
      if (orgNode.agents && Array.isArray(orgNode.agents)) {
        const agentNodes: DataNode[] = orgNode.agents
          .filter((agent: any) => {
            if (!searchText) return true;
            const searchLower = searchText.toLowerCase();
            const agentName = (agent.name || agent.card?.name || '').toLowerCase();
            const agentDesc = (agent.description || agent.card?.description || '').toLowerCase();
            // 模糊匹配：name 或 description IncludeSearch关键字即可
            return agentName.includes(searchLower) || agentDesc.includes(searchLower);
          })
          .map((agent: any) => {
            const agentId = agent.id || agent.card?.id;
            const agentName = agent.name || agent.card?.name || 'Unnamed Agent';
            const isMyTwin = agentId === myTwinAgentId;
            const displayName = isMyTwin 
              ? `${t('pages.chat.myself')}（${agentName}）`
              : agentName;
            
            return {
              title: (
                <Space>
                  <UserOutlined style={{ color: '#52c41a' }} />
                  <span>{displayName}</span>
                </Space>
              ),
              key: agentId,
              isLeaf: true,
              selectable: true,
            };
          });
        children.push(...agentNodes);
      }

      // 2. 再Add子组织
      if (orgNode.children && Array.isArray(orgNode.children)) {
        const childOrgNodes = orgNode.children
          .map((child: any) => buildTreeNode(child))
          .filter((childNode: DataNode) => {
            // If有Search文本，Filter掉没有匹配代理的组织
            if (searchText) {
              return childNode.children && childNode.children.length > 0;
            }
            return true;
          });
        children.push(...childOrgNodes);
      }

      // 组织节点的标题，Include图标和代理Count
      const orgTitle = (
        <Space>
          <ApartmentOutlined style={{ color: '#1890ff' }} />
          <span>{orgNode.name || 'Unnamed Organization'}</span>
          {agentCount > 0 && (
            <span style={{ color: '#1890ff', fontSize: '12px', fontWeight: 500 }}>
              ({agentCount})
            </span>
          )}
        </Space>
      );

      return {
        title: orgTitle,
        key: `org-${orgNode.id}`,
        selectable: false,
        children: children,
      };
    };

    // 使用 treeOrgs 构建树形结构
    if (treeOrgs && treeOrgs.length > 0) {
      return treeOrgs
        .map(treeOrg => buildTreeNode(treeOrg))
        .filter((node: DataNode) => {
          // If有Search文本，Filter掉没有匹配代理的根组织
          if (searchText) {
            return node.children && node.children.length > 0;
          }
          return true;
        });
    }

    // If没有组织树，Create一个虚拟根节点IncludeAll agents
    if (agents && agents.length > 0) {
      const filteredAgents = agents.filter((agent: any) => {
        if (!searchText) return true;
        const searchLower = searchText.toLowerCase();
        const agentName = (agent.name || agent.card?.name || '').toLowerCase();
        const agentDesc = (agent.description || agent.card?.description || '').toLowerCase();
        // 模糊匹配：name 或 description IncludeSearch关键字即可
        return agentName.includes(searchLower) || agentDesc.includes(searchLower);
      });

      // Create一个虚拟的"All代理"节点
      return [{
        title: (
          <Space>
            <ApartmentOutlined style={{ color: '#1890ff' }} />
            <span>{t('pages.chat.allAgents')}</span>
            {filteredAgents.length > 0 && (
              <span style={{ color: '#1890ff', fontSize: '12px', fontWeight: 500 }}>
                ({filteredAgents.length})
              </span>
            )}
          </Space>
        ),
        key: 'virtual-root',
        selectable: false,
        children: filteredAgents.map((agent: any) => {
          const agentId = agent.id || agent.card?.id;
          const agentName = agent.name || agent.card?.name || 'Unnamed Agent';
          const isMyTwin = agentId === myTwinAgentId;
          const displayName = isMyTwin 
            ? `${t('pages.chat.myself')}（${agentName}）`
            : agentName;
          
          return {
            title: (
              <Space>
                <UserOutlined style={{ color: '#52c41a' }} />
                <span>{displayName}</span>
              </Space>
            ),
            key: agentId,
            isLeaf: true,
            selectable: true,
          };
        }),
      }];
    }

    return [];
  }, [treeOrgs, agents, searchText, t, myTwinAgentId]);

  // 收集All组织节点的 key Used forExpand
  useEffect(() => {
    const collectOrgKeys = (nodes: DataNode[]): React.Key[] => {
      const keys: React.Key[] = [];
      nodes.forEach(node => {
        if (node.key && (node.key as string).startsWith('org-')) {
          keys.push(node.key);
        }
        if (node.children && node.children.length > 0) {
          keys.push(...collectOrgKeys(node.children));
        }
      });
      return keys;
    };

    if (treeData.length > 0) {
      const allOrgKeys = collectOrgKeys(treeData);
      setExpandedKeys(allOrgKeys);
    }
  }, [treeData]);

  const handleSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const agentId = selectedKeys[0] as string;
      // Don't select org nodes
      if (!agentId.startsWith('org-')) {
        onSelect(agentId);
      }
    }
  };

  const handleClear = () => {
    onSelect(null);
  };

  return (
    <Modal
      title={t('pages.chat.selectAgent')}
      open={visible}
      onCancel={onCancel}
      onOk={() => onCancel()}
      width={600}
      footer={null}
    >
      <div style={{ marginBottom: 16 }}>
        <Input
          placeholder={t('pages.chat.searchAgent')}
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          allowClear
        />
      </div>

      {selectedAgentId && (
        <div style={{ marginBottom: 16 }}>
          <span style={{ marginRight: 8 }}>
            {t('pages.chat.filterApplied')}:
          </span>
          <span style={{ fontWeight: 'bold' }}>
            {agents.find((a) => a.card?.id === selectedAgentId)?.card?.name || selectedAgentId}
          </span>
          <a
            onClick={handleClear}
            style={{ marginLeft: 16 }}
          >
            {t('pages.chat.clearFilter')}
          </a>
        </div>
      )}

      {treeData.length > 0 ? (
        <div style={{ 
          maxHeight: 400, 
          overflow: 'auto',
          background: 'rgba(15, 23, 42, 0.5)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '8px',
          padding: '12px'
        }}>
          <Tree
            treeData={treeData}
            selectedKeys={selectedAgentId ? [selectedAgentId] : []}
            onSelect={handleSelect}
            expandedKeys={expandedKeys}
            onExpand={(keys) => setExpandedKeys(keys)}
            showLine={{ showLeafIcon: false }}
            showIcon={false}
            blockNode
            selectable
          />
        </div>
      ) : (
        <Empty description={t('pages.chat.noAgentsAvailable')} />
      )}
    </Modal>
  );
};

export default AgentFilterModal;

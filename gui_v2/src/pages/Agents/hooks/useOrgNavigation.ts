import { useMemo } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useOrgStore } from '@/stores/orgStore';
import { TreeOrgNode, DisplayNode, OrgAgent } from '../../Orgs/types';
import type { Agent } from '../types';
import { findTreeNodeById, extractAllAgents } from '../utils/orgTreeUtils';
import { buildDoorsForNode, mapOrgAgentToAgent, UNASSIGNED_NODE_ID } from '../utils/agentMappers';

/**
 * 组织导航的自定义 Hook
 * 负责处理组织树导航的所有逻辑
 */
export function useOrgNavigation() {
  const { orgId } = useParams<{ orgId?: string }>();
  const location = useLocation();
  const { treeOrgs } = useOrgStore();

  // 解析嵌套路径中的实际 orgId
  const actualOrgId = useMemo(() => {
    const orgMatches = location.pathname.match(/organization\/([^/]+)/g);
    
    if (orgMatches && orgMatches.length > 0) {
      const lastMatch = orgMatches[orgMatches.length - 1];
      const extractedOrgId = lastMatch.replace('organization/', '');
      return extractedOrgId;
    }
    return orgId;
  }, [location.pathname, orgId]);

  const rootNode = treeOrgs[0];
  const isRootView = !actualOrgId || actualOrgId === 'root';
  const isUnassignedView = actualOrgId === UNASSIGNED_NODE_ID;

  // 获取当前节点
  const currentNode = useMemo(() => {
    if (!rootNode) {
      return null;
    }

    if (isRootView || isUnassignedView) {
      return rootNode;
    }

    return findTreeNodeById(rootNode, actualOrgId!);
  }, [actualOrgId, isRootView, isUnassignedView, rootNode]);

  // 构建当前层级的门列表
  const levelDoors = useMemo(() => {
    if (!rootNode) {
      return [] as DisplayNode[];
    }

    if (isUnassignedView) {
      return [] as DisplayNode[];
    }

    const includeUnassignedDoor = isRootView;
    const targetNode = isRootView ? rootNode : currentNode;

    if (!targetNode) {
      return [] as DisplayNode[];
    }

    return buildDoorsForNode(targetNode, includeUnassignedDoor);
  }, [rootNode, currentNode, isRootView, isUnassignedView]);

  // 获取原始 Agent 数据
  const rawAgents = useMemo(() => {
    if (!rootNode) {
      return [] as OrgAgent[];
    }

    if (isUnassignedView) {
      return rootNode.agents || [];
    }

    if (!actualOrgId || !currentNode) {
      return [] as OrgAgent[];
    }

    return currentNode.agents || [];
  }, [rootNode, currentNode, isUnassignedView, actualOrgId]);

  // 转换为展示用的 Agent 数据
  const agentsForDisplay = useMemo(() => {
    const currentOrgId = isUnassignedView ? undefined : actualOrgId;
    return rawAgents.map((agent) => mapOrgAgentToAgent(agent, currentOrgId));
  }, [rawAgents, actualOrgId, isUnassignedView]);

  return {
    actualOrgId,
    rootNode,
    currentNode,
    isRootView,
    isUnassignedView,
    levelDoors,
    rawAgents,
    agentsForDisplay,
  };
}

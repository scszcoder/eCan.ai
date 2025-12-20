import { get_ipc_api } from '@/services/ipc_api';

export type QueryGraphsResult = {
  nodes: Array<{ id: string; labels: string[]; properties: Record<string, any> }>;
  edges: Array<{ id: string; source: string; target: string; type?: string; properties: Record<string, any> }>;
  is_truncated?: boolean;
} | null;

export async function queryGraphs(label: string, maxDepth: number, maxNodes: number): Promise<QueryGraphsResult> {
  const payload = { label, maxDepth, maxNodes };
  try {
    // Use standard IPC call via lightragApi
    const response = await get_ipc_api().lightragApi.queryGraphs(payload);
    if (response.success && response.data) {
        return response.data as any;
    }
    return { nodes: [], edges: [], is_truncated: false };
  } catch (e) {
    console.error('Query graphs error:', e);
    return { nodes: [], edges: [], is_truncated: false };
  }
}

/**
 * 获取热门标签列表
 */
export async function getPopularLabels(limit: number = 10): Promise<string[]> {
  try {
    const response = await get_ipc_api().lightragApi.getPopularLabels({ limit });
    if (response.success && response.data) {
      const result = response.data as any;
      if (Array.isArray(result)) {
        return result;
      }
    }
    return [];
  } catch (e) {
    console.error('Get popular labels error:', e);
    return [];
  }
}

/**
 * 搜索标签
 */
export async function searchLabels(query: string, limit: number = 20): Promise<string[]> {
  try {
    const response = await get_ipc_api().lightragApi.searchLabels({ query, limit });
    if (response.success && response.data) {
      const result = response.data as any;
      if (Array.isArray(result)) {
        return result;
      }
    }
    return [];
  } catch (e) {
    console.error('Search labels error:', e);
    return [];
  }
}

/**
 * 扩展节点 - 查询节点的邻居并添加到图中
 */
export async function expandNode(nodeId: string, maxDepth: number = 1, maxNodes: number = 50): Promise<QueryGraphsResult> {
  try {
    const response = await get_ipc_api().lightragApi.expandNode({ nodeId, maxDepth, maxNodes });
    if (response.success && response.data) {
      return response.data as any;
    }
    return { nodes: [], edges: [], is_truncated: false };
  } catch (e) {
    console.error('Expand node error:', e);
    return { nodes: [], edges: [], is_truncated: false };
  }
}

/**
 * 修剪节点 - 从图中移除节点及其相关边
 */
export async function pruneNode(nodeId: string): Promise<{ success: boolean; message?: string }> {
  try {
    const response = await get_ipc_api().lightragApi.pruneNode({ nodeId });
    if (response.success) {
      const data = response.data as any;
      return { success: true, message: data?.message };
    }
    return { success: false, message: response.error?.message };
  } catch (e: any) {
    console.error('Prune node error:', e);
    return { success: false, message: e?.message || 'Unknown error' };
  }
}

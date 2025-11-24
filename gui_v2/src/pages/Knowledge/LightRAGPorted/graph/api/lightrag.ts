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
    const response = await get_ipc_api().lightragApi.getGraphLabelList();
    if (response.success && response.data) {
      const result = response.data as any;
      if (result && Array.isArray(result.data)) {
        return result.data.slice(0, limit);
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
    const response = await get_ipc_api().lightragApi.getGraphLabelList();
    if (response.success && response.data) {
      const result = response.data as any;
      if (result && Array.isArray(result.data)) {
        const normalizedQuery = query.toLowerCase();
        return result.data
          .filter((label: string) => label.toLowerCase().includes(normalizedQuery))
          .slice(0, limit);
      }
    }
    return [];
  } catch (e) {
    console.error('Search labels error:', e);
    return [];
  }
}

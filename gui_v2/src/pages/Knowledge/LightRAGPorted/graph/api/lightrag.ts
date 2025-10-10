import { get_ipc_api } from '@/services/ipc_api';

export type QueryGraphsResult = {
  nodes: Array<{ id: string; labels: string[]; properties: Record<string, any> }>;
  edges: Array<{ id: string; source: string; target: string; type?: string; properties: Record<string, any> }>;
  is_truncated?: boolean;
} | null;

export async function queryGraphs(label: string, maxDepth: number, maxNodes: number): Promise<QueryGraphsResult> {
  const api: any = get_ipc_api();
  const payload = { label, maxDepth, maxNodes };
  if (api?.lightrag?.queryGraphs) {
    return api.lightrag.queryGraphs(payload);
  }
  // Fallback: no handler wired
  return { nodes: [], edges: [], is_truncated: false };
}

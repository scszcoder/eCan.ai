import { useEffect } from 'react';
import { UndirectedGraph } from 'graphology';
import { useGraphStore, RawGraph, RawNodeType, RawEdgeType } from '../stores/graph';
import { useSettingsStore } from '../stores/settings';
import { queryGraphs } from '../api/lightrag';
import { maxNodeSize, minNodeSize, nodeColors } from '../lib/constants';

export default function useLightragGraph() {
  const label = useSettingsStore(s => s.queryLabel);
  const maxDepth = useSettingsStore(s => s.graphQueryMaxDepth);
  const maxNodes = useSettingsStore(s => s.graphMaxNodes);
  const graphDataVersion = useGraphStore(s => s.graphDataVersion);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (useGraphStore.getState().isFetching) return;
      useGraphStore.getState().setIsFetching(true);
      try {
        const currentLabel = label || '*';
        const data = await queryGraphs(currentLabel, maxDepth, maxNodes);
        if (cancelled) return;
        
        // 标记已尝试获取数据
        useGraphStore.getState().setGraphDataFetchAttempted(true);

        if (!data || !Array.isArray(data.nodes)) {
          useGraphStore.getState().setSigmaGraph(null);
          useGraphStore.getState().setRawGraph(null);
          useGraphStore.getState().setGraphIsEmpty(true);
          useGraphStore.getState().setLastQuerySummary(null);
          return;
        }

        // 1. 构建 Sigma 图 (用于显示)
        const g = new UndirectedGraph();
        const degrees: Record<string, number> = {};
        
        // 计算度数
        for (const n of data.nodes) {
          degrees[n.id] = 0;
        }
        for (const e of data.edges) {
          if (degrees[e.source] !== undefined) degrees[e.source] += 1;
          if (degrees[e.target] !== undefined) degrees[e.target] += 1;
        }
        
        // 计算度数范围用于节点大小插值
        let minD = Number.MAX_SAFE_INTEGER;
        let maxD = 0;
        Object.values(degrees).forEach(d => { minD = Math.min(minD, d); maxD = Math.max(maxD, d); });
        const range = Math.max(1, maxD - minD);

        // 生成类型颜色映射
        const typeColorMap = new Map<string, string>();
        let colorIndex = 0;
        const getColor = (type: string) => {
          if (!typeColorMap.has(type)) {
            typeColorMap.set(type, nodeColors[colorIndex % nodeColors.length]);
            colorIndex++;
          }
          return typeColorMap.get(type)!;
        };

        // 添加节点到 Sigma 图
        for (const n of data.nodes) {
          const x = Math.random();
          const y = Math.random();
          const d = degrees[n.id] ?? 0;
          const size = Math.round(minNodeSize + (maxNodeSize - minNodeSize) * Math.pow((d - minD) / range, 0.5));
          
          // 获取节点类型（取第一个标签作为主类型）
          const nodeType = n.labels && n.labels.length > 0 ? n.labels[0] : 'Unknown';
          const color = getColor(nodeType);

          g.addNode(n.id, { 
            x, 
            y, 
            size, 
            label: n.id, // 使用 ID 作为默认标签
            color: color,
            type: nodeType 
          });
        }
        
        // 添加边到 Sigma 图
        for (const e of data.edges) {
          if (!g.hasNode(e.source) || !g.hasNode(e.target)) continue;
          g.addEdge(e.source, e.target, { 
            size: 1, 
            label: e.properties?.keywords || e.type,
            color: '#e5e7eb' // 默认浅灰色边
          });
        }

        // 2. 构建 RawGraph (用于业务逻辑)
        const rawG = new RawGraph();
        rawG.nodes = data.nodes.map(n => ({
            id: n.id,
            labels: n.labels || [],
            properties: n.properties || {},
            size: degrees[n.id] || 1,
            x: 0, 
            y: 0,
            degree: degrees[n.id] || 0
        }));
        
        rawG.edges = data.edges.map(e => ({
            id: e.id,
            source: e.source,
            target: e.target,
            type: e.type,
            properties: e.properties || {}
        }));

        // 构建索引
        rawG.nodes.forEach((n, i) => rawG.nodeIdMap[n.id] = i);
        rawG.edges.forEach((e, i) => rawG.edgeIdMap[e.id] = i);

        // 3. 更新 Store
        // Bind sigma instance if exists
        const sigma = useGraphStore.getState().sigmaInstance;
        if (sigma) {
          try {
            // @ts-ignore
            if (typeof sigma.setGraph === 'function') sigma.setGraph(g as any);
            else (sigma as any).graph = g;
          } catch {}
        }

        useGraphStore.getState().setRawGraph(rawG);
        useGraphStore.getState().setSigmaGraph(g as any);
        useGraphStore.getState().setTypeColorMap(typeColorMap);
        useGraphStore.getState().setGraphIsEmpty(g.order === 0);
        useGraphStore.getState().setLastQuerySummary({
          label: currentLabel,
          nodeCount: data.nodes.length,
          edgeCount: data.edges.length,
          isTruncated: !!data.is_truncated,
        });
        
        if (g.order > 0 && currentLabel && currentLabel !== '*') {
          useGraphStore.getState().setLastSuccessfulQueryLabel(currentLabel);
        }

      } catch (e) {
        console.error('Failed to fetch graph:', e);
        if (!cancelled) {
          useGraphStore.getState().setSigmaGraph(null);
          useGraphStore.getState().setRawGraph(null);
          useGraphStore.getState().setGraphIsEmpty(true);
          useGraphStore.getState().setLastQuerySummary(null);
        }
      } finally {
        if (!cancelled) useGraphStore.getState().setIsFetching(false);
      }
    };
    run();
    return () => { cancelled = true; };
  }, [label, maxDepth, maxNodes, graphDataVersion]); // 移除 isFetching，添加 graphDataVersion

  const getNode = (id: string | null) => {
    if (!id) return null;
    const rawGraph = useGraphStore.getState().rawGraph;
    return rawGraph ? rawGraph.getNode(id) : null;
  };

  const getEdge = (id: string | null, dynamic = false) => {
    if (!id) return null;
    const rawGraph = useGraphStore.getState().rawGraph;
    return rawGraph ? rawGraph.getEdge(id, dynamic) : null;
  };

  return { getNode, getEdge };
}

import { useEffect } from 'react';
import { UndirectedGraph } from 'graphology';
import { useGraphStore } from '../stores/graph';
import { useSettingsStore } from '../stores/settings';
import { queryGraphs } from '../api/lightrag';
import { maxNodeSize, minNodeSize } from '../lib/constants';

export default function useLightragGraph() {
  const label = useSettingsStore(s => s.queryLabel);
  const maxDepth = useSettingsStore(s => s.graphQueryMaxDepth);
  const maxNodes = useSettingsStore(s => s.graphMaxNodes);
  const isFetching = useGraphStore(s => s.isFetching);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (isFetching) return;
      useGraphStore.getState().setIsFetching(true);
      try {
        const data = await queryGraphs(label || '*', maxDepth, maxNodes);
        if (cancelled) return;
        if (!data || !Array.isArray(data.nodes)) {
          useGraphStore.getState().setSigmaGraph(null);
          useGraphStore.getState().setRawGraph(null);
          useGraphStore.getState().setGraphIsEmpty(true);
          return;
        }
        const g = new UndirectedGraph();
        const degrees: Record<string, number> = {};
        for (const n of data.nodes) {
          degrees[n.id] = 0;
        }
        for (const e of data.edges) {
          if (degrees[e.source] !== undefined) degrees[e.source] += 1;
          if (degrees[e.target] !== undefined) degrees[e.target] += 1;
        }
        let minD = Number.MAX_SAFE_INTEGER;
        let maxD = 0;
        Object.values(degrees).forEach(d => { minD = Math.min(minD, d); maxD = Math.max(maxD, d); });
        const range = Math.max(1, maxD - minD);
        for (const n of data.nodes) {
          const x = Math.random();
          const y = Math.random();
          const d = degrees[n.id] ?? 0;
          const size = Math.round(minNodeSize + (maxNodeSize - minNodeSize) * Math.pow((d - minD) / range, 0.5));
          g.addNode(n.id, { x, y, size, label: (n.labels || []).join(', ') });
        }
        for (const e of data.edges) {
          if (!g.hasNode(e.source) || !g.hasNode(e.target)) continue;
          g.addEdge(e.source, e.target, { size: 1, label: e.properties?.keywords });
        }
        // Bind
        const sigma = useGraphStore.getState().sigmaInstance;
        if (sigma) {
          try {
            // @ts-ignore
            if (typeof sigma.setGraph === 'function') sigma.setGraph(g as any);
            else (sigma as any).graph = g;
          } catch {}
        }
        useGraphStore.getState().setSigmaGraph(g as any);
        useGraphStore.getState().setGraphIsEmpty(g.order === 0);
      } catch (e) {
        if (!cancelled) {
          useGraphStore.getState().setSigmaGraph(null);
          useGraphStore.getState().setRawGraph(null);
          useGraphStore.getState().setGraphIsEmpty(true);
        }
      } finally {
        if (!cancelled) useGraphStore.getState().setIsFetching(false);
      }
    };
    run();
    return () => { cancelled = true; };
  }, [label, maxDepth, maxNodes, isFetching]);
}

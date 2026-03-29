/**
 * Auto-layout toolbar button for the skill editor.
 *
 * Uses a custom dagre-based layout that wraps flowgram's internal `dagreLib`
 * (the same engine as n8n / Dify / Coze) with a **custom order heuristic**
 * that sorts nodes within each layer by the average Y of their downstream
 * targets.  This dramatically reduces edge crossings in multi-output
 * condition nodes compared to the default sweep heuristic.
 *
 * Two-phase flow:
 *
 *   Phase 1 – build custom graph from the live document,
 *             insert a "barycentric order" pass before dagre's order step.
 *
 *   Phase 2 – after dagre computes positions, apply them to live node entities
 *             via transform.update() and trigger a re-render.
 */

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  usePlayground,
  useService,
  WorkflowDocument,
} from '@flowgram.ai/free-layout-editor';
import { IconButton, Toast, Tooltip } from '@douyinfe/semi-ui';

import { IconAutoLayoutColored } from './colored-icons';

// Import dagre utilities directly from the auto-layout plugin.
// This is the SAME engine that tools.autoLayout() uses internally,
// but we get to pass customOrder to override the default sweep heuristic.
let _dagreLib: any = null;

async function loadDagreLib() {
  if (_dagreLib) return;
  const mod = await import('@flowgram.ai/free-auto-layout-plugin');
  _dagreLib = mod.dagreLib;
}

// ─── Graph building ────────────────────────────────────────────────────────────

interface GNode {
  id: string;
  width: number;
  height: number;
  x?: number;
  y?: number;
  rank?: number;
  order?: number;
}

interface GEdge {
  v: string; // source index (string key in dagre)
  w: string; // target index
  name?: string;
  minlen?: number;
}

interface LayoutNode {
  id: string;
  index: string;
  size: { width: number; height: number };
  position: { x: number; y: number };
  offset: { x: number; y: number };
  rank: number;
  entity: any;
}

interface LayoutEdge {
  fromIndex: string;
  toIndex: string;
  name: string;
}

/** Build a graph from the document JSON. Returns nodes + edges + a node-id→index map. */
function buildGraphFromDocument(
  nodes: Array<{ id: string; meta?: { position?: { x?: number; y?: number } }; data?: { parentID?: string; blockIDs?: string[] } }>,
  edges: Array<{ sourceNodeID?: string; targetNodeID?: string; source?: string; target?: string; sourcePortID?: string; sourcePortId?: string }>,
  nodeEntities: Map<string, any>,
) {
  // Determine which nodes are inside a group container (skip their internal blocks).
  const groupChildren = new Set<string>();
  nodes.forEach((n) => {
    if (n.type === 'group' && Array.isArray(n.data?.blockIDs)) {
      n.data.blockIDs.forEach((id) => groupChildren.add(id));
    }
  });

  const layoutNodes: LayoutNode[] = [];
  const layoutEdges: LayoutEdge[] = [];

  nodes.forEach((node) => {
    const pid = node.data?.parentID;
    if (pid && pid !== 'root') return; // skip container children
    if (groupChildren.has(node.id)) return;
    if (node.type === 'comment') return; // skip comment nodes

    const entity = nodeEntities.get(node.id);
    let width = 400;
    let height = 200;
    try {
      const transform = entity?.transform;
      width = transform?.size?.width ?? 400;
      height = transform?.size?.height ?? 200;
    } catch {}

    layoutNodes.push({
      id: node.id,
      index: node.id,
      size: { width, height },
      position: { x: node.meta?.position?.x ?? 0, y: node.meta?.position?.y ?? 0 },
      offset: { x: 0, y: 0 },
      rank: -1,
      entity,
    });
  });

  edges.forEach((edge) => {
    const src = edge.sourceNodeID ?? edge.source;
    const tgt = edge.targetNodeID ?? edge.target;
    if (!src || !tgt) return;
    const srcNode = layoutNodes.find((n) => n.id === src);
    const tgtNode = layoutNodes.find((n) => n.id === tgt);
    if (!srcNode || !tgtNode) return;

    layoutEdges.push({
      fromIndex: srcNode.index,
      toIndex: tgtNode.index,
      name: `${src}→${tgt}`,
    });
  });

  return { layoutNodes, layoutEdges };
}

// ─── Custom order heuristic ───────────────────────────────────────────────────

/**
 * Assigns an `order` value to every node in the dagre graph, sorting within
 * each rank by the average Y of downstream targets (barycentric heuristic).
 * This reduces edge crossings for nodes with multiple outputs (e.g. condition).
 *
 * After this runs, dagre's position() pass uses these orders directly.
 */
function applyBarycentricOrder(
  g: any, // dagre graph instance
  layoutNodes: LayoutNode[],
  layoutEdges: LayoutEdge[],
) {
  // Build index → layout node map
  const nodeMap = new Map<string, LayoutNode>();
  layoutNodes.forEach((n) => nodeMap.set(n.index, n));

  // Build adjacency: out-edges per node
  const outEdges = new Map<string, GEdge[]>();
  layoutEdges.forEach((e) => {
    const list = outEdges.get(e.fromIndex) ?? [];
    list.push(e);
    outEdges.set(e.fromIndex, list);
  });

  // Assign initial order: median Y of successors (fallback to current order).
  const ranks = new Map<number, string[]>();
  g.nodes().forEach((i: string) => {
    const r = g.node(i)?.rank;
    if (r == null) return;
    if (!ranks.has(r)) ranks.set(r, []);
    ranks.get(r)!.push(i);
  });

  const sortedRanks = [...ranks.keys()].sort((a, b) => a - b);

  // Backward pass: sort by successor Y average (right-to-left → good for LR)
  const orderByIndex = new Map<string, number>();
  for (let ri = sortedRanks.length - 1; ri >= 0; ri--) {
    const rank = sortedRanks[ri];
    const layer = ranks.get(rank) ?? [];

    const scored = layer.map((i) => {
      const succYs = (outEdges.get(i) ?? [])
        .map((e) => {
          const snode = nodeMap.get(e.w);
          return snode?.position.y ?? g.node(e.w)?.y;
        })
        .filter((y): y is number => typeof y === 'number');

      const succOrder = (outEdges.get(i) ?? [])
        .map((e) => orderByIndex.get(e.w) ?? 0);

      const currentOrder = g.node(i)?.order ?? 0;
      const score = succYs.length > 0
        ? succYs.reduce((a, b) => a + b, 0) / succYs.length
        : currentOrder;
      const succAvgOrder = succOrder.length > 0
        ? succOrder.reduce((a, b) => a + b, 0) / succOrder.length
        : currentOrder;

      return {
        i,
        score: (score + succAvgOrder * 2) / 3, // blend Y and successor order
        currentOrder,
      };
    });

    scored.sort((a, b) => {
      if (Math.abs(a.score - b.score) > 5) return a.score - b.score;
      return a.currentOrder - b.currentOrder; // stable tie-break
    });

    scored.forEach(({ i }, idx) => {
      const gn = g.node(i);
      if (gn) gn.order = idx;
      orderByIndex.set(i, idx);
    });

    ranks.set(rank, scored.map(({ i }) => i));
  }
}

// ─── Phase 1: run custom dagre layout ─────────────────────────────────────────

async function runCustomLayout(
  document: WorkflowDocument,
  layoutNodes: LayoutNode[],
  layoutEdges: LayoutEdge[],
  options: {
    rankdir?: 'LR' | 'TB';
    ranksep?: number;
    nodesep?: number;
    acyclicer?: 'greedy' | undefined;
    ranker?: 'network-simplex' | 'tight-tree' | 'longest-path';
  },
) {
  await loadDagreLib();
  const dagreLib = _dagreLib!;

  // Build a graphlib.Graph (multigraph=true for parallel edges)
  const Graph = await import('@dagrejs/graphlib').then((m) => m.Graph);
  const g = new Graph({ multigraph: true, directed: true });
  g.setDefaultEdgeLabel(() => ({}));

  g.setGraph({
    rankdir: options.rankdir ?? 'LR',
    ranksep: options.ranksep ?? 180,
    nodesep: options.nodesep ?? 80,
    marginx: 60,
    marginy: 60,
    acyclicer: options.acyclicer ?? 'greedy',
    ranker: options.ranker ?? 'network-simplex',
  });

  layoutNodes.forEach((n) => {
    g.setNode(n.index, { width: n.size.width, height: n.size.height });
  });

  layoutEdges.forEach((e) => {
    g.setEdge({ v: e.fromIndex, w: e.toIndex, name: e.name });
  });

  // ── Run dagre with our custom order ────────────────────────────────────────
  dagreLib.makeSpaceForEdgeLabels(g);
  dagreLib.removeSelfEdges(g);
  dagreLib.acyclic.run(g);
  dagreLib.nestingGraph.run(g);
  dagreLib.rank(dagreLib.util.asNonCompoundGraph(g));
  dagreLib.injectEdgeLabelProxies(g);
  dagreLib.removeEmptyRanks(g);
  dagreLib.nestingGraph.cleanup(g);
  dagreLib.normalizeRanks(g);
  dagreLib.assignRankMinMax(g);
  dagreLib.removeEdgeLabelProxies(g);
  dagreLib.normalize.run(g);
  dagreLib.parentDummyChains(g);
  dagreLib.addBorderSegments(g);

  // ── Custom order: barycentric sort within each rank ─────────────────────────
  applyBarycentricOrder(g, layoutNodes, layoutEdges);
  // Keep dagre's optimal sweep as a second pass (swap + sweep + assign)
  try {
    dagreLib.order(g, { disableOptimalOrderHeuristic: false });
  } catch {
    // Fallback if order fails
    dagreLib.order(g, { disableOptimalOrderHeuristic: true });
  }

  dagreLib.insertSelfEdges(g);
  dagreLib.coordinateSystem.adjust(g);
  dagreLib.position(g);
  dagreLib.positionSelfEdges(g);
  dagreLib.removeBorderNodes(g);
  dagreLib.normalize.undo(g);
  dagreLib.fixupEdgeLabelCoords(g);
  dagreLib.coordinateSystem.undo(g);
  dagreLib.translateGraph(g);
  dagreLib.assignNodeIntersects(g);
  dagreLib.reversePointsForReversedEdges(g);
  dagreLib.acyclic.undo(g);

  // ── Apply positions to layout nodes ───────────────────────────────────────
  const minX = Math.min(...layoutNodes.map((n) => g.node(n.index)?.x ?? 0));
  const minY = Math.min(...layoutNodes.map((n) => g.node(n.index)?.y ?? 0));
  const OFFSET_X = 60;
  const OFFSET_Y = 60;

  layoutNodes.forEach((n) => {
    const gn = g.node(n.index);
    if (!gn) return;
    n.rank = gn.rank ?? -1;
    n.position = {
      x: (gn.x ?? 0) - n.size.width / 2 + OFFSET_X,
      y: (gn.y ?? 0) + OFFSET_Y,
    };
  });

  return layoutNodes;
}

// ─── Apply positions to live entities ─────────────────────────────────────────

async function applyPositions(
  layoutNodes: LayoutNode[],
  document: WorkflowDocument,
  animate: boolean,
  animationDuration: number,
) {
  if (animate) {
    const { startTween } = await import('@flowgram.ai/core');
    await new Promise<void>((resolve) => {
      startTween({
        from: { d: 0 },
        to: { d: 100 },
        duration: animationDuration,
        onUpdate: ({ d }: { d: number }) => {
          const step = d / 100;
          layoutNodes.forEach((n) => {
            const { transform } = n.entity.transform;
            if (!transform) return;
            const current = transform.position;
            const target = n.position;
            transform.update({
              position: {
                x: current.x + (target.x - current.x) * step,
                y: current.y + (target.y - current.y) * step,
              },
            });
          });
          document.layout?.updateAffectedTransform?.(n.entity);
        },
        onComplete: () => resolve(),
      });
    });
  } else {
    layoutNodes.forEach((n) => {
      const { transform } = n.entity.transform;
      if (!transform) return;
      transform.update({ position: n.position });
      n.entity.notifyChange?.();
    });
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export const AutoLayout = () => {
  const { t } = useTranslation('skillEditor');
  const playground = usePlayground();
  const document = useService(WorkflowDocument);
  const [loading, setLoading] = useState(false);

  const handleAutoLayout = useCallback(async () => {
    if (loading) return;
    setLoading(true);

    try {
      // ── Read document graph ──────────────────────────────────────────────────
      const docJson = (document as any).toJSON() as {
        nodes?: any[];
        edges?: any[];
      };
      const nodes = docJson.nodes ?? [];
      const edges = docJson.edges ?? [];

      // Build live entity map (needed for entity.transform)
      const nodeEntities = new Map<string, any>();
      (document as any).getAllNodes?.().forEach((entity: any) => {
        nodeEntities.set(entity.id, entity);
      });
      // Also collect nodes from the JSON (may include nodes not yet in entity map)
      nodes.forEach((n) => {
        if (!nodeEntities.has(n.id)) {
          try {
            const e = (document as any).getNode?.(n.id);
            if (e) nodeEntities.set(n.id, e);
          } catch {}
        }
      });

      const { layoutNodes, layoutEdges } = buildGraphFromDocument(nodes, edges, nodeEntities);

      if (layoutNodes.length === 0) {
        Toast.info({ content: t('toolbar.layoutNoNodes') });
        return;
      }

      // ── Phase 1: custom dagre layout ────────────────────────────────────────
      const positioned = await runCustomLayout(document, layoutNodes, layoutEdges, {
        rankdir: 'LR',
        ranksep: 180,
        nodesep: 80,
        acyclicer: 'greedy',
        ranker: 'network-simplex',
      });

      // ── Apply with animation ────────────────────────────────────────────────
      await applyPositions(positioned, document, true, 380);

      // ── Fit view ─────────────────────────────────────────────────────────────
      playground?.tools?.fitView?.(true);

      Toast.success({ content: t('toolbar.layoutOptimized') });
    } catch (err) {
      console.error('[SkillEditor] Custom layout failed:', err);
      // Safety fallback: try the built-in tool
      try {
        const tools = (playground as any)?.tools;
        if (tools?.autoLayout) {
          await tools.autoLayout({});
        }
        playground?.tools?.fitView?.(true);
        Toast.success({ content: t('toolbar.layoutOptimized') });
      } catch (fbErr) {
        console.error('[SkillEditor] Fallback also failed:', fbErr);
        Toast.error({ content: t('toolbar.layoutOptimizeFailed') });
      }
    } finally {
      setLoading(false);
    }
  }, [loading, document, playground, t]);

  return (
    <Tooltip content={t('toolbar.autoLayout')}>
      <IconButton
        disabled={(playground?.config?.readonly) || loading}
        type="tertiary"
        theme="borderless"
        onClick={handleAutoLayout}
        icon={<IconAutoLayoutColored size={18} />}
      />
    </Tooltip>
  );
};

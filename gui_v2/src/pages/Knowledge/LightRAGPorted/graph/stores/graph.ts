import { create } from 'zustand';
import { Sigma } from 'sigma';
import type { UndirectedGraph } from 'graphology';

export type RawNodeType = {
  id: string;
  labels: string[];
  properties: Record<string, any>;
  size: number;
  x: number;
  y: number;
  color?: string;
  degree?: number;
};

export type RawEdgeType = {
  id: string;
  source: string;
  target: string;
  type?: string;
  properties: Record<string, any>;
  dynamicId?: string;
};

export class RawGraph {
  nodes: RawNodeType[] = [];
  edges: RawEdgeType[] = [];
  nodeIdMap: Record<string, number> = {};
  edgeIdMap: Record<string, number> = {};
  getNode(id: string) { return this.nodes[this.nodeIdMap[id]]; }
  getEdge(id: string, dynamic = false) {
    if (dynamic) return this.edges.find(e => e.dynamicId === id) || null as any;
    return this.edges[this.edgeIdMap[id]];
  }
  buildDynamicMap() {/* no-op for now */}
}

interface GraphState {
  sigmaInstance: Sigma | null;
  sigmaGraph: UndirectedGraph | null;
  rawGraph: RawGraph | null;
  selectedNode: string | null;
  focusedNode: string | null;
  selectedEdge: string | null;
  focusedEdge: string | null;
  isFetching: boolean;
  graphIsEmpty: boolean;
  moveToSelectedNode: boolean;
  // actions
  setSigmaInstance: (s: Sigma | null) => void;
  setSigmaGraph: (g: UndirectedGraph | null) => void;
  setRawGraph: (g: RawGraph | null) => void;
  setSelectedNode: (id: string | null, move?: boolean) => void;
  setFocusedNode: (id: string | null) => void;
  setSelectedEdge: (id: string | null) => void;
  setFocusedEdge: (id: string | null) => void;
  setIsFetching: (v: boolean) => void;
  setGraphIsEmpty: (v: boolean) => void;
  setMoveToSelectedNode: (v: boolean) => void;
  clearSelection: () => void;
  reset: () => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  sigmaInstance: null,
  sigmaGraph: null,
  rawGraph: null,
  selectedNode: null,
  focusedNode: null,
  selectedEdge: null,
  focusedEdge: null,
  isFetching: false,
  graphIsEmpty: false,
  moveToSelectedNode: false,
  setSigmaInstance: (s) => set({ sigmaInstance: s }),
  setSigmaGraph: (g) => set({ sigmaGraph: g }),
  setRawGraph: (g) => set({ rawGraph: g }),
  setSelectedNode: (id, move=false) => set({ selectedNode: id, focusedNode: id ?? null, moveToSelectedNode: !!move }),
  setFocusedNode: (id) => set({ focusedNode: id }),
  setSelectedEdge: (id) => set({ selectedEdge: id, focusedEdge: id ?? null }),
  setFocusedEdge: (id) => set({ focusedEdge: id }),
  setIsFetching: (v) => set({ isFetching: v }),
  setGraphIsEmpty: (v) => set({ graphIsEmpty: v }),
  setMoveToSelectedNode: (v) => set({ moveToSelectedNode: v }),
  clearSelection: () => set({ selectedNode: null, focusedNode: null, selectedEdge: null, focusedEdge: null }),
  reset: () => set({ sigmaGraph: null, rawGraph: null, selectedNode: null, focusedNode: null, selectedEdge: null, focusedEdge: null, moveToSelectedNode: false })
}));

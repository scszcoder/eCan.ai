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
  graphDataVersion: number;
  searchEngine: any | null; // MiniSearch instance
  typeColorMap: Map<string, string>;
  graphDataFetchAttempted: boolean;
  lastSuccessfulQueryLabel: string;
  lastQuerySummary: {
    label: string;
    nodeCount: number;
    edgeCount: number;
    isTruncated: boolean;
  } | null;
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
  incrementGraphDataVersion: () => void;
  updateNodeAndSelect: (id: string, entityId: string | undefined, prop: string, val: any) => void;
  updateEdgeAndSelect: (id: string, dynamicId: string | undefined, source: string, target: string, prop: string, val: any) => void;
  setSearchEngine: (engine: any) => void;
  resetSearchEngine: () => void;
  setTypeColorMap: (map: Map<string, string>) => void;
  setGraphDataFetchAttempted: (v: boolean) => void;
  setLastSuccessfulQueryLabel: (label: string) => void;
  clearSelection: () => void;
  reset: () => void;
  setLastQuerySummary: (summary: GraphState['lastQuerySummary']) => void;
}

export const useGraphStore = create<GraphState>((set, get) => ({
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
  graphDataVersion: 0,
  searchEngine: null,
  typeColorMap: new Map(),
  graphDataFetchAttempted: false,
  lastSuccessfulQueryLabel: '',
  lastQuerySummary: null,
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
  incrementGraphDataVersion: () => set((state) => ({ graphDataVersion: state.graphDataVersion + 1 })),
  setSearchEngine: (engine) => set({ searchEngine: engine }),
  resetSearchEngine: () => set({ searchEngine: null }),
  setTypeColorMap: (map) => set({ typeColorMap: map }),
  setGraphDataFetchAttempted: (v) => set({ graphDataFetchAttempted: v }),
  setLastSuccessfulQueryLabel: (label) => set({ lastSuccessfulQueryLabel: label }),
  setLastQuerySummary: (summary) => set({ lastQuerySummary: summary }),
  
  updateNodeAndSelect: (id, entityId, prop, val) => {
    const { rawGraph, sigmaGraph } = get();
    if (rawGraph) {
      const node = rawGraph.getNode(id);
      if (node) {
        // Update property
        node.properties[prop] = val;
        
        // If renaming entity_id, we might want to update label in sigmaGraph if it matches
        if (prop === 'entity_id' && sigmaGraph && sigmaGraph.hasNode(id)) {
           // Assuming label often mirrors entity_id or name
           // sigmaGraph.setNodeAttribute(id, 'label', val); 
        }
      }
    }
    set((state) => ({ 
      graphDataVersion: state.graphDataVersion + 1,
      selectedNode: id 
    }));
  },

  updateEdgeAndSelect: (id, dynamicId, source, target, prop, val) => {
    const { rawGraph } = get();
    if (rawGraph) {
      const edge = rawGraph.getEdge(id); // ID here is raw ID usually
      if (edge) {
        edge.properties[prop] = val;
      }
    }
    set((state) => ({ 
      graphDataVersion: state.graphDataVersion + 1,
      selectedEdge: id 
    }));
  },

  clearSelection: () => set({ selectedNode: null, focusedNode: null, selectedEdge: null, focusedEdge: null }),
  reset: () => set({ 
    sigmaGraph: null, 
    rawGraph: null, 
    selectedNode: null, 
    focusedNode: null, 
    selectedEdge: null, 
    focusedEdge: null, 
    moveToSelectedNode: false, 
    graphDataVersion: 0,
    searchEngine: null,
    typeColorMap: new Map(),
    graphDataFetchAttempted: false,
    lastSuccessfulQueryLabel: '',
    lastQuerySummary: null
  })
}));

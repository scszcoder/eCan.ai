import { create } from 'zustand';

interface SettingsState {
  theme: 'light' | 'dark' | 'system';
  showPropertyPanel: boolean;
  showNodeSearchBar: boolean;
  enableNodeDrag: boolean;
  showLegend: boolean;
  enableEdgeEvents: boolean;
  enableHideUnselectedEdges: boolean;
  showEdgeLabel: boolean;
  showNodeLabel: boolean;
  minEdgeSize: number;
  maxEdgeSize: number;
  graphLayoutMaxIterations: number;
  graphQueryMaxDepth: number;
  graphMaxNodes: number;
  queryLabel: string;
  setQueryLabel: (v: string) => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  theme: 'light',
  showPropertyPanel: true,
  showNodeSearchBar: true,
  enableNodeDrag: true,
  showLegend: false,
  enableEdgeEvents: true,
  enableHideUnselectedEdges: false,
  showEdgeLabel: false,
  showNodeLabel: true,
  minEdgeSize: 1,
  maxEdgeSize: 4,
  graphLayoutMaxIterations: 200,
  graphQueryMaxDepth: 1,
  graphMaxNodes: 400,
  queryLabel: '*',
  setQueryLabel: (v) => set({ queryLabel: v }),
}));

/**
 * Store for Open skill picker state.
 * This lives outside the component tree to persist state across error boundary recoveries.
 */
import { create } from 'zustand';

type SkillFileItem = {
  filePath: string;
  fileName?: string;
  fileSize?: number;
  skillName?: string;
  updatedAt?: string;
};

interface OpenPickerState {
  visible: boolean;
  loading: boolean;
  openLoading: boolean;
  query: string;
  items: SkillFileItem[];
  selectedItem: SkillFileItem | null;
  workflowDocument: any | null; // Store the document reference here
  
  setVisible: (visible: boolean) => void;
  setLoading: (loading: boolean) => void;
  setOpenLoading: (loading: boolean) => void;
  setQuery: (query: string) => void;
  setItems: (items: SkillFileItem[]) => void;
  setSelectedItem: (item: SkillFileItem | null) => void;
  setWorkflowDocument: (doc: any) => void;
  reset: () => void;
}

export const useOpenPickerStore = create<OpenPickerState>((set) => ({
  visible: false,
  loading: false,
  openLoading: false,
  query: '',
  items: [],
  selectedItem: null,
  workflowDocument: null,
  
  setVisible: (visible) => set({ visible }),
  setLoading: (loading) => set({ loading }),
  setOpenLoading: (openLoading) => set({ openLoading }),
  setQuery: (query) => set({ query }),
  setItems: (items) => set({ items }),
  setSelectedItem: (selectedItem) => set({ selectedItem }),
  setWorkflowDocument: (workflowDocument) => set({ workflowDocument }),
  reset: () => set({ visible: false, loading: false, openLoading: false, query: '', items: [], selectedItem: null }),
}));

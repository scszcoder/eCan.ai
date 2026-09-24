import { create } from 'zustand';

/**
 * Who opened Fast Deploy, and for which store. The panel lives in MainLayout
 * (Agents page only), while "Deploy agents" is on a store's page -- this is how
 * the one hands the other a store to deploy into.
 */
interface FastDeployState {
  open: boolean;
  /** Store to preselect; '' = let the user pick. */
  storeId: string;
  toggle: () => void;
  close: () => void;
  openFor: (storeId: string) => void;
}

export const useFastDeployStore = create<FastDeployState>((set) => ({
  open: false,
  storeId: '',
  toggle: () => set((s) => ({ open: !s.open, storeId: s.open ? s.storeId : '' })),
  close: () => set({ open: false, storeId: '' }),
  openFor: (storeId) => set({ open: true, storeId }),
}));

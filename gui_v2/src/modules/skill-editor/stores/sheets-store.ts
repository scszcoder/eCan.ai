import { create } from 'zustand';
import { nanoid } from 'nanoid/non-secure';
import blankFlow from '../data/blank-flow.json';

export interface Sheet {
  id: string;
  name: string;
  // Persisted workflow JSON for this sheet
  document?: any;
  createdAt: number;
  lastOpenedAt: number;
}

interface SheetsState {
  sheets: Record<string, Sheet>;
  order: string[]; // creation order
  openTabs: string[]; // in open order (oldest first)
  activeSheetId: string | null;
  maxOpenTabs: number;
  revision: number; // bump to signal consumers to refresh

  // actions
  initMain: (initialDoc?: any) => void;
  newSheet: (name?: string, initialDoc?: any) => string;
  openSheet: (id: string) => void;
  closeSheet: (id: string) => void;
  deleteSheet: (id: string) => void;
  renameSheet: (id: string, name: string) => void;
  setActiveSheet: (id: string) => void;
  saveActiveDocument: (doc: any) => void;
  getActiveDocument: () => any | null;
  clearActiveSheet: () => void;
  // reorder tabs
  moveTabLeft: (id: string) => void;
  moveTabRight: (id: string) => void;
  reorderTabs: (order: string[]) => void;
  // bundle helpers
  getAllSheets: () => { mainSheetId: string; sheets: Sheet[]; openTabs: string[]; activeSheetId: string | null };
  loadBundle: (bundle: { mainSheetId: string; sheets: Sheet[]; openTabs?: string[]; activeSheetId?: string | null }) => void;
}

export const useSheetsStore = create<SheetsState>((set, get) => ({
  sheets: {},
  order: [],
  openTabs: [],
  activeSheetId: null,
  maxOpenTabs: 10,
  revision: 0,

  initMain: (initialDoc?: any) => {
    const exists = get().sheets['main'];
    if (exists) return;
    const now = Date.now();
    const main: Sheet = {
      id: 'main',
      name: 'Main',
      document: initialDoc ?? null,
      createdAt: now,
      lastOpenedAt: now,
    };
    set((s) => ({
      sheets: { ...s.sheets, [main.id]: main },
      order: [...s.order, main.id],
      openTabs: [main.id],
      activeSheetId: main.id,
    }));
  },

  newSheet: (name?: string, initialDoc?: any) => {
    const id = nanoid(8);
    const now = Date.now();
    const sheet: Sheet = {
      id,
      name: name || `Sheet ${get().order.length + 1}`,
      document: initialDoc ?? (blankFlow as any),
      createdAt: now,
      lastOpenedAt: now,
    };
    set((s) => ({
      sheets: { ...s.sheets, [id]: sheet },
      order: [...s.order, id],
    }));
    return id;
  },

  openSheet: (id: string) => {
    const st = get();
    if (!st.sheets[id]) return;
    const already = st.openTabs.includes(id);
    let openTabs = already ? [...st.openTabs] : [...st.openTabs, id];
    // Enforce max tabs by evicting oldest (not the one we just opened)
    while (openTabs.length > st.maxOpenTabs) {
      const evict = openTabs[0];
      if (evict === id && openTabs.length > 1) {
        // avoid evicting the newly opened when only overflow by 1
        openTabs = openTabs.slice(1).concat(evict);
      }
      openTabs = openTabs.slice(1);
    }
    set({
      openTabs,
      activeSheetId: id,
      sheets: {
        ...st.sheets,
        [id]: { ...st.sheets[id], lastOpenedAt: Date.now() },
      },
    });
  },

  closeSheet: (id: string) => {
    const st = get();
    if (!st.openTabs.includes(id)) return;
    const openTabs = st.openTabs.filter((x) => x !== id);
    let activeSheetId = st.activeSheetId;
    if (activeSheetId === id) {
      activeSheetId = openTabs[openTabs.length - 1] || null;
    }
    set({ openTabs, activeSheetId });
  },

  deleteSheet: (id: string) => {
    const st = get();
    if (id === 'main') return; // protect main for MVP
    const { [id]: _, ...rest } = st.sheets;
    const order = st.order.filter((x) => x !== id);
    const openTabs = st.openTabs.filter((x) => x !== id);
    let activeSheetId = st.activeSheetId;
    if (activeSheetId === id) {
      activeSheetId = openTabs[openTabs.length - 1] || 'main';
    }
    set({ sheets: rest, order, openTabs, activeSheetId });
  },

  renameSheet: (id, name) => {
    const st = get();
    if (!st.sheets[id]) return;
    set({ sheets: { ...st.sheets, [id]: { ...st.sheets[id], name } } });
  },

  setActiveSheet: (id) => {
    const st = get();
    if (st.sheets[id]) set({ activeSheetId: id });
  },

  saveActiveDocument: (doc: any) => {
    const st = get();
    const id = st.activeSheetId;
    if (!id) return;
    const sheet = st.sheets[id];
    if (!sheet) return;
    set({ sheets: { ...st.sheets, [id]: { ...sheet, document: doc } } });
  },

  getActiveDocument: () => {
    const st = get();
    const id = st.activeSheetId;
    if (!id) return null;
    return st.sheets[id]?.document ?? null;
  },

  clearActiveSheet: () => {
    const st = get();
    const id = st.activeSheetId;
    if (!id) return;
    const sheet = st.sheets[id];
    if (!sheet) return;
    set({
      sheets: { ...st.sheets, [id]: { ...sheet, document: (blankFlow as any) } },
      revision: st.revision + 1,
    });
  },

  moveTabLeft: (id: string) => {
    const st = get();
    const idx = st.openTabs.indexOf(id);
    if (idx <= 0) return;
    const newOrder = [...st.openTabs];
    [newOrder[idx - 1], newOrder[idx]] = [newOrder[idx], newOrder[idx - 1]];
    set({ openTabs: newOrder });
  },
  moveTabRight: (id: string) => {
    const st = get();
    const idx = st.openTabs.indexOf(id);
    if (idx === -1 || idx >= st.openTabs.length - 1) return;
    const newOrder = [...st.openTabs];
    [newOrder[idx], newOrder[idx + 1]] = [newOrder[idx + 1], newOrder[idx]];
    set({ openTabs: newOrder });
  },
  reorderTabs: (order: string[]) => {
    set({ openTabs: order });
  },

  getAllSheets: () => {
    const st = get();
    const sheets = st.order.map((id) => st.sheets[id]).filter(Boolean) as Sheet[];
    return { mainSheetId: st.order[0] || 'main', sheets, openTabs: [...st.openTabs], activeSheetId: st.activeSheetId };
  },
  loadBundle: (bundle) => {
    const map: Record<string, Sheet> = {};
    const order: string[] = [];
    bundle.sheets.forEach((s) => {
      map[s.id] = { ...s, lastOpenedAt: Date.now(), createdAt: s.createdAt ?? Date.now() } as Sheet;
      order.push(s.id);
    });
    const openTabs = bundle.openTabs && bundle.openTabs.length ? bundle.openTabs.filter((id) => map[id]) : [bundle.mainSheetId];
    set({
      sheets: map,
      order,
      openTabs,
      activeSheetId: bundle.activeSheetId ?? bundle.mainSheetId,
      revision: get().revision + 1,
    });
  },
}));

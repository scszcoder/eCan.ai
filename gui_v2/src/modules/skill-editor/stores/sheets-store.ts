import { create } from 'zustand';
import { nanoid } from 'nanoid/non-secure';
import blankFlow from '../data/blank-flow.json';
import { validateBundle } from '../services/sheets-resolver';

export interface Sheet {
  id: string;
  name: string;
  // Persisted workflow JSON for this sheet
  document?: any;
  createdAt: number;
  lastOpenedAt: number;
  view?: { zoom?: number };
  selectionIds?: string[];
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
  // Save document for a specific sheet id (used during sheet switch)
  saveDocumentFor?: (id: string, doc: any) => void;
  getActiveDocument: () => any | null;
  clearActiveSheet: () => void;
  saveActiveViewState: (view: { zoom?: number }) => void;
  saveViewStateFor: (id: string, view: { zoom?: number }) => void;
  getActiveViewState: () => { zoom?: number } | null;
  getViewStateFor: (id: string) => { zoom?: number } | null;
  saveActiveSelection: (ids: string[]) => void;
  saveSelectionFor: (id: string, ids: string[]) => void;
  getActiveSelection: () => string[];
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
      // Deep clone to avoid shared object references
      document: initialDoc ? JSON.parse(JSON.stringify(initialDoc)) : null,
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

  // Persist current sheet's view state (zoom only for now)
  saveActiveViewState: (view: { zoom?: number }) => {
    const st = get();
    const id = st.activeSheetId;
    if (!id) return;
    const sheet = st.sheets[id];
    if (!sheet) return;
    set({ sheets: { ...st.sheets, [id]: { ...sheet, view: { ...(sheet.view || {}), ...view } } } });
  },
  // Save view state for a specific sheet (used during sheet switch)
  saveViewStateFor: (id: string, view: { zoom?: number }) => {
    const st = get();
    const sheet = st.sheets[id];
    if (!sheet) return;
    set({ sheets: { ...st.sheets, [id]: { ...sheet, view: { ...(sheet.view || {}), ...view } } } });
  },
  getActiveViewState: () => {
    const st = get();
    const id = st.activeSheetId;
    if (!id) return null;
    return st.sheets[id]?.view || null;
  },
  getViewStateFor: (id: string) => {
    const st = get();
    return st.sheets[id]?.view || null;
  },

  // Persist and retrieve selection IDs for active sheet
  saveActiveSelection: (ids: string[]) => {
    const st = get();
    const id = st.activeSheetId;
    if (!id) return;
    const sheet = st.sheets[id];
    if (!sheet) return;
    set({ sheets: { ...st.sheets, [id]: { ...sheet, selectionIds: Array.isArray(ids) ? [...ids] : [] } } });
  },
  // Save selection for a specific sheet (used during sheet switch)
  saveSelectionFor: (id: string, ids: string[]) => {
    const st = get();
    const sheet = st.sheets[id];
    if (!sheet) return;
    set({ sheets: { ...st.sheets, [id]: { ...sheet, selectionIds: Array.isArray(ids) ? [...ids] : [] } } });
  },
  getActiveSelection: () => {
    const st = get();
    const id = st.activeSheetId;
    if (!id) return [];
    return st.sheets[id]?.selectionIds || [];
  },

  newSheet: (name?: string, initialDoc?: any) => {
    const id = nanoid(8);
    const now = Date.now();
    const sheet: Sheet = {
      id,
      name: name || `Sheet ${get().order.length + 1}`,
      // Ensure each sheet gets its own document object
      document: initialDoc
        ? JSON.parse(JSON.stringify(initialDoc))
        : JSON.parse(JSON.stringify(blankFlow as any)),
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

  // Explicitly save for a specific sheet id (useful when switching sheets)
  saveDocumentFor: (id: string, doc: any) => {
    const st = get();
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
      // Reset to a fresh blank document (deep clone)
      sheets: { ...st.sheets, [id]: { ...sheet, document: JSON.parse(JSON.stringify(blankFlow as any)) } },
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
    // Normalize bundle: upgrade legacy sheet-call fields to use targetSheetId
    const cloned = JSON.parse(JSON.stringify(bundle || {}));
    try {
      const sheetsArr: any[] = Array.isArray(cloned.sheets) ? cloned.sheets : [];
      const sheetById: Record<string, any> = {};
      const sheetByNameCI: Record<string, any> = {};
      sheetsArr.forEach((s) => {
        if (!s || !s.id) return;
        sheetById[s.id] = s;
        const nm = (s.name || '').toString();
        if (nm) sheetByNameCI[nm.toLowerCase()] = s;
      });
      sheetsArr.forEach((s) => {
        const doc = (s && s.document) || { nodes: [], edges: [] };
        const nodes: any[] = Array.isArray(doc.nodes) ? doc.nodes : [];
        nodes.forEach((n) => {
          if (!n || n.type !== 'sheet-call') return;
          const data = (n.data = n.data || {});
          let tid = data.targetSheetId;
          const known = tid && !!sheetById[tid];
          if (!known) {
            const tName = (data.target_sheet || data.targetSheet || data.name || data.target || '').toString();
            if (tName) {
              const hit = sheetByNameCI[tName.toLowerCase()];
              if (hit) {
                data.targetSheetId = hit.id;
                // Mirror for backend compatibility and future saves
                data.target_sheet = hit.name;
                data.targetSheet = hit.name;
              }
            } else {
              // Fallback: if there is exactly one other sheet in the bundle (excluding current), default to it
              try {
                const candidates = sheetsArr.filter((x) => x && x.id && x.id !== s.id);
                if (candidates.length === 1) {
                  const only = candidates[0];
                  data.targetSheetId = only.id;
                  data.target_sheet = only.name;
                  data.targetSheet = only.name;
                }
              } catch {}
            }
          } else {
            // Ensure mirrored name fields exist
            try {
              const hit = sheetById[tid];
              if (hit) {
                data.target_sheet = data.target_sheet || hit.name;
                data.targetSheet = data.targetSheet || hit.name;
              }
            } catch {}
          }
        });
      });
    } catch {}

    // Validate before applying
    const validation = validateBundle(cloned as any);
    if (!validation.ok) {
      // eslint-disable-next-line no-alert
      alert('Bundle validation failed: ' + validation.errors.map((e) => e.message).join('; '));
      return;
    }
    if (validation.warnings.length) {
      // eslint-disable-next-line no-console
      console.warn('[Sheets] Bundle validation warnings:', validation.warnings);
    }
    const map: Record<string, Sheet> = {};
    const order: string[] = [];
    cloned.sheets.forEach((s) => {
      map[s.id] = { ...s, lastOpenedAt: Date.now(), createdAt: s.createdAt ?? Date.now() } as Sheet;
      order.push(s.id);
    });
    // Enforce main sheet display name
    if (cloned.mainSheetId && map[cloned.mainSheetId]) {
      map[cloned.mainSheetId] = { ...map[cloned.mainSheetId], name: 'Main' };
    }
    const maxTabs = get().maxOpenTabs;
    const openTabs = cloned.openTabs && cloned.openTabs.length
      ? cloned.openTabs.filter((id) => map[id])
      : order.slice(0, maxTabs);
    // visibility log
    try { console.log('[Sheets][LOAD_BUNDLE]', { sheetsCount: order.length, mainSheetId: cloned.mainSheetId, openTabs }); } catch {}
    set({
      sheets: map,
      order,
      openTabs,
      activeSheetId: cloned.activeSheetId ?? cloned.mainSheetId,
      revision: get().revision + 1,
    });
  },
}));

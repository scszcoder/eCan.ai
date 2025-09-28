import { useEffect, useRef } from 'react';
import { useClientContext, usePlayground, usePlaygroundTools } from '@flowgram.ai/free-layout-editor';
import { useSheetsStore } from '../../stores/sheets-store';
import blankFlowData from '../../data/blank-flow.json';

/**
 * Keeps the editor's WorkflowDocument in sync with the active sheet in the sheets store.
 * - Before sheet change: persist current document JSON to the active sheet.
 * - After sheet change: load target sheet's document into the editor.
 */
export const ActiveSheetBinder = () => {
  const ctx = useClientContext();
  const playground = usePlayground();
  const tools = usePlaygroundTools();
  const activeSheetId = useSheetsStore((s) => s.activeSheetId);
  const getActiveDocument = useSheetsStore((s) => s.getActiveDocument);
  const saveActiveDocument = useSheetsStore((s) => s.saveActiveDocument);
  const revision = useSheetsStore((s) => s.revision);
  const saveActiveViewState = useSheetsStore((s) => s.saveActiveViewState);
  const getActiveViewState = useSheetsStore((s) => s.getActiveViewState);

  const lastSheetIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!ctx?.document) return;

    // On sheet switch: save current, then load new
    const lastId = lastSheetIdRef.current;
    if (lastId && lastId !== activeSheetId) {
      try {
        const currentJson = ctx.document.toJSON();
        saveActiveDocument(currentJson);
      } catch (e) {
        /* noop */
      }
      // Save current zoom as view state
      try {
        if (typeof tools.zoom === 'number') {
          saveActiveViewState({ zoom: tools.zoom });
        }
      } catch {}
    }

    // Load active sheet document into editor
    const nextDoc = getActiveDocument();
    // Always clear to ensure blank sheets start empty
    ctx.document.clear();
    // If no saved document, load an explicit blank flow (no nodes/edges)
    const docToLoad = nextDoc ?? (blankFlowData as any);
    if (docToLoad) {
      ctx.document.fromJSON(docToLoad);
    }
    // Restore view state (zoom) if available, otherwise fit view
    try {
      const view = getActiveViewState();
      if (view?.zoom && playground?.config?.updateZoom) {
        playground.config.updateZoom(view.zoom);
      } else {
        (ctx.document as any).fitView && (ctx.document as any).fitView();
      }
    } catch {
      (ctx.document as any).fitView && (ctx.document as any).fitView();
    }

    lastSheetIdRef.current = activeSheetId ?? null;
  }, [activeSheetId, revision, ctx, getActiveDocument, saveActiveDocument]);

  return null;
};

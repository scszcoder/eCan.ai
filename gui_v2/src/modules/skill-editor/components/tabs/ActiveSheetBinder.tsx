import { useEffect, useRef } from 'react';
import { useClientContext, usePlayground, usePlaygroundTools, useService, WorkflowSelectService, FlowNodeFormData } from '@flowgram.ai/free-layout-editor';
import { useSheetsStore } from '../../stores/sheets-store';
import blankFlowData from '../../data/blank-flow.json';
import { useSkillInfoStore } from '../../stores/skill-info-store';

/**
 * Keeps the editor's WorkflowDocument in sync with the active sheet in the sheets store.
 * - Before sheet change: persist current document JSON to the active sheet.
 * - After sheet change: load target sheet's document into the editor.
 */
export const ActiveSheetBinder = () => {
  const ctx = useClientContext();
  const playground = usePlayground();
  const tools = usePlaygroundTools();
  const selectService = useService(WorkflowSelectService);
  const activeSheetId = useSheetsStore((s) => s.activeSheetId);
  const getActiveDocument = useSheetsStore((s) => s.getActiveDocument);
  const saveActiveDocument = useSheetsStore((s) => s.saveActiveDocument);
  const saveDocumentFor = useSheetsStore((s) => s.saveDocumentFor);
  const revision = useSheetsStore((s) => s.revision);
  const saveActiveViewState = useSheetsStore((s) => s.saveActiveViewState);
  const getActiveViewState = useSheetsStore((s) => s.getActiveViewState);
  const saveActiveSelection = useSheetsStore((s) => s.saveActiveSelection);
  const getActiveSelection = useSheetsStore((s) => s.getActiveSelection);
  const setBreakpoints = useSkillInfoStore((s) => s.setBreakpoints);

  const lastSheetIdRef = useRef<string | null>(null);
  const initialFitViewDoneRef = useRef(false);
  
  // Store refs for unstable references to avoid infinite loops
  const toolsRef = useRef(tools);
  const playgroundRef = useRef(playground);
  toolsRef.current = tools;
  playgroundRef.current = playground;

  useEffect(() => {
    if (!ctx?.document) return;

    // On sheet switch: save current doc/zoom/selection, then load new
    const lastId = lastSheetIdRef.current;
    if (lastId && lastId !== activeSheetId) {
      try {
        const currentJson = ctx.document.toJSON();
        try { console.log('[ActiveSheetBinder] Saving previous sheet document', { sheetId: lastId, nodes: currentJson?.nodes?.length, edges: currentJson?.edges?.length }); } catch {}
        // Merge breakpoint flags from store into node JSON before saving
        try {
          const bpSet = new Set<string>(useSkillInfoStore.getState().breakpoints || []);
          if (Array.isArray(currentJson?.nodes)) {
            currentJson.nodes = currentJson.nodes.map((n: any) => ({
              ...n,
              data: { ...(n?.data || {}), breakpoint: bpSet.has(n?.id) },
            }));
          }
        } catch {}
        // Save to the previously active sheet, not the newly activated one
        saveDocumentFor && saveDocumentFor(lastId, currentJson);
      } catch (e) {
        /* noop */
      }
      // Save current zoom as view state
      try {
        if (typeof tools.zoom === 'number') {
          saveActiveViewState({ zoom: tools.zoom });
        }
      } catch {}
      // Save current selection ids
      try {
        const ids: string[] = Array.isArray((selectService as any)?.selection)
          ? (selectService as any).selection.map((n: any) => n?.id).filter(Boolean)
          : (typeof (selectService as any)?.getSelectedIds === 'function'
              ? (selectService as any).getSelectedIds()
              : []);
        if (ids?.length >= 0) {
          saveActiveSelection(ids);
        }
      } catch {}
    }

    // Load active sheet document into editor
    const nextDoc = getActiveDocument();
    try { console.log('[ActiveSheetBinder] Loading active sheet', { activeSheetId, hasDoc: !!nextDoc, nodes: nextDoc?.nodes?.length, edges: nextDoc?.edges?.length, revision }); } catch {}
    // Always clear to ensure blank sheets start empty
    ctx.document.clear();
    // If no saved document, load an explicit blank flow (no nodes/edges)
    const docToLoad = nextDoc ?? (blankFlowData as any);
    if (docToLoad) {
      try { console.log('[ActiveSheetBinder] fromJSON()', { nodeCount: Array.isArray(docToLoad?.nodes) ? docToLoad.nodes.length : 'n/a' }); } catch {}
      try {
        console.time('[ActiveSheetBinder] fromJSON duration');
        ctx.document.fromJSON(docToLoad);
        console.timeEnd('[ActiveSheetBinder] fromJSON duration');
        
        // Restore flip states from loaded document
        if (docToLoad?.nodes && Array.isArray(docToLoad.nodes)) {
          setTimeout(() => {
            docToLoad.nodes.forEach((node: any) => {
              if (node?.data?.hFlip === true) {
                console.log('[ActiveSheetBinder] Restoring hFlip for node:', node.id);
                const loadedNode = ctx.document.getNode(node.id);
                if (loadedNode) {
                  // Set in raw data
                  if (!loadedNode.raw) (loadedNode as any).raw = {};
                  if (!loadedNode.raw.data) (loadedNode.raw as any).data = {};
                  loadedNode.raw.data.hFlip = true;
                  
                  // Set in JSON
                  const json = (loadedNode as any).json;
                  if (json) {
                    if (!json.data) json.data = {};
                    json.data.hFlip = true;
                  }
                  
                  // Set in form using setFieldValue (same as node-menu)
                  try {
                    const formData = (loadedNode as any).getData?.(FlowNodeFormData);
                    const formModel = formData?.getFormModel?.();
                    const formControl = formModel?.formControl as any;
                    if (formControl?.setFieldValue) {
                      formControl.setFieldValue('data.hFlip', true);
                      console.log('[ActiveSheetBinder] Set hFlip via setFieldValue for node:', node.id);
                    } else {
                      console.warn('[ActiveSheetBinder] formControl.setFieldValue not available for node:', node.id);
                    }
                  } catch (e) {
                    console.warn('[ActiveSheetBinder] Could not set form field:', e);
                  }
                }
              }
            });
          }, 200); // Increased delay to ensure forms are ready
        }
      } catch (e) {
        console.error('[ActiveSheetBinder] fromJSON error', e);
      }
    }
    // Restore view state (zoom) if available, otherwise fit view
    // Use a small delay to ensure the document is fully rendered before fitView
    const isInitialLoad = !initialFitViewDoneRef.current;
    const isSheetSwitch = lastId && lastId !== activeSheetId;
    
    const doFitView = (retryCount = 0) => {
      try {
        const currentPlayground = playgroundRef.current;
        const currentTools = toolsRef.current;
        
        // Check if tools are ready
        if (!currentTools?.fitView && retryCount < 5) {
          console.log('[ActiveSheetBinder] tools.fitView not ready, retrying...', retryCount);
          setTimeout(() => doFitView(retryCount + 1), 200);
          return;
        }
        
        // Only restore saved zoom when switching between sheets (not on initial load or refresh)
        const view = getActiveViewState();
        if (isSheetSwitch && view?.zoom && currentPlayground?.config?.updateZoom) {
          currentPlayground.config.updateZoom(view.zoom);
          console.log('[ActiveSheetBinder] Restored zoom for sheet switch:', view.zoom);
        } else {
          // For initial load, refresh, or new file: always fitView
          console.log('[ActiveSheetBinder] Executing fitView (initial/refresh)...');
          if (currentTools?.fitView) {
            currentTools.fitView();
            console.log('[ActiveSheetBinder] fitView completed via tools');
          } else if ((ctx.document as any).fitView) {
            (ctx.document as any).fitView();
            console.log('[ActiveSheetBinder] fitView completed via ctx.document');
          } else {
            console.warn('[ActiveSheetBinder] No fitView method available');
          }
        }
        initialFitViewDoneRef.current = true;
      } catch (e) {
        console.error('[ActiveSheetBinder] fitView error', e);
      }
    };
    
    // Delay fitView to ensure nodes are rendered (longer delay for initial load)
    const fitViewTimeout = setTimeout(() => doFitView(0), isInitialLoad ? 300 : 100);

    // Restore selection for this sheet if any
    try {
      const ids = getActiveSelection();
      if (ids && ids.length > 0 && (selectService as any)?.selectByIds) {
        (selectService as any).selectByIds(ids);
      }
    } catch {}

    // Sync breakpoint list from node JSON (nodes with data.breakpoint === true)
    try {
      const json = ctx.document.toJSON?.();
      const nodes: any[] = Array.isArray(json?.nodes) ? json.nodes : [];
      const bp = nodes.filter((n) => n?.data?.breakpoint === true).map((n) => n.id).filter(Boolean);
      setBreakpoints(bp);
    } catch {}

    lastSheetIdRef.current = activeSheetId ?? null;
    
    // Cleanup timeout on unmount or re-run
    return () => {
      clearTimeout(fitViewTimeout);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSheetId, revision, ctx, getActiveDocument, saveActiveDocument]);

  return null;
};

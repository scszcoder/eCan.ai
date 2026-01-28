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
  const tools = usePlaygroundTools();
  const playground = usePlayground();
  const selectService = useService(WorkflowSelectService);
  const activeSheetId = useSheetsStore((s) => s.activeSheetId);
  const getActiveDocument = useSheetsStore((s) => s.getActiveDocument);
  const saveDocumentFor = useSheetsStore((s) => s.saveDocumentFor);
  const revision = useSheetsStore((s) => s.revision);
  const saveViewStateFor = useSheetsStore((s) => s.saveViewStateFor);
  const getViewStateFor = useSheetsStore((s) => s.getViewStateFor);
  const saveSelectionFor = useSheetsStore((s) => s.saveSelectionFor);
  const getActiveSelection = useSheetsStore((s) => s.getActiveSelection);
  const setBreakpoints = useSkillInfoStore((s) => s.setBreakpoints);

  const lastSheetIdRef = useRef<string | null>(null);
  const initialFitViewDoneRef = useRef(false);
  
  // Store refs for unstable references to avoid infinite loops
  const toolsRef = useRef(tools);
  const playgroundRef = useRef(playground);
  toolsRef.current = tools;
  playgroundRef.current = playground;
  
  // Track all timeouts for cleanup
  const timeoutsRef = useRef<NodeJS.Timeout[]>([]);
  const clearAllTimeouts = () => {
    timeoutsRef.current.forEach(clearTimeout);
    timeoutsRef.current = [];
  };
  const addTimeout = (fn: () => void, delay: number) => {
    const id = setTimeout(fn, delay);
    timeoutsRef.current.push(id);
    return id;
  };

  useEffect(() => {
    if (!ctx?.document) return;

    // On sheet switch: save current doc/zoom/selection, then load new
    const lastId = lastSheetIdRef.current;
    if (lastId && lastId !== activeSheetId) {
      try {
        const currentJson = ctx.document.toJSON();
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
      } catch {
        /* noop */
      }
      // Save current zoom as view state to the PREVIOUS sheet (lastId), not the new active sheet
      try {
        const currentZoom = playground?.config?.zoom;
        if (typeof currentZoom === 'number') {
          saveViewStateFor(lastId, { zoom: currentZoom });
        }
      } catch {}
      // Save current selection ids to the PREVIOUS sheet
      try {
        const ids: string[] = Array.isArray((selectService as any)?.selection)
          ? (selectService as any).selection.map((n: any) => n?.id).filter(Boolean)
          : (typeof (selectService as any)?.getSelectedIds === 'function'
              ? (selectService as any).getSelectedIds()
              : []);
        if (ids?.length >= 0) {
          saveSelectionFor(lastId, ids);
        }
      } catch {}
    }

    // Load active sheet document into editor
    const nextDoc = getActiveDocument();
    
    // Clear any previous timeouts before starting new ones
    clearAllTimeouts();
    
    // CRITICAL: Defer document operations to next event loop tick.
    // This prevents React state updates and flowgram's internal async operations
    // from accessing context during React's transitional render phase,
    // which causes React error #321 (Invalid hook call).
    addTimeout(() => {
      // Check if document is still valid (not disposed)
      if (ctx?.document?.disposed) {
        return;
      }
      
      // Always clear to ensure blank sheets start empty
      try {
        ctx.document.clear();
      } catch (clearErr) {
        console.error('[ActiveSheetBinder] Error clearing document:', clearErr);
        return; // Don't proceed if clear failed
      }
      // If no saved document, load an explicit blank flow (no nodes/edges)
      const docToLoad = nextDoc ?? (blankFlowData as any);
      if (docToLoad) {
        try {
          ctx.document.fromJSON(docToLoad);
        
        // Restore flip states from loaded document
        if (docToLoad?.nodes && Array.isArray(docToLoad.nodes)) {
          addTimeout(() => {
            docToLoad.nodes.forEach((node: any) => {
              if (node?.data?.hFlip === true) {
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
                    }
                  } catch (err) {
                    console.warn('[ActiveSheetBinder] Could not set hFlip form field:', err);
                  }
                }
              }
            });
          }, 200); // Increased delay to ensure forms are ready
        }
      } catch (err) {
        console.error('[ActiveSheetBinder] Error loading document:', err);
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
          addTimeout(() => doFitView(retryCount + 1), 200);
          return;
        }
        
        // Only restore saved zoom when switching between sheets (not on initial load or refresh)
        // Use getViewStateFor with the NEW activeSheetId to get the correct zoom
        const view = activeSheetId ? getViewStateFor(activeSheetId) : null;
        if (isSheetSwitch && view?.zoom && currentPlayground?.config?.updateZoom) {
          currentPlayground.config.updateZoom(view.zoom);
        } else {
          // TEMPORARILY DISABLED: fitView is causing context invalidation that crashes Tools
          // TODO: Find a way to call fitView without triggering cascading re-renders
          /*
          // For initial load, refresh, or new file: always fitView
          // CRITICAL: Use requestAnimationFrame to ensure React has finished its render cycle
          // before triggering fitView, which causes internal state updates in flowgram
          // that can invalidate context during React's transitional state.
          console.log('[ActiveSheetBinder] Scheduling fitView via requestAnimationFrame...');
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              // Double RAF to ensure we're after React's commit phase
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
            });
          });
          */
        }
        initialFitViewDoneRef.current = true;
      } catch (err) {
        console.error('[ActiveSheetBinder] Error in fitView:', err);
      }
    };
    
    // Delay fitView to ensure nodes are rendered (longer delay for initial load)
    addTimeout(() => doFitView(0), isInitialLoad ? 300 : 100);

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
    
    }, 0); // End of documentLoadTimeoutId setTimeout - defer to next event loop tick
    
    // Cleanup all timeouts on unmount or re-run
    return () => {
      clearAllTimeouts();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSheetId, revision, ctx, getActiveDocument]);

  return null;
};

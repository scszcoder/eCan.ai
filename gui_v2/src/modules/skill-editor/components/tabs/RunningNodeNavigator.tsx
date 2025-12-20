import { useEffect, useRef } from 'react';
import { useClientContext, useService, WorkflowSelectService } from '@flowgram.ai/free-layout-editor';
import { useRunningNodeStore } from '../../stores/running-node-store';
import { useSheetsStore } from '../../stores/sheets-store';
import { scrollToView } from '../base-node/utils';

/**
 * Listens for running node updates from backend and:
 * - Switches to the sheet that contains the node
 * - Attempts to pan/center the canvas on that node
 */
export const RunningNodeNavigator = () => {
  const ctx = useClientContext();
  const selectService = useService(WorkflowSelectService);
  const runningNodeId = useRunningNodeStore((s) => s.runningNodeId);

  const lastHandledIdRef = useRef<string | null>(null);
  const pendingCenterRef = useRef<string | null>(null);

  useEffect(() => {
    // Clear last handled ref when runningNodeId becomes null
    if (!runningNodeId) {
      lastHandledIdRef.current = null;
      pendingCenterRef.current = null;
      return;
    }

    // Avoid re-handling the same node id repeatedly
    if (lastHandledIdRef.current === runningNodeId && !pendingCenterRef.current) {
      return;
    }

    // If a center operation is already scheduled, avoid re-triggering sheet switch
    if (pendingCenterRef.current) {
      return;
    }

    const state = useSheetsStore.getState();
    const { sheets, activeSheetId } = state;

    // Find which sheet contains this node id
    let ownerSheetId: string | null = null;
    try {
      for (const [sid, sheet] of Object.entries(sheets)) {
        const nodes = (sheet.document?.nodes as any[]) || [];
        if (nodes.some((n) => n && n.id === runningNodeId)) {
          ownerSheetId = sid;
          break;
        }
      }
    } catch {}

    if (!ownerSheetId) {
      lastHandledIdRef.current = runningNodeId; // avoid trying again until id changes
      return;
    }

    let timeoutId1: NodeJS.Timeout | null = null;
    let timeoutId2: NodeJS.Timeout | null = null;

    const doCenter = () => {
      tryCenterOnNode(ctx, selectService, runningNodeId);
      pendingCenterRef.current = null;
      lastHandledIdRef.current = runningNodeId;
    };

    if (ownerSheetId !== activeSheetId) {
      // Switch to that sheet; defer centering
      state.openSheet(ownerSheetId);
      pendingCenterRef.current = runningNodeId;
      timeoutId1 = setTimeout(() => {
        // first attempt after sheet switch
        doCenter();
        // if still pending (rare), retry once more
        if (pendingCenterRef.current) {
          timeoutId2 = setTimeout(doCenter, 400);
        }
      }, 400);
    } else {
      // Already on the right sheet; center now
      doCenter();
    }

    // Cleanup timeouts on unmount or re-run
    return () => {
      if (timeoutId1) clearTimeout(timeoutId1);
      if (timeoutId2) clearTimeout(timeoutId2);
    };
  }, [runningNodeId, ctx, selectService]);

  return null;
};

function tryCenterOnNode(ctx: any, selectService: any, nodeId: string | null) {
  if (!nodeId || !ctx?.document) return;
  try {
    // Prefer selecting the node so user sees it highlighted; avoid redundant selection
    const getSelected = (selectService as any)?.getSelectedIds;
    const alreadySelected = Array.isArray(getSelected?.call?.(selectService))
      ? getSelected.call(selectService).includes(nodeId)
      : false;
    if (selectService && typeof selectService.selectByIds === 'function' && !alreadySelected) {
      selectService.selectByIds([nodeId]);
    }
  } catch {}

  // Try to obtain the node entity to center on
  try {
    const getEntity = (ctx.document as any).getNodeEntityById || (ctx.document as any).getNodeById;
    const entity = typeof getEntity === 'function' ? getEntity.call(ctx.document, nodeId) : null;
    if (entity) {
      scrollToView(ctx, entity);
      return;
    }
  } catch {}
}

export default RunningNodeNavigator;

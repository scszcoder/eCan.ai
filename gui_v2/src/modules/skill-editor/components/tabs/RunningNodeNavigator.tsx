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
  const { sheets, activeSheetId, openSheet } = useSheetsStore((s) => ({
    sheets: s.sheets,
    activeSheetId: s.activeSheetId,
    openSheet: s.openSheet,
  }));

  const pendingCenterRef = useRef<string | null>(null);

  useEffect(() => {
    if (!runningNodeId) return;
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

    if (!ownerSheetId) return;

    // Switch to that sheet if needed
    if (ownerSheetId !== activeSheetId) {
      openSheet(ownerSheetId);
      // defer centering after document loads
      pendingCenterRef.current = runningNodeId;
      setTimeout(() => {
        tryCenterOnNode(ctx, selectService, pendingCenterRef.current);
        pendingCenterRef.current = null;
      }, 200);
    } else {
      // Already on the right sheet; try to center immediately
      tryCenterOnNode(ctx, selectService, runningNodeId);
    }
  }, [runningNodeId, sheets, activeSheetId, openSheet, ctx, selectService]);

  return null;
};

function tryCenterOnNode(ctx: any, selectService: any, nodeId: string | null) {
  if (!nodeId || !ctx?.document) return;
  try {
    // Prefer selecting the node so user sees it highlighted
    if (selectService && typeof selectService.selectByIds === 'function') {
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

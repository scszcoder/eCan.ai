import React, { useEffect } from 'react';
import { useRunningNodeStore } from '../../stores/running-node-store';
import { useRuntimeStateStore } from '../../stores/runtime-state-store';
import { useSkillInfoStore } from '../../stores/skill-info-store';

/**
 * Minimal, conservative binder:
 * - If no node is currently marked as running
 * - And any node runtime status is paused/breakpoint/stalled
 * => set running node to that node so the canvas shows breakpoint visuals.
 *
 * This avoids races by only acting when there is no active running node.
 */
export const BreakpointBinder: React.FC = () => {
  const runningNodeId = useRunningNodeStore((s) => s.runningNodeId);
  const setRunningNodeId = useRunningNodeStore((s) => s.setRunningNodeId);
  const getNodeRuntimeState = useRuntimeStateStore((s) => s.getNodeRuntimeState);
  const workFlow = useSkillInfoStore((s) => s.skillInfo?.workFlow);

  useEffect(() => {
    if (runningNodeId != null) return; // UI already showing a running node

    try {
      const nodes = workFlow?.nodes as Array<{ id: string }>|undefined;
      if (!Array.isArray(nodes) || nodes.length === 0) return;

      for (const n of nodes) {
        const rs = getNodeRuntimeState(n.id);
        const status = rs?.status as string | undefined;
        if (status === 'paused' || status === 'breakpoint' || status === 'stalled') {
          setRunningNodeId(n.id);
          break;
        }
      }
    } catch {}
  }, [runningNodeId, getNodeRuntimeState, workFlow, setRunningNodeId]);

  return null;
};

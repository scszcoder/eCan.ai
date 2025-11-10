/**
 * Port side flipping integration (Option A: upstream extension planned)
 *
 * This module attempts to flip port anchor sides using CommandService commands
 * that are expected to be provided by @flowgram.ai/free-layout-editor in a future
 * update. Until those commands exist, calls will be no-ops with console logs.
 */

import { useService, CommandService, WorkflowDocument, WorkflowLinesManager } from '@flowgram.ai/free-layout-editor';

export type PortSide = 'left' | 'right' | 'top' | 'bottom';

// Candidate command names for future API
const CMD_UPDATE_PORT_SIDE = 'workflow.port.updateSide';
const CMD_UPDATE_NODE_PORTS_SIDE = 'workflow.node.updatePortsSide';

export const usePortSideService = () => {
  const cmdSvc = useService(CommandService);
  const doc = useService(WorkflowDocument);
  const lines = useService(WorkflowLinesManager);

  const hasCommand = (name: string) => {
    try { return !!(cmdSvc as any)?.getCommand?.(name); } catch { return false; }
  };

  const canFlipAnchors = (): boolean => {
    // Supported if commands exist or if we can directly update port entities
    if (hasCommand(CMD_UPDATE_PORT_SIDE) || hasCommand(CMD_UPDATE_NODE_PORTS_SIDE)) return true;
    try {
      const ports = (doc as any)?.getAllPorts?.() || [];
      return Array.isArray(ports) && ports.some((p: any) => typeof p?.update === 'function');
    } catch {
      return false;
    }
  };

  const logNoop = (why: string) => {
    try {
      // eslint-disable-next-line no-console
      console.info('[PortSide] Anchor flip is a no-op:', why);
    } catch {}
  };

  /**
   * Apply H-flip at anchor level. When flip=true: inputs -> right, outputs -> left.
   * When flip=false: inputs -> left, outputs -> right.
   */
  const applyHFlipAnchors = async (node: any, flip: boolean) => {
    try {
      const nodeId = node?.id;
      if (!nodeId || !doc || !cmdSvc) return logNoop('missing services or node');

      const toInputSide: PortSide = flip ? 'right' : 'left';
      const toOutputSide: PortSide = flip ? 'left' : 'right';

      const exec = async (name: string, payload: any) => {
        return (cmdSvc as any)?.executeCommand?.(name, payload);
      };

      if (hasCommand(CMD_UPDATE_NODE_PORTS_SIDE)) {
        // Preferred bulk command on the node
        await exec(CMD_UPDATE_NODE_PORTS_SIDE, {
          nodeId,
          rules: [
            { role: 'input', side: toInputSide },
            { role: 'output', side: toOutputSide },
          ],
        });
      } else if (hasCommand(CMD_UPDATE_PORT_SIDE)) {
        // Fallback: enumerate ports and update one by one
        const allPorts = (doc as any)?.getAllPorts?.() || [];
        const targetPorts = allPorts.filter((p: any) => p?.node?.id === nodeId);
        for (const p of targetPorts) {
          const pid: string = p?.id || '';
          const isIn = pid.includes('port_input_');
          const isOut = pid.includes('port_output_');
          const side: PortSide = isIn ? toInputSide : isOut ? toOutputSide : toOutputSide;
          await exec(CMD_UPDATE_PORT_SIDE, { nodeId, portId: pid, side });
        }
      } else {
        // No commands: directly update port entity location (supported by free-layout-core)
        const allPorts = (doc as any)?.getAllPorts?.() || [];
        const targetPorts = allPorts.filter((p: any) => p?.node?.id === nodeId);
        let changed = false;
        for (const p of targetPorts) {
          const pid: string = p?.id || '';
          const isIn = pid.includes('port_input_');
          const isOut = pid.includes('port_output_');
          const loc: PortSide = isIn ? toInputSide : isOut ? toOutputSide : toOutputSide;
          if (typeof p?.update === 'function') {
            p.update({ location: loc });
            changed = true;
          }
        }
        if (!changed) {
          return logNoop('no supported command exposed and port.update missing');
        }
      }

      // Ask lines to refresh visuals and force editor to re-render nodes
      try { (lines as any)?.forceUpdate?.(); } catch {}
      try { (doc as any)?.fireContentChange?.(); } catch {}
      try { (doc as any)?.fireRender?.(); } catch {}
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn('[PortSide] applyHFlipAnchors failed', e);
    }
  };

  return {
    canFlipAnchors,
    applyHFlipAnchors,
  };
};

import React from 'react';
import { eventBus } from '@/utils/eventBus';
import { useDisplayRunningNodeStore } from '../../stores/display-running-store';

/**
 * DisplayRunningBinder: listens to runtime updates and drives a deduped,
 * cooldown-based running-node display to prevent back-jump flicker.
 */
export const DisplayRunningBinder: React.FC = () => {
  const setDisplay = useDisplayRunningNodeStore((s) => s.setDisplayRunningNodeId);

  React.useEffect(() => {
    const GN: any = (window as any);
    if (!GN.__displayRun) GN.__displayRun = {
      showing: null as string | null,
      shownAt: 0,
      recentShown: new Map<string, number>(),
      COOLDOWN_MS: 800,
      MIN_VISIBLE_MS: 800,
      clearT: null as any,
    };
    const q = GN.__displayRun as {
      showing: string | null;
      shownAt: number;
      recentShown: Map<string, number>;
      COOLDOWN_MS: number;
      MIN_VISIBLE_MS: number;
      clearT: any;
    };

    const now = () => Date.now();

    const show = (id: string) => {
      q.showing = id;
      q.shownAt = now();
      q.recentShown.set(id, q.shownAt);
      setDisplay(id);
    };

    const maybeClearAfterMin = () => {
      const elapsed = now() - (q.shownAt || 0);
      const remaining = Math.max(0, q.MIN_VISIBLE_MS - elapsed);
      if (q.clearT) { try { clearTimeout(q.clearT); } catch {} q.clearT = null; }
      q.clearT = setTimeout(() => {
        if (q.showing) return; // someone else already showed
        setDisplay(null);
      }, Math.max(remaining, 200));
    };

    const handler = (params: any) => {
      try {
        const status = params?.status as string | undefined;
        const nodeId = (params?.current_node ?? params?.currentNode) as string | undefined;

        // Handle terminal statuses: clear after respecting min visible time
        if (status === 'completed' || status === 'failed' || status === 'canceled' || status === 'cancelled') {
          // Mark not showing; schedule clear after MIN_VISIBLE
          q.showing = null;
          maybeClearAfterMin();
          return;
        }

        if (typeof nodeId !== 'string' || nodeId.length === 0) return;

        // Skip if same as current
        if (q.showing === nodeId) return;

        // Skip if shown very recently (cooldown)
        const last = q.recentShown.get(nodeId) || 0;
        if (now() - last < q.COOLDOWN_MS) return;

        // Ensure we respect min visible time for previous node; if not elapsed, delay switch a bit
        const elapsed = now() - (q.shownAt || 0);
        if (elapsed < q.MIN_VISIBLE_MS && q.showing) {
          const delay = Math.max(50, q.MIN_VISIBLE_MS - elapsed);
          setTimeout(() => {
            // Re-check cooldown and current before switching
            const last2 = q.recentShown.get(nodeId) || 0;
            if (q.showing === nodeId) return;
            if (now() - last2 < q.COOLDOWN_MS) return;
            show(nodeId);
          }, delay);
          return;
        }

        show(nodeId);
      } catch {}
    };

    eventBus.on('chat:latestSkillRunStat', handler);
    return () => {
      eventBus.off('chat:latestSkillRunStat', handler);
      try { if (q.clearT) clearTimeout(q.clearT); } catch {}
    };
  }, [setDisplay]);

  return null;
};

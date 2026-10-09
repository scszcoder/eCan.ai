import { useCallback, useEffect, useRef, useState } from 'react';
import { eventBus } from '@/utils/eventBus';
import { ksApi, KSJob } from '@/services/ipc/ksApi';

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);

export const isJobDone = (job?: KSJob | null) => !!job && TERMINAL.has(job.status);

/**
 * Follow one Knowledge Service job. Progress arrives as `ks.jobProgress`
 * pushes; polling every second is the fallback in case a push is missed.
 */
export function useJob(onDone?: (job: KSJob) => void) {
  const [job, setJob] = useState<KSJob | null>(null);
  const jobIdRef = useRef<string | null>(null);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  const apply = useCallback((next: KSJob) => {
    if (next.id !== jobIdRef.current) return;
    setJob(prev => {
      if (prev && prev.updated_at && next.updated_at && next.updated_at < prev.updated_at) return prev;
      if (isJobDone(next) && !isJobDone(prev)) {
        setTimeout(() => doneRef.current?.(next), 0);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    const handler = (msg: any) => {
      const payload = msg?.payload ?? msg;
      if (payload && payload.id) apply(payload as KSJob);
    };
    eventBus.on('localws:ks.jobProgress', handler);
    return () => eventBus.off('localws:ks.jobProgress', handler);
  }, [apply]);

  useEffect(() => {
    if (!job || isJobDone(job)) return;
    const timer = setInterval(async () => {
      try {
        apply(await ksApi.getJob(job.id));
      } catch {
        /* keep polling; the job row may not be visible yet */
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [job, apply]);

  const track = useCallback((started: KSJob) => {
    jobIdRef.current = started.id;
    setJob(started);
  }, []);

  const clear = useCallback(() => {
    jobIdRef.current = null;
    setJob(null);
  }, []);

  return { job, track, clear, running: !!job && !isJobDone(job) };
}

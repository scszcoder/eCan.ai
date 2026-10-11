import { useEffect, useState } from 'react';
import { get_ipc_api } from '@/services/ipc_api';

// Per-task run state from the runner (get_task_run_states): waiting for a
// resource, held for prerequisites, last missed run. One shared poll for all
// mounted task cards.

export interface TaskRunState {
  waiting_resource?: { resources: string[]; behind: string[]; since: number; class: string };
  waiting_after?: string[];
  last_missed?: { at: string; due: string; why: string };
}

type Listener = (states: Record<string, TaskRunState>) => void;

const POLL_MS = 5000;
const listeners = new Set<Listener>();
let latest: Record<string, TaskRunState> = {};
let timer: ReturnType<typeof setInterval> | undefined;

async function poll() {
  const api = get_ipc_api();
  if (!api) return;
  try {
    const res = await api.executeRequest<{ states: Record<string, TaskRunState> }>('get_task_run_states', {});
    if (res?.success && res.data?.states) {
      latest = res.data.states;
      listeners.forEach((l) => l(latest));
    }
  } catch {
    /* next poll */
  }
}

function subscribe(l: Listener) {
  listeners.add(l);
  if (!timer) {
    poll();
    timer = setInterval(poll, POLL_MS);
  }
  return () => {
    listeners.delete(l);
    if (!listeners.size && timer) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

export function useTaskRunState(taskId?: string): TaskRunState | undefined {
  const [state, setState] = useState<TaskRunState | undefined>(taskId ? latest[taskId] : undefined);
  useEffect(() => {
    if (!taskId) return undefined;
    setState(latest[taskId]);
    return subscribe((all) => {
      const next = all[taskId];
      setState((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
    });
  }, [taskId]);
  return state;
}

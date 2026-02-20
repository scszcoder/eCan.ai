import { create } from 'zustand';

interface DevTaskInfo {
  runId: string;
  skillId?: string;
  ecsTaskArn?: string;
  startedAt: number; // Date.now()
}

interface RunningNodeState {
  runningNodeId: string | null;
  setRunningNodeId: (nodeId: string | null) => void;
  /** The run_id of the currently active skill run (used for cancel/stop). */
  activeRunId: string | null;
  setActiveRunId: (runId: string | null) => void;

  /** All Fargate dev-mode tasks launched from skill editor during this session */
  devTasks: DevTaskInfo[];
  /** Track a newly launched dev-mode Fargate task */
  addDevTask: (task: DevTaskInfo) => void;
  /** Remove a dev task (e.g. after cancel or completion) */
  removeDevTask: (runId: string) => void;
  /** Clear all dev task tracking */
  clearDevTasks: () => void;
}

export const useRunningNodeStore = create<RunningNodeState>((set) => ({
  runningNodeId: null,
  setRunningNodeId: (nodeId) => {
    set({ runningNodeId: nodeId });
  },
  activeRunId: null,
  setActiveRunId: (runId) => {
    set({ activeRunId: runId });
  },

  devTasks: [],
  addDevTask: (task) => {
    set((state) => ({
      devTasks: [...state.devTasks.filter((t) => t.runId !== task.runId), task],
    }));
  },
  removeDevTask: (runId) => {
    set((state) => ({
      devTasks: state.devTasks.filter((t) => t.runId !== runId),
    }));
  },
  clearDevTasks: () => {
    set({ devTasks: [] });
  },
}));


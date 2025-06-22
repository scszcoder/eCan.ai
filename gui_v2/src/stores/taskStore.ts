// stores/taskStore.ts
import { create } from 'zustand';

interface TaskState {
  taskname: string | null;
  setTaskname: (taskname: string) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  taskname: null,
  setTaskname: (taskname) => set({ taskname }),
}));

import { create } from 'zustand';

/** A subscribed skill with a newer author version and/or changed prompts
 *  (gui/ipc/w2p_handlers/subscription_update_handler.py). */
export interface SubscriptionUpdate {
  skill_id: string;
  name: string;
  author: string;
  local_version?: string | null;
  cloud_version?: string | null;
  skill_newer: boolean;
  prompts: string[];
  /** Why it was not applied automatically (a task is using the skill). */
  busy?: string;
  error?: string;
}

export interface AppliedUpdate { skill_id: string; name: string }

interface SubscriptionUpdateState {
  items: SubscriptionUpdate[];
  /** Updates the backend applied on its own in the latest check (idle skills). */
  applied: AppliedUpdate[];
  checkedAt: number;
  setFromPush: (items: SubscriptionUpdate[], applied: AppliedUpdate[], checkedAt?: number) => void;
  setItems: (items: SubscriptionUpdate[]) => void;
  clearApplied: () => void;
}

export const useSubscriptionUpdateStore = create<SubscriptionUpdateState>((set) => ({
  items: [],
  applied: [],
  checkedAt: 0,
  setFromPush: (items, applied, checkedAt) => set({ items, applied, checkedAt: checkedAt || Date.now() / 1000 }),
  setItems: (items) => set({ items }),
  clearApplied: () => set({ applied: [] }),
}));

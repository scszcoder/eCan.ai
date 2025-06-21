// stores/userStore.ts
import { create } from 'zustand';

interface UserState {
  username: string | null;
  setUsername: (username: string | null) => void;
}

export const useUserStore = create<UserState>((set) => ({
  username: null,
  setUsername: (username) => set({ username }),
}));

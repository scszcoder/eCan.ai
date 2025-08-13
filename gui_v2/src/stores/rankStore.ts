// stores/taskStore.ts
import { create } from 'zustand';

interface OrganizationState {
  organizationname: string | null;
  setOrganizationname: (organizationname: string) => void;
}

export const useTaskStore = create<OrganizationState>((set) => ({
  organizationname: null,
  setOrganizationname: (organizationname) => set({ organizationname }),
}));

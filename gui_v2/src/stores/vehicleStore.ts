// stores/vehicleStore.ts
import { create } from 'zustand';

interface VehicleState {
  vehiclename: string | null;
  setVehiclename: (vehiclename: string) => void;
}

export const useVehicleStore = create<VehicleState>((set) => ({
  vehiclename: null,
  setVehiclename: (vehiclename) => set({ vehiclename }),
}));

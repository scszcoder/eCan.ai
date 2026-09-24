export interface StoreMeter {
  scenario_code: string;
  meter_code: string;
  display_name_zh: string;
  display_name_en: string;
  unit: string;
  definition: string;
  d7: number;
  d30: number;
}

export interface StoreLocal {
  agents: { id: string; name: string; running: boolean; status: string }[];
  tasks: { id: string; name: string; agent_id: string }[];
  meters: StoreMeter[];
}

/** One row of `store.overview`: cloud placement (may be absent) + local picture. */
export interface StoreRow {
  storeId: string;
  platform?: string;
  label?: string;
  status?: string;
  assignedVehicleId?: string | null;
  assignedVehicleOnline?: boolean | null;
  reportedVehicleId?: string | null;
  reportedVehicleOnline?: boolean | null;
  misplaced?: boolean;
  loginState?: string;
  lastReportedAt?: string | null;
  /** Billed amounts, in fen: what the account was charged, not the vendor cost. */
  llm30d?: { calls: number; tokens: number; costFen: number };
  /** The local catalog record: what the store IS (placement lives in the cloud). */
  definition?: { name: string; platform: string; store_urls: string[]; browser_profile_id?: string | null; source: string };
  /** false when the store is only known locally (no cloud row yet). */
  cloudKnown?: boolean;
  local: StoreLocal;
}

/** A machine a store can be assigned to (store.machines). */
export interface StoreMachine {
  id: string;
  name: string;
  type: string;          // 'desktop' | 'cloud'
  status: string;        // 'active' | 'offline'
  this?: boolean;
}

export interface StoreOverview {
  stores: StoreRow[];
  this_vehicle_id: string;
  cloud_error: string;
}

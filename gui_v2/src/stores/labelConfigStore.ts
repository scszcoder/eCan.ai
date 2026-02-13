// stores/labelConfigStore.ts
import { create } from 'zustand';
import { apiRouter } from '../services/api/api-router';
import type { APIResponse } from '../services/ipc/api';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from '../services/api/api-config';

export interface LabelConfig {
  name: string;
  id: string;
  unit: 'in' | 'mm';
  sheet_width: number;
  sheet_height: number;
  label_width: number;
  label_height: number;
  top_margin: number;
  left_margin: number;
  rows: number;
  cols: number;
  row_pitch: number;
  col_pitch: number;
  _filepath?: string;
  _filename?: string;
  _source?: string;
}

export type ConfigSource = 'system' | 'user' | 'custom';

const DEFAULT_CONFIG_KEY = 'labelConfig.defaultId';
const DEFAULT_CONFIG_ID = 'wl_5422'; // Initial default

/**
 * Unpack a label config from GraphQL response.
 * The lambda packs all non-schema fields (unit, dimensions, _source, etc.)
 * into the `settings` AWSJSON field.
 * For IPC, the data comes with fields directly on the object.
 */
function unpackLabelConfig(raw: any): LabelConfig {
  if (!raw || typeof raw !== 'object') return raw;
  // If settings is a JSON string, unpack dimension fields and _source
  // Handle multiple encoding levels: AppSync AWSJSON may return string or object
  let extra: any = null;
  if (typeof raw.settings === 'string') {
    try {
      let parsed = JSON.parse(raw.settings);
      // Handle double-encoding: if parsed result is still a string, parse again
      if (typeof parsed === 'string') {
        try { parsed = JSON.parse(parsed); } catch { /* use first parse result */ }
      }
      if (parsed && typeof parsed === 'object') {
        extra = parsed;
      }
    } catch { /* ignore parse error */ }
  } else if (raw.settings && typeof raw.settings === 'object') {
    // AppSync AWSJSON may also return the object directly
    extra = raw.settings;
  }
  if (extra) {
    return { ...extra, id: raw.id, name: raw.name || extra.name };
  }
  return raw;
}

interface LabelConfigStoreState {
  systemConfigs: LabelConfig[];
  userConfigs: LabelConfig[];
  selectedConfig: LabelConfig | null;
  selectedSource: ConfigSource;
  isCustomMode: boolean;
  customConfig: LabelConfig;
  loading: boolean;
  error: string | null;
  lastFetched: number | null;
  defaultConfigId: string;
  
  // Actions
  fetchConfigs: () => Promise<void>;
  forceRefresh: () => Promise<void>;
  selectConfig: (config: LabelConfig, source: ConfigSource) => void;
  enterCustomMode: () => void;
  updateCustomConfig: (updates: Partial<LabelConfig>) => void;
  saveCustomConfig: (overwrite?: boolean) => Promise<{ success: boolean; error?: string }>;
  deleteUserConfig: (id: string) => Promise<{ success: boolean; error?: string }>;
  checkNameExists: (name: string, excludeId?: string) => Promise<boolean>;
  setDefaultConfig: (id: string) => void;
  clearError: () => void;
}

const DEFAULT_CUSTOM_CONFIG: LabelConfig = {
  name: '',
  id: '',
  unit: 'in',
  sheet_width: 8.5,
  sheet_height: 11.0,
  label_width: 4.0,
  label_height: 2.0,
  top_margin: 0.5,
  left_margin: 0.25,
  rows: 5,
  cols: 2,
  row_pitch: 0.0,
  col_pitch: 0.0,
};

export const useLabelConfigStore = create<LabelConfigStoreState>((set, get) => ({
  systemConfigs: [],
  userConfigs: [],
  selectedConfig: null,
  selectedSource: 'system',
  isCustomMode: false,
  customConfig: { ...DEFAULT_CUSTOM_CONFIG },
  loading: false,
  error: null,
  lastFetched: null,
  defaultConfigId: localStorage.getItem(DEFAULT_CONFIG_KEY) || DEFAULT_CONFIG_ID,

  fetchConfigs: async () => {
    const { lastFetched } = get();
    const now = Date.now();
    const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

    if (lastFetched && now - lastFetched < CACHE_DURATION) {
      console.log('[LabelConfigStore] Using cached configs');
      return;
    }

    console.log('[LabelConfigStore] Fetching label configs from backend...');
    set({ loading: true, error: null });
    try {
      const response: APIResponse<any> = await apiRouter.execute(
        {
          method: 'label_config.get_all',
          graphql: {
            query: GRAPHQL_QUERIES.GET_LABEL_FORMATS,
            resultPath: 'getLabelFormats'
          }
        },
        {}
      );

      console.log('[LabelConfigStore] Response:', response);

      if (response.success && response.data) {
        let system_configs: LabelConfig[] = [];
        let user_configs: LabelConfig[] = [];

        if (Array.isArray(response.data)) {
          // GraphQL path: flat array with _source packed in settings
          const allConfigs = response.data.map(unpackLabelConfig);
          system_configs = allConfigs.filter((c: any) => c._source === 'system');
          user_configs = allConfigs.filter((c: any) => c._source === 'user');
        } else {
          // IPC path: { system_configs, user_configs }
          system_configs = response.data.system_configs || [];
          user_configs = response.data.user_configs || [];
        }

        console.log('[LabelConfigStore] Loaded', system_configs.length, 'system configs,', user_configs.length, 'user configs');
        set({
          systemConfigs: system_configs,
          userConfigs: user_configs,
          loading: false,
          lastFetched: Date.now(),
        });

        // Auto-select default config if nothing selected
        const state = get();
        if (!state.selectedConfig) {
          const allConfigs = [...(system_configs || []), ...(user_configs || [])];
          const defaultConfig = allConfigs.find(c => c.id === state.defaultConfigId);
          if (defaultConfig) {
            const source = (system_configs || []).some(c => c.id === defaultConfig.id) ? 'system' : 'user';
            set({ selectedConfig: defaultConfig, selectedSource: source });
          } else if (system_configs && system_configs.length > 0) {
            set({ selectedConfig: system_configs[0], selectedSource: 'system' });
          }
        }
      } else {
        console.error('[LabelConfigStore] Failed to fetch:', response.error);
        throw new Error(response.error?.message || 'Failed to fetch label configs');
      }
    } catch (error) {
      console.error('[LabelConfigStore] Error fetching configs:', error);
      const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
      set({ error: errorMessage, loading: false });
    }
  },

  forceRefresh: async () => {
    set({ lastFetched: null });
    await get().fetchConfigs();
  },

  selectConfig: (config: LabelConfig, source: ConfigSource) => {
    set({
      selectedConfig: config,
      selectedSource: source,
      isCustomMode: false,
    });
  },

  enterCustomMode: () => {
    set({
      isCustomMode: true,
      selectedSource: 'custom',
      customConfig: { ...DEFAULT_CUSTOM_CONFIG },
      selectedConfig: null,
    });
  },

  updateCustomConfig: (updates: Partial<LabelConfig>) => {
    const { customConfig } = get();
    set({
      customConfig: { ...customConfig, ...updates },
    });
  },

  saveCustomConfig: async (overwrite = false) => {
    const { customConfig } = get();

    if (!customConfig.name || !customConfig.name.trim()) {
      return { success: false, error: 'Name is required' };
    }

    // Generate id from name if not set
    const configToSave = {
      ...customConfig,
      id: customConfig.id || customConfig.name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, ''),
    };

    try {
      const exists = get().userConfigs.some(c => c.id === configToSave.id);
      const mutation = exists ? GRAPHQL_MUTATIONS.UPDATE_LABEL_FORMATS : GRAPHQL_MUTATIONS.ADD_LABEL_FORMATS;
      const resultPath = exists ? 'UpdateLabelFormats' : 'addLabelFormats';
      const response: APIResponse<any> = await apiRouter.execute(
        {
          method: 'label_config.save',
          graphql: { mutation, resultPath }
        },
        { config: configToSave, overwrite, input: [configToSave] }
      );

      if (response.success && response.data) {
        // Refresh configs to get updated list
        await get().forceRefresh();
        
        // Select the newly saved config
        const { userConfigs } = get();
        const savedConfig = userConfigs.find(c => c.id === configToSave.id);
        if (savedConfig) {
          set({
            selectedConfig: savedConfig,
            selectedSource: 'user',
            isCustomMode: false,
          });
        }
        
        return { success: true };
      } else {
        return { success: false, error: response.error?.message || 'Failed to save config' };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
      return { success: false, error: errorMessage };
    }
  },

  deleteUserConfig: async (id: string) => {
    try {
      const response: APIResponse<any> = await apiRouter.execute(
        {
          method: 'label_config.delete',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_LABEL_FORMATS,
            resultPath: 'RemoveLabelFormats'
          }
        },
        { id, ids: [id] }
      );

      if (response.success) {
        await get().forceRefresh();
        
        // If deleted config was selected, clear selection
        const { selectedConfig } = get();
        if (selectedConfig?.id === id) {
          const { systemConfigs } = get();
          if (systemConfigs.length > 0) {
            set({ selectedConfig: systemConfigs[0], selectedSource: 'system' });
          } else {
            set({ selectedConfig: null });
          }
        }
        
        return { success: true };
      } else {
        return { success: false, error: response.error?.message || 'Failed to delete config' };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
      return { success: false, error: errorMessage };
    }
  },

  checkNameExists: async (name: string, excludeId?: string) => {
    // For web mode, check locally in loaded configs instead of IPC call
    const { systemConfigs, userConfigs } = get();
    const allConfigs = [...systemConfigs, ...userConfigs];
    return allConfigs.some(c => c.name === name && c.id !== excludeId);
  },

  setDefaultConfig: (id: string) => {
    localStorage.setItem(DEFAULT_CONFIG_KEY, id);
    set({ defaultConfigId: id });
  },

  clearError: () => {
    set({ error: null });
  },
}));

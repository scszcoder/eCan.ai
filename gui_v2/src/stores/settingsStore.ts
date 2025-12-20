// stores/settingsStore.ts
/**
 * Application Settings Store
 * 
 * ⚠️ IMPORTANT: Settings are APPLICATION-LEVEL configurations, NOT user preferences!
 * 
 * Settings include:
 * - debug_mode: Application debug mode
 * - local_server_port: Local server port
 * - default_webdriver_path: WebDriver path
 * - default_llm: Default LLM provider
 * - wan_api_endpoint: Cloud API endpoint
 * - ... other application-level configurations
 * 
 * These settings are:
 * ✅ Shared across all users
 * ✅ Loaded at application startup
 * ✅ Persisted globally (not per-user)
 * ✅ Managed by Settings page UI
 * 
 * Usage:
 * 1. Load settings at app startup: await useSettingsStore.getState().loadSettings()
 * 2. Access in components: const { settings } = useSettingsStore()
 * 3. Update settings: updateSettings(partial) or setSettings(full)
 * 4. Save settings: await saveSettings(newSettings)
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { Settings } from '@/pages/Settings/types';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';

interface SettingsState {
  // Application settings (shared across all users)
  settings: Settings | null;
  
  // Loading state
  isLoading: boolean;
  
  // Error state
  error: string | null;
  
  // Actions
  setSettings: (settings: Settings) => void;
  updateSettings: (partialSettings: Partial<Settings>) => void;
  loadSettings: () => Promise<void>;
  saveSettings: (settings: Settings) => Promise<boolean>;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

// Helper to load settings from backend
const loadSettingsFromBackend = async (): Promise<Settings | null> => {
  try {
    const api = get_ipc_api();
    if (!api) {
      logger.warn('[SettingsStore] IPC API not available');
      return null;
    }

    const response = await api.getSettings<{ settings: Settings; message: string }>('system');
    if (response.success && response.data?.settings) {
      logger.info('[SettingsStore] Settings loaded from backend');
      return response.data.settings;
    }
    
    logger.warn('[SettingsStore] No settings returned from backend');
    return null;
  } catch (error) {
    logger.error('[SettingsStore] Failed to load settings from backend:', error);
    return null;
  }
};

// Helper to save settings to backend
const saveSettingsToBackend = async (settings: Settings): Promise<boolean> => {
  try {
    const api = get_ipc_api();
    if (!api) {
      logger.warn('[SettingsStore] IPC API not available');
      return false;
    }

    const response = await api.saveSettings(settings);
    if (response.success) {
      logger.info('[SettingsStore] Settings saved to backend successfully');
      return true;
    }
    
    logger.error('[SettingsStore] Failed to save settings:', response.error);
    return false;
  } catch (error) {
    logger.error('[SettingsStore] Error saving settings:', error);
    return false;
  }
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: null,
      isLoading: false,
      error: null,

      /**
       * Set application settings
       */
      setSettings: (settings: Settings) => {
        logger.debug('[SettingsStore] Setting application settings');
        set({ settings, error: null });
      },

      /**
       * Update partial settings (merge with existing)
       */
      updateSettings: (partialSettings: Partial<Settings>) => {
        const { settings } = get();
        if (!settings) {
          logger.warn('[SettingsStore] Cannot update settings: no settings loaded');
          return;
        }

        logger.debug('[SettingsStore] Updating partial settings');
        set({ 
          settings: {
            ...settings,
            ...partialSettings
          },
          error: null
        });
      },

      /**
       * Load settings from backend
       */
      loadSettings: async () => {
        logger.info('[SettingsStore] Loading settings from backend...');
        set({ isLoading: true, error: null });
        
        try {
          const settings = await loadSettingsFromBackend();
          if (settings) {
            set({ settings, isLoading: false, error: null });
          } else {
            set({ isLoading: false, error: 'Failed to load settings' });
          }
        } catch (error) {
          logger.error('[SettingsStore] Error loading settings:', error);
          set({ isLoading: false, error: String(error) });
        }
      },

      /**
       * Save settings to backend
       */
      saveSettings: async (settings: Settings) => {
        logger.info('[SettingsStore] Saving settings to backend...');
        set({ isLoading: true, error: null });
        
        try {
          const success = await saveSettingsToBackend(settings);
          if (success) {
            set({ settings, isLoading: false, error: null });
            return true;
          } else {
            set({ isLoading: false, error: 'Failed to save settings' });
            return false;
          }
        } catch (error) {
          logger.error('[SettingsStore] Error saving settings:', error);
          set({ isLoading: false, error: String(error) });
          return false;
        }
      },

      /**
       * Set loading state
       */
      setLoading: (isLoading: boolean) => {
        set({ isLoading });
      },

      /**
       * Set error state
       */
      setError: (error: string | null) => {
        set({ error });
      },

      /**
       * Reset to initial state
       */
      reset: () => {
        logger.info('[SettingsStore] Resetting settings store');
        set({ settings: null, isLoading: false, error: null });
      },
    }),
    {
      name: 'ecan-app-settings',
      storage: createJSONStorage(() => localStorage),
      
      // Only persist settings, not loading/error states
      partialize: (state) => ({
        settings: state.settings,
      }),
    }
  )
);

// Helper functions for convenient access
export const getSettings = (): Settings | null => {
  return useSettingsStore.getState().settings;
};

export const isSettingsLoaded = (): boolean => {
  return useSettingsStore.getState().settings !== null;
};

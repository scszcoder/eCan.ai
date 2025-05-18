import { create } from 'zustand';
import type { SystemInfo, AppSettings } from '../types/ipc';

interface AppState {
    systemInfo: SystemInfo | null;
    settings: AppSettings;
    isConnected: boolean;
    setSystemInfo: (info: SystemInfo) => void;
    setSettings: (settings: AppSettings) => void;
    setConnected: (connected: boolean) => void;
}

const defaultSettings: AppSettings = {
    theme: 'light',
    language: 'zh-CN',
    autoStart: false,
};

export const useAppStore = create<AppState>((set) => ({
    systemInfo: null,
    settings: defaultSettings,
    isConnected: false,
    setSystemInfo: (info) => set({ systemInfo: info }),
    setSettings: (settings) => set({ settings }),
    setConnected: (connected) => set({ isConnected: connected }),
})); 
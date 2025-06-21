import { create } from 'zustand';

interface SystemInfo {
    version: string;
    platform: string;
    memory: {
        total: number;
        used: number;
    };
}

interface AppSettings {
    theme: 'light' | 'dark';
    language: string;
    autoStart: boolean;
}

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
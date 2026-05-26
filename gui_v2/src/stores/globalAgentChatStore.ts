import { create } from 'zustand';

export const DEFAULT_CHAT_WIDTH = 360;
export const MIN_CHAT_WIDTH = 280;
export const MAX_CHAT_WIDTH = 600;

interface GlobalAgentChatState {
  isCollapsed: boolean;
  width: number;
  mounted: boolean;
  toggle: () => void;
  open: () => void;
  close: () => void;
  setWidth: (width: number) => void;
  resizeBy: (delta: number) => void;
}

const clampWidth = (w: number) =>
  Math.max(MIN_CHAT_WIDTH, Math.min(MAX_CHAT_WIDTH, w));

const readFreshHandoff = (): boolean => {
  try {
    const raw = sessionStorage.getItem('ecanSkillEditorHandoff');
    if (!raw) return false;
    const payload = JSON.parse(raw);
    const stashedAt = Number(payload?.stashed_at_ms || 0);
    return Number.isFinite(stashedAt) && stashedAt > 0 && (Date.now() - stashedAt) < 5 * 60 * 1000;
  } catch {
    return false;
  }
};

const initialFresh = readFreshHandoff();

export const useGlobalAgentChatStore = create<GlobalAgentChatState>((set) => ({
  isCollapsed: !initialFresh,
  width: DEFAULT_CHAT_WIDTH,
  mounted: initialFresh,
  toggle: () => set((s) => ({
    isCollapsed: !s.isCollapsed,
    mounted: s.mounted || s.isCollapsed,
  })),
  open: () => set({ isCollapsed: false, mounted: true }),
  close: () => set({ isCollapsed: true }),
  setWidth: (width) => set({ width: clampWidth(width) }),
  resizeBy: (delta) => set((s) => ({ width: clampWidth(s.width + delta) })),
}));

/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { create } from 'zustand';
import type { SkillInfo } from '../typings/skill-info';

interface SkillInfoStoreState {
  skillInfo: SkillInfo | null;
  setSkillInfo: (info: SkillInfo) => void;
  breakpoints: string[];
  addBreakpoint: (nodeId: string) => void;
  removeBreakpoint: (nodeId: string) => void;
  setBreakpoints: (nodeIds: string[]) => void;
  // File path tracking for desktop platform
  currentFilePath: string | null;
  setCurrentFilePath: (path: string | null) => void;
  hasUnsavedChanges: boolean;
  setHasUnsavedChanges: (hasChanges: boolean) => void;
  previewMode: boolean;
  setPreviewMode: (preview: boolean) => void;
}

export const useSkillInfoStore = create<SkillInfoStoreState>((set) => ({
  skillInfo: null,
  setSkillInfo: (info) => set({ skillInfo: info }),
  breakpoints: [],
  addBreakpoint: (nodeId) =>
    set((state) => ({ breakpoints: [...new Set([...state.breakpoints, nodeId])] })), // Avoid duplicates
  removeBreakpoint: (nodeId) =>
    set((state) => ({ breakpoints: state.breakpoints.filter((id) => id !== nodeId) })),
  setBreakpoints: (nodeIds) => set({ breakpoints: nodeIds }),
  // File path tracking
  currentFilePath: null,
  setCurrentFilePath: (path) => set({ currentFilePath: path }),
  hasUnsavedChanges: false,
  setHasUnsavedChanges: (hasChanges) => set({ hasUnsavedChanges: hasChanges }),
  previewMode: false,
  setPreviewMode: (preview) => set({ previewMode: preview }),
}));
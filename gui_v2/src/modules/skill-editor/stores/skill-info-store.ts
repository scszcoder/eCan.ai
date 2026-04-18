/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { create } from 'zustand';
import type { SkillInfo } from '../typings/skill-info';

export interface ToolsetDef {
  name: string;
  description?: string;
  toolNames: string[];
}

export interface SkillsetDef {
  name: string;
  description?: string;
  skillIds: string[];
}

interface SkillInfoStoreState {
  skillInfo: SkillInfo | null;
  setSkillInfo: (info: SkillInfo) => void;
  toolsets: ToolsetDef[];
  setToolsets: (toolsets: ToolsetDef[]) => void;
  skillsets: SkillsetDef[];
  setSkillsets: (skillsets: SkillsetDef[]) => void;
  dataMappingJson: string | null;
  dataMappingPath: string | null;
  dataMappingDirty: boolean;
  setDataMappingJson: (json: string | null, dirty?: boolean) => void;
  setDataMappingPath: (path: string | null) => void;
  setDataMappingDirty: (dirty: boolean) => void;
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
  // Cloud execution toggle - when true, skill runs in cloud worker
  runInCloud: boolean;
  setRunInCloud: (runInCloud: boolean) => void;
  // Hybrid cloud mode - when true, a local helper skill works with the cloud skill
  hybridCloudMode: boolean;
  setHybridCloudMode: (hybridCloudMode: boolean) => void;
  // Local helper skill ID for hybrid cloud mode
  localHelperSkillId: string | null;
  setLocalHelperSkillId: (skillId: string | null) => void;
  // Local helper machine hostname for hybrid cloud mode
  localHelperMachine: string | null;
  setLocalHelperMachine: (machine: string | null) => void;
  // Loading guard — true while a skill file is being loaded onto the canvas
  isSkillLoading: boolean;
  setIsSkillLoading: (loading: boolean) => void;
}

export const useSkillInfoStore = create<SkillInfoStoreState>((set) => ({
  skillInfo: null,
  setSkillInfo: (info) => set({ skillInfo: info }),
  toolsets: [],
  setToolsets: (toolsets) => set({ toolsets }),
  skillsets: [],
  setSkillsets: (skillsets) => set({ skillsets }),
  dataMappingJson: null,
  dataMappingPath: null,
  dataMappingDirty: false,
  setDataMappingJson: (json, dirty = false) => set({ dataMappingJson: json, dataMappingDirty: dirty }),
  setDataMappingPath: (path) => set({ dataMappingPath: path }),
  setDataMappingDirty: (dirty) => set({ dataMappingDirty: dirty }),
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
  // Cloud execution - default is local (false)
  runInCloud: false,
  setRunInCloud: (runInCloud) => set({ runInCloud }),
  // Hybrid cloud mode - default is false
  hybridCloudMode: false,
  setHybridCloudMode: (hybridCloudMode) => set({ hybridCloudMode }),
  // Local helper skill ID - default is null
  localHelperSkillId: null,
  setLocalHelperSkillId: (skillId) => set({ localHelperSkillId: skillId }),
  // Local helper machine hostname - default is null
  localHelperMachine: null,
  setLocalHelperMachine: (machine) => set({ localHelperMachine: machine }),
  // Loading guard - true while a skill is being loaded
  isSkillLoading: false,
  setIsSkillLoading: (loading) => set({ isSkillLoading: loading }),
}));
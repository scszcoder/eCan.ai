/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { create } from 'zustand';
import type { SkillInfo } from '../../typings/skill-info';

interface SkillInfoStoreState {
  skillInfo: SkillInfo | null;
  setSkillInfo: (info: SkillInfo) => void;
}

export const useSkillInfoStore = create<SkillInfoStoreState>((set) => ({
  skillInfo: null,
  setSkillInfo: (info) => set({ skillInfo: info }),
})); 
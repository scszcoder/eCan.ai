/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { unstableSetCreateRoot } from '@flowgram.ai/form-materials';

/**
 * React 18+ polyfill for form-materials
 * Fixes "unmountComponentAtNode is deprecated" warning
 * This runs once when skill-editor module is imported
 */
unstableSetCreateRoot((dom: HTMLElement) => {
  const root = createRoot(dom);
  return {
    render: (children: React.ReactNode) => root.render(children),
    unmount: () => root.unmount(),
  };
});

export { Editor } from './editor';

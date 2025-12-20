/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useState, useEffect } from 'react';

import { CommentEditorModel } from '../model';
import { CommentEditorEvent } from '../constant';

export const usePlaceholder = (params: { model: CommentEditorModel }): string | undefined => {
  const { model } = params;

  const [placeholder, setPlaceholder] = useState<string | undefined>('Enter a comment...');

  // 监听 change 事件
  useEffect(() => {
    const changeDisposer = model.on((event: any) => {
      if (event.type !== CommentEditorEvent.Change) {
        return;
      }
      if (event.value) {
        setPlaceholder(undefined);
      } else {
        setPlaceholder('Enter a comment...');
      }
    });
    return () => {
      changeDisposer.dispose();
    };
  }, [model]);

  return placeholder;
};

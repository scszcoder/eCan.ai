/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useCallback, useEffect, useState } from 'react';

import { useCurrentEntity, useService } from '@flowgram.ai/free-layout-editor';
import {
  NodeIntoContainerService,
  NodeIntoContainerType,
} from '@flowgram.ai/free-container-plugin';

import { TipsGlobalStore } from './global-store';

export const useControlTips = () => {
  const node = useCurrentEntity();
  const [visible, setVisible] = useState(false);
  const globalStore = TipsGlobalStore.instance;

  const nodeIntoContainerService = useService<NodeIntoContainerService>(NodeIntoContainerService);

  const show = useCallback(() => {
    if (globalStore.isClosed()) {
      return;
    }

    setVisible(true);
  }, [globalStore]);

  const close = useCallback(() => {
    globalStore.close();
    setVisible(false);
  }, [globalStore]);

  const closeForever = useCallback(() => {
    globalStore.closeForever();
    close();
  }, [close, globalStore]);

  useEffect(() => {
    // Listen移入
    const inDisposer = nodeIntoContainerService.on((e) => {
      if (e.type !== NodeIntoContainerType.In) {
        return;
      }
      if (e.targetContainer === node) {
        show();
      }
    });
    // Listen移出Event
    const outDisposer = nodeIntoContainerService.on((e) => {
      if (e.type !== NodeIntoContainerType.Out) {
        return;
      }
      if (e.sourceContainer === node && !node.blocks.length) {
        setVisible(false);
      }
    });
    return () => {
      inDisposer.dispose();
      outDisposer.dispose();
    };
  }, [nodeIntoContainerService, node, show, close, visible]);

  return {
    visible,
    close,
    closeForever,
  };
};

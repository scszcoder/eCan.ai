/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState } from 'react';

import classNames from 'classnames';
import { IconChevronDown } from '@douyinfe/semi-icons';

import { useNodeRenderContext } from '../../../../hooks';

import styles from './index.module.less';

interface NodeStatusBarProps {
  header?: React.ReactNode;
  defaultShowDetail?: boolean;
  extraBtns?: React.ReactNode[];
}

export const NodeStatusHeader: React.FC<React.PropsWithChildren<NodeStatusBarProps>> = ({
  header,
  defaultShowDetail,
  children,
  extraBtns = [],
}) => {
  const [showDetail, setShowDetail] = useState(defaultShowDetail);
  const { selectNode } = useNodeRenderContext();

  const handleToggleShowDetail = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectNode(e);
    setShowDetail(!showDetail);
  };

  return (
    <div
      className={styles['node-status-header']}
      // Must要Forbid down 冒泡，防止判定圈选和 node hover（不Support多边形）
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div
        className={classNames(
          styles['node-status-header-content'],
          showDetail && styles['node-status-header-content-opened']
        )}
        // Must要Forbid down 冒泡，防止判定圈选和 node hover（不Support多边形）
        onMouseDown={(e) => e.stopPropagation()}
        // 其他Event统一走ClickEvent，且也Need阻止冒泡
        onClick={handleToggleShowDetail}
      >
        <div className={styles['status-title']}>
          {header}
          {extraBtns.length > 0 ? extraBtns : null}
        </div>
        <div className={styles['status-btns']}>
          <IconChevronDown
            className={classNames({
              [styles['is-show-detail']]: showDetail,
            })}
          />
        </div>
      </div>
      {showDetail ? children : null}
    </div>
  );
};

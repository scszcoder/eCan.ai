/**
 * TreeWidget - Renders a `{type: "tree"}` chat widget sent by a cloud agent:
 * host/vehicle -> store -> agent -> task -> skill, each node expandable to
 * show its details and its children. The desktop builds the data
 * (agent/a2a/machine_tree.py) and the cloud passes it through untouched, so
 * the names and counts here come from the machines, not from a model.
 */

import React, { useMemo } from 'react';
import { Tree } from 'antd';
import type { DataNode } from 'antd/es/tree';
import {
  ApartmentOutlined, AppstoreOutlined, DesktopOutlined, FolderOutlined,
  RobotOutlined, ScheduleOutlined, ShopOutlined,
} from '@ant-design/icons';
import styled from 'styled-components';

export interface TreeWidgetNode {
  key: string;
  kind?: string;          // host | store | agent | task | skill | group
  label: string;
  badge?: string;
  details?: Array<{ label: string; value: string }>;
  children?: TreeWidgetNode[];
}

export interface TreeWidgetSpec {
  type: 'tree';
  title?: string;
  nodes: TreeWidgetNode[];
  /** keys expanded at first (the rest start collapsed) */
  expand?: string[];
}

/** A payload's widget when it is one this panel can draw, else undefined. */
export const asTreeWidget = (w: any): TreeWidgetSpec | undefined =>
  w && typeof w === 'object' && w.type === 'tree' && Array.isArray(w.nodes) ? (w as TreeWidgetSpec) : undefined;

const KIND_ICON: Record<string, React.ReactNode> = {
  host: <DesktopOutlined />,
  store: <ShopOutlined />,
  agent: <RobotOutlined />,
  task: <ScheduleOutlined />,
  skill: <AppstoreOutlined />,
  group: <FolderOutlined />,
};

const Card = styled.div`
  background: rgba(30, 41, 59, 0.9);
  border: 1px solid rgba(59, 130, 246, 0.35);
  border-radius: 12px;
  padding: 12px 12px 8px;
  margin: 8px 0;
  max-width: 100%;
  overflow-x: auto;

  .ant-tree {
    background: transparent;
    color: #e2e8f0;
    font-size: 13px;
  }
  .ant-tree .ant-tree-node-content-wrapper:hover {
    background: rgba(59, 130, 246, 0.15);
  }
  .ant-tree .ant-tree-switcher {
    color: #94a3b8;
  }
`;

const Title = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
`;

const Label = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 6px;
`;

const Badge = styled.span<{ $warn?: boolean }>`
  font-size: 11px;
  padding: 0 6px;
  border-radius: 8px;
  line-height: 18px;
  color: ${p => (p.$warn ? '#fbbf24' : '#93c5fd')};
  background: ${p => (p.$warn ? 'rgba(251, 191, 36, 0.12)' : 'rgba(59, 130, 246, 0.15)')};
`;

const Detail = styled.span`
  font-size: 12px;
  color: #94a3b8;

  b {
    font-weight: 500;
    color: #cbd5e1;
  }
`;

const WARN = /offline|not loaded|not runnable|failed|no store record/i;

const toData = (n: TreeWidgetNode): DataNode => {
  // Details are leaf rows shown when the node is expanded, ahead of its children.
  const detailRows: DataNode[] = (n.details || []).map((d, i) => ({
    key: `${n.key}#d${i}`,
    selectable: false,
    isLeaf: true,
    title: <Detail><b>{d.label}:</b> {d.value}</Detail>,
  }));
  const children = [...detailRows, ...(n.children || []).map(toData)];
  return {
    key: n.key,
    selectable: false,
    title: (
      <Label>
        {KIND_ICON[n.kind || ''] || <ApartmentOutlined />}
        <span>{n.label}</span>
        {n.badge ? <Badge $warn={WARN.test(n.badge)}>{n.badge}</Badge> : null}
      </Label>
    ),
    children: children.length ? children : undefined,
    isLeaf: children.length === 0,
  };
};

export const TreeWidget: React.FC<{ widget: TreeWidgetSpec }> = ({ widget }) => {
  const treeData = useMemo(() => widget.nodes.map(toData), [widget]);
  return (
    <Card>
      {widget.title ? <Title><ApartmentOutlined />{widget.title}</Title> : null}
      <Tree
        showLine={{ showLeafIcon: false }}
        blockNode
        treeData={treeData}
        defaultExpandedKeys={widget.expand || widget.nodes.map(n => n.key)}
      />
    </Card>
  );
};

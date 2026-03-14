/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

/* eslint-disable no-console */
import { useMemo } from 'react';

import { debounce } from 'lodash-es';
import { createMinimapPlugin } from '@flowgram.ai/minimap-plugin';
import { createFreeSnapPlugin } from '@flowgram.ai/free-snap-plugin';
import { createFreeNodePanelPlugin } from '@flowgram.ai/free-node-panel-plugin';
import { createFreeLinesPlugin } from '@flowgram.ai/free-lines-plugin';
import { createFreeHistoryPlugin } from '@flowgram.ai/free-history-plugin';
import { createFreeStackPlugin } from '@flowgram.ai/free-stack-plugin';
import {
  FlowNodeBaseType,
  FreeLayoutProps,
  FreeLayoutPluginContext,
  WorkflowDocument,
  WorkflowNodeEntity,
} from '@flowgram.ai/free-layout-editor';
import { createFreeGroupPlugin } from '@flowgram.ai/free-group-plugin';
import { createContainerNodePlugin } from '@flowgram.ai/free-container-plugin';

import { canContainNode, onDragLineEnd } from '../utils';
import { FlowNodeRegistry, FlowDocumentJSON } from '../typings';
import { shortcuts } from '../shortcuts';
import { CustomService, ValidateService } from '../services';
import { WorkflowRuntimeService } from '../plugins/runtime-plugin/runtime-service';
import {
  createRuntimePlugin,
  createContextMenuPlugin,
  createVariablePanelPlugin,
  createPanelManagerPlugin,
} from '../plugins';
import { defaultFormMeta } from '../nodes/default-form-meta';
import { WorkflowNodeType } from '../nodes';
import { useNodeFlipStore } from '../stores/node-flip-store';
import { SelectorBoxPopover } from '../components/selector-box-popover';
import { BaseNode, CommentRender, GroupNodeRender, LineAddButton, NodePanel } from '../components';
import { useSkillInfoStore } from '../stores/skill-info-store';
import { useSheetsStore } from '../stores/sheets-store';
import { traverseWorkflowNodes } from '../utils/traverse-workflow-nodes';
import { setWorkflowDocumentRef } from '../workflow-document-binding';

export function useEditorProps(
  initialData: FlowDocumentJSON,
  nodeRegistries: FlowNodeRegistry[]
): FreeLayoutProps {
  return useMemo<FreeLayoutProps>(
    () => ({
      /**
       * Whether to enable the background
       */
      background: true,
      /**
       * 画布相关Configuration
       * Canvas-related configurations
       */
      playground: {
        /**
         * Prevent Mac browser gestures from turning pages
         * 阻止 mac Browser手势翻页
         */
        preventGlobalGesture: true,
        /**
         * Enable canvas panning by dragging on empty areas
         * 启用画布拖拽功能
         */
        grabDisable: false,
      },
      /**
       * Whether it is read-only or not, the node cannot be dragged in read-only mode
       */
      readonly: false,
      /**
       * Line support both-way connection (default true)
       * 线条支持双向连接
       */
      twoWayConnection: true,
      /**
       * Initial data
       * InitializeData
       */
      initialData,
      /**
       * Node registries
       * 节点Register
       */
      nodeRegistries,
      /**
       * Get the default node registry, which will be merged with the 'nodeRegistries'
       * 提供Default的节点Register，这个会和 nodeRegistries 做合并
       */
      getNodeDefaultRegistry(type) {
        return {
          type,
          meta: {
            defaultExpanded: false,
          },
          formMeta: defaultFormMeta,
        };
      },
      /**
       * 节点DataConvert, 由 ctx.document.fromJSON 调用
       * Node data transformation, called by ctx.document.fromJSON
       * @param node
       * @param json
       */
      fromNodeJSON(_node, json) {
        return json;
      },
      /**
       * 节点DataConvert, 由 ctx.document.toJSON 调用
       * Node data transformation, called by ctx.document.toJSON
       * @param node
       * @param json
       */
      toNodeJSON(_node, json) {
        return json;
      },
      lineColor: {
        hidden: 'var(--g-workflow-line-color-hidden,transparent)',
        default: 'var(--g-workflow-line-color-default,#4d53e8)',
        drawing: 'var(--g-workflow-line-color-drawing, #5DD6E3)',
        hovered: 'var(--g-workflow-line-color-hover,#37d0ff)',
        selected: 'var(--g-workflow-line-color-selected,#37d0ff)',
        error: 'var(--g-workflow-line-color-error,red)',
        flowing: 'var(--g-workflow-line-color-flowing,#4d53e8)',
      },
      /*
       * Check whether the line can be added
       * 判断是否连线
       */
      canAddLine(_ctx, fromPort, toPort) {
        // Cannot be a self-loop on the same node / 不能是同一节点自Loop
        if (fromPort.node === toPort.node) {
          return false;
        }
        // Cannot be in different containers - 不能在不同Container
        if (
          fromPort.node.parent?.id !== toPort.node.parent?.id &&
          ![fromPort.node.parent?.flowNodeType, toPort.node.parent?.flowNodeType].includes(
            FlowNodeBaseType.GROUP
          )
        ) {
          return false;
        }
        // Allow all feedback loops and cyclic connections
        return true;
      },
      /**
       * Check whether the line can be deleted, this triggers on the default shortcut `Bakspace` or `Delete`
       * 判断是否能Delete连线, 这个会在Default快捷键 (Backspace or Delete) Trigger
       */
      canDeleteLine(_ctx, _line, _newLineInfo, _silent) {
        return true;
      },
      /**
       * Check whether the node can be deleted, this triggers on the default shortcut `Bakspace` or `Delete`
       * 判断是否能Delete节点, 这个会在Default快捷键 (Backspace or Delete) Trigger
       */
      canDeleteNode(_ctx, _node) {
        return true;
      },
      /**
       * 是否允许拖入子画布 (loop or group)
       * Whether to allow dragging into the sub-canvas (loop or group)
       */
      canDropToNode: (_ctx, params) => canContainNode(params.dragNodeType!, params.dropNodeType!),
      /**
       * Whether to reset line
       * 是否允许重连
       * @param ctx
       * @param oldLine
       * @param newLineInfo
       */
      canResetLine: (_ctx, _oldLine, _newLineInfo) => true,
      /**
       * Drag the end of the line to create an add panel (feature optional)
       * 拖拽线条结束需要创建一个添加面板 （功能可选）
       * 希望提供控制线条粗细的配置项
       */
      onDragLineEnd,
      /**
       * SelectBox config
       */
      selectBox: {
        SelectorBoxPopover,
      },
      scroll: {
        /**
         * Whether to restrict the node from rolling out of the canvas needs to be closed because there is a running results pane
         * 是否Limit节点不能滚出画布，由于有RunResult面板，所以NeedClose
         */
        enableScrollLimit: false,
      },
      materials: {
        components: {},
        /**
         * Render Node
         */
        renderDefaultNode: BaseNode,
        renderNodes: {
          [WorkflowNodeType.Comment]: CommentRender,
        },
      },
      /**
       * Node engine enable, you can configure formMeta in the FlowNodeRegistry
       */
      nodeEngine: {
        enable: true,
      },
      /**
       * Variable engine enable
       */
      variableEngine: {
        enable: true,
      },
      /**
       * Redo/Undo enable
       */
      history: {
        enable: true,
        /**
         * Listen form data change, default true
         */
        enableChangeNode: true,
      },
      /**
       * Content change
       * TEMPORARILY DISABLED: Testing if onContentChange causes the crash
       */
      onContentChange: debounce((ctx) => {
        try {
          const json = ctx?.document?.toJSON?.();
          if (!json) {
            return;
          }

          const { isFlipped } = useNodeFlipStore.getState();
          const breakpoints = new Set<string>(useSkillInfoStore.getState().breakpoints || []);

          const syncNodeState = (nodes: any[]) => {
            traverseWorkflowNodes(nodes, (node: any) => {
              if (!node.data) {
                node.data = {};
              }

              if (isFlipped(node.id)) {
                node.data.hFlip = true;
              } else if (node.data.hFlip) {
                delete node.data.hFlip;
              }

              if (breakpoints.has(node.id)) {
                node.data.breakpoint = true;
              } else if (node.data.breakpoint) {
                delete node.data.breakpoint;
              }
            });
          };

          if (Array.isArray(json.nodes)) {
            syncNodeState(json.nodes);
          }

          useSheetsStore.getState().saveActiveDocument(json);
          useSkillInfoStore.getState().setHasUnsavedChanges(true);
        } catch (error) {
          console.warn('[onContentChange] Failed to sync document state:', error);
        }
      }, 250),
      /**
       * Running line
       */
      isFlowingLine: (ctx, line) => {
        try {
          return ctx.get(WorkflowRuntimeService).isFlowingLine(line);
        } catch {
          // WorkflowRuntimeService might not be available in all contexts
          return false;
        }
      },
      /**
       * Shortcuts
       */
      shortcuts,
      /**
       * Bind custom service
       */
      onBind: ({ bind, isBound }) => {
        bind(CustomService).toSelf().inSingletonScope();
        bind(ValidateService).toSelf().inSingletonScope();
        if (!isBound(WorkflowDocument)) {
          bind(WorkflowDocument).toDynamicValue(({ container }) => {
            const context = container.get(FreeLayoutPluginContext) as FreeLayoutPluginContext;
            const document = context.document;
            if (!document) {
              throw new Error('WorkflowDocument requested before initialisation');
            }
            setWorkflowDocumentRef(document);
            return document;
          }).inSingletonScope();
        }
      },
      /**
       * Playground init
       */
      onInit(ctx) {
        console.log('--- Playground init ---');
        setWorkflowDocumentRef(ctx.document);
      },
      /**
       * Playground render
       */
      onAllLayersRendered(ctx) {
        // ctx.tools.autoLayout(); // init auto layout
        ctx.tools.fitView(false);
        console.log('--- Playground rendered ---');
      },
      /**
       * Playground dispose
       */
      onDispose() {
        console.log('---- Playground Dispose ----');
        setWorkflowDocumentRef(null);
      },
      i18n: {
        locale: navigator.language,
        languages: {
          'zh-CN': {
            'Never Remind': '不再Prompt',
            'Hold {{key}} to drag node out': '按住 {{key}} Can将节点拖出',
          },
          'en-US': {},
        },
      },
      plugins: () => [
        /**
         * Line render plugin
         * 连线Render插件
         */
        createFreeLinesPlugin({
          renderInsideLine: LineAddButton,
        }),
        /**
         * History plugin
         * 历史记录插件
         */
        createFreeHistoryPlugin({}),
        /**
         * Custom node sorting, the code below will make the comment nodes always below the normal nodes
         * 自定义节点排序，下边的代码会让 comment 节点永远在普通节点下边
         */
        createFreeStackPlugin({
          sortNodes: (nodes: WorkflowNodeEntity[]) => {
            const commentNodes: WorkflowNodeEntity[] = [];
            const otherNodes: WorkflowNodeEntity[] = [];
            nodes.forEach((node) => {
              if (node.flowNodeType === WorkflowNodeType.Comment) {
                commentNodes.push(node);
              } else {
                otherNodes.push(node);
              }
            });
            return [...commentNodes, ...otherNodes];
          },
        }),
        /**
         * Minimap plugin
         * 缩略图插件
         */
        createMinimapPlugin({
          disableLayer: true,
          canvasStyle: {
            canvasWidth: 182,
            canvasHeight: 102,
            canvasPadding: 50,
            canvasBackground: 'rgba(242, 243, 245, 1)',
            canvasBorderRadius: 10,
            viewportBackground: 'rgba(255, 255, 255, 1)',
            viewportBorderRadius: 4,
            viewportBorderColor: 'rgba(6, 7, 9, 0.10)',
            viewportBorderWidth: 1,
            viewportBorderDashLength: undefined,
            nodeColor: 'rgba(0, 0, 0, 0.10)',
            nodeBorderRadius: 2,
            nodeBorderWidth: 0.145,
            nodeBorderColor: 'rgba(6, 7, 9, 0.10)',
            overlayColor: 'rgba(255, 255, 255, 0.55)',
          },
          inactiveDebounceTime: 1,
        }),

        /**
         * Snap plugin
         * 自动Align及Helper线插件
         */
        createFreeSnapPlugin({
          edgeColor: '#00B2B2',
          alignColor: '#00B2B2',
          edgeLineWidth: 1,
          alignLineWidth: 1,
          alignCrossWidth: 8,
        }),
        /**
         * NodeAddPanel render plugin
         * 节点Add面板Render插件
         */
        createFreeNodePanelPlugin({
          renderer: NodePanel,
        }),
        /**
         * This is used for the rendering of the loop node sub-canvas
         * 这个Used for loop 节点子画布的Render
         */
        createContainerNodePlugin({}),
        /**
         * Group plugin
         */
        createFreeGroupPlugin({
          groupNodeRender: GroupNodeRender,
        }),
        /**
         * ContextMenu plugin
         */
        createContextMenuPlugin({}),
        /**
         * Runtime plugin
         */
        createRuntimePlugin({
          mode: 'browser',
          // mode: 'server',
          // serverConfig: {
          //   domain: 'localhost',
          //   port: 4000,
          //   protocol: 'http',
          // },
        }),

        /**
         * Variable panel plugin
         * 变量面板插件
         */
        createVariablePanelPlugin({}),
        /** Float layout plugin */
        createPanelManagerPlugin(),
      ],
    }),
    []
  );
}

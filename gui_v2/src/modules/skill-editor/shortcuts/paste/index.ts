/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import {
  delay,
  EntityManager,
  FlowNodeTransformData,
  FreeLayoutPluginContext,
  IPoint,
  PlaygroundConfigEntity,
  Rectangle,
  ShortcutsHandler,
  WorkflowDocument,
  WorkflowDragService,
  WorkflowHoverService,
  WorkflowJSON,
  WorkflowNodeEntity,
  WorkflowNodeMeta,
  WorkflowSelectService,
  Playground,
} from '@flowgram.ai/free-layout-editor';
import { Toast } from '@douyinfe/semi-ui';

import { WorkflowClipboardData, WorkflowClipboardRect } from '../type';
import { FlowCommandId, WorkflowClipboardDataID } from '../constants';
import { generateUniqueWorkflow } from './unique-workflow';
import { canContainNode } from '../../utils';

export class PasteShortcut implements ShortcutsHandler {
  public commandId = FlowCommandId.PASTE;

  public shortcuts = ['meta v', 'ctrl v'];

  private playgroundConfig: PlaygroundConfigEntity;

  private document: WorkflowDocument;

  private selectService: WorkflowSelectService;

  private entityManager: EntityManager;

  private hoverService: WorkflowHoverService;

  private dragService: WorkflowDragService;

  private playground: Playground;

  /**
   * initialize paste shortcut handler - Initialize粘贴快捷键Process器
   */
  constructor(context: FreeLayoutPluginContext) {
    this.playgroundConfig = context.playground.config;
    this.document = context.get(WorkflowDocument);
    this.selectService = context.get(WorkflowSelectService);
    this.entityManager = context.get(EntityManager);
    this.hoverService = context.get(WorkflowHoverService);
    this.dragService = context.get(WorkflowDragService);
    this.playground = context.playground;
    this.execute = this.execute.bind(this);
  }

  /**
   * execute paste action - Execute粘贴Operation
   */
  public async execute(): Promise<WorkflowNodeEntity[] | undefined> {
    if (this.readonly) {
      return;
    }
    const data = await this.tryReadClipboard();
    if (!data) {
      return;
    }
    if (!this.isValidData(data)) {
      return;
    }
    const nodes = this.apply(data);
    if (nodes.length > 0) {
      Toast.success({
        content: 'Copy successfully',
        showClose: false,
      });
      // wait for nodes to render - 等待节点Render
      await this.nextTick();
      // scroll to visible area - Scroll到可视区域
      this.scrollNodesToView(nodes);
    }
    return nodes;
  }

  /** apply clipboard data - 应用剪切板Data */
  public apply(data: WorkflowClipboardData): WorkflowNodeEntity[] {
    // extract raw json from clipboard data - 从剪贴板Data中提取原始JSON
    const { json: rawJSON } = data;
    const json = generateUniqueWorkflow({
      json: rawJSON,
      isUniqueId: (id: string) => !this.entityManager.getEntityById(id),
    });

    const offset = this.calcPasteOffset(data.bounds);
    let parent = this.getSelectedContainer();
    // loop 不支持嵌套
    if (parent && json.nodes.some((n) => !canContainNode(n.type, parent!.flowNodeType))) {
      parent = undefined;
    }
    this.applyOffset({ json, offset, parent });
    const { nodes } = this.document.batchAddFromJSON(json, {
      parent,
    });
    this.selectNodes(nodes);
    // 这里Need focus 画布才能继续使用快捷键
    // The focus canvas is needed here to continue using the shortcuts
    this.playground.node.focus();
    return nodes;
  }

  /**
   * readonly - 是否只读
   */
  private get readonly(): boolean {
    return this.playgroundConfig.readonly;
  }

  private isValidData(data?: WorkflowClipboardData): boolean {
    if (data?.type !== WorkflowClipboardDataID) {
      Toast.error({
        content: 'Invalid clipboard data',
      });
      return false;
    }
    // Cross-domain means different environments, different plugins, cannot be copied - 跨域名表示不同Environment，上架插件不同，不能复制
    if (data.source.host !== window.location.host) {
      Toast.error({
        content: 'Cannot paste nodes from different host',
      });
      return false;
    }
    // Check container - CheckContainer
    const parent = this.getSelectedContainer();
    for (const nodeJSON of data.json.nodes) {
      const res = this.dragService.canDropToNode({
        dragNodeType: nodeJSON.type,
        dropNodeType: parent?.flowNodeType,
        dropNode: parent,
      });
      if (!res.allowDrop) {
        Toast.error({
          content: res.message ?? 'Cannot paste nodes to invalid container',
        });
        return false;
      }
    }
    return true;
  }

  /** try to read clipboard - 尝试读取剪贴板 */
  private async tryReadClipboard(): Promise<WorkflowClipboardData | undefined> {
    try {
      // need user permission to access clipboard, may throw NotAllowedError - NeedUser授予网页剪贴板读取Permission, IfUser没有授予Permission, Code可能会抛出Exception NotAllowedError
      const text: string = (await navigator.clipboard.readText()) || '';
      const clipboardData: WorkflowClipboardData = JSON.parse(text);
      return clipboardData;
    } catch (e) {
      // clipboard data is not fixed, no need to show error - 这里本身剪贴板里的Data就不固定，所以没必要报错
      return;
    }
  }

  /** calculate paste offset - 计算粘贴偏移 */
  private calcPasteOffset(boundsData: WorkflowClipboardRect): IPoint {
    // extract bounds data - 提取BoundaryData
    const { x, y, width, height } = boundsData;
    const rect = new Rectangle(x, y, width, height);
    const { center } = rect;
    const mousePos = this.hoverService.hoveredPos;
    return {
      x: mousePos.x - center.x,
      y: mousePos.y - center.y,
    };
  }

  /**
   * apply offset to node positions - 应用偏移到节点Position
   */
  private applyOffset(params: {
    json: WorkflowJSON;
    offset: IPoint;
    parent?: WorkflowNodeEntity;
  }): void {
    const { json, offset, parent } = params;
    json.nodes.forEach((nodeJSON) => {
      if (!nodeJSON.meta?.position) {
        return;
      }
      // calculate new position - 计算新Position
      let position = {
        x: nodeJSON.meta.position.x + offset.x,
        y: nodeJSON.meta.position.y + offset.y,
      };
      if (parent) {
        position = this.dragService.adjustSubNodePosition(
          nodeJSON.type as string,
          parent,
          position
        );
      }
      nodeJSON.meta.position = position;
    });
  }

  /** get selected container node - Get鼠标选中的Container */
  private getSelectedContainer(): WorkflowNodeEntity | undefined {
    const { activatedNode } = this.selectService;
    return activatedNode?.getNodeMeta<WorkflowNodeMeta>().isContainer ? activatedNode : undefined;
  }

  /** select nodes - 选中节点 */
  private selectNodes(nodes: WorkflowNodeEntity[]): void {
    this.selectService.selection = nodes;
  }

  /** scroll to nodes - Scroll到节点 */
  private async scrollNodesToView(nodes: WorkflowNodeEntity[]): Promise<void> {
    const nodeBounds = nodes.map((node) => node.getData(FlowNodeTransformData).bounds);
    await this.document.playgroundConfig.scrollToView({
      bounds: Rectangle.enlarge(nodeBounds),
    });
  }

  /** wait for next frame - 等待下一帧 */
  private async nextTick(): Promise<void> {
    // 16ms is one render frame - 16ms 为一个Render帧
    const frameTime = 16;
    await delay(frameTime);
    await new Promise((resolve) => requestAnimationFrame(resolve));
  }
}

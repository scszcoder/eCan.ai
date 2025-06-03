import {
  WorkflowNodeJSON as FlowNodeJSONDefault,
  WorkflowNodeRegistry as FlowNodeRegistryDefault,
  FreeLayoutPluginContext,
  FlowNodeEntity,
  type WorkflowEdgeJSON,
  WorkflowNodeMeta,
} from '@flowgram.ai/free-layout-editor';
import { IFlowValue } from '@flowgram.ai/form-materials';

import { type JsonSchema } from './json-schema';
import { type CallableFunction } from './callable';

/**
 * Interface for defining a goal
 * 定义目标的接口
 */
export interface Goal {
  /**
   * Goal name
   * 目标名称
   */
  name: string;
  
  /**
   * Goal description
   * 目标描述
   */
  description: string;
  
  /**
   * Minimum criteria for goal achievement
   * 目标达成的最低标准
   */
  minCriteria: string;
  
  /**
   * Goal score
   * 目标分数
   */
  score: number;
  
  /**
   * Goal weight
   * 目标权重
   */
  weight: number;
}

/**
 * Interface for defining node state
 * 定义节点状态的接口
 */
export interface NodeState {
  /**
   * Input data
   * 输入数据
   */
  input: Record<string, any>;
  
  /**
   * Message history
   * 消息历史
   */
  messages: any[];
  
  /**
   * Execution result
   * 执行结果
   */
  result: Record<string, any>;
  
  /**
   * Number of retries
   * 重试次数
   */
  retries: number;
  
  /**
   * Whether the node is resolved
   * 节点是否已解决
   */
  resolved: boolean;
  
  /**
   * Condition evaluation result
   * 条件评估结果
   */
  condition: boolean;
  
  /**
   * Case identifier
   * 案例标识符
   */
  case: string;
  
  /**
   * List of goals
   * 目标列表
   */
  goals: Goal[];
}

/**
 * You can customize the data of the node, and here you can use JsonSchema to define the input and output of the node
 * 你可以自定义节点的 data 业务数据, 这里演示 通过 JsonSchema 来定义节点的输入/输出
 */
export interface FlowNodeJSON extends FlowNodeJSONDefault {
  data: {
    /**
     * Node title
     */
    title?: string;
    /**
     * Inputs data values
     */
    inputsValues?: Record<string, IFlowValue>;
    /**
     * Define the inputs data of the node by JsonSchema
     */
    inputs?: JsonSchema;
    /**
     * Define the outputs data of the node by JsonSchema
     */
    outputs?: JsonSchema;
    /**
     * callable function data
     */
    callable?: CallableFunction;
    /**
     * Rest properties
     */
    [key: string]: any;
  };
}

/**
 * You can customize your own node meta
 * 你可以自定义节点的meta
 */
export interface FlowNodeMeta extends WorkflowNodeMeta {
  disableSideBar?: boolean;
}

/**
 * You can customize your own node registry
 * 你可以自定义节点的注册器
 */
export interface FlowNodeRegistry extends FlowNodeRegistryDefault {
  meta: FlowNodeMeta;
  info?: {
    icon: string;
    description: string;
  };
  canAdd?: (ctx: FreeLayoutPluginContext) => boolean;
  canDelete?: (ctx: FreeLayoutPluginContext, from: FlowNodeEntity) => boolean;
  onAdd?: (ctx: FreeLayoutPluginContext) => FlowNodeJSON;
}

export interface FlowDocumentJSON {
  nodes: FlowNodeJSON[];
  edges: WorkflowEdgeJSON[];
}

import { customAlphabet } from 'nanoid';
import type { WorkflowJSON, WorkflowNodeJSON } from '@flowgram.ai/free-layout-editor';

import { traverse, TraverseContext } from './traverse';

namespace UniqueWorkflowUtils {
  /** generate unique id - 生成唯一ID */
  const generateUniqueId = customAlphabet('1234567890', 6); // create a function to generate 6-digit number - Create一个生成6位数字的Function

  /** get all node ids from workflow json - 从工作流JSON中GetAll节点ID */
  export const getAllNodeIds = (json: WorkflowJSON): string[] => {
    const nodeIds = new Set<string>(); // use set to store unique ids - 使用SetStorage唯一ID
    const addNodeId = (node: WorkflowNodeJSON) => {
      nodeIds.add(node.id);
      if (node.blocks?.length) {
        node.blocks.forEach((child) => addNodeId(child)); // recursively add child node ids - RecursiveAdd子节点ID
      }
    };
    json.nodes.forEach((node) => addNodeId(node));
    return Array.from(nodeIds);
  };

  /** generate node replacement mapping - 生成节点替换Map */
  export const generateNodeReplaceMap = (
    nodeIds: string[],
    isUniqueId: (id: string) => boolean
  ): Map<string, string> => {
    const nodeReplaceMap = new Map<string, string>(); // create map for id replacement - CreateID替换Map
    nodeIds.forEach((id) => {
      if (isUniqueId(id)) {
        nodeReplaceMap.set(id, id); // keep original id if unique - IfID唯一则保持不变
      } else {
        let newId: string;
        do {
          newId = generateUniqueId(); // generate new id until unique - 生成新ID直到唯一
        } while (!isUniqueId(newId));
        nodeReplaceMap.set(id, newId);
      }
    });
    return nodeReplaceMap;
  };

  /** check if value exists - CheckValue是否存在 */
  const isExist = (value: unknown): boolean => value !== null && value !== undefined;

  /** check if node should be handled - Check节点是否NeedProcess */
  const shouldHandle = (context: TraverseContext): boolean => {
    const { node } = context;
    // check edge data - Check边Data
    if (
      node?.key &&
      ['sourceNodeID', 'targetNodeID'].includes(node.key) &&
      node.parent?.parent?.key === 'edges'
    ) {
      return true;
    }
    // check node data - Check节点Data
    if (
      node?.key === 'id' &&
      isExist(node.container?.type) &&
      isExist(node.container?.meta) &&
      isExist(node.container?.data)
    ) {
      return true;
    }
    // check variable data - Check变量Data
    if (
      node?.key === 'blockID' &&
      isExist(node.container?.name) &&
      node.container?.source === 'block-output'
    ) {
      return true;
    }
    return false;
  };

  /**
   * replace node ids in workflow json - 替换工作流JSON中的节点ID
   * notice: this method has side effects, it will modify the input json to avoid deep copy overhead
   * - Note：此Method有副作用，会修改Input的json以避免深拷贝开销
   */
  export const replaceNodeId = (
    json: WorkflowJSON,
    nodeReplaceMap: Map<string, string>
  ): WorkflowJSON => {
    traverse(json, (context) => {
      if (!shouldHandle(context)) {
        return;
      }
      const { node } = context;
      if (nodeReplaceMap.has(node.value)) {
        context.setValue(nodeReplaceMap.get(node.value)); // replace old id with new id - 用新ID替换旧ID
      }
    });
    return json;
  };
}

/** generate unique workflow json - 生成唯一工作流JSON */
export const generateUniqueWorkflow = (params: {
  json: WorkflowJSON;
  isUniqueId: (id: string) => boolean;
}): WorkflowJSON => {
  const { json, isUniqueId } = params;
  const nodeIds = UniqueWorkflowUtils.getAllNodeIds(json); // get all existing node ids - GetAll现有节点ID
  const nodeReplaceMap = UniqueWorkflowUtils.generateNodeReplaceMap(nodeIds, isUniqueId); // generate id replacement map - 生成ID替换Map
  return UniqueWorkflowUtils.replaceNodeId(json, nodeReplaceMap); // replace all node ids - 替换All节点ID
};

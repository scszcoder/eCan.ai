// traverse value type - TraverseValueType
export type TraverseValue = any;

// traverse node interface - Traverse节点Interface
export interface TraverseNode {
  value: TraverseValue; // node value - 节点Value
  container?: TraverseValue; // parent container - 父Container
  parent?: TraverseNode; // parent node - 父节点
  key?: string; // object key - 对象键名
  index?: number; // array index - 数组索引
}

// traverse context interface - Traverse上下文Interface
export interface TraverseContext {
  node: TraverseNode; // current node - When前节点
  setValue: (value: TraverseValue) => void; // set value function - SettingsValueFunction
  getParents: () => TraverseNode[]; // get parents function - Get父节点Function
  getPath: () => Array<string | number>; // get path function - GetPathFunction
  getStringifyPath: () => string; // get string path function - Get字符串PathFunction
  deleteSelf: () => void; // delete self function - Delete自身Function
}

// traverse handler type - TraverseProcess器Type
export type TraverseHandler = (context: TraverseContext) => void;

/**
 * traverse object deeply and handle each value - DepthTraverse对象并Process每个Value
 * @param value traverse target - Traverse目标
 * @param handle handler function - ProcessFunction
 */
export const traverse = <T extends TraverseValue = TraverseValue>(
  value: T,
  handler: TraverseHandler | TraverseHandler[]
): T => {
  const traverseHandler: TraverseHandler = Array.isArray(handler)
    ? (context: TraverseContext) => {
        handler.forEach((handlerFn) => handlerFn(context));
      }
    : handler;
  TraverseUtils.traverseNodes({ value }, traverseHandler);
  return value;
};

namespace TraverseUtils {
  /**
   * traverse nodes deeply and handle each value - DepthTraverse节点并Process每个Value
   * @param node traverse node - Traverse节点
   * @param handle handler function - ProcessFunction
   */
  export const traverseNodes = (node: TraverseNode, handle: TraverseHandler): void => {
    const { value } = node;
    if (!value) {
      // handle null value - Process空Value
      return;
    }
    if (Object.prototype.toString.call(value) === '[object Object]') {
      // traverse object properties - Traverse对象Property
      Object.entries(value).forEach(([key, item]) =>
        traverseNodes(
          {
            value: item,
            container: value,
            key,
            parent: node,
          },
          handle
        )
      );
    } else if (Array.isArray(value)) {
      // traverse array elements from end to start - 从末尾开始Traverse数组元素
      for (let index = value.length - 1; index >= 0; index--) {
        const item: string = value[index];
        traverseNodes(
          {
            value: item,
            container: value,
            index,
            parent: node,
          },
          handle
        );
      }
    }
    const context: TraverseContext = createContext({ node });
    handle(context);
  };

  /**
   * create traverse context - CreateTraverse上下文
   * @param node traverse node - Traverse节点
   */
  const createContext = ({ node }: { node: TraverseNode }): TraverseContext => ({
    node,
    setValue: (value: unknown) => setValue(node, value),
    getParents: () => getParents(node),
    getPath: () => getPath(node),
    getStringifyPath: () => getStringifyPath(node),
    deleteSelf: () => deleteSelf(node),
  });

  /**
   * set node value - Settings节点Value
   * @param node traverse node - Traverse节点
   * @param value new value - 新Value
   */
  const setValue = (node: TraverseNode, value: unknown) => {
    // handle empty value - Process空Value
    if (!value || !node) {
      return;
    }
    node.value = value;
    // get container info from parent scope - 从父作用域GetContainerInformation
    const { container, key, index } = node;
    if (key && container) {
      container[key] = value;
    } else if (typeof index === 'number') {
      container[index] = value;
    }
  };

  /**
   * get parent nodes - Get父节点List
   * @param node traverse node - Traverse节点
   */
  const getParents = (node: TraverseNode): TraverseNode[] => {
    const parents: TraverseNode[] = [];
    let currentNode: TraverseNode | undefined = node;
    while (currentNode) {
      parents.unshift(currentNode);
      currentNode = currentNode.parent;
    }
    return parents;
  };

  /**
   * get node path - Get节点Path
   * @param node traverse node - Traverse节点
   */
  const getPath = (node: TraverseNode): Array<string | number> => {
    const path: Array<string | number> = [];
    const parents = getParents(node);
    parents.forEach((parent) => {
      if (parent.key) {
        path.unshift(parent.key);
      } else if (parent.index) {
        path.unshift(parent.index);
      }
    });
    return path;
  };

  /**
   * get stringify path - Get字符串Path
   * @param node traverse node - Traverse节点
   */
  const getStringifyPath = (node: TraverseNode): string => {
    const path = getPath(node);
    return path.reduce((stringifyPath: string, pathItem: string | number) => {
      if (typeof pathItem === 'string') {
        const re = /\W/g;
        if (re.test(pathItem)) {
          // handle special characters - Process特殊字符
          return `${stringifyPath}["${pathItem}"]`;
        }
        return `${stringifyPath}.${pathItem}`;
      } else {
        return `${stringifyPath}[${pathItem}]`;
      }
    }, '');
  };

  /**
   * delete current node - DeleteWhen前节点
   * @param node traverse node - Traverse节点
   */
  const deleteSelf = (node: TraverseNode): void => {
    const { container, key, index } = node;
    if (key && container) {
      delete container[key];
    } else if (typeof index === 'number') {
      container.splice(index, 1);
    }
  };
}

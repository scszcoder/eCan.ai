type ConditionValue = {
  key: string;
  value?: any;
};

type NodeLike = {
  id: string;
  meta?: {
    position?: {
      x?: number;
      y?: number;
    };
  };
};

type EdgeLike = {
  source?: string;
  sourceNodeID?: string;
  sourcePortID?: string;
  sourcePortId?: string;
  target?: string;
  targetNodeID?: string;
};

export const getConditionType = (key: string): 'if' | 'elif' | 'else' => {
  if (key.startsWith('if_')) return 'if';
  if (key.startsWith('elif_')) return 'elif';
  if (key.startsWith('else_')) return 'else';
  return 'elif';
};

const getSemanticBuckets = (conditions: ConditionValue[]) => {
  const ordered = [...conditions];
  const ifConditions = ordered.filter((item) => getConditionType(item.key) === 'if');
  const elifConditions = ordered.filter((item) => getConditionType(item.key) === 'elif');
  const elseConditions = ordered.filter((item) => getConditionType(item.key) === 'else');
  return { ifConditions, elifConditions, elseConditions };
};

export const getOrderedConditions = (
  conditions: ConditionValue[],
  preferredPortOrder?: string[],
): ConditionValue[] => {
  if (!Array.isArray(conditions) || conditions.length === 0) return [];

  const { ifConditions, elifConditions, elseConditions } = getSemanticBuckets(conditions);
  const preferredIndex = new Map((preferredPortOrder ?? []).map((key, index) => [key, index]));

  const orderedElifs = [...elifConditions].sort((a, b) => {
    const indexA = preferredIndex.get(a.key);
    const indexB = preferredIndex.get(b.key);
    if (indexA != null && indexB != null) return indexA - indexB;
    if (indexA != null) return -1;
    if (indexB != null) return 1;
    return 0;
  });

  return [...ifConditions, ...orderedElifs, ...elseConditions];
};

export const buildConditionPortOrder = (
  nodeId: string,
  conditions: ConditionValue[],
  nodes: NodeLike[],
  edges: EdgeLike[],
): string[] => {
  const base = getOrderedConditions(conditions);
  if (base.length <= 2) {
    return base.map((item) => item.key);
  }

  const { ifConditions, elifConditions, elseConditions } = getSemanticBuckets(base);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const sourceEdges = edges.filter((edge) => (edge.sourceNodeID ?? edge.source) === nodeId);

  const scoreForKey = (key: string, fallbackIndex: number) => {
    const targetYs = sourceEdges
      .filter((edge) => (edge.sourcePortID ?? edge.sourcePortId) === key)
      .map((edge) => edge.targetNodeID ?? edge.target)
      .filter((targetId): targetId is string => Boolean(targetId))
      .map((targetId) => nodeById.get(targetId)?.meta?.position?.y)
      .filter((y): y is number => typeof y === 'number');

    if (targetYs.length === 0) {
      return Number.MAX_SAFE_INTEGER / 2 + fallbackIndex;
    }

    return targetYs.reduce((sum, y) => sum + y, 0) / targetYs.length;
  };

  const sortedElifs = [...elifConditions]
    .map((condition, index) => ({
      condition,
      score: scoreForKey(condition.key, index),
      index,
    }))
    .sort((a, b) => a.score - b.score || a.index - b.index)
    .map((item) => item.condition);

  return [...ifConditions, ...sortedElifs, ...elseConditions].map((item) => item.key);
};

/**
 * Like buildConditionPortOrder but reads target positions from the live Flowgram
 * entity graph (via document.getNode) instead of from the JSON snapshot.
 * Used for the final polish pass after the second dagre run.
 */
export const buildConditionPortOrderFromEntities = (
  nodeId: string,
  conditions: ConditionValue[],
  conditionEntity: any,
  document: any,
  edges: EdgeLike[],
): string[] => {
  const base = getOrderedConditions(conditions);
  if (base.length <= 2) {
    return base.map((item) => item.key);
  }

  const { ifConditions, elifConditions, elseConditions } = getSemanticBuckets(base);
  const sourceEdges = edges.filter((edge) => (edge.sourceNodeID ?? edge.source) === nodeId);

  const scoreForKey = (key: string, fallbackIndex: number) => {
    const targetIds = sourceEdges
      .filter((edge) => (edge.sourcePortID ?? edge.sourcePortId) === key)
      .map((edge) => edge.targetNodeID ?? edge.target)
      .filter((targetId): targetId is string => Boolean(targetId));

    const targetYs = targetIds
      .map((targetId) => {
        try {
          const targetEntity = document.getNode?.(targetId);
          const transform = targetEntity?.transform;
          return transform?.position?.y;
        } catch {
          return undefined;
        }
      })
      .filter((y): y is number => typeof y === 'number');

    if (targetYs.length === 0) {
      return Number.MAX_SAFE_INTEGER / 2 + fallbackIndex;
    }

    return targetYs.reduce((sum, y) => sum + y, 0) / targetYs.length;
  };

  const sortedElifs = [...elifConditions]
    .map((condition, index) => ({
      condition,
      score: scoreForKey(condition.key, index),
      index,
    }))
    .sort((a, b) => a.score - b.score || a.index - b.index)
    .map((item) => item.condition);

  return [...ifConditions, ...sortedElifs, ...elseConditions].map((item) => item.key);
};

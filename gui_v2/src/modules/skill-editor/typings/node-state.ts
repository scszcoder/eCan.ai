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
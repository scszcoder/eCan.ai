/**
 * Interface for defining a goal
 * Definition目标的Interface
 */
export interface Goal {
    /**
     * Goal name
     * 目标Name
     */
    name: string;
    
    /**
     * Goal description
     * 目标Description
     */
    description: string;
    
    /**
     * Minimum criteria for goal achievement
     * 目标达成的最低Standard
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
   * Definition节点Status的Interface
   */
  export interface NodeState {
    /**
     * Input data
     * InputData
     */
    input: Record<string, any>;
    
    /**
     * Message history
     * Message历史
     */
    messages: any[];
    
    /**
     * Execution result
     * ExecuteResult
     */
    result: Record<string, any>;
    
    /**
     * Number of retries
     * Retry次数
     */
    retries: number;
    
    /**
     * Whether the node is resolved
     * 节点是否已解决
     */
    resolved: boolean;
    
    /**
     * Condition evaluation result
     * 条件评估Result
     */
    condition: boolean;
    
    /**
     * Case identifier
     * 案例标识符
     */
    case: string;
    
    /**
     * List of goals
     * 目标List
     */
    goals: Goal[];
  }
// 工具相关的类型定义
export interface Tool {
  name: string;
  description: string;
  inputSchema: {
    type: string;
    required: string[];
    properties: Record<string, any>;
  };
  annotations: any;
} 
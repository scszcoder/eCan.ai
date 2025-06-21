export interface Tool {
  name: string;
  description: string;
  inputSchema: {
    type: string;
    required: string[];
    properties: Record<string, any>;
  };
  annotations: any;
  // 更多属性...
} 
export interface Tool {
  name: string;
  title: string | null;
  description: string;
  inputSchema: any;
  outputSchema: any;
  annotations: any;
  meta: any;
} 
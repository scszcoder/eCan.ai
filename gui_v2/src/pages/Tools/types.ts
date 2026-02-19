export interface Tool {
  id: string;
  name: string;
  title: string | null;
  description: string;
  owner: string;
  tool_type: string;
  version: string;
  path: string;
  level: number;
  config: any;
  capabilities: any;
  limitations: any;
  dependencies: any;
  public: boolean;
  rentable: boolean;
  price: number;
  price_model: string | null;
  status: string;
  settings: any;
  inputSchema: any;
  outputSchema: any;
  icons: any;
  annotations: any;
  meta: any;
  source?: string;
  readOnly?: boolean;
}

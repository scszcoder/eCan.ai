// 代理相关的类型定义
export interface Agent {
  card: {
    name: string;
    id: string;
    description: string;
    url: string;
    provider: string | null;
    version: string;
    documentationUrl: string | null;
    capabilities: {
      streaming: boolean;
      pushNotifications: boolean;
      stateTransitionHistory: boolean;
    };
    authentication: any;
    defaultInputModes: string[];
    defaultOutputModes: string[];
  };
  supervisors: any[];
  subordinates: any[];
  peers: any[];
  rank: string;
  organizations: any[];
  job_description: string;
  personalities: any[];
} 
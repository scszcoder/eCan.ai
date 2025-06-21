// 技能相关的类型定义
export interface Skill {
  id: string;
  work_flow: any;
  owner: string;
  name: string;
  description: string;
  config: any;
  ui_info: {
    text: string;
    icon: string;
  };
  objectives: any[];
  need_inputs: any[];
  version: string;
  level: string;
} 
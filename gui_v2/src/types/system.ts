// 通用类型定义
export interface Knowledge {
  [key: string]: any;
}

export interface Chat {
  [key: string]: any;
}

// 系统完整数据结构
export interface SystemData {
  token: string;
  agents: Agent[];
  skills: Skill[];
  tools: Tool[];
  tasks: Task[];
  vehicles: Vehicle[];
  settings: Settings;
  knowledges: Knowledge;
  chats: Chat;
  message: string;
}

// 从其他文件导入类型
import { Agent } from './agent';
import { Skill } from './skill';
import { Tool } from './tool';
import { Task } from './task';
import { Vehicle } from './vehicle';
import { Settings } from './settings'; 
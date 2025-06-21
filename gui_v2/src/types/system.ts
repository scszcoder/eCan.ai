import type { Chat } from '../pages/Chat/types/chat';
import type { Agent } from '../pages/Agents/types';
import type { Skill } from './skill';
import type { Tool } from './tool';
import type { Task } from './task';
import type { Settings } from './settings';
import { Knowledge } from '../pages/Knowledge/types';

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
  chats: Chat[];
  message: string;
}

export interface Vehicle {
  vid: number;
  name: string;
  model: string;
  status: string;
} 
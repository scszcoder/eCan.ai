import type { Agent, Skill, Tool, Task, Vehicle, Settings } from './index';
import type { ChatSession } from '../pages/Chat/types/chat';
import { Knowledge } from '@/pages/Knowledge/types';

// 系统完整数据结构
export interface SystemData {
  token: string;
  agents: Agent[];
  skills: Skill[];
  tools: Tool[];
  tasks: Task[];
  vehicles: Vehicle[];
  settings: Settings;
  knowledges: Knowledge[];
  chats: ChatSession[];
  message: string;
} 
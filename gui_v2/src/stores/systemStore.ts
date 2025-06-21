import { create } from 'zustand';
import type { 
  Agent, 
  Skill, 
  Tool, 
  Task, 
  Vehicle, 
  Settings, 
  Knowledge, 
  Chat, 
  SystemData 
} from '../types';

interface SystemState {
  // 数据状态
  token: string | null;
  agents: Agent[];
  skills: Skill[];
  tools: Tool[];
  tasks: Task[];
  vehicles: Vehicle[];
  settings: Settings | null;
  knowledges: Knowledge;
  chats: Chat;
  
  // 加载状态
  isLoading: boolean;
  error: string | null;
  
  // 操作方法
  setData: (data: SystemData) => void;
  setToken: (token: string) => void;
  setAgents: (agents: Agent[]) => void;
  setSkills: (skills: Skill[]) => void;
  setTools: (tools: Tool[]) => void;
  setTasks: (tasks: Task[]) => void;
  setVehicles: (vehicles: Vehicle[]) => void;
  setSettings: (settings: Settings) => void;
  setKnowledges: (knowledges: Knowledge) => void;
  setChats: (chats: Chat) => void;
  
  // 更新单个项目
  updateAgent: (id: string, updates: Partial<Agent>) => void;
  updateSkill: (id: string, updates: Partial<Skill>) => void;
  updateTool: (name: string, updates: Partial<Tool>) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  updateVehicle: (vid: number, updates: Partial<Vehicle>) => void;
  
  // 添加项目
  addAgent: (agent: Agent) => void;
  addSkill: (skill: Skill) => void;
  addTool: (tool: Tool) => void;
  addTask: (task: Task) => void;
  addVehicle: (vehicle: Vehicle) => void;
  
  // 删除项目
  removeAgent: (id: string) => void;
  removeSkill: (id: string) => void;
  removeTool: (name: string) => void;
  removeTask: (id: string) => void;
  removeVehicle: (vid: number) => void;
  
  // 加载状态管理
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  
  // 清空数据
  clearData: () => void;
}

const initialState = {
  token: null,
  agents: [],
  skills: [],
  tools: [],
  tasks: [],
  vehicles: [],
  settings: null,
  knowledges: {},
  chats: {},
  isLoading: false,
  error: null,
};

export const useSystemStore = create<SystemState>((set, get) => ({
  ...initialState,

  setData: (data: SystemData) => set({
    token: data.token,
    agents: data.agents || [],
    skills: data.skills || [],
    tools: data.tools || [],
    tasks: data.tasks || [],
    vehicles: data.vehicles || [],
    settings: data.settings || null,
    knowledges: data.knowledges || {},
    chats: data.chats || {},
    error: null,
  }),

  setToken: (token: string) => set({ token }),
  
  setAgents: (agents: Agent[]) => set({ agents }),
  setSkills: (skills: Skill[]) => set({ skills }),
  setTools: (tools: Tool[]) => set({ tools }),
  setTasks: (tasks: Task[]) => set({ tasks }),
  setVehicles: (vehicles: Vehicle[]) => set({ vehicles }),
  setSettings: (settings: Settings) => set({ settings }),
  setKnowledges: (knowledges: Knowledge) => set({ knowledges }),
  setChats: (chats: Chat) => set({ chats }),

  updateAgent: (id: string, updates: Partial<Agent>) => set((state) => ({
    agents: state.agents.map(agent => 
      agent.card.id === id ? { ...agent, ...updates } : agent
    ),
  })),

  updateSkill: (id: string, updates: Partial<Skill>) => set((state) => ({
    skills: state.skills.map(skill => 
      skill.id === id ? { ...skill, ...updates } : skill
    ),
  })),

  updateTool: (name: string, updates: Partial<Tool>) => set((state) => ({
    tools: state.tools.map(tool => 
      tool.name === name ? { ...tool, ...updates } : tool
    ),
  })),

  updateTask: (id: string, updates: Partial<Task>) => set((state) => ({
    tasks: state.tasks.map(task => 
      task.id === id ? { ...task, ...updates } : task
    ),
  })),

  updateVehicle: (vid: number, updates: Partial<Vehicle>) => set((state) => ({
    vehicles: state.vehicles.map(vehicle => 
      vehicle.vid === vid ? { ...vehicle, ...updates } : vehicle
    ),
  })),

  addAgent: (agent: Agent) => set((state) => ({
    agents: [...state.agents, agent],
  })),

  addSkill: (skill: Skill) => set((state) => ({
    skills: [...state.skills, skill],
  })),

  addTool: (tool: Tool) => set((state) => ({
    tools: [...state.tools, tool],
  })),

  addTask: (task: Task) => set((state) => ({
    tasks: [...state.tasks, task],
  })),

  addVehicle: (vehicle: Vehicle) => set((state) => ({
    vehicles: [...state.vehicles, vehicle],
  })),

  removeAgent: (id: string) => set((state) => ({
    agents: state.agents.filter(agent => agent.card.id !== id),
  })),

  removeSkill: (id: string) => set((state) => ({
    skills: state.skills.filter(skill => skill.id !== id),
  })),

  removeTool: (name: string) => set((state) => ({
    tools: state.tools.filter(tool => tool.name !== name),
  })),

  removeTask: (id: string) => set((state) => ({
    tasks: state.tasks.filter(task => task.id !== id),
  })),

  removeVehicle: (vid: number) => set((state) => ({
    vehicles: state.vehicles.filter(vehicle => vehicle.vid !== vid),
  })),

  setLoading: (loading: boolean) => set({ isLoading: loading }),
  setError: (error: string | null) => set({ error }),

  clearData: () => set(initialState),
})); 
export interface Agent {
    id: number;
    name: string;
    role: string;
    status: 'active' | 'busy' | 'offline';
    skills: string[];
    tasksCompleted: number;
    efficiency: number;
    lastActive: string;
    avatar?: string;
    currentTask?: string;
}

// 创建事件总线
const agentsEventBus = {
    listeners: new Set<(data: Agent[]) => void>(),
    subscribe(listener: (data: Agent[]) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    },
    emit(data: Agent[]) {
        this.listeners.forEach(listener => listener(data));
    }
};

// 导出更新数据的函数
export const updateAgentsGUI = (data: Agent[]) => {
    agentsEventBus.emit(data);
};

// 导出事件总线供组件使用
export { agentsEventBus }; 
export interface AgentCard {
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
    authentication: any | null;
    defaultInputModes: string[];
    defaultOutputModes: string[];
}

export interface Agent {
    card: AgentCard;
    supervisors: string[];
    subordinates: string[];
    peers: string[];
    rank: string;
    organizations: string[];
    job_description: string;
    personalities: string[];
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
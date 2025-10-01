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

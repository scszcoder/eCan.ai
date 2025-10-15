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
    supervisor_id: string;  // Single supervisor ID (unified naming)
    rank: string;
    org_id: string;  // Single organization ID (unified naming)
    job_description: string;
    personalities: string[];
    // Note: subordinates can be queried via supervisor_id reverse lookup, no need to store
    // Note: peers relationship not yet implemented, no need to store
}

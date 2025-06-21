export interface Knowledge {
  id: number;
  name: string;
  type: string;
  status: 'active' | 'maintenance' | 'offline';
  battery: number;
  location: string;
  lastMaintenance: string;
  totalDistance: number;
  currentTask?: string;
  nextMaintenance?: string;
}

export const knowledgeEventBus = {
  listeners: new Set<(data: Knowledge[]) => void>(),
  subscribe(listener: (data: Knowledge[]) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  },
  emit(data: Knowledge[]) {
    this.listeners.forEach(listener => listener(data));
  }
};

export const updateKnowledgeGUI = (data: Knowledge[]) => {
  knowledgeEventBus.emit(data);
}; 
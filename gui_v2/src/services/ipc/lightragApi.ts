// Frontend IPC service stubs for LightRAG operations
// NOTE: Methods expect backend to register matching IPC handlers.

import { IPCAPI, APIResponse } from './api';

export type IngestFilesPayload = {
  paths: string[];
  options?: Record<string, any>;
};

export type IngestDirectoryPayload = {
  dirPath: string;
  options?: Record<string, any>;
};

export type ScanDirectoryPayload = {
  dirPath: string;
};

export type QueryPayload = {
  text: string;
  options?: Record<string, any>;
};

export type JobPayload = { jobId: string };

export type DeleteDocumentPayload = { id: string };

export type InsertTextPayload = {
  text: string;
  metadata?: Record<string, any>;
};

export type UpdateEntityPayload = {
  entity_name: string;
  updated_data: Record<string, any>;
  allow_rename?: boolean;
  allow_merge?: boolean;
};

export type UpdateRelationPayload = {
  source_id: string;
  target_id: string;
  updated_data: Record<string, any>;
};

export type CheckEntityExistsPayload = {
  name: string;
};

export type DocumentsPaginatedPayload = {
  page: number;
  page_size: number;
  status_filter?: string | null;
  sort_field?: string;
  sort_direction?: 'asc' | 'desc';
};

export type ProcessingProgress = {
  status: 'idle' | 'processing' | 'completed';
  processing_count: number;
  pending_count: number;
  processed_count: number;
  failed_count: number;
  total_count: number;
  progress_percentage: number;
  track_id?: string;
  documents?: any[];
  pipeline?: {
    job_name?: string;
    current_batch?: number;
    total_batches?: number;
    latest_message?: string;
    total_chunks?: number;
    processed_chunks?: number;
    current_chunk_file?: string;  // File path of document currently being processed
  };
};

// 传入 apiInstance，返回 LightRAG 相关Method的对象
export function createLightRAGApi(apiInstance: IPCAPI) {
  return {
    async ingestFiles<T>(payload: IngestFilesPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.ingestFiles', payload);
    },

    async ingestDirectory<T>(payload: IngestDirectoryPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.ingestDirectory', payload);
    },

    async scanDirectory<T>(payload: ScanDirectoryPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.scanDirectory', payload);
    },

    async query<T>(payload: QueryPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.query', payload);
    },

    async queryStream<T>(payload: QueryPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.queryStream', payload);
    },

    async status<T>(payload: JobPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.status', payload);
    },

    async scan<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.scan', {});
    },

    async listDocuments<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.listDocuments', {});
    },

    async getDocumentsPaginated<T>(payload: DocumentsPaginatedPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.getDocumentsPaginated', payload);
    },

    async getProcessingProgress(track_id?: string): Promise<APIResponse<ProcessingProgress>> {
      return apiInstance.executeRequest<ProcessingProgress>('lightrag.getProcessingProgress', track_id ? { track_id } : {});
    },

    async deleteDocument<T>(payload: DeleteDocumentPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.deleteDocument', payload);
    },

    async abortDocument<T>(payload: { id: string }): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.abortDocument', payload);
    },

    async insertText<T>(payload: InsertTextPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.insertText', payload);
    },

    async clearCache<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.clearCache', {});
    },

    async getStatusCounts<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.getStatusCounts', {});
    },

    async health<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.health', {});
    },

    async updateEntity<T>(payload: UpdateEntityPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.updateEntity', payload);
    },

    async updateRelation<T>(payload: UpdateRelationPayload): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.updateRelation', payload);
    },

    async checkEntityNameExists(payload: CheckEntityExistsPayload): Promise<APIResponse<{ exists: boolean }>> {
      return apiInstance.executeRequest<{ exists: boolean }>('lightrag.checkEntityNameExists', payload);
    },

    async getGraphLabelList<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.getGraphLabelList', {});
    },

    async getPopularLabels<T>(payload: { limit: number }): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.getPopularLabels', payload);
    },

    async searchLabels<T>(payload: { query: string; limit: number }): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.searchLabels', payload);
    },

    async saveSettings<T>(settings: Record<string, any>): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.saveSettings', settings);
    },

    async getSettings<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.getSettings', {});
    },

    async queryGraphs<T>(payload: { label: string; maxDepth: number; maxNodes: number }): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.queryGraphs', payload);
    },

    async getInputHistory<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.getInputHistory', {});
    },

    async saveInputHistory<T>(history: string[]): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.saveInputHistory', { history });
    },

    async getConversationHistory<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.getConversationHistory', {});
    },

    async saveConversationHistory<T>(messages: any[]): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.saveConversationHistory', { messages });
    },

    async expandNode<T>(payload: { nodeId: string; maxDepth: number; maxNodes: number }): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.expandNode', payload);
    },

    async pruneNode<T>(payload: { nodeId: string }): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.pruneNode', payload);
    },

    async downloadFile<T>(payload: { fileName: string }): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.downloadFile', payload);
    },

    async getWorkspaces<T>(): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.getWorkspaces', {});
    },

    async deleteWorkspace<T>(payload: { workspace_name: string }): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.deleteWorkspace', payload);
    },

    async restartServer<T>(payload: Record<string, any>): Promise<APIResponse<T>> {
      return apiInstance.executeRequest<T>('lightrag.restartServer', payload);
    }
  };
}


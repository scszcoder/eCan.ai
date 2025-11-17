// Frontend IPC service stubs for LightRAG operations
// NOTE: Methods expect backend to register matching IPC handlers.

import { get_ipc_api } from '@/services/ipc_api';

export type IngestFilesPayload = {
  paths: string[];
  options?: Record<string, any>;
};

export type IngestDirectoryPayload = {
  dirPath: string;
  options?: Record<string, any>;
};

export type QueryPayload = {
  text: string;
  options?: Record<string, any>;
};

export type JobPayload = { jobId: string };

export type DeleteDocumentPayload = { filePath: string };

export type InsertTextPayload = {
  text: string;
  metadata?: Record<string, any>;
};

export const lightragIpc = {
  async ingestFiles(payload: IngestFilesPayload): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.ingestFiles', payload);
  },

  async ingestDirectory(payload: IngestDirectoryPayload): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.ingestDirectory', payload);
  },

  async query(payload: QueryPayload): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.query', payload);
  },

  async queryStream(payload: QueryPayload): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.queryStream', payload);
  },

  async status(payload: JobPayload): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.status', payload);
  },

  async scan(): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.scan', {});
  },

  async listDocuments(): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.listDocuments', {});
  },

  async deleteDocument(payload: DeleteDocumentPayload): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.deleteDocument', payload);
  },

  async insertText(payload: InsertTextPayload): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.insertText', payload);
  },

  async clearCache(): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.clearCache', {});
  },

  async getStatusCounts(): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.getStatusCounts', {});
  },

  async health(): Promise<any> {
    const api: any = get_ipc_api();
    return await api.call('lightrag.health', {});
  },
};

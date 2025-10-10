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

export const lightragIpc = {
  async ingestFiles(payload: IngestFilesPayload): Promise<any> {
    const api: any = get_ipc_api();
    if (api?.lightrag?.ingestFiles) return api.lightrag.ingestFiles(payload);
    throw new Error('IPC handler not wired: lightrag.ingestFiles');
  },

  async ingestDirectory(payload: IngestDirectoryPayload): Promise<any> {
    const api: any = get_ipc_api();
    if (api?.lightrag?.ingestDirectory) return api.lightrag.ingestDirectory(payload);
    throw new Error('IPC handler not wired: lightrag.ingestDirectory');
  },

  async query(payload: QueryPayload): Promise<any> {
    const api: any = get_ipc_api();
    if (api?.lightrag?.query) return api.lightrag.query(payload);
    throw new Error('IPC handler not wired: lightrag.query');
  },

  async status(payload: JobPayload): Promise<any> {
    const api: any = get_ipc_api();
    if (api?.lightrag?.status) return api.lightrag.status(payload);
    throw new Error('IPC handler not wired: lightrag.status');
  },

  async abort(payload: JobPayload): Promise<any> {
    const api: any = get_ipc_api();
    if (api?.lightrag?.abort) return api.lightrag.abort(payload);
    throw new Error('IPC handler not wired: lightrag.abort');
  },
};

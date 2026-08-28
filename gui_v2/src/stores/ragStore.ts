import { create } from 'zustand';
import { apiRouter } from '../services/api/api-router';
import type { APIResponse } from '../services/ipc/api';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from '../services/api/api-config';
import { getRagIndexStatus, listRagRelayDocuments, queryRagIndex, startRagIndex, uploadWithRagRelay } from '../services/web/presignedFileOps';
import { isWebPlatform } from '../config/platform';

// ── Types ──────────────────────────────────────────────────────────────

export interface RAGDocument {
  docKey: string;
  fileName: string;
  fileType: string;
  fileSize: number;
  uploadedAt: string;
  status: string;
  pid?: string;
}

export interface RAGChunk {
  text: string;
  score: number;
  source: string;
  metadata?: Record<string, unknown>;
}

export interface RAGQueryResult {
  answer?: string;
  chunks: RAGChunk[];
  query: string;
  mode?: string;
}

export interface RAGChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  chunks?: RAGChunk[];
  timestamp: number;
}

export interface RAGIndexStatus {
  status: string;
  message?: string;
  progress?: number;
  taskArn?: string;
  lastIndexedAt?: string;
  docCount?: number;
  chunkCount?: number;
}

// ── Store ──────────────────────────────────────────────────────────────

interface RAGStoreState {
  documents: RAGDocument[];
  indexStatus: RAGIndexStatus | null;
  queryResult: RAGQueryResult | null;
  chatHistory: RAGChatMessage[];
  loading: boolean;
  uploading: boolean;
  uploadProgress: number;       // 0‑100
  indexing: boolean;
  querying: boolean;
  error: string | null;

  fetchDocs: (pid?: string) => Promise<void>;
  fetchIndexStatus: (pid?: string) => Promise<void>;
  uploadFiles: (files: File[], pid?: string) => Promise<boolean>;
  triggerIndex: (pid?: string) => Promise<boolean>;
  deleteDocs: (docKeys: string[], pid?: string) => Promise<void>;
  query: (queryText: string, pid?: string, mode?: string, topK?: number) => Promise<void>;
  clearQuery: () => void;
  clearChat: () => void;
}

export const useRAGStore = create<RAGStoreState>((set, get) => ({
  documents: [],
  indexStatus: null,
  queryResult: null,
  chatHistory: [],
  loading: false,
  uploading: false,
  uploadProgress: 0,
  indexing: false,
  querying: false,
  error: null,

  // ── List documents ───────────────────────────────────────────────────
  fetchDocs: async (pid?: string) => {
    if (isWebPlatform()) {
      set({ loading: true, error: null });
      try {
        const documents = await listRagRelayDocuments(pid || 'default');
        set({
          documents: documents.map((document) => ({
            docKey: document.key,
            fileName: document.fileName,
            fileType: 'application/octet-stream',
            fileSize: document.fileSize,
            uploadedAt: document.uploadedAt || '',
            status: document.status,
            pid: document.pid,
          })),
          loading: false,
        });
      } catch (error: any) {
        set({ loading: false, error: error?.message || 'Failed to fetch RAG documents' });
      }
      return;
    }
    set({ loading: true, error: null });
    try {
      const res: APIResponse<Array<{
        fid: string;
        pid: string;
        file: string;
        type: string;
        options: unknown;
        objectKey: string;
        createdAt: string;
      }>> = await apiRouter.execute(
        {
          method: 'rag_list_docs',
          graphql: {
            query: GRAPHQL_QUERIES.RAG_LIST_DOCS,
            resultPath: 'getRagDocuments',
          },
        },
        { pid: pid || 'default' },
      );
      if (res.success && Array.isArray(res.data)) {
        set({
          documents: res.data.map((document) => ({
            docKey: document.objectKey,
            fileName: document.file,
            fileType: document.type,
            fileSize: Number((document.options as { size?: number } | null)?.size || 0),
            uploadedAt: document.createdAt,
            status: 'uploaded',
            pid: document.pid,
          })),
          loading: false,
        });
      } else {
        throw new Error((res as any).error?.message || 'Failed to fetch RAG docs');
      }
    } catch (e: any) {
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },

  // ── Index status ─────────────────────────────────────────────────────
  fetchIndexStatus: async (pid?: string) => {
    if (isWebPlatform()) {
      try {
        set({ indexStatus: await getRagIndexStatus(pid || 'default') });
      } catch {
        // silent for status polling
      }
      return;
    }
    try {
      const res: APIResponse<RAGIndexStatus> = await apiRouter.execute(
        {
          method: 'rag_get_index_status',
          graphql: {
            query: GRAPHQL_QUERIES.RAG_GET_INDEX_STATUS,
            resultPath: 'ragGetIndexStatus',
          },
        },
        { pid: pid || 'default' },
      );
      if (res.success && res.data) {
        set({ indexStatus: res.data });
      }
    } catch {
      // silent for status polling
    }
  },

  // ── Upload files ─────────────────────────────────────────────────────
  uploadFiles: async (files: File[], pid?: string) => {
    set({ uploading: true, uploadProgress: 0, error: null });
    const effectivePid = pid || 'default';
    let stage = 'preparing upload';

    try {
      const uploadedDocuments: RAGDocument[] = [];
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const fileType = file.type || 'application/octet-stream';
        const fid = `rag-${Date.now()}-${i}-${Math.random().toString(36).slice(2, 8)}`;
        stage = `uploading ${file.name}`;
        await uploadWithRagRelay(file, fileType, effectivePid);

        stage = `registering ${file.name}`;
        const registerRes = await apiRouter.execute(
          {
            method: 'rag_register_documents',
            graphql: {
              mutation: GRAPHQL_MUTATIONS.RAG_REGISTER_DOCUMENTS,
              resultPath: 'reqRAGStore',
            },
          },
          {
            input: [{
              fid,
              pid: effectivePid,
              file: file.name,
              type: fileType,
              format: file.name.split('.').pop()?.toLowerCase() || 'bin',
              options: { size: file.size },
              version: '1',
            }],
          },
        );
        if (!registerRes.success) {
          throw new Error((registerRes as any).error?.message || `Failed to register ${file.name}`);
        }

        uploadedDocuments.push({
          docKey: `${effectivePid}/docs/${file.name}`,
          fileName: file.name,
          fileType,
          fileSize: file.size,
          uploadedAt: new Date().toISOString(),
          status: 'uploaded',
          pid: effectivePid,
        });
        set({ uploadProgress: Math.round(((i + 1) / files.length) * 100) });
      }

      set((state) => ({
        documents: [...uploadedDocuments, ...state.documents.filter((doc) => doc.pid !== effectivePid)],
        uploading: false,
        uploadProgress: 100,
      }));
      return true;
    } catch (e: any) {
      const message = e?.message || 'Unknown upload error';
      set({ uploading: false, error: `RAG upload failed while ${stage}: ${message}` });
      return false;
    }
  },

  // ── Trigger indexing ─────────────────────────────────────────────────
  triggerIndex: async (pid?: string) => {
    if (isWebPlatform()) {
      set({
        indexing: true,
        error: null,
        indexStatus: { status: 'indexing', message: 'Starting indexer', progress: 0 },
      });
      try {
        const indexStatus = await startRagIndex(pid || 'default');
        set({ indexStatus, indexing: false });
        return true;
      } catch (error: any) {
        set({ indexing: false, error: error?.message || 'Failed to trigger indexing' });
        return false;
      }
    }
    set({ indexing: true, error: null });
    try {
      const res: APIResponse<RAGIndexStatus> = await apiRouter.execute(
        {
          method: 'rag_trigger_index',
          graphql: {
            query: GRAPHQL_MUTATIONS.RAG_TRIGGER_INDEX,
            resultPath: 'ragTriggerIndex',
          },
        },
        { pid: pid || 'default' },
      );
      if (res.success && res.data) {
        set({ indexStatus: res.data, indexing: false });
        return true;
      } else {
        throw new Error((res as any).error?.message || 'Failed to trigger indexing');
      }
    } catch (e: any) {
      set({ indexing: false, error: e?.message || 'Unknown error' });
      return false;
    }
  },

  // ── Delete documents ─────────────────────────────────────────────────
  deleteDocs: async (docKeys: string[], pid?: string) => {
    set({ loading: true, error: null });
    const effectivePid = pid || 'default';
    try {
      await apiRouter.execute(
        {
          method: 'rag_delete_docs',
          graphql: {
            query: GRAPHQL_MUTATIONS.RAG_DELETE_DOCS,
            resultPath: 'ragDeleteDocs',
          },
        },
        { input: { docKeys, pid: effectivePid } },
      );
      // Remove from local state
      const deleted = new Set(docKeys);
      set(s => ({
        documents: s.documents.filter(d => !deleted.has(d.docKey)),
        loading: false,
      }));
    } catch (e: any) {
      set({ loading: false, error: e?.message || 'Delete failed' });
    }
  },

  // ── Query ────────────────────────────────────────────────────────────
  query: async (queryText: string, pid?: string, mode?: string, topK?: number) => {
    const userMsg: RAGChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: queryText,
      timestamp: Date.now(),
    };
    set(s => ({ querying: true, error: null, chatHistory: [...s.chatHistory, userMsg] }));
    try {
      if (isWebPlatform()) {
        const result = await queryRagIndex(queryText, pid || 'default', topK || 5);
        const asstMsg: RAGChatMessage = {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: result.answer || 'No grounded answer was returned.',
          chunks: result.chunks,
          timestamp: Date.now(),
        };
        set(s => ({ queryResult: result, querying: false, chatHistory: [...s.chatHistory, asstMsg] }));
        return;
      }
      const res: APIResponse<RAGQueryResult> = await apiRouter.execute(
        {
          method: 'rag_query',
          graphql: {
            query: GRAPHQL_QUERIES.RAG_QUERY,
            resultPath: 'ragQuery',
          },
        },
        { input: { query: queryText, pid: pid || 'default', mode: mode || 'hybrid', topK: topK || 5 } },
      );
      if (res.success && res.data) {
        const asstMsg: RAGChatMessage = {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: res.data.answer || '_(No synthesized answer — showing matching chunks only)_',
          chunks: res.data.chunks,
          timestamp: Date.now(),
        };
        set(s => ({ queryResult: res.data!, querying: false, chatHistory: [...s.chatHistory, asstMsg] }));
      } else {
        throw new Error((res as any).error?.message || 'Query failed');
      }
    } catch (e: any) {
      const errMsg: RAGChatMessage = {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${e?.message || 'Query failed'}`,
        timestamp: Date.now(),
      };
      set(s => ({ querying: false, error: e?.message || 'Query failed', chatHistory: [...s.chatHistory, errMsg] }));
    }
  },

  clearQuery: () => set({ queryResult: null }),
  clearChat: () => set({ chatHistory: [], queryResult: null }),
}));

// ── LightRAG Provider Settings Sync ───────────────────────────────────
// Subscribes to backend push events and bumps a version counter so
// SettingsTab useEffects know to reload settings + providers without
// requiring a manual page refresh.

export interface LightRAGSettingsStore {
  /** Bumped whenever a provider (LLM/Embedding/Rerank) is saved in Settings. */
  providerVersion: number;
  /** Call this when the backend broadcasts 'lightrag.providersUpdated'. */
  bumpProviderVersion: () => void;
}

export const useLightRAGSettingsStore = create<LightRAGSettingsStore>((set) => ({
  providerVersion: 0,
  bumpProviderVersion: () =>
    set((s) => ({ providerVersion: s.providerVersion + 1 })),
}));

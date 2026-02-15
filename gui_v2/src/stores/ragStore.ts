import { create } from 'zustand';
import { apiRouter } from '../services/api/api-router';
import type { APIResponse } from '../services/ipc/api';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from '../services/api/api-config';

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

interface RAGUploadRequest {
  fileName: string;
  fileType: string;
  fileSize: number;
  pid?: string;
}

interface RAGUploadURL {
  uploadUrl: string;
  docKey: string;
  expiresIn: number;
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
  triggerIndex: (pid?: string) => Promise<void>;
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
    set({ loading: true, error: null });
    try {
      const res: APIResponse<RAGDocument[]> = await apiRouter.execute(
        {
          method: 'rag_list_docs',
          graphql: {
            query: GRAPHQL_QUERIES.RAG_LIST_DOCS,
            resultPath: 'ragListDocs',
          },
        },
        { pid: pid || 'default' },
      );
      if (res.success && Array.isArray(res.data)) {
        set({ documents: res.data, loading: false });
      } else {
        throw new Error((res as any).error?.message || 'Failed to fetch RAG docs');
      }
    } catch (e: any) {
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },

  // ── Index status ─────────────────────────────────────────────────────
  fetchIndexStatus: async (pid?: string) => {
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

    try {
      // 1. Request presigned upload URLs
      const uploadRequests: RAGUploadRequest[] = files.map(f => ({
        fileName: f.name,
        fileType: f.type || 'application/octet-stream',
        fileSize: f.size,
        pid: effectivePid,
      }));

      const urlRes: APIResponse<RAGUploadURL[]> = await apiRouter.execute(
        {
          method: 'rag_request_upload_urls',
          graphql: {
            query: GRAPHQL_MUTATIONS.RAG_REQUEST_UPLOAD_URLS,
            resultPath: 'ragRequestUploadURLs',
          },
        },
        { input: uploadRequests },
      );

      if (!urlRes.success || !Array.isArray(urlRes.data)) {
        throw new Error('Failed to get upload URLs');
      }

      const urls = urlRes.data;

      // 2. Upload each file via presigned PUT
      const docKeys: string[] = [];
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const urlInfo = urls[i];
        if (!urlInfo?.uploadUrl) {
          console.error(`No upload URL for ${file.name}`);
          continue;
        }
        await fetch(urlInfo.uploadUrl, {
          method: 'PUT',
          headers: { 'Content-Type': file.type || 'application/octet-stream' },
          body: file,
        });
        docKeys.push(urlInfo.docKey);
        set({ uploadProgress: Math.round(((i + 1) / files.length) * 100) });
      }

      // 3. Confirm uploads
      if (docKeys.length > 0) {
        await apiRouter.execute(
          {
            method: 'rag_confirm_uploads',
            graphql: {
              query: GRAPHQL_MUTATIONS.RAG_CONFIRM_UPLOADS,
              resultPath: 'ragConfirmUploads',
            },
          },
          { docKeys, pid: effectivePid },
        );
      }

      set({ uploading: false, uploadProgress: 100 });
      // Refresh doc list
      await get().fetchDocs(effectivePid);
      return true;
    } catch (e: any) {
      set({ uploading: false, error: e?.message || 'Upload failed' });
      return false;
    }
  },

  // ── Trigger indexing ─────────────────────────────────────────────────
  triggerIndex: async (pid?: string) => {
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
      } else {
        throw new Error((res as any).error?.message || 'Failed to trigger indexing');
      }
    } catch (e: any) {
      set({ indexing: false, error: e?.message || 'Unknown error' });
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

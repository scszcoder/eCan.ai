import { appSyncRequest } from './appSyncClient';
import { getCachedAppConfig } from '../../contexts/AppConfigContext';

export interface FileOp {
  op: string;
  names: string | string[];
  options?: string;
}

export interface PresignedRequest {
  url: string;
  method?: 'PUT' | 'POST' | 'GET';
  fields?: Record<string, string>;
  headers?: Record<string, string>;
  raw?: any;
}

const REQ_FILE_OP_QUERY = `
  query ReqFileOp($fo: [FileOp!]!) {
    reqFileOp(fo: $fo)
  }
`;

const parseAwsJson = (value: any): any => {
  if (typeof value !== 'string') return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
};

const unwrapResult = (value: any): any => {
  if (!value) return value;
  const parsed = parseAwsJson(value);
  if (parsed !== value) return unwrapResult(parsed);
  if (Array.isArray(value)) return unwrapResult(value[0]);
  if (value?.result) return unwrapResult(value.result);
  if (value?.urls) return unwrapResult(value.urls);
  if (value?.body) return unwrapResult(value.body);
  return value;
};

const extractPresignedRequest = (value: any): PresignedRequest => {
  const entry = unwrapResult(value);
  if (!entry || typeof entry !== 'object') {
    throw new Error('Invalid presigned URL payload');
  }

  const url =
    entry.upload_url ||
    entry.download_url ||
    entry.presigned_url ||
    entry.url ||
    entry.s3_url ||
    entry.s3PresignedUrl;

  if (!url || typeof url !== 'string') {
    throw new Error('Presigned URL missing in response');
  }

  const fields = entry.fields && typeof entry.fields === 'object' ? entry.fields : undefined;
  const headers = entry.headers || entry.requestHeaders;

  return {
    url,
    method: fields ? 'POST' : entry.method || 'PUT',
    fields,
    headers,
    raw: entry,
  };
};

export const requestFileOps = async (ops: FileOp[]): Promise<any> => {
  const data = await appSyncRequest<{ reqFileOp: any }>(REQ_FILE_OP_QUERY, { fo: ops });
  return parseAwsJson(data.reqFileOp);
};

export const getPresignedUpload = async (ops: FileOp[]): Promise<PresignedRequest> => {
  const payload = await requestFileOps(ops);
  return extractPresignedRequest(payload);
};

export const getPresignedDownload = async (ops: FileOp[]): Promise<PresignedRequest> => {
  const payload = await requestFileOps(ops);
  return extractPresignedRequest(payload);
};

export const uploadWithPresignedUrl = async (
  file: Blob,
  presigned: PresignedRequest,
  contentType?: string
): Promise<Response> => {
  if (presigned.fields) {
    const formData = new FormData();
    Object.entries(presigned.fields).forEach(([key, value]) => {
      formData.append(key, value);
    });
    formData.append('file', file);

    const response = await fetch(presigned.url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Presigned POST upload failed: ${response.status}`);
    }

    return response;
  }

  const headers: Record<string, string> = {
    ...(presigned.headers || {}),
  };

  if (contentType && !headers['Content-Type']) {
    headers['Content-Type'] = contentType;
  }

  const response = await fetch(presigned.url, {
    method: presigned.method || 'PUT',
    headers,
    body: file,
  });

  if (!response.ok) {
    throw new Error(`Presigned upload failed: ${response.status}`);
  }

  return response;
};

export const uploadWithRagRelay = async (
  file: File,
  contentType?: string,
  pid = 'default',
): Promise<void> => {
  const envId = getCachedAppConfig()?.auth.cloudbase_env_id;
  if (!envId) throw new Error('CloudBase RAG signer is not configured');
  const cloudbase = (await import('@cloudbase/js-sdk')).default;
  const app = cloudbase.init({ env: envId, region: 'ap-shanghai' });
  const result = await app.callFunction({
    name: 'rag_upload_signer_event',
    data: { pid, fileName: file.name },
  });
  const payload = (result as any)?.result || result;
  if (!payload?.success || !payload?.uploadUrl) {
    throw new Error(payload?.error || 'Unable to obtain RAG upload URL');
  }

  const formData = new FormData();
  formData.append('uploadUrl', payload.uploadUrl);
  formData.append('contentType', contentType || file.type || 'application/octet-stream');
  formData.append('file', file, file.name);

  const response = await fetch('/api/rag-upload.php', { method: 'POST', body: formData });
  const relayPayload = await response.json().catch(() => ({}));
  if (!response.ok || !relayPayload.success) {
    throw new Error(relayPayload.error || `RAG upload relay failed (HTTP ${response.status})`);
  }
};

export interface RagRelayDocument {
  key: string;
  fileName: string;
  fileSize: number;
  uploadedAt: string | null;
  status: string;
  pid: string;
}

export const listRagRelayDocuments = async (pid = 'default'): Promise<RagRelayDocument[]> => {
  const envId = getCachedAppConfig()?.auth.cloudbase_env_id;
  if (!envId) throw new Error('CloudBase RAG signer is not configured');
  const cloudbase = (await import('@cloudbase/js-sdk')).default;
  const app = cloudbase.init({ env: envId, region: 'ap-shanghai' });
  const result = await app.callFunction({ name: 'rag_upload_signer_event', data: { action: 'listDocuments', pid } });
  const payload = (result as any)?.result || result;
  if (!payload?.success || !Array.isArray(payload.documents)) {
    throw new Error(payload?.error || 'Unable to list RAG documents');
  }
  return payload.documents;
};

export interface RagIndexResponse {
  status: string;
  message?: string;
  progress?: number;
  lastIndexedAt?: string;
  docCount?: number;
  chunkCount?: number;
}

const ragIndexRequest = async (action: 'startIndex' | 'getIndexStatus', pid = 'default'): Promise<RagIndexResponse> => {
  const envId = getCachedAppConfig()?.auth.cloudbase_env_id;
  if (!envId) throw new Error('CloudBase RAG indexer is not configured');
  const cloudbase = (await import('@cloudbase/js-sdk')).default;
  const app = cloudbase.init({ env: envId, region: 'ap-shanghai' });
  const result = await app.callFunction({ name: 'rag_index_event', data: { action, pid } });
  const payload = (result as any)?.result || result;
  if (!payload?.success) throw new Error(payload?.message || payload?.error || 'RAG indexing request failed');
  return payload;
};

export const startRagIndex = (pid = 'default') => ragIndexRequest('startIndex', pid);

export const getRagIndexStatus = (pid = 'default') => ragIndexRequest('getIndexStatus', pid);

export interface RagQueryResponse {
  answer?: string;
  chunks: Array<{ text: string; score: number; source: string; metadata?: Record<string, unknown> }>;
  query: string;
  mode?: string;
}

export const queryRagIndex = async (query: string, pid = 'default', topK = 5): Promise<RagQueryResponse> => {
  const envId = getCachedAppConfig()?.auth.cloudbase_env_id;
  if (!envId) throw new Error('CloudBase RAG indexer is not configured');
  const cloudbase = (await import('@cloudbase/js-sdk')).default;
  const app = cloudbase.init({ env: envId, region: 'ap-shanghai' });
  const result = await app.callFunction({ name: 'rag_index_event', data: { action: 'queryIndex', query, pid, topK } });
  const payload = (result as any)?.result || result;
  if (!payload?.success || !Array.isArray(payload.chunks)) throw new Error(payload?.message || payload?.error || 'RAG query failed');
  return payload;
};

export const downloadWithPresignedUrl = async (
  presigned: PresignedRequest
): Promise<Blob> => {
  const headers: Record<string, string> = {
    ...(presigned.headers || {}),
  };

  const response = await fetch(presigned.url, {
    method: presigned.method || 'GET',
    headers,
  });

  if (!response.ok) {
    throw new Error(`Presigned download failed: ${response.status}`);
  }

  return response.blob();
};

export const createFileOp = (op: string, names: string | string[], options?: string): FileOp => ({
  op,
  names,
  options,
});

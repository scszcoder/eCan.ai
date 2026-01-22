import { appSyncRequest } from './appSyncClient';

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

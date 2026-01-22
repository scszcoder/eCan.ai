import { randomUUID } from "node:crypto";
import { S3Client, PutObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const S3_BUCKET = process.env.S3_BUCKET;
const APPSYNC_API_URL = process.env.APPSYNC_API_URL;
const APPSYNC_API_KEY = process.env.APPSYNC_API_KEY;
const DEFAULT_OWNER = process.env.NOTIFY_OWNER;
const DEFAULT_EXPIRES = Number.parseInt(process.env.PRESIGNED_EXPIRES || "900", 10);

const MUTATION = `
mutation PublishAccountNotification($input: AccountNotificationInput!) {
  publishAccountNotification(input: $input) {
    id
    owner
    type
    title
    message
    payload
    created_at
  }
}
`;

const requireEnv = (value, name) => {
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
};

const appSyncRequest = async (url, apiKey, payload) => {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(`AppSync request failed: ${response.status} ${response.statusText}`);
  }
  return data;
};

export const handler = async (event = {}) => {
  const bucket = requireEnv(S3_BUCKET, "S3_BUCKET");
  const appsyncUrl = requireEnv(APPSYNC_API_URL, "APPSYNC_API_URL");
  const appsyncKey = requireEnv(APPSYNC_API_KEY, "APPSYNC_API_KEY");

  const owner = event.owner || DEFAULT_OWNER;
  if (!owner) {
    throw new Error("Missing owner in event or NOTIFY_OWNER env var");
  }

  const key = event.key || `presigned-tests/${randomUUID()}.txt`;
  const contentType = event.contentType || event.content_type || "text/plain";
  const expiresIn = Number.parseInt(event.expiresIn || event.expires_in || DEFAULT_EXPIRES, 10);

  const s3 = new S3Client({});
  const uploadUrl = await getSignedUrl(
    s3,
    new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      ContentType: contentType,
    }),
    { expiresIn }
  );

  const downloadUrl = await getSignedUrl(
    s3,
    new GetObjectCommand({
      Bucket: bucket,
      Key: key,
    }),
    { expiresIn }
  );

  const payload = {
    type: "presigned_test",
    bucket,
    key,
    contentType,
    upload: {
      url: uploadUrl,
      method: "PUT",
      headers: {
        "Content-Type": contentType,
      },
    },
    download: {
      url: downloadUrl,
      method: "GET",
    },
  };

  const variables = {
    input: {
      owner,
      type: "PRESIGNED_TEST",
      title: event.title || "Presigned URL Test",
      message: event.message || "Presigned upload/download links",
      payload: JSON.stringify(payload),
    },
  };

  const appsyncResponse = await appSyncRequest(appsyncUrl, appsyncKey, {
    query: MUTATION,
    variables,
    operationName: "PublishAccountNotification",
  });

  return {
    statusCode: 200,
    payload,
    appsyncResponse,
  };
};

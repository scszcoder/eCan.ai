/**
 * Tool handler: s3_put_object
 * Upload content to an S3 key.
 */
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { readFile } from "node:fs/promises";

const s3 = new S3Client({});

export async function s3_put_object(toolInput) {
  const { bucket, key, user_name, content, local_path, content_type } = toolInput;
  if (!bucket || !key || !user_name) {
    throw new Error("bucket, key, and user_name are required");
  }
  if (!content && !local_path) {
    throw new Error("either content (string) or local_path (file to upload) is required");
  }

  const fullKey = key.startsWith(user_name) ? key : `${user_name}/${key}`;

  let body;
  if (local_path) {
    body = await readFile(local_path);
  } else {
    body = content;
  }

  await s3.send(new PutObjectCommand({
    Bucket: bucket,
    Key: fullKey,
    Body: body,
    ContentType: content_type || "application/octet-stream",
  }));

  return { uploaded: fullKey, size: typeof body === "string" ? body.length : body.byteLength };
}

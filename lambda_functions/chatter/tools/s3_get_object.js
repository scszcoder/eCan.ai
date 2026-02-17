/**
 * Tool handler: s3_get_object
 * Download an S3 object to /tmp and return its content or local_path.
 */
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";

const s3 = new S3Client({});

export async function s3_get_object(toolInput) {
  const { bucket, key, user_name, local_path } = toolInput;
  if (!bucket || !key || !user_name) {
    throw new Error("bucket, key, and user_name are required");
  }

  const fullKey = key.startsWith(user_name) ? key : `${user_name}/${key}`;

  const resp = await s3.send(new GetObjectCommand({
    Bucket: bucket,
    Key: fullKey,
  }));

  const bodyBytes = await resp.Body.transformToByteArray();
  const fileName = fullKey.split("/").pop();
  const destPath = local_path || join("/tmp", fileName);

  await writeFile(destPath, bodyBytes);

  // Try to return text content for small text files
  const contentType = resp.ContentType || "";
  const size = bodyBytes.length;
  let textContent = null;
  if (size < 1_000_000 && (contentType.startsWith("text/") || contentType.includes("json") || contentType.includes("xml"))) {
    textContent = new TextDecoder().decode(bodyBytes);
  }

  return {
    local_path: destPath,
    size,
    content_type: contentType,
    text_content: textContent,
  };
}

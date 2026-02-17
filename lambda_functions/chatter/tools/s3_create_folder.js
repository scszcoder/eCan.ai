/**
 * Tool handler: s3_create_folder
 * Create a zero-byte folder marker in S3.
 */
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";

const s3 = new S3Client({});

export async function s3_create_folder(toolInput) {
  const { bucket, key, user_name } = toolInput;
  if (!bucket || !key || !user_name) {
    throw new Error("bucket, key, and user_name are required");
  }

  const folderKey = key.endsWith("/") ? key : `${key}/`;
  const fullKey = folderKey.startsWith(user_name) ? folderKey : `${user_name}/${folderKey}`;

  await s3.send(new PutObjectCommand({
    Bucket: bucket,
    Key: fullKey,
    Body: "",
  }));

  return { created: fullKey };
}

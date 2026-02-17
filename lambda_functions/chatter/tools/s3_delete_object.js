/**
 * Tool handler: s3_delete_object
 * Delete a single object from S3.
 */
import { S3Client, DeleteObjectCommand } from "@aws-sdk/client-s3";

const s3 = new S3Client({});

export async function s3_delete_object(toolInput) {
  const { bucket, key, user_name } = toolInput;
  if (!bucket || !key || !user_name) {
    throw new Error("bucket, key, and user_name are required");
  }

  const fullKey = key.startsWith(user_name) ? key : `${user_name}/${key}`;

  await s3.send(new DeleteObjectCommand({
    Bucket: bucket,
    Key: fullKey,
  }));

  return { deleted: fullKey };
}

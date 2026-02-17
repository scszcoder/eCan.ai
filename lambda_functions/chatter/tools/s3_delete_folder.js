/**
 * Tool handler: s3_delete_folder
 * Delete a folder (all objects under a prefix) in S3.
 */
import { S3Client, ListObjectsV2Command, DeleteObjectsCommand } from "@aws-sdk/client-s3";

const s3 = new S3Client({});

export async function s3_delete_folder(toolInput) {
  const { bucket, key, user_name } = toolInput;
  if (!bucket || !key || !user_name) {
    throw new Error("bucket, key, and user_name are required");
  }

  const prefix = key.endsWith("/") ? key : `${key}/`;
  const fullPrefix = prefix.startsWith(user_name) ? prefix : `${user_name}/${prefix}`;

  // List all objects under prefix
  let continuationToken;
  let deletedCount = 0;

  do {
    const listResp = await s3.send(new ListObjectsV2Command({
      Bucket: bucket,
      Prefix: fullPrefix,
      ContinuationToken: continuationToken,
    }));

    const objects = listResp.Contents || [];
    if (objects.length > 0) {
      await s3.send(new DeleteObjectsCommand({
        Bucket: bucket,
        Delete: { Objects: objects.map((o) => ({ Key: o.Key })) },
      }));
      deletedCount += objects.length;
    }

    continuationToken = listResp.NextContinuationToken;
  } while (continuationToken);

  return { deleted_prefix: fullPrefix, deleted_count: deletedCount };
}

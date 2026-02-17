/**
 * Tool handler: s3_move_object
 * Move (copy + delete) an S3 object from one key to another.
 */
import { S3Client, CopyObjectCommand, DeleteObjectCommand } from "@aws-sdk/client-s3";

const s3 = new S3Client({});

export async function s3_move_object(toolInput) {
  const { bucket, key, destination_key, user_name } = toolInput;
  if (!bucket || !key || !destination_key || !user_name) {
    throw new Error("bucket, key, destination_key, and user_name are required");
  }

  const srcKey = key.startsWith(user_name) ? key : `${user_name}/${key}`;
  const dstKey = destination_key.startsWith(user_name) ? destination_key : `${user_name}/${destination_key}`;

  // Copy to destination
  await s3.send(new CopyObjectCommand({
    Bucket: bucket,
    CopySource: `${bucket}/${srcKey}`,
    Key: dstKey,
  }));

  // Delete source
  await s3.send(new DeleteObjectCommand({
    Bucket: bucket,
    Key: srcKey,
  }));

  return { moved_from: srcKey, moved_to: dstKey };
}

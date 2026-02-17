/**
 * Tool handler: s3_copy_object
 * Copy an S3 object from one key to another.
 */
import { S3Client, CopyObjectCommand } from "@aws-sdk/client-s3";

const s3 = new S3Client({});

export async function s3_copy_object(toolInput) {
  const { bucket, key, destination_key, user_name } = toolInput;
  if (!bucket || !key || !destination_key || !user_name) {
    throw new Error("bucket, key, destination_key, and user_name are required");
  }

  const srcKey = key.startsWith(user_name) ? key : `${user_name}/${key}`;
  const dstKey = destination_key.startsWith(user_name) ? destination_key : `${user_name}/${destination_key}`;

  await s3.send(new CopyObjectCommand({
    Bucket: bucket,
    CopySource: `${bucket}/${srcKey}`,
    Key: dstKey,
  }));

  return { copied_from: srcKey, copied_to: dstKey };
}

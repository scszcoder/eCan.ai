/**
 * Tool handler: s3_list_objects
 * List objects under an S3 key prefix, gated by user_name.
 */
import { S3Client, ListObjectsV2Command } from "@aws-sdk/client-s3";

const s3 = new S3Client({});

export async function s3_list_objects(toolInput) {
  const { bucket, key, user_name, pattern, recursive, max_keys } = toolInput;
  if (!bucket || !key || !user_name) {
    throw new Error("bucket, key, and user_name are required");
  }

  const prefix = key.startsWith(user_name) ? key : `${user_name}/${key}`;
  const params = {
    Bucket: bucket,
    Prefix: prefix,
    MaxKeys: max_keys || 1000,
  };
  if (!recursive) {
    params.Delimiter = "/";
  }

  const resp = await s3.send(new ListObjectsV2Command(params));
  let objects = (resp.Contents || []).map((o) => ({
    key: o.Key,
    size: o.Size,
    last_modified: o.LastModified?.toISOString(),
  }));
  const folders = (resp.CommonPrefixes || []).map((p) => p.Prefix);

  // Apply glob pattern filter if provided
  if (pattern && pattern !== "*") {
    const regex = new RegExp(
      "^" + pattern.replace(/\*/g, ".*").replace(/\?/g, ".") + "$"
    );
    objects = objects.filter((o) => {
      const name = o.key.split("/").pop();
      return regex.test(name);
    });
  }

  return { objects, folders, count: objects.length, folder_count: folders.length };
}

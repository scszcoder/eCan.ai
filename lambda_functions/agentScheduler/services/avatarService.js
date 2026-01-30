// Avatar service backed by MySQL/Aurora via RDS Data API
const crypto = require("crypto");
const { execute } = require("../db/rdsClient");

const JSON_FIELDS = ["avatar_metadata"];

function genId(prefix) {
  return `${prefix}_${crypto.randomBytes(8).toString("hex")}`;
}

function toDbParam(name, value) {
  if (value === null || value === undefined) {
    return { name, value: { isNull: true } };
  }
  if (typeof value === "number") {
    return { name, value: { doubleValue: value } };
  }
  if (typeof value === "boolean") {
    return { name, value: { booleanValue: value } };
  }
  return { name, value: { stringValue: String(value) } };
}

function safeJsonStringify(value, fallback = null) {
  try {
    if (value === null || value === undefined) return fallback;
    return JSON.stringify(value);
  } catch (e) {
    return fallback;
  }
}

function parseFieldValue(field) {
  if (!field) return null;
  if (field.stringValue !== undefined) return field.stringValue;
  if (field.longValue !== undefined) return field.longValue;
  if (field.doubleValue !== undefined) return field.doubleValue;
  if (field.booleanValue !== undefined) return field.booleanValue;
  return null;
}

function rowsToObjects(result) {
  const cols = result.columnMetadata?.map((c) => c.name) || [];
  return (result.records || []).map((row) => {
    const obj = {};
    cols.forEach((col, idx) => {
      obj[col] = parseFieldValue(row[idx]);
      if (JSON_FIELDS.includes(col) && typeof obj[col] === "string") {
        try {
          obj[col] = JSON.parse(obj[col]);
        } catch (e) {
          // leave as string if parsing fails
        }
      }
    });
    return obj;
  });
}

async function addAvatarResource(resource) {
  const id = resource.id || genId("avatar");
  const sql = `
    INSERT INTO avatar_resources
    (id, resource_type, name, description, image_path, video_path, image_hash, video_hash,
     cloud_image_url, cloud_video_url, cloud_image_key, cloud_video_key, cloud_synced,
     avatar_metadata, usage_count, last_used_at, owner, is_public)
    VALUES
    (:id, :resource_type, :name, :description, :image_path, :video_path, :image_hash, :video_hash,
     :cloud_image_url, :cloud_video_url, :cloud_image_key, :cloud_video_key, :cloud_synced,
     :avatar_metadata, :usage_count, :last_used_at, :owner, :is_public)
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("resource_type", resource.resource_type || "uploaded"),
    toDbParam("name", resource.name || null),
    toDbParam("description", resource.description || null),
    toDbParam("image_path", resource.image_path || null),
    toDbParam("video_path", resource.video_path || null),
    toDbParam("image_hash", resource.image_hash || null),
    toDbParam("video_hash", resource.video_hash || null),
    toDbParam("cloud_image_url", resource.cloud_image_url || null),
    toDbParam("cloud_video_url", resource.cloud_video_url || null),
    toDbParam("cloud_image_key", resource.cloud_image_key || null),
    toDbParam("cloud_video_key", resource.cloud_video_key || null),
    toDbParam("cloud_synced", resource.cloud_synced || false),
    toDbParam("avatar_metadata", safeJsonStringify(resource.avatar_metadata, "{}")),
    toDbParam("usage_count", resource.usage_count || 0),
    toDbParam("last_used_at", resource.last_used_at || null),
    toDbParam("owner", resource.owner || null),
    toDbParam("is_public", resource.is_public || false)
  ];
  await execute(sql, params);
  return { success: true, id };
}

async function updateAvatarResource(id, fields) {
  const allowed = [
    "resource_type",
    "name",
    "description",
    "image_path",
    "video_path",
    "image_hash",
    "video_hash",
    "cloud_image_url",
    "cloud_video_url",
    "cloud_image_key",
    "cloud_video_key",
    "cloud_synced",
    "avatar_metadata",
    "usage_count",
    "last_used_at",
    "owner",
    "is_public"
  ];
  const setParts = [];
  const params = [toDbParam("id", id)];
  for (const key of allowed) {
    if (key in fields) {
      setParts.push(`${key} = :${key}`);
      const val = JSON_FIELDS.includes(key) ? safeJsonStringify(fields[key]) : fields[key];
      params.push(toDbParam(key, val));
    }
  }
  if (!setParts.length) return { success: false, error: "No valid fields to update" };
  const sql = `UPDATE avatar_resources SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true };
}

async function deleteAvatarResource(id) {
  // Clear agent references
  await execute("UPDATE agents SET avatar_resource_id = NULL WHERE avatar_resource_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM avatar_resources WHERE id = :id", [toDbParam("id", id)]);
  return { success: true };
}

async function getAvatarResource(id) {
  const res = await execute("SELECT * FROM avatar_resources WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  const rows = rowsToObjects(res);
  return rows[0] || null;
}

async function getAvatarResourcesByOwner(owner, resource_type) {
  const where = ["owner = :owner"];
  const params = [toDbParam("owner", owner)];
  if (resource_type) {
    where.push("resource_type = :resource_type");
    params.push(toDbParam("resource_type", resource_type));
  }
  const sql = `SELECT * FROM avatar_resources WHERE ${where.join(" AND ")} ORDER BY created_at DESC`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

async function getAvatarByHash(image_hash, owner) {
  const where = ["image_hash = :image_hash"];
  const params = [toDbParam("image_hash", image_hash)];
  if (owner) {
    where.push("owner = :owner");
    params.push(toDbParam("owner", owner));
  }
  const sql = `SELECT * FROM avatar_resources WHERE ${where.join(" AND ")} LIMIT 1`;
  const res = await execute(sql, params);
  const rows = rowsToObjects(res);
  return rows[0] || null;
}

async function getAllAvatarResources(limit) {
  const sql = limit
    ? `SELECT * FROM avatar_resources ORDER BY created_at DESC LIMIT ${Number(limit)}`
    : "SELECT * FROM avatar_resources ORDER BY created_at DESC";
  const res = await execute(sql);
  return rowsToObjects(res);
}

async function checkAvatarExists(id) {
  const res = await execute("SELECT 1 FROM avatar_resources WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  return (res.records || []).length > 0;
}

module.exports = {
  addAvatarResource,
  updateAvatarResource,
  deleteAvatarResource,
  getAvatarResource,
  getAvatarResourcesByOwner,
  getAvatarByHash,
  getAllAvatarResources,
  checkAvatarExists
};

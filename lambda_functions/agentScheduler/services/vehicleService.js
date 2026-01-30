// Vehicle service backed by MySQL/Aurora via RDS Data API
const crypto = require("crypto");
const { execute } = require("../db/rdsClient");

const JSON_FIELDS = ["gpu_info", "capabilities", "limitations", "settings", "extra_metadata"];

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

async function addVehicle(vehicle) {
  const requestedId = vehicle.id;
  const id = requestedId || genId("veh");

  if (requestedId) {
    const existing = await getVehicleById(requestedId);
    if (existing) {
      return { success: false, id: requestedId, error: "ID_TAKEN: Vehicle id already exists" };
    }
  }

  const sql = `
    INSERT INTO agent_vehicles
    (id, name, description, owner, vehicle_type, platform, architecture, ip_address, hostname, port, url,
     cpu_cores, memory_gb, storage_gb, gpu_info, status, health_score, last_heartbeat, uptime_seconds,
     capabilities, limitations, max_concurrent_tasks, location, timezone, environment, security_level,
     access_token, ssl_enabled, settings, extra_metadata)
    VALUES
    (:id, :name, :description, :owner, :vehicle_type, :platform, :architecture, :ip_address, :hostname, :port, :url,
     :cpu_cores, :memory_gb, :storage_gb, :gpu_info, :status, :health_score, :last_heartbeat, :uptime_seconds,
     :capabilities, :limitations, :max_concurrent_tasks, :location, :timezone, :environment, :security_level,
     :access_token, :ssl_enabled, :settings, :extra_metadata)
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("name", vehicle.name || ""),
    toDbParam("description", vehicle.description || null),
    toDbParam("owner", vehicle.owner),
    toDbParam("vehicle_type", vehicle.vehicle_type || "desktop"),
    toDbParam("platform", vehicle.platform || null),
    toDbParam("architecture", vehicle.architecture || null),
    toDbParam("ip_address", vehicle.ip_address || null),
    toDbParam("hostname", vehicle.hostname || null),
    toDbParam("port", vehicle.port || null),
    toDbParam("url", vehicle.url || null),
    toDbParam("cpu_cores", vehicle.cpu_cores || null),
    toDbParam("memory_gb", vehicle.memory_gb || null),
    toDbParam("storage_gb", vehicle.storage_gb || null),
    toDbParam("gpu_info", safeJsonStringify(vehicle.gpu_info)),
    toDbParam("status", vehicle.status || "offline"),
    toDbParam("health_score", vehicle.health_score != null ? vehicle.health_score : 1.0),
    toDbParam("last_heartbeat", vehicle.last_heartbeat || null),
    toDbParam("uptime_seconds", vehicle.uptime_seconds || 0),
    toDbParam("capabilities", safeJsonStringify(vehicle.capabilities)),
    toDbParam("limitations", safeJsonStringify(vehicle.limitations)),
    toDbParam("max_concurrent_tasks", vehicle.max_concurrent_tasks || 1),
    toDbParam("location", vehicle.location || null),
    toDbParam("timezone", vehicle.timezone || null),
    toDbParam("environment", vehicle.environment || "production"),
    toDbParam("security_level", vehicle.security_level || "standard"),
    toDbParam("access_token", vehicle.access_token || null),
    toDbParam("ssl_enabled", vehicle.ssl_enabled !== false), // default true
    toDbParam("settings", safeJsonStringify(vehicle.settings)),
    toDbParam("extra_metadata", safeJsonStringify(vehicle.extra_metadata))
  ];
  try {
    await execute(sql, params);
    return { success: true, id };
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("duplicate")) {
      return { success: false, id, error: "ID_TAKEN: Vehicle id already exists" };
    }
    throw err;
  }
}

async function updateVehicle(id, owner, fields) {
  const current = await getVehicleById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Vehicle not found" };
  }
  if (owner && current.owner !== owner) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  const allowed = [
    "name",
    "description",
    "owner",
    "vehicle_type",
    "platform",
    "architecture",
    "ip_address",
    "hostname",
    "port",
    "url",
    "cpu_cores",
    "memory_gb",
    "storage_gb",
    "gpu_info",
    "status",
    "health_score",
    "last_heartbeat",
    "uptime_seconds",
    "capabilities",
    "limitations",
    "max_concurrent_tasks",
    "location",
    "timezone",
    "environment",
    "security_level",
    "access_token",
    "ssl_enabled",
    "settings",
    "extra_metadata"
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
  const sql = `UPDATE agent_vehicles SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true, id };
}

async function deleteVehicle(id, owner) {
  const current = await getVehicleById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Vehicle not found" };
  }
  if (owner && current.owner !== owner) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  // Clean up task rels referencing this vehicle
  await execute("DELETE FROM agent_task_rels WHERE vehicle_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_vehicles WHERE id = :id", [toDbParam("id", id)]);
  return { success: true };
}

async function getVehicleById(id) {
  const res = await execute("SELECT * FROM agent_vehicles WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  const rows = rowsToObjects(res);
  return rows[0] || null;
}

async function queryVehicles({ id, name, description }) {
  const where = [];
  const params = [];
  if (id) {
    where.push("id = :id");
    params.push(toDbParam("id", id));
  }
  if (name) {
    where.push("name LIKE :name");
    params.push(toDbParam("name", `%${name}%`));
  }
  if (description) {
    where.push("description LIKE :description");
    params.push(toDbParam("description", `%${description}%`));
  }
  const sql = `SELECT * FROM agent_vehicles${where.length ? " WHERE " + where.join(" AND ") : ""}`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

async function updateVehicleStatus(id, status, health_score) {
  const params = [
    toDbParam("id", id),
    toDbParam("status", status),
    toDbParam("health_score", health_score != null ? health_score : null),
    toDbParam("last_heartbeat", new Date().toISOString().slice(0, 19).replace("T", " "))
  ];
  const setParts = ["status = :status", "last_heartbeat = :last_heartbeat"];
  if (health_score != null) setParts.push("health_score = :health_score");
  const sql = `UPDATE agent_vehicles SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true };
}

async function updateHeartbeat(id, uptime_seconds) {
  const params = [
    toDbParam("id", id),
    toDbParam("uptime_seconds", uptime_seconds != null ? uptime_seconds : null),
    toDbParam("last_heartbeat", new Date().toISOString().slice(0, 19).replace("T", " "))
  ];
  const setParts = ["last_heartbeat = :last_heartbeat"];
  if (uptime_seconds != null) setParts.push("uptime_seconds = :uptime_seconds");
  const sql = `UPDATE agent_vehicles SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true };
}

async function getVehicleTasks(vehicleId, status) {
  const where = ["vehicle_id = :vehicle_id"];
  const params = [toDbParam("vehicle_id", vehicleId)];
  if (status) {
    where.push("status = :status");
    params.push(toDbParam("status", status));
  }
  const sql = `SELECT * FROM agent_task_rels WHERE ${where.join(" AND ")} ORDER BY created_at DESC`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

module.exports = {
  addVehicle,
  updateVehicle,
  deleteVehicle,
  getVehicleById,
  queryVehicles,
  updateVehicleStatus,
  updateHeartbeat,
  getVehicleTasks
};

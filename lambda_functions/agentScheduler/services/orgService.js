// Organization service backed by MySQL/Aurora via RDS Data API
const crypto = require("crypto");
const { execute } = require("../db/rdsClient");

const JSON_FIELDS = ["settings"];

function genId() {
  return crypto.randomBytes(8).toString("hex");
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

function isRootPlaceholder(value) {
  if (!value) return false;
  const normalized = String(value).trim().toLowerCase();
  return normalized === "root" || normalized === "__virtual_root__" || normalized === "virtual_root";
}

async function countOrgs() {
  const res = await execute("SELECT COUNT(*) AS cnt FROM agent_orgs");
  const rows = rowsToObjects(res);
  return rows[0]?.cnt || 0;
}

/**
 * Ensure the owner column exists in agent_orgs table.
 * This is a migration helper - call once at startup or on demand.
 */
async function ensureOwnerColumn() {
  try {
    // Check if owner column exists
    const checkSql = `
      SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
      WHERE TABLE_NAME = 'agent_orgs' AND COLUMN_NAME = 'owner'
    `;
    const checkRes = await execute(checkSql, []);
    const rows = rowsToObjects(checkRes);
    if (rows.length === 0) {
      // Add owner column
      console.log("[orgService] Adding owner column to agent_orgs table...");
      await execute("ALTER TABLE agent_orgs ADD COLUMN owner VARCHAR(128) AFTER status", []);
      console.log("[orgService] owner column added successfully");
    }
  } catch (err) {
    console.error("[orgService] Error checking/adding owner column:", err.message);
  }
}

/**
 * Get or create the root organization for a user.
 * The root org is identified by: parent_id IS NULL AND owner = ownerSub
 * If it doesn't exist, create one with name = ownerSub and org_type = 'company'
 */
async function getOrCreateUserRootOrg(ownerSub) {
  if (!ownerSub) {
    console.error("[orgService] getOrCreateUserRootOrg: ownerSub is required");
    return null;
  }
  
  // Ensure owner column exists (migration helper)
  await ensureOwnerColumn();
  
  // Try to find existing root org for this user
  const findSql = `
    SELECT * FROM agent_orgs 
    WHERE parent_id IS NULL AND owner = :owner 
    ORDER BY created_at ASC LIMIT 1
  `;
  const findRes = await execute(findSql, [toDbParam("owner", ownerSub)]);
  const existing = rowsToObjects(findRes);
  
  if (existing.length > 0) {
    console.log(`[orgService] Found existing root org for ${ownerSub}: ${existing[0].id}`);
    return existing[0];
  }
  
  // Create new root org for this user
  const id = genId();
  console.log(`[orgService] Creating new root org for ${ownerSub} with id=${id}`);
  
  const insertSql = `
    INSERT INTO agent_orgs (id, name, description, parent_id, org_type, level, sort_order, status, owner, settings)
    VALUES (:id, :name, :description, NULL, 'company', 0, 0, 'active', :owner, :settings)
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("name", ownerSub),  // Name is the Cognito sub ID (frontend will display username)
    toDbParam("description", "User Organization"),
    toDbParam("owner", ownerSub),
    toDbParam("settings", safeJsonStringify({ autoCreated: true }))
  ];
  
  try {
    await execute(insertSql, params);
    const created = await getOrgById(id);
    console.log(`[orgService] Created root org: ${JSON.stringify(created)}`);
    return created;
  } catch (err) {
    console.error(`[orgService] Error creating root org for ${ownerSub}:`, err.message);
    // In case of race condition, try to find it again
    const retryRes = await execute(findSql, [toDbParam("owner", ownerSub)]);
    const retryRows = rowsToObjects(retryRes);
    return retryRows[0] || null;
  }
}

/**
 * Get all orgs owned by a specific user (by Cognito sub ID)
 */
async function getOrgsByOwner(ownerSub) {
  if (!ownerSub) return [];
  
  await ensureOwnerColumn();
  
  const sql = `SELECT * FROM agent_orgs WHERE owner = :owner ORDER BY level, sort_order, name`;
  const res = await execute(sql, [toDbParam("owner", ownerSub)]);
  return rowsToObjects(res);
}

/**
 * Get the org tree for a specific user.
 * Finds the user's root org, then builds the full tree from it.
 */
async function getOrgTreeByOwner(ownerSub) {
  if (!ownerSub) {
    return { success: false, data: null, error: "ownerSub is required" };
  }
  
  // Get or create the user's root org
  const rootOrg = await getOrCreateUserRootOrg(ownerSub);
  if (!rootOrg) {
    return { success: false, data: null, error: "Could not get or create root org" };
  }
  
  // Build tree from root
  const tree = await buildTreeNode(rootOrg);
  return { success: true, data: tree, error: null };
}

async function addOrg(data, owner = null) {
  const requestedId = data.id;
  const id = requestedId || genId();

  if (requestedId) {
    const existing = await getOrgById(requestedId);
    if (existing) {
      return { success: false, id: requestedId, data: null, error: "ID_TAKEN: Org id already exists" };
    }
  }

  // Ensure owner column exists
  await ensureOwnerColumn();

  let level = 0;
  let parentId = data.parent_id || null;
  let orgOwner = owner || data.owner || null;
  
  if (parentId) {
    const parent = await getOrgById(parentId);
    if (!parent) {
      if (isRootPlaceholder(parentId)) {
        parentId = null;
      } else {
        const totalOrgs = await countOrgs();
        if (totalOrgs === 0) {
          parentId = null;
        } else {
          return { success: false, id: null, data: null, error: `Parent org ${parentId} not found` };
        }
      }
    } else {
      level = (parent.level || 0) + 1;
      // Inherit owner from parent if not specified
      if (!orgOwner && parent.owner) {
        orgOwner = parent.owner;
      }
    }
  }
  const sql = `
    INSERT INTO agent_orgs
    (id, name, description, parent_id, org_type, level, sort_order, status, owner, settings)
    VALUES
    (:id, :name, :description, :parent_id, :org_type, :level, :sort_order, :status, :owner, :settings)
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("name", data.name || ""),
    toDbParam("description", data.description || null),
    toDbParam("parent_id", parentId || null),
    toDbParam("org_type", data.org_type || "department"),
    toDbParam("level", level),
    toDbParam("sort_order", data.sort_order || 0),
    toDbParam("status", data.status || "active"),
    toDbParam("owner", orgOwner),
    toDbParam("settings", safeJsonStringify(data.settings))
  ];
  try {
    await execute(sql, params);
    const created = await getOrgById(id);
    return { success: true, id, data: created, error: null };
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("duplicate")) {
      return { success: false, id, data: null, error: "ID_TAKEN: Org id already exists" };
    }
    throw err;
  }
}

async function getOrgById(id) {
  const res = await execute("SELECT * FROM agent_orgs WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  const rows = rowsToObjects(res);
  return rows[0] || null;
}

async function deleteOrg(id) {
  // enforce no children
  const childRes = await execute("SELECT COUNT(*) AS cnt FROM agent_orgs WHERE parent_id = :id", [toDbParam("id", id)]);
  const childCount = rowsToObjects(childRes)[0]?.cnt || 0;
  if (childCount > 0) {
    return { success: false, error: "Cannot delete org with children. Delete children first." };
  }
  await execute("DELETE FROM agent_org_rels WHERE org_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_orgs WHERE id = :id", [toDbParam("id", id)]);
  return { success: true, error: null };
}

async function searchOrgs({ name, org_type, status }) {
  const where = [];
  const params = [];
  if (name) {
    where.push("name LIKE :name");
    params.push(toDbParam("name", `%${name}%`));
  }
  if (org_type) {
    where.push("org_type = :org_type");
    params.push(toDbParam("org_type", org_type));
  }
  if (status) {
    where.push("status = :status");
    params.push(toDbParam("status", status));
  }
  const sql = `SELECT * FROM agent_orgs${where.length ? " WHERE " + where.join(" AND ") : ""} ORDER BY level, sort_order, name`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

async function getAllOrgs() {
  const res = await execute("SELECT * FROM agent_orgs ORDER BY level, sort_order, name");
  return rowsToObjects(res);
}

async function getOrgsByParent(parent_id) {
  const res = await execute("SELECT * FROM agent_orgs WHERE parent_id = :parent_id ORDER BY sort_order, name", [
    toDbParam("parent_id", parent_id)
  ]);
  return rowsToObjects(res);
}

async function updateOrg(id, data) {
  const current = await getOrgById(id);
  if (!current) {
    return { success: false, data: null, error: "NOT_FOUND: Org not found" };
  }

  const allowed = ["name", "description", "parent_id", "org_type", "level", "sort_order", "status", "settings"];
  const setParts = [];
  const params = [toDbParam("id", id)];
  for (const key of allowed) {
    if (key in data) {
      setParts.push(`${key} = :${key}`);
      const val = JSON_FIELDS.includes(key) ? safeJsonStringify(data[key]) : data[key];
      params.push(toDbParam(key, val));
    }
  }
  if (!setParts.length) return { success: false, data: null, error: "No valid fields to update" };
  const sql = `UPDATE agent_orgs SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  const updated = await getOrgById(id);
  return { success: true, data: updated, error: null };
}

async function buildTreeNode(org) {
  const children = await getOrgsByParent(org.id);
  return { ...org, children: await Promise.all(children.map(buildTreeNode)) };
}

async function getOrgTree(root_id) {
  if (root_id) {
    const root = await getOrgById(root_id);
    if (!root) return { success: false, data: null, error: `Organization with id ${root_id} not found` };
    return { success: true, data: await buildTreeNode(root), error: null };
  }
  const rootsRes = await execute("SELECT * FROM agent_orgs WHERE parent_id IS NULL ORDER BY sort_order, name");
  const roots = rowsToObjects(rootsRes);
  const tree = [];
  for (const r of roots) {
    tree.push(await buildTreeNode(r));
  }
  return { success: true, data: tree, error: null };
}

module.exports = {
  addOrg,
  getOrgById,
  deleteOrg,
  searchOrgs,
  getAllOrgs,
  getOrgsByParent,
  getOrgsByOwner,
  getOrCreateUserRootOrg,
  getOrgTreeByOwner,
  updateOrg,
  getOrgTree,
  ensureOwnerColumn
};

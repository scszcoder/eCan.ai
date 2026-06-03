/**
 * Skill Service - Skill domain CRUD operations backed by MySQL/Aurora via RDS Data API
 *
 * Data Model Overview:
 * - agent_skills     : Skill entity (name, description, config, source, owner, etc.)
 * - agent_skill_rels : Many-to-many relationship (agent <-> skill) with usage tracking
 * - agent_skill_tool_rels    : Many-to-many (skill <-> tool)
 * - agent_skill_knowledge_rels: Many-to-many (skill <-> knowledge)
 * - agent_skill_versions: Version history snapshots
 *
 * Key Design Decisions:
 *
 * 1. owner vs skill_owner (two-field ownership model):
 *    - owner:      The user who "has" this skill record (the subscriber / current user).
 *                  Used for permission checks and querying "my skills".
 *    - skill_owner: The original creator of the skill.
 *                  Used for marketplace/subscription scenarios.
 *
 *    When owner == skill_owner  → source = 'ui'     (user created their own skill)
 *    When owner != skill_owner  → source = 'subscribed' (skill was copied/subscribed)
 *
 * 2. source field semantics:
 *    - 'ui':         Skill created through the UI (editable by owner)
 *    - 'code':       Built-in code-based skill from resource/my_skills (read-only)
 *    - 'subscribed': Third-party skill subscribed from marketplace (read-only)
 *    - 'external':   Skill managed outside the system (read-only)
 *    NOTE: The source field is immutable after creation (blocked in updateSkill).
 *
 * 3. Soft delete strategy:
 *    - Deleting a skill sets deleted_at timestamp (not a hard DELETE).
 *    - Deleting a skill cascades to deactivate all agent_skill_rels.
 *    - Deleted skill IDs are tracked in a local file to prevent re-sync from cloud.
 *
 * 4. Subscription model (agent_skill_rels):
 *    - subscribe:   INSERT (or reactivate if duplicate key) with status='active'
 *    - unsubscribe: UPDATE status='inactive' (preserves usage history, allows re-subscribe)
 *    - Stats enrichment: subscribers count and usage_count are aggregated from agent_skill_rels.
 *
 * 5. Multi-identity owner resolution:
 *    - Users may be identified by email, Cognito sub, or sanitized username.
 *    - getSkillsByOwners queries all formats in a single OR query.
 *    - This handles legacy skills stored with different identity formats.
 */

const crypto = require("crypto");
const { execute } = require("../db/rdsClient");

/**
 * JSON columns in agent_skills that need parsing from string to object
 * after reading from the database, and stringification before writing.
 */
const JSON_FIELDS = [
  "config",
  "diagram",
  "tags",
  "examples",
  "inputModes",
  "outputModes",
  "apps",
  "limitations",
  "tool_config",
  "parameters",
  "knowledge_scope",
  "skill_config"
];

/**
 * Generate a short unique ID with a human-readable prefix.
 * @param {string} prefix - e.g. "skill", "asr", "rel_st"
 */
function genId(prefix) {
  return `${prefix}_${crypto.randomBytes(8).toString("hex")}`;
}

/**
 * Convert a JS value to an RDS Data API parameter object.
 * Handles null, number, boolean, and string types.
 */
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

/**
 * Safely JSON.stringify with a fallback for non-serializable values.
 * Returns fallback (default null) if serialization fails.
 */
function safeJsonStringify(value, fallback = null) {
  try {
    if (value === null || value === undefined) return fallback;
    return JSON.stringify(value);
  } catch (e) {
    return fallback;
  }
}

/**
 * Parse a single field value from an RDS Data API response row.
 * RDS returns typed objects: { stringValue }, { longValue }, { doubleValue }, { booleanValue }.
 */
function parseFieldValue(field) {
  if (!field) return null;
  if (field.stringValue !== undefined) return field.stringValue;
  if (field.longValue !== undefined) return field.longValue;
  if (field.doubleValue !== undefined) return field.doubleValue;
  if (field.booleanValue !== undefined) return field.booleanValue;
  return null;
}

/**
 * Convert an RDS Data API result object to an array of plain JS objects.
 * Also auto-parses JSON string columns back into objects.
 */
function rowsToObjects(result) {
  const cols = result.columnMetadata?.map((c) => c.name) || [];
  return (result.records || []).map((row) => {
    const obj = {};
    cols.forEach((col, idx) => {
      obj[col] = parseFieldValue(row[idx]);
      // Auto-parse known JSON columns
      if (JSON_FIELDS.includes(col) && typeof obj[col] === "string") {
        try {
          obj[col] = JSON.parse(obj[col]);
        } catch (e) {
          // leave as string if parsing fails (e.g. empty or malformed JSON)
        }
      }
    });
    return obj;
  });
}

/**
 * Add a new skill to agent_skills.
 *
 * Key logic: source field resolution based on owner vs skill_owner.
 * - If skill_owner is explicitly provided and differs from owner → source = 'subscribed'
 * - Otherwise → source = 'ui' (default) or user-provided value
 *
 * Uses the skill's own id if provided; otherwise generates a new one.
 * Returns error if id is already taken.
 */
async function addSkill(skill) {
  const requestedId = skill.id;
  const id = requestedId || genId("skill");

  // Prevent duplicate IDs (idempotency check)
  if (requestedId) {
    const existing = await getSkillById(requestedId);
    if (existing) {
      return { success: false, id: requestedId, error: "ID_TAKEN: Skill id already exists" };
    }
  }

  // --- Source resolution ---
  // skill_owner: original creator of the skill (null means same as owner)
  // owner:      current user who "has" this skill record
  // If they differ, this is a subscribed skill (copied from another user).
  const skillOwner = skill.skill_owner || skill.owner;
  const isSubscribed = skill.owner !== skillOwner;
  // Resolve final source: 'subscribed' if copied, otherwise use provided value or default 'ui'
  const resolvedSource = isSubscribed ? "subscribed" : (skill.source || "ui");

  const sql = `
    INSERT INTO agent_skills
    (id, askid, name, owner, skill_owner, description, version, path, source, level,
     config, diagram, tags, examples, inputModes, outputModes, apps, limitations,
     price, price_model, public, rentable)
    VALUES
    (:id, :askid, :name, :owner, :skill_owner, :description, :version, :path, :source, :level,
     :config, :diagram, :tags, :examples, :inputModes, :outputModes, :apps, :limitations,
     :price, :price_model, :public, :rentable)
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("askid", skill.askid || 0),
    toDbParam("name", skill.name || ""),
    toDbParam("owner", skill.owner),
    toDbParam("skill_owner", skillOwner),
    toDbParam("description", skill.description || null),
    toDbParam("version", skill.version || "1.0.0"),
    toDbParam("path", skill.path || null),
    toDbParam("source", resolvedSource),
    toDbParam("level", skill.level || null),
    toDbParam("config", safeJsonStringify(skill.config)),
    toDbParam("diagram", safeJsonStringify(skill.diagram)),
    toDbParam("tags", safeJsonStringify(skill.tags)),
    toDbParam("examples", safeJsonStringify(skill.examples)),
    toDbParam("inputModes", safeJsonStringify(skill.inputModes)),
    toDbParam("outputModes", safeJsonStringify(skill.outputModes)),
    toDbParam("apps", safeJsonStringify(skill.apps)),
    toDbParam("limitations", safeJsonStringify(skill.limitations)),
    toDbParam("price", skill.price || 0),
    toDbParam("price_model", skill.price_model || null),
    toDbParam("public", skill.public || false),
    toDbParam("rentable", skill.rentable || false)
  ];
  try {
    await execute(sql, params);
    return { success: true, id };
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("duplicate")) {
      return { success: false, id, error: "ID_TAKEN: Skill id already exists" };
    }
    throw err;
  }
}

/**
 * Update an existing skill.
 *
 * - Permission check: only the owner (or matching email/sub) can update.
 * - source field is protected: users cannot change it (maintains data integrity).
 *   This prevents a subscribed skill from being renamed to source='ui'.
 * - Only whitelisted fields can be updated (no arbitrary column injection).
 */
async function updateSkill(id, owner, fields) {
  const current = await getSkillById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Skill not found" };
  }
  if (owner && current.owner !== owner) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  // --- Source immutability: prevent non-admin users from changing source ---
  // Changing source='subscribed' to source='ui' would break the subscription model.
  if (fields.source !== undefined && fields.source !== current.source) {
    delete fields.source;
  }

  // Whitelist of updatable fields (prevents SQL injection / accidental column writes)
  const allowed = [
    "askid",
    "name",
    "owner",
    "skill_owner",
    "description",
    "version",
    "path",
    "level",
    "config",
    "diagram",
    "tags",
    "examples",
    "inputModes",
    "outputModes",
    "apps",
    "limitations",
    "price",
    "price_model",
    "public",
    "rentable"
  ];
  const setParts = [];
  const params = [toDbParam("id", id)];
  for (const key of allowed) {
    if (key in fields) {
      setParts.push(`${key} = :${key}`);
      // JSON fields must be serialized to string before writing to DB
      const val = JSON_FIELDS.includes(key) ? safeJsonStringify(fields[key]) : fields[key];
      params.push(toDbParam(key, val));
    }
  }
  if (!setParts.length) return { success: false, error: "No valid fields to update" };
  const sql = `UPDATE agent_skills SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true, id };
}

/**
 * Soft-delete a skill.
 *
 * Three-step cascade:
 *   1. Set deleted_at on agent_skills (soft delete the skill entity)
 *   2. Set status='inactive' on all agent_skill_rels (deactivate all subscriptions)
 *   3. Track deleted skill IDs in a local file to prevent cloud re-sync
 *
 * Ownership check supports both email and Cognito sub as identity tokens.
 */
async function deleteSkill(id, ownerEmail, ownerSub) {
  const current = await getSkillById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Skill not found" };
  }
  // Support both email and Cognito sub as owner identifiers
  const ownerMatches =
    !current.owner ||
    (ownerEmail && current.owner === ownerEmail) ||
    (ownerSub && current.owner === ownerSub);
  if (!ownerMatches) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  const now = new Date().toISOString().slice(0, 23);

  // Step 1: soft delete the skill entity
  await execute(
    `UPDATE agent_skills
     SET deleted_at = :deleted_at
     WHERE id = :id`,
    [toDbParam("deleted_at", now), toDbParam("id", id)]
  );

  // Step 2: cascade soft delete to all subscriptions (preserve usage history)
  await execute(
    `UPDATE agent_skill_rels
     SET status = 'inactive', updated_at = :now
     WHERE skill_id = :id`,
    [toDbParam("now", now), toDbParam("id", id)]
  );

  // Step 3: track locally so deleted skills are not re-synced from cloud
  await markSkillAsDeleted(id, ownerEmail || ownerSub);

  return { success: true };
}

/** Fetch a single skill by id (includes soft-deleted skills for admin use). */
async function getSkillById(id) {
  const res = await execute("SELECT * FROM agent_skills WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  const rows = rowsToObjects(res);
  return rows[0] || null;
}

/**
 * Enrich a list of skills with statistics from agent_skill_rels and agent_skill_reviews.
 *
 * Adds computed fields to each skill:
 *   - subscribers:         count of active agent_skill_rels (subscriber count)
 *   - subscription_count:  alias for subscribers (for frontend compatibility)
 *   - usage_count:         sum of usage_count across all active subscriptions
 *   - rating:              average rating from agent_skill_reviews (rounded to 1 decimal)
 *   - reviewCount:         total number of reviews
 *   - rating_distribution:  { 1: count, 2: count, ..., 5: count }
 *
 * Uses two GROUP BY queries for efficiency (avoids N+1).
 */
async function enrichSkillsWithStats(skills) {
  if (!skills || skills.length === 0) return skills;

  const skillIds = skills.map(s => s.id).filter(Boolean);
  if (skillIds.length === 0) return skills;

  const placeholders = skillIds.map((_, i) => `:sid${i}`).join(", ");
  const params = skillIds.map((id, i) => toDbParam(`sid${i}`, id));

  // Aggregate subscriber count and total usage per skill (only active subscriptions)
  const aggRes = await execute(
    `SELECT skill_id, COUNT(*) AS subscriber_count, SUM(usage_count) AS total_usage
     FROM agent_skill_rels
     WHERE skill_id IN (${placeholders}) AND status = 'active'
     GROUP BY skill_id`,
    params
  );

  // Build a lookup map: skillId -> { subscribers, usage_count }
  const aggMap = {};
  if (aggRes && aggRes.records) {
    aggRes.records.forEach(row => {
      aggMap[row[0].stringValue] = {
        subscribers: Number(row[1].longValue) || 0,
        usage_count: Number(row[2].longValue) || 0,
      };
    });
  }

  // Aggregate review stats per skill (batch query)
  const reviewRes = await execute(
    `SELECT skill_id, COUNT(*) AS review_count,
            AVG(rating) AS avg_rating,
            SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) AS star_1,
            SUM(CASE WHEN rating = 2 THEN 1 ELSE 0 END) AS star_2,
            SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END) AS star_3,
            SUM(CASE WHEN rating = 4 THEN 1 ELSE 0 END) AS star_4,
            SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END) AS star_5
     FROM agent_skill_reviews
     WHERE skill_id IN (${placeholders})
     GROUP BY skill_id`,
    params
  );

  const reviewMap = {};
  if (reviewRes && reviewRes.records) {
    reviewRes.records.forEach(row => {
      const count = Number(row[1].longValue) || 0;
      reviewMap[row[0].stringValue] = {
        reviewCount: count,
        avgRating: count > 0 ? Math.round(Number(row[2].doubleValue) * 10) / 10 : 0,
        distribution: {
          1: Number(row[3].longValue) || 0,
          2: Number(row[4].longValue) || 0,
          3: Number(row[5].longValue) || 0,
          4: Number(row[6].longValue) || 0,
          5: Number(row[7].longValue) || 0,
        }
      };
    });
  }

  // Annotate each skill with computed stats
  skills.forEach(skill => {
    const agg = aggMap[skill.id] || {};
    const review = reviewMap[skill.id] || {};
    skill.subscribers = agg.subscribers || 0;
    skill.subscription_count = agg.subscribers || 0;
    skill.usage_count = agg.usage_count || 0;
    skill.rating = review.avgRating || 0;
    skill.reviewCount = review.reviewCount || 0;
    skill.rating_distribution = review.distribution || { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  });

  return skills;
}

/** Get all skills for a single owner, with stats enrichment. */
async function getSkillsByOwner(owner) {
  const res = await execute("SELECT * FROM agent_skills WHERE owner = :owner", [toDbParam("owner", owner)]);
  const skills = rowsToObjects(res);
  return enrichSkillsWithStats(skills);
}

/**
 * Get skills by multiple owner identifiers (email, Cognito sub, sanitized username).
 *
 * Motivation: Legacy skills may be stored with any of these identity formats.
 * Querying all formats in a single OR query ensures no skills are missed.
 *
 * Example: user@example.com might have skills stored under:
 *   - "user@example.com"        (email)
 *   - "us-er_-example_-com"     (Cognito sub)
 *   - "user_example_com"        (sanitized email)
 * All three are queried to return a complete skill list.
 */
async function getSkillsByOwners(ownerEmail, ownerSub, ownerSanitized) {
  // Deduplicate: collect unique, non-empty owner candidates
  const ownerSet = new Set(
    [ownerEmail, ownerSub, ownerSanitized].filter(o => o && o.trim())
  );
  const owners = Array.from(ownerSet);
  if (owners.length === 0) {
    return [];
  }
  if (owners.length === 1) {
    return getSkillsByOwner(owners[0]);
  }
  // Build dynamic OR query for all owner candidates
  const conditions = [];
  const params = [];
  owners.forEach((o, i) => {
    const paramName = `owner${i}`;
    conditions.push(`owner = :${paramName}`);
    params.push(toDbParam(paramName, o));
  });
  const res = await execute(
    `SELECT * FROM agent_skills WHERE ${conditions.join(" OR ")}`,
    params
  );
  const skills = rowsToObjects(res);
  return enrichSkillsWithStats(skills);
}

/** Basic keyword search across skill name and description, with limit/offset. */
async function querySkills({ id, name, description, limit = 100, offset = 0 }) {
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
  const sql = `SELECT * FROM agent_skills${where.length ? " WHERE " + where.join(" AND ") : ""} ORDER BY updated_at DESC LIMIT :limit OFFSET :offset`;
  params.push(toDbParam("limit", Math.min(limit, 1000)));
  params.push(toDbParam("offset", offset));
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

/**
 * Paginated skill query with optional owner and search filters.
 * Returns { skills, total, hasMore } for frontend pagination.
 */
async function querySkillsPaginated({ owner, category, tags, search, limit = 20, offset = 0 }) {
  const where = [];
  const params = [];

  if (owner) {
    where.push("owner = :owner");
    params.push(toDbParam("owner", owner));
  }

  if (search) {
    where.push("(name LIKE :search OR description LIKE :search)");
    params.push(toDbParam("search", `%${search}%`));
  }

  // Count total for pagination metadata (separate query)
  const countSql = `SELECT COUNT(*) as total FROM agent_skills${where.length ? " WHERE " + where.join(" AND ") : ""}`;
  const countRes = await execute(countSql, params);
  const total = countRes?.records?.[0]?.[0]?.longValue || 0;

  // Fetch data page with limit/offset
  const dataParams = [...params, toDbParam("limit", Math.min(limit, 1000)), toDbParam("offset", offset)];
  const dataSql = `SELECT * FROM agent_skills${where.length ? " WHERE " + where.join(" AND ") : ""} ORDER BY updated_at DESC LIMIT :limit OFFSET :offset`;
  const dataRes = await execute(dataSql, dataParams);
  const skills = rowsToObjects(dataRes);

  await enrichSkillsWithStats(skills);

  return {
    skills,
    total,
    hasMore: offset + skills.length < total
  };
}

// ============================================================================
// Skill <-> Tool relationship
// ============================================================================

/**
 * Associate a tool with a skill.
 * Uses DELETE + INSERT (upsert) to handle re-registration cleanly.
 */
async function addToolToSkill(skillId, toolId, { dependency_type = "required", usage_frequency = "medium", importance = 1, tool_config = {} } = {}) {
  await execute("DELETE FROM agent_skill_tool_rels WHERE skill_id = :skill_id AND tool_id = :tool_id", [
    toDbParam("skill_id", skillId),
    toDbParam("tool_id", toolId)
  ]);
  const sql = `
    INSERT INTO agent_skill_tool_rels
    (id, skill_id, tool_id, dependency_type, usage_frequency, importance, tool_config)
    VALUES (:id, :skill_id, :tool_id, :dependency_type, :usage_frequency, :importance, :tool_config)
  `;
  const params = [
    toDbParam("id", genId("rel_st")),
    toDbParam("skill_id", skillId),
    toDbParam("tool_id", toolId),
    toDbParam("dependency_type", dependency_type),
    toDbParam("usage_frequency", usage_frequency),
    toDbParam("importance", importance),
    toDbParam("tool_config", safeJsonStringify(tool_config, "{}"))
  ];
  await execute(sql, params);
  return { success: true };
}

/** Remove a tool-skill association (hard delete). */
async function removeToolFromSkill(skillId, toolId) {
  await execute("DELETE FROM agent_skill_tool_rels WHERE skill_id = :skill_id AND tool_id = :tool_id", [
    toDbParam("skill_id", skillId),
    toDbParam("tool_id", toolId)
  ]);
  return { success: true };
}

/** Get all tools associated with a skill, optionally filtered by dependency type. */
async function getSkillTools(skillId, dependency_type) {
  const where = ["skill_id = :skill_id"];
  const params = [toDbParam("skill_id", skillId)];
  if (dependency_type) {
    where.push("dependency_type = :dependency_type");
    params.push(toDbParam("dependency_type", dependency_type));
  }
  const sql = `SELECT * FROM agent_skill_tool_rels WHERE ${where.join(" AND ")} ORDER BY importance DESC`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

// ============================================================================
// Skill <-> Knowledge relationship
// ============================================================================

/**
 * Associate a knowledge base with a skill.
 * Uses DELETE + INSERT (upsert) pattern.
 */
async function addKnowledgeToSkill(skillId, knowledgeId, { dependency_type = "required", access_pattern = "read", knowledge_scope = [] } = {}) {
  await execute("DELETE FROM agent_skill_knowledge_rels WHERE skill_id = :skill_id AND knowledge_id = :knowledge_id", [
    toDbParam("skill_id", skillId),
    toDbParam("knowledge_id", knowledgeId)
  ]);
  const sql = `
    INSERT INTO agent_skill_knowledge_rels
    (id, skill_id, knowledge_id, dependency_type, access_pattern, knowledge_scope)
    VALUES (:id, :skill_id, :knowledge_id, :dependency_type, :access_pattern, :knowledge_scope)
  `;
  const params = [
    toDbParam("id", genId("rel_sk")),
    toDbParam("skill_id", skillId),
    toDbParam("knowledge_id", knowledgeId),
    toDbParam("dependency_type", dependency_type),
    toDbParam("access_pattern", access_pattern),
    toDbParam("knowledge_scope", safeJsonStringify(knowledge_scope || [], "[]"))
  ];
  await execute(sql, params);
  return { success: true };
}

/** Remove a knowledge-skill association (hard delete). */
async function removeKnowledgeFromSkill(skillId, knowledgeId) {
  await execute("DELETE FROM agent_skill_knowledge_rels WHERE skill_id = :skill_id AND knowledge_id = :knowledge_id", [
    toDbParam("skill_id", skillId),
    toDbParam("knowledge_id", knowledgeId)
  ]);
  return { success: true };
}

/** Get all knowledge bases associated with a skill. */
async function getSkillKnowledges(skillId, dependency_type) {
  const where = ["skill_id = :skill_id"];
  const params = [toDbParam("skill_id", skillId)];
  if (dependency_type) {
    where.push("dependency_type = :dependency_type");
    params.push(toDbParam("dependency_type", dependency_type));
  }
  const sql = `SELECT * FROM agent_skill_knowledge_rels WHERE ${where.join(" AND ")} ORDER BY importance DESC`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

// ============================================================================
// Skill version history
// ============================================================================

/**
 * Create a versioned snapshot of the current skill state.
 * Used for change tracking and rollback.
 * Snapshot includes all core fields but not stats or computed fields.
 */
async function createSkillVersion(skillId, version, operator) {
  const skill = await getSkillById(skillId);
  if (!skill) return { success: false, error: "SKILL_NOT_FOUND" };

  const versionId = genId("skv");
  const now = new Date().toISOString().slice(0, 23);

  // Snapshot: serialize core skill fields as JSON
  const snapshot = JSON.stringify({
    name: skill.name,
    description: skill.description,
    version: skill.version,
    level: skill.level,
    config: skill.config,
    diagram: skill.diagram,
    tags: skill.tags,
    examples: skill.examples,
    apps: skill.apps,
    limitations: skill.limitations,
  });

  const sql = `
    INSERT INTO agent_skill_versions
    (id, skill_id, version, snapshot, changelog, created_by, created_at)
    VALUES (:id, :skill_id, :version, :snapshot, :changelog, :created_by, :created_at)
  `;
  const params = [
    toDbParam("id", versionId),
    toDbParam("skill_id", skillId),
    toDbParam("version", version),
    toDbParam("snapshot", snapshot),
    toDbParam("changelog", ""),
    toDbParam("created_by", operator),
    toDbParam("created_at", now),
  ];

  await execute(sql, params);
  return { success: true, id: versionId, version };
}

/** Get version history for a skill (newest first). Deserializes snapshot JSON. */
async function getSkillVersions(skillId, limit = 10) {
  const sql = `SELECT * FROM agent_skill_versions WHERE skill_id = :skill_id ORDER BY created_at DESC LIMIT :limit`;
  const res = await execute(sql, [toDbParam("skill_id", skillId), toDbParam("limit", limit)]);
  const rows = rowsToObjects(res);
  return rows.map(row => ({
    ...row,
    snapshot: typeof row.snapshot === 'string' ? JSON.parse(row.snapshot) : row.snapshot
  }));
}

// ============================================================================
// Deleted skill tracking (local file — prevents re-sync from cloud)
// ============================================================================

/**
 * Local file path for tracking deleted skill IDs.
 * Used to prevent cloud re-sync of locally-deleted skills.
 * File format: JSON { [skillId]: { deletedAt, deletedBy } }
 */
const DELETED_SKILLS_FILE = '/tmp/deleted_skills.json';

/**
 * Record a skill as deleted in local tracking file.
 * After this, sync logic should skip this skillId.
 */
async function markSkillAsDeleted(skillId, deletedBy) {
  const fs = require('fs');
  let deleted = {};
  try {
    if (fs.existsSync(DELETED_SKILLS_FILE)) {
      deleted = JSON.parse(fs.readFileSync(DELETED_SKILLS_FILE, 'utf8'));
    }
  } catch (e) {
    // Start fresh if file is corrupt or unreadable
  }

  deleted[skillId] = {
    deletedAt: new Date().toISOString(),
    deletedBy: deletedBy
  };

  try {
    fs.writeFileSync(DELETED_SKILLS_FILE, JSON.stringify(deleted, null, 2));
  } catch (e) {
    console.warn(`[skillService] Could not persist deleted_skills: ${e.message}`);
  }

  return { success: true };
}

/** Check if a skill ID is in the local deleted tracking file. */
async function isSkillDeleted(skillId) {
  const fs = require('fs');
  if (!fs.existsSync(DELETED_SKILLS_FILE)) return false;
  try {
    const deleted = JSON.parse(fs.readFileSync(DELETED_SKILLS_FILE, 'utf8'));
    return !!deleted[skillId];
  } catch (e) {
    return false;
  }
}

// ============================================================================
// Subscription management (agent <-> skill relationship)
// ============================================================================

/**
 * List all public skills (public=true OR owner='public').
 * Used for marketplace / browse discovery.
 * Includes subscriber and usage statistics.
 */
async function getPublicSkills() {
  const res = await execute(
    "SELECT * FROM agent_skills WHERE `public` = TRUE OR owner = 'public'",
    []
  );
  const skills = rowsToObjects(res);
  return enrichSkillsWithStats(skills);
}

/**
 * Subscribe an agent to a skill by creating an agent_skill_rels record.
 *
 * - INSERT with ON DUPLICATE KEY UPDATE status='active' to safely handle
 *   re-subscription (previously unsubscribed skill can be re-subscribed).
 * - Does NOT create a new agent_skills record; the skill must already exist.
 * - Proficiency level defaults to 'beginner'.
 * - Sets status='active' on INSERT; re-subscription reactivates the record.
 */
async function subscribeToSkill(agentId, skillId, proficiencyLevel = "beginner") {
  const id = genId("asr");
  const now = new Date().toISOString().slice(0, 23);
  try {
    await execute(
      `INSERT INTO agent_skill_rels
       (id, agent_id, skill_id, proficiency_level, status, created_at, updated_at)
       VALUES (:id, :agent_id, :skill_id, :proficiency_level, 'active', :now, :now)
       ON DUPLICATE KEY UPDATE
         status = 'active',
         proficiency_level = :proficiency_level,
         updated_at = :now`,
      [
        toDbParam("id", id),
        toDbParam("agent_id", agentId),
        toDbParam("skill_id", skillId),
        toDbParam("proficiency_level", proficiencyLevel),
        toDbParam("now", now),
      ]
    );
  } catch (err) {
    // Duplicate key = already subscribed → reactivate silently (idempotent)
    if (err.message && err.message.includes("Duplicate")) {
      return { success: true, id: skillId };
    }
    throw err;
  }
  return { success: true, id: skillId };
}

/**
 * Unsubscribe an agent from a skill (soft delete).
 *
 * - Sets status='inactive' (NOT a hard DELETE).
 * - Preserves usage_count history for analytics.
 * - Allows re-subscription later (subscribeToSkill will re-activate).
 */
async function unsubscribeFromSkill(agentId, skillId) {
  const now = new Date().toISOString().slice(0, 23);
  await execute(
    `UPDATE agent_skill_rels
     SET status = 'inactive', updated_at = :now
     WHERE agent_id = :agent_id AND skill_id = :skill_id`,
    [
      toDbParam("now", now),
      toDbParam("agent_id", agentId),
      toDbParam("skill_id", skillId),
    ]
  );
  return { success: true, id: skillId };
}

/**
 * Get all skill IDs that a list of agents are subscribed to.
 * Returns deduplicated skill_id list.
 */
async function getSubscribedSkillIds(agentIds) {
  if (!agentIds || agentIds.length === 0) return [];
  const placeholders = agentIds.map((_, i) => `:aid${i}`);
  const params = agentIds.map((aid, i) => toDbParam(`aid${i}`, aid));
  const res = await execute(
    `SELECT DISTINCT skill_id FROM agent_skill_rels WHERE agent_id IN (${placeholders.join(",")})`,
    params
  );
  return rowsToObjects(res).map(r => r.skill_id);
}

// ============================================================================
// Skill Reviews / Ratings
// ============================================================================

async function upsertSkillReview(skillId, reviewerId, rating, reviewText) {
  const reviewId = `skr_${crypto.randomBytes(8).toString("hex")}`;
  const now = new Date().toISOString().slice(0, 23);

  // Check if review already exists for this (skill, reviewer) pair
  const checkSql = `SELECT id FROM agent_skill_reviews WHERE skill_id = :skill_id AND reviewer_id = :reviewer_id LIMIT 1`;
  const checkRes = await execute(checkSql, [toDbParam("skill_id", skillId), toDbParam("reviewer_id", reviewerId)]);
  const existing = rowsToObjects(checkRes);

  if (existing.length > 0) {
    // Update existing review
    const updateSql = `UPDATE agent_skill_reviews SET rating = :rating, review_text = :review_text, updated_at = :updated_at WHERE skill_id = :skill_id AND reviewer_id = :reviewer_id`;
    await execute(updateSql, [
      toDbParam("rating", rating),
      toDbParam("review_text", reviewText || ""),
      toDbParam("updated_at", now),
      toDbParam("skill_id", skillId),
      toDbParam("reviewer_id", reviewerId),
    ]);
    return { success: true, id: existing[0].id, action: "updated" };
  }

  // Insert new review
  const insertSql = `INSERT INTO agent_skill_reviews (id, skill_id, reviewer_id, rating, review_text, helpful, created_at, updated_at) VALUES (:id, :skill_id, :reviewer_id, :rating, :review_text, :helpful, :created_at, :updated_at)`;
  await execute(insertSql, [
    toDbParam("id", reviewId),
    toDbParam("skill_id", skillId),
    toDbParam("reviewer_id", reviewerId),
    toDbParam("rating", rating),
    toDbParam("review_text", reviewText || ""),
    toDbParam("helpful", 0),
    toDbParam("created_at", now),
    toDbParam("updated_at", now),
  ]);
  return { success: true, id: reviewId, action: "created" };
}

async function getSkillReviews(skillId) {
  const sql = `SELECT * FROM agent_skill_reviews WHERE skill_id = :skill_id ORDER BY created_at DESC`;
  const res = await execute(sql, [toDbParam("skill_id", skillId)]);
  return rowsToObjects(res);
}

async function getSkillRatingStats(skillId) {
  const sql = `SELECT COUNT(*) as total, AVG(rating) as avg_rating, SUM(helpful) as total_helpful FROM agent_skill_reviews WHERE skill_id = :skill_id`;
  const res = await execute(sql, [toDbParam("skill_id", skillId)]);
  const rows = rowsToObjects(res);
  if (!rows.length) return { total: 0, avgRating: 0, totalHelpful: 0 };
  return {
    total: rows[0].total || 0,
    avgRating: rows[0].avg_rating ? Math.round(rows[0].avg_rating * 10) / 10 : 0,
    totalHelpful: rows[0].total_helpful || 0,
  };
}

async function deleteSkillReview(reviewId, reviewerId) {
  const sql = `DELETE FROM agent_skill_reviews WHERE id = :id AND reviewer_id = :reviewer_id`;
  await execute(sql, [toDbParam("id", reviewId), toDbParam("reviewer_id", reviewerId)]);
  return { success: true };
}


// ============================================================================
// Public API
// ============================================================================

module.exports = {
  addSkill,
  updateSkill,
  deleteSkill,
  getSkillById,
  getSkillsByOwner,
  getSkillsByOwners,
  querySkills,
  querySkillsPaginated,
  addToolToSkill,
  removeToolFromSkill,
  getSkillTools,
  addKnowledgeToSkill,
  removeKnowledgeFromSkill,
  getSkillKnowledges,
  getPublicSkills,
  subscribeToSkill,
  unsubscribeFromSkill,
  getSubscribedSkillIds,
  createSkillVersion,
  getSkillVersions,
  markSkillAsDeleted,
  isSkillDeleted,
  upsertSkillReview,
  getSkillReviews,
  getSkillRatingStats,
  deleteSkillReview,
};

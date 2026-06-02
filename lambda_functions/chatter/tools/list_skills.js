/**
 * Tool handler: list_skills
 * List all available skills and their statuses.
 *
 * Data source: Aurora (RDS Data API) — table: agent_skills
 *
 * Key features:
 *   - Multi-identity owner resolution (owner_id, owner_email, owner_sub, owner_sanitized)
 *   - Filtering by category, tags, and text search (name + description)
 *   - Stats enrichment (subscribers count, usage_count) from agent_skill_rels
 *   - source normalization: legacy 'chatter' source is mapped to 'ui'
 *
 * Query logic:
 *   SELECT * FROM agent_skills WHERE owner IN (owner1, owner2, ...) [AND filters]
 *   → The IN clause with multiple identifiers handles legacy skills stored under
 *     different identity formats (email, Cognito sub, sanitized username).
 */
import { execute, strParam } from "./rdsClient.js";

/**
 * Convert RDS Data API result rows to plain JS objects.
 * Auto-parses known JSON string columns back to objects.
 * Also normalizes legacy 'chatter' source values to 'ui'.
 */
function rowsToObjects(result) {
  const cols = result.columnMetadata?.map((c) => c.name) || [];
  return (result.records || []).map((row) => {
    const obj = {};
    cols.forEach((col, idx) => {
      const field = row[idx];
      if (field?.stringValue !== undefined) obj[col] = field.stringValue;
      else if (field?.longValue !== undefined) obj[col] = field.longValue;
      else if (field?.doubleValue !== undefined) obj[col] = field.doubleValue;
      else if (field?.booleanValue !== undefined) obj[col] = field.booleanValue;
      else obj[col] = null;
    });
    // Parse JSON string fields
    const JSON_FIELDS = ["config", "diagram", "tags", "examples", "inputModes", "outputModes", "apps", "limitations", "parameters", "knowledge_scope", "skill_config"];
    JSON_FIELDS.forEach((jsonField) => {
      if (obj[jsonField] && typeof obj[jsonField] === "string") {
        try { obj[jsonField] = JSON.parse(obj[jsonField]); } catch (_) { /* leave as string */ }
      }
    });
    // Normalize source field: 'chatter' is a legacy source value → map to 'ui'
    if (obj.source === 'chatter') {
      obj.source = 'ui';
    }
    return obj;
  });
}

/**
 * Tool input schema:
 *   owner_id          — required, primary owner identifier
 *   owner_email       — optional, additional identity to search
 *   owner_sub         — optional, Cognito sub (additional identity)
 *   owner_sanitized   — optional, sanitized username (additional identity)
 *   category          — optional, filter by category (matches tags)
 *   tags_filter       — optional, array of tags (OR match)
 *   search            — optional, full-text search on name + description
 *   limit             — max results, default 100
 */
export async function list_skills(toolInput) {
  const {
    owner_id,
    owner_email,
    owner_sub,
    owner_sanitized,
    category,
    status_filter,
    tags_filter,
    search,
    limit = 100,
  } = toolInput;

  // At least one owner identifier is required
  if (!owner_id && !owner_email && !owner_sub && !owner_sanitized) {
    throw new Error("At least one owner identifier is required");
  }

  // --- Multi-identity owner resolution ---
  // Collect unique, non-empty owner candidates from all provided identity formats.
  // Deduplication ensures we don't query the same owner twice.
  // Example: user@example.com + user_example_com (sanitized) → 2 values in set
  const ownerSet = new Set(
    [owner_id, owner_email, owner_sub, owner_sanitized].filter(o => o && String(o).trim())
  );
  const owners = Array.from(ownerSet);

  if (owners.length === 0) {
    return { skills: [], count: 0 };
  }

  // Build dynamic OR query for all owner candidates
  const conditions = [];
  const params = [];
  owners.forEach((o, i) => {
    const paramName = `owner${i}`;
    conditions.push(`owner = :${paramName}`);
    params.push(strParam(paramName, String(o)));
  });

  let sql = `SELECT * FROM agent_skills WHERE ${conditions.join(" OR ")}`;

  // --- Category filter (matches tags array) ---
  // Supports both JSON array format (JSON_CONTAINS) and plain comma-separated string.
  if (category) {
    sql += ` AND (JSON_CONTAINS(tags, :cat, '$') OR FIND_IN_SET(:cat2, tags))`;
    params.push(strParam("cat", JSON.stringify(category)));
    params.push(strParam("cat2", category));
  }

  // --- Tags filter (OR match — skills matching ANY of the provided tags) ---
  if (tags_filter && Array.isArray(tags_filter) && tags_filter.length > 0) {
    tags_filter.forEach((tag, i) => {
      sql += ` AND (JSON_CONTAINS(tags, :tag${i}, '$') OR FIND_IN_SET(:tag${i}b, tags))`;
      params.push(strParam(`tag${i}`, JSON.stringify(tag)));
      params.push(strParam(`tag${i}b`, tag));
    });
  }

  // --- Text search (name OR description) ---
  if (search) {
    sql += ` AND (name LIKE :search OR description LIKE :search2)`;
    params.push(strParam("search", `%${search}%`));
    params.push(strParam("search2", `%${search}%`));
  }

  sql += ` ORDER BY updated_at DESC LIMIT :limit`;
  params.push(strParam("limit", String(limit)));

  const result = await execute(sql, params);
  const skills = rowsToObjects(result);

  // --- Stats enrichment from agent_skill_rels ---
  // For each returned skill, query the subscription table to get:
  //   subscribers: count of active agent_skill_rels for this skill
  //   usage_count: sum of usage_count across all active subscriptions
  //   rating: always null (no review table; frontend shows "NEW")
  //
  // Uses a single GROUP BY query for all skills (avoids N+1).
  if (skills.length > 0) {
    const skillIds = skills.map((s) => s.id).filter(Boolean);
    const placeholders = skillIds.map((_, i) => `:sid${i}`).join(", ");
    const aggParams = skillIds.map((id, i) => strParam(`sid${i}`, id));

    const aggSql = `
      SELECT
        skill_id,
        COUNT(*) AS subscriber_count,
        SUM(usage_count) AS total_usage_count
      FROM agent_skill_rels
      WHERE skill_id IN (${placeholders}) AND status = 'active'
      GROUP BY skill_id
    `;
    const aggResult = await execute(aggSql, aggParams);
    const aggMap = {};
    if (aggResult && aggResult.records) {
      aggResult.records.forEach((row) => {
        aggMap[row[0].stringValue] = {
          subscriber_count: row[1].longValue || 0,
          total_usage_count: row[2].longValue || 0,
        };
      });
    }

    skills.forEach((skill) => {
      const agg = aggMap[skill.id] || {};
      // subscribers = count of active agent_skill_rels
      skill.subscribers = agg.subscriber_count || 0;
      // usage_count = sum of usage_count across all agent_skill_rels
      skill.usage_count = agg.total_usage_count || 0;
      // rating: not available in Aurora — use null (frontend shows "NEW")
      skill.rating = null;
    });
  }

  return { skills, count: skills.length };
}

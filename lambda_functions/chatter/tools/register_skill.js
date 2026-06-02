/**
 * Tool handler: register_skill
 * Register a new skill in the skill registry.
 *
 * Data source: Aurora (RDS Data API) — table: agent_skills
 *
 * Design notes:
 *   - This is a lightweight handler for agent/CLI use cases.
 *     For full field support (level, examples, apps, limitations, etc.),
 *     use the agentScheduler skillService.addSkill path instead.
 *   - source defaults to 'ui' (skills registered through the UI are user-created).
 *   - Uses ON DUPLICATE KEY UPDATE for idempotency — re-registering a skill
 *     with the same ID updates its fields rather than failing.
 *   - Does NOT set skill_owner: when a user registers their own skill,
 *     owner == skill_owner (both are the registering user), so they are
 *     effectively the same. The skill_owner column defaults to NULL in SQL,
 *     and the skillService.addSkill path handles the explicit case.
 */
import { execute, strParam } from "./rdsClient.js";
import { randomUUID } from "node:crypto";

/** Generate a human-readable unique skill ID with a "skill_" prefix. */
function genId(prefix) {
  return `${prefix}_${randomUUID().replace(/-/g, "").slice(0, 16)}`;
}

/**
 * Tool input schema:
 *   owner_id     — required, the user registering this skill
 *   name         — required, unique skill name
 *   category     — optional, stored as a tag in the tags array
 *   description  — optional
 *   version      — optional, defaults to "1.0.0"
 *   tags         — optional array of tags
 *   input_schema / output_schema — optional, stored inside the config JSON
 *   public       — optional, whether visible in the marketplace
 *   rentable     — optional, whether can be rented
 *   price        — optional, price in cents (0 = free)
 *   price_model  — optional, e.g. 'per-use', 'subscription'
 *   level        — optional, skill difficulty
 *   apps         — optional array
 *   limitations  — optional array
 *   examples     — optional array
 *   source       — optional, defaults to "ui"
 */
export async function register_skill(toolInput) {
  const {
    owner_id, name, category, description,
    input_schema, output_schema,
    version = "1.0.0",
    tags = [],
    public: isPublic = false,
    rentable = false,
    price = 0,
    price_model = null,
    level = null,
    apps = [],
    limitations = [],
    examples = [],
    // source defaults to 'ui' for skills registered through the UI
    source = "ui",
  } = toolInput;

  if (!owner_id || !name) {
    throw new Error("owner_id and name are required");
  }

  const skillId = toolInput.skill_id || genId("skill");
  const now = new Date().toISOString().slice(0, 23);

  // Build config JSON with input/output schemas if provided.
  // The config field is a JSON column that can store arbitrary structured data.
  const config = {
    input_schema: input_schema || null,
    output_schema: output_schema || null,
    ...(toolInput.config || {}),
  };
  const configJson = JSON.stringify(config);

  // Merge category into tags array.
  // If tags are already provided, use them as-is.
  // If no tags but category is provided, use [category] as the tags.
  const mergedTags = tags && tags.length > 0
    ? tags
    : (category ? [category] : []);

  // --- SQL: INSERT with ON DUPLICATE KEY UPDATE (upsert semantics) ---
  // If the skill ID already exists, update its fields instead of failing.
  // This enables idempotent re-registration.
  // NOTE: source is NOT updated on duplicate key (it is set only on INSERT).
  // NOTE: skill_owner is NOT set here — owner == skill_owner implicitly.
  const sql = `
    INSERT INTO agent_skills
    (id, name, owner, description, version, tags, config,
     apps, limitations, examples, level,
     price, price_model, public, rentable, source,
     created_at, updated_at)
    VALUES
    (:id, :name, :owner, :desc, :version, :tags, :config,
     :apps, :limitations, :examples, :level,
     :price, :price_model, :public, :rentable, :source,
     :now, :now)
    ON DUPLICATE KEY UPDATE
      name = VALUES(name),
      description = VALUES(description),
      version = VALUES(version),
      tags = VALUES(tags),
      config = VALUES(config),
      apps = VALUES(apps),
      limitations = VALUES(limitations),
      examples = VALUES(examples),
      level = VALUES(level),
      price = VALUES(price),
      price_model = VALUES(price_model),
      public = VALUES(public),
      rentable = VALUES(rentable),
      updated_at = VALUES(updated_at)
  `;

  await execute(sql, [
    strParam("id", skillId),
    strParam("name", name),
    strParam("owner", owner_id),
    strParam("desc", description || ""),
    strParam("version", version),
    strParam("tags", JSON.stringify(mergedTags)),
    strParam("config", configJson),
    strParam("apps", JSON.stringify(apps)),
    strParam("limitations", JSON.stringify(limitations)),
    strParam("examples", JSON.stringify(examples)),
    strParam("level", level),
    strParam("price", price),
    strParam("price_model", price_model),
    // MySQL boolean: "1" = true, "0" = false (RDS Data API string representation)
    strParam("public", isPublic ? "1" : "0"),
    strParam("rentable", rentable ? "1" : "0"),
    strParam("source", source),
    strParam("now", now),
  ]);

  return {
    skill_id: skillId,
    name,
    category,
    status: "registered",
    created_at: now,
  };
}

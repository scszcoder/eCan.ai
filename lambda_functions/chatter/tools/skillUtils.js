/**
 * Shared utilities for skill operations in the chatter tool handlers.
 *
 * These functions are used by multiple tool handlers (subscribe_skill, unsubscribe_skill)
 * to avoid code duplication and ensure consistent logic across handlers.
 *
 * Two main utilities:
 *   - resolveAgentIdByOwner: resolve agent_id from multiple owner identity formats
 *   - subscribeSkill / unsubscribeSkill: subscription management on agent_skill_rels
 *
 * Source normalization utilities are also provided for reference, though
 * the primary source logic lives in skillService.js (agentScheduler).
 */
import { execute, strParam } from "./rdsClient.js";

/**
 * Resolve an agent ID from multiple owner identity formats.
 *
 * Motivation: Agents are stored in the agents table with an 'owner' column.
 *            That 'owner' value can be an email, a Cognito sub, or a sanitized username,
 *            depending on how and when the agent was created.
 *
 *            This function queries all three formats in a single OR query
 *            to find the agent regardless of which identity format was used.
 *
 * Example: A user might have agents stored under:
 *   - owner = "user@example.com"        (email-based)
 *   - owner = "us-er-examp-le-com"     (Cognito sub, dots replaced)
 *   - owner = "user_example_com"       (sanitized email)
 *
 * Returns the first matching agent ID, or null if no agent found.
 *
 * @param {string} owner        - Username / raw owner string
 * @param {string} ownerEmail   - Email address (also added as sanitized variant)
 * @param {string} ownerSub     - Cognito sub identifier
 * @returns {Promise<string|null>} - Agent ID or null
 */
export async function resolveAgentIdByOwner(owner, ownerEmail, ownerSub) {
  const owners = new Set();
  if (owner) owners.add(owner);
  if (ownerEmail) owners.add(ownerEmail);
  if (ownerSub) owners.add(ownerSub);
  // Also add sanitized email (dots and @ replaced with _) as a lookup variant
  if (ownerEmail) owners.add(ownerEmail.replace(/[@.]/g, "_"));

  if (owners.size === 0) return null;

  const ownerList = Array.from(owners);
  const placeholders = ownerList.map((_, i) => `:owner${i}`).join(", ");
  const params = ownerList.map((o, i) => strParam(`owner${i}`, o));

  const res = await execute(
    `SELECT id FROM agents WHERE owner IN (${placeholders}) LIMIT 1`,
    params
  );

  if (!res || !res.records || res.records.length === 0) {
    return null;
  }
  return res.records[0][0].stringValue;
}

/**
 * Normalize source field to valid SkillSource values.
 *
 * Valid values: 'ui' | 'code' | 'subscribed' | 'external'
 *
 * Legacy values mapped:
 *   - 'chatter' → 'ui' (backward compatibility for old skill registrations)
 *
 * Unknown/invalid values → 'ui' (safe default).
 *
 * @param {string} source - Raw source value
 * @returns {string} - Normalized source
 */
export function normalizeSkillSource(source) {
  if (!source) return "ui";
  if (source === "chatter") return "ui"; // backward compatibility
  if (source === "code" || source === "ui" || source === "subscribed" || source === "external") {
    return source;
  }
  return "ui"; // default fallback for unknown values
}

/**
 * Validate whether a source value is one of the allowed SkillSource values.
 * @param {string} source - Source value to validate
 * @returns {boolean} - True if valid
 */
export function isValidSkillSource(source) {
  const valid = ["ui", "code", "subscribed", "external"];
  return valid.includes(source);
}

/**
 * Subscribe an agent to a skill (create or reactivate agent_skill_rels record).
 *
 * Subscription model:
 *   - INSERT INTO agent_skill_rels with status='active'
 *   - ON DUPLICATE KEY UPDATE status='active' (reactivate if previously unsubscribed)
 *
 * This is an upsert: subscribing to an already-subscribed skill re-activates it.
 * The proficiency_level is set/updated on each subscription.
 *
 * Does NOT modify the agent_skills record (no source field changes here).
 *
 * @param {string} agentId         - Agent ID (from agents table)
 * @param {string} skillId        - Skill ID (from agent_skills table)
 * @param {string} proficiencyLevel - Proficiency level, default 'beginner'
 * @returns {Promise<{success: boolean, agent_id: string, skill_id: string}>}
 */
export async function subscribeSkill(agentId, skillId, proficiencyLevel = "beginner") {
  const { randomUUID } = await import("node:crypto");
  const relId = `asr_${randomUUID().replace(/-/g, "").slice(0, 16)}`;
  const now = new Date().toISOString().slice(0, 23);

  const sql = `INSERT INTO agent_skill_rels
    (id, agent_id, skill_id, proficiency_level, status, created_at, updated_at)
    VALUES (:id, :agent_id, :skill_id, :proficiency_level, 'active', :now, :now)
    ON DUPLICATE KEY UPDATE
      status = 'active',
      proficiency_level = :proficiency_level,
      updated_at = :now`;

  await execute(sql, [
    strParam("id", relId),
    strParam("agent_id", agentId),
    strParam("skill_id", skillId),
    strParam("proficiency_level", proficiencyLevel),
    strParam("now", now),
  ]);

  return { success: true, agent_id: agentId, skill_id: skillId };
}

/**
 * Unsubscribe an agent from a skill (soft delete agent_skill_rels record).
 *
 * Soft delete semantics:
 *   - Sets status='inactive' (preserves usage history for analytics)
 *   - Hard DELETE is NOT used (would lose valuable usage data)
 *   - Re-subscribing will reactivate the existing row (upsert in subscribeSkill)
 *
 * Only affects active subscriptions (WHERE status = 'active').
 * If already inactive, this is a no-op (idempotent).
 *
 * @param {string} agentId - Agent ID
 * @param {string} skillId - Skill ID
 * @returns {Promise<{success: boolean, agent_id: string, skill_id: string}>}
 */
export async function unsubscribeSkill(agentId, skillId) {
  const now = new Date().toISOString().slice(0, 23);
  const sql = `UPDATE agent_skill_rels SET status = 'inactive', updated_at = :now
               WHERE agent_id = :agent_id AND skill_id = :skill_id AND status = 'active'`;

  await execute(sql, [
    strParam("now", now),
    strParam("agent_id", agentId),
    strParam("skill_id", skillId),
  ]);

  return { success: true, agent_id: agentId, skill_id: skillId };
}

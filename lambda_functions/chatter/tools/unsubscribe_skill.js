/**
 * Tool handler: unsubscribe_skill
 * Unsubscribe an agent from a skill (soft-delete agent_skill_rels record).
 *
 * Data source: Aurora (RDS Data API) — table: agent_skill_rels
 *
 * Identity resolution (same as subscribe_skill):
 *   Accepts either:
 *     - agent_id directly, OR
 *     - owner / owner_email / owner_sub (resolved to agent_id internally)
 *
 * Soft delete semantics:
 *   - Sets status='inactive' on the agent_skill_rels row.
 *   - Does NOT hard-delete the record — preserves usage history for analytics.
 *   - The agent can re-subscribe later (subscribeSkill will reactivate the row).
 *   - This contrasts with skillService.deleteSkill which soft-deletes the
 *     entire skill entity (agent_skills.deleted_at).
 *
 * NOTE: This unsubscribes the agent's subscription to the skill.
 *       It does NOT delete the skill entity itself.
 */
import { resolveAgentIdByOwner, unsubscribeSkill } from "./skillUtils.js";

/**
 * Tool input schema:
 *   agent_id    — optional, direct agent ID (if not provided, resolved from owner*)
 *   owner       — optional, username of agent owner
 *   owner_email — optional, email of agent owner
 *   owner_sub   — optional, Cognito sub
 *   skill_id    — required, ID of the skill to unsubscribe from
 *
 * At least one identity field (agent_id OR owner/owner_email/owner_sub) is required.
 */
export async function unsubscribe_skill(toolInput) {
  const {
    agent_id,
    owner,
    owner_email,
    owner_sub,
    skill_id,
  } = toolInput;

  // --- Resolve agent ID if not provided directly ---
  let resolvedAgentId = agent_id;

  if (!resolvedAgentId) {
    if (!owner && !owner_email && !owner_sub) {
      throw new Error("Either agent_id or owner/owner_email/owner_sub must be provided");
    }
    resolvedAgentId = await resolveAgentIdByOwner(owner, owner_email, owner_sub);
    if (!resolvedAgentId) {
      throw new Error(`No agent found for owner=${owner}, email=${owner_email}`);
    }
  }

  if (!skill_id) {
    throw new Error("skill_id is required");
  }

  // Soft delete: mark subscription as inactive instead of removing the relationship.
  // Only affects active subscriptions (WHERE status = 'active').
  // If already inactive, this is a no-op (idempotent).
  await unsubscribeSkill(resolvedAgentId, skill_id);

  return { agent_id: resolvedAgentId, skill_id, status: "unsubscribed" };
}

/**
 * Tool handler: subscribe_skill
 * Subscribe an agent to a skill, creating an agent_skill_rels record.
 *
 * Data source: Aurora (RDS Data API) — table: agent_skill_rels
 *
 * Identity resolution:
 *   Accepts either:
 *     - agent_id directly (primary key of agents table), OR
 *     - owner / owner_email / owner_sub
 *       (resolved to agent_id via resolveAgentIdByOwner in skillUtils.js)
 *
 *   This two-path approach unifies the Python backend (which uses owner/username
 *   as primary identity) with agent callers (which may only know the agent_id).
 *
 * Subscription semantics:
 *   - Does NOT create a new agent_skills record — the skill must already exist.
 *   - Creates a NEW agent_skill_rels row (agent <-> skill link).
 *   - If already subscribed, the existing row is reactivated (status='active').
 *   - Proficiency level defaults to 'beginner'.
 *
 * Note on source field:
 *   The skill's source field should be 'subscribed' when the subscriber
 *   (owner) differs from the skill's creator (skill_owner).
 *   This is set by skillService.addSkill when creating a copied/subscribed skill.
 *   subscribe_skill itself does NOT modify the agent_skills record.
 */
import { resolveAgentIdByOwner, subscribeSkill } from "./skillUtils.js";

/**
 * Tool input schema:
 *   agent_id        — optional, direct agent ID (if not provided, resolved from owner*)
 *   owner           — optional, username of agent owner (used if agent_id missing)
 *   owner_email     — optional, email of agent owner (used if agent_id missing)
 *   owner_sub       — optional, Cognito sub (used if agent_id missing)
 *   skill_id        — required, ID of the skill to subscribe to
 *   proficiency_level — optional, default "beginner"
 *
 * At least one identity field (agent_id OR owner/owner_email/owner_sub) is required.
 */
export async function subscribe_skill(toolInput) {
  const {
    agent_id,
    owner,
    owner_email,
    owner_sub,
    skill_id,
    proficiency_level,
  } = toolInput;

  // --- Resolve agent ID if not provided directly ---
  // This handles the case where callers only know the owner's identity
  // (username, email, or Cognito sub) but not the internal agent ID.
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

  // Create or reactivate the agent_skill_rels subscription record.
  // Idempotent: re-subscribing an already-subscribed skill is a no-op (returns success).
  const result = await subscribeSkill(resolvedAgentId, skill_id, proficiency_level || "beginner");

  return {
    success: result.success,
    agent_id: resolvedAgentId,
    skill_id,
    status: "subscribed",
    subscribed_at: new Date().toISOString().slice(0, 23),
  };
}

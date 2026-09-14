/**
 * Display names for the seeded departments.
 *
 * `agent/ec_agents/organization_template.json` seeds every new account with the
 * same eight organizations, and their names are stored in the DB in English —
 * so a CN build shows "Sales" and "Finance" sitting next to otherwise-Chinese
 * UI. The names are data, not UI strings, so i18next cannot reach them.
 *
 * They are translated by the template's **stable id** rather than by matching
 * the name text: an org a customer created has its own id and falls through
 * with whatever they called it, and one they *renamed* keeps their name because
 * the lookup is only consulted when the stored name is still the seeded default.
 *
 * The company root is deliberately absent — "eCan.ai" is a brand, not a word.
 */

/** The seeded ids, mapped to the name each carries in organization_template.json. */
export const SEEDED_ORG_DEFAULT_NAMES: Record<string, string> = {
  org_agent_resource_001: 'Agent Resource',
  org_accounting_001: 'Accounting',
  org_finance_001: 'Finance',
  org_legal_001: 'Legal',
  org_marketing_001: 'Marketing',
  org_sales_001: 'Sales',
  org_rnd_001: 'Research and Development',
};

export const SEEDED_ORG_KEY_PREFIX = 'pages.agents.departments.';

/**
 * The i18n key for a seeded department, or null.
 *
 * `storedName` guards against overwriting a rename: if the customer changed
 * "Sales" to "华东销售", the stored name no longer matches the seeded default
 * and their name is what should be shown.
 */
export function seededOrgNameKey(orgId?: string, storedName?: string): string | null {
  if (!orgId) return null;
  const seeded = SEEDED_ORG_DEFAULT_NAMES[orgId];
  if (!seeded) return null;
  if (typeof storedName === 'string' && storedName.trim() && storedName.trim() !== seeded) {
    return null;
  }
  return `${SEEDED_ORG_KEY_PREFIX}${orgId}`;
}

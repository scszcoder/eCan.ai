/**
 * Store rules: one text per topic; Save writes back one policy per changed topic.
 */

export interface PolicyTopic { value: string; label: string }

export interface PolicyChanges {
  save: { topic: string; text: string }[];
  /** Ids of saved rules whose section was emptied. */
  remove: { topic: string; id: string }[];
}

/** What Save must do: write changed sections, delete emptied ones.
 *  ``texts``: the edited text per topic, trimmed ('' = left empty). */
export function policyChanges(
  texts: Record<string, string>,
  existing: Record<string, { id: string; text: string } | undefined>,
): PolicyChanges {
  const save: PolicyChanges['save'] = [];
  const remove: PolicyChanges['remove'] = [];
  Object.entries(texts).forEach(([topic, text]) => {
    const prev = existing[topic];
    if (text) {
      if (!prev || prev.text.trim() !== text) save.push({ topic, text });
    } else if (prev) {
      remove.push({ topic, id: prev.id });
    }
  });
  return { save, remove };
}

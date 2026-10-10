/**
 * Store rules as ONE markdown document: a "## <topic label>" section per topic,
 * each with an example hint in an HTML comment. The user scrolls and fills in
 * the sections; Save writes back one policy per section.
 */

export interface PolicyTopic { value: string; label: string }

/** A hint shown inside a section (never saved). */
const HINT_RE = /<!--[\s\S]*?-->/g;

export function buildPolicyDoc(
  topics: PolicyTopic[],
  textOf: (topic: string) => string,
  hintOf: (topic: string) => string,
): string {
  return topics.map(({ value, label }) => {
    const text = (textOf(value) || '').trim();
    const hint = (hintOf(value) || '').trim();
    return `## ${label}\n${hint ? `<!-- ${hint.replace(/-->/g, '—>')} -->\n` : ''}${text}\n`;
  }).join('\n');
}

export interface ParsedPolicyDoc {
  /** Section text per topic (hints removed, trimmed; '' = left empty). */
  texts: Record<string, string>;
  /** "## ..." headings that match no topic (their text is not saved). */
  unknown: string[];
}

/** Read the sections back; a heading matches a topic by its label or key. */
export function parsePolicyDoc(doc: string, topics: PolicyTopic[]): ParsedPolicyDoc {
  const byHeading = new Map<string, string>();
  topics.forEach(({ value, label }) => {
    byHeading.set(label.trim().toLowerCase(), value);
    byHeading.set(value.trim().toLowerCase(), value);
  });
  const texts: Record<string, string> = {};
  const unknown: string[] = [];
  let current: string | null = null;
  let lines: string[] = [];
  const flush = () => {
    if (current !== null) {
      const body = lines.join('\n').replace(HINT_RE, '').trim();
      texts[current] = texts[current] ? `${texts[current]}\n\n${body}`.trim() : body;
    }
    lines = [];
  };
  for (const line of doc.replace(/\r\n/g, '\n').split('\n')) {
    const m = /^##\s+(.+?)\s*#*\s*$/.exec(line);
    if (m) {
      flush();
      const topic = byHeading.get(m[1].trim().toLowerCase());
      if (topic) {
        current = topic;
      } else {
        current = null;
        unknown.push(m[1].trim());
      }
      continue;
    }
    if (current !== null) lines.push(line);
  }
  flush();
  return { texts, unknown };
}

export interface PolicyChanges {
  save: { topic: string; text: string }[];
  /** Ids of saved rules whose section was emptied. */
  remove: { topic: string; id: string }[];
}

/** What Save must do: write changed sections, delete emptied ones. */
export function policyChanges(
  parsed: ParsedPolicyDoc,
  existing: Record<string, { id: string; text: string } | undefined>,
): PolicyChanges {
  const save: PolicyChanges['save'] = [];
  const remove: PolicyChanges['remove'] = [];
  Object.entries(parsed.texts).forEach(([topic, text]) => {
    const prev = existing[topic];
    if (text) {
      if (!prev || prev.text.trim() !== text) save.push({ topic, text });
    } else if (prev) {
      remove.push({ topic, id: prev.id });
    }
  });
  return { save, remove };
}

import { Tool } from './types';

/**
 * Tools carry their taxonomy inline in the description string, e.g.
 *
 *   "<category>RPA</category><sub-category>Supervisor</sub-category>As a RPA
 *    supervisor, fetches daily work schedule ..."
 *
 * 296 of the 332 shipped tools follow this shape; the rest have a plain
 * description. The backend has no structured `category` field, and
 * `tool_type` is not populated (`tool_type` is always "custom" for local
 * tools). So the tag block is the only real taxonomy we have and we parse it
 * on the client rather than inventing a second source of truth.
 *
 * Keep this parser deliberately tolerant: unknown tags are left in the
 * description text so nothing is silently dropped.
 */

export const UNCATEGORIZED = '\u0000uncategorized';

const CATEGORY_RE = /<category>([\s\S]*?)<\/category>/;
const SUBCATEGORY_RE = /<sub-category>([\s\S]*?)<\/sub-category>/;
// Matches any leftover self-closing or paired tag we know about, plus a
// generic fallback so a future <foo>x</foo> does not leak into the UI.
const TAG_RE = /<\/?(?:category|sub-category)>/gi;

export interface ToolTaxonomy {
  /** Real category, or '' when the description had no <category> tag. */
  category: string;
  /** Real sub-category, or '' when absent. */
  subcategory: string;
  /** Description with the taxonomy tag block stripped. */
  description: string;
}

export function parseToolTaxonomy(tool: Pick<Tool, 'description'>): ToolTaxonomy {
  const raw = tool?.description ?? '';

  const catMatch = raw.match(CATEGORY_RE);
  const subMatch = raw.match(SUBCATEGORY_RE);

  const description = decodeEntities(
    raw
      .replace(CATEGORY_RE, '')
      .replace(SUBCATEGORY_RE, '')
      .replace(TAG_RE, '')
      .trim()
  );

  return {
    category: catMatch ? decodeEntities(catMatch[1].trim()) : '',
    subcategory: subMatch ? decodeEntities(subMatch[1].trim()) : '',
    description,
  };
}

/** Minimal entity decode — descriptions occasionally contain &amp; / &quot;. */
function decodeEntities(s: string): string {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');
}

export interface CategoryBucket {
  /** Display name; also the filter key. */
  name: string;
  /** True for the synthetic "uncategorized" bucket. */
  isUncategorized: boolean;
  count: number;
  /** Distinct sub-categories inside this bucket, with counts, descending. */
  subcategories: { name: string; count: number }[];
}

/**
 * Group tools by their parsed category. Sorting is stable and intentional:
 * biggest buckets first (that is what people actually reach for), with the
 * synthetic uncategorized bucket always last.
 */
export function buildCategoryBuckets(
  tools: Tool[],
  uncategorizedLabel: string
): CategoryBucket[] {
  const map = new Map<string, { count: number; subs: Map<string, number> }>();

  for (const tool of tools) {
    const { category, subcategory } = parseToolTaxonomy(tool);
    const key = category || UNCATEGORIZED;
    let entry = map.get(key);
    if (!entry) {
      entry = { count: 0, subs: new Map() };
      map.set(key, entry);
    }
    entry.count += 1;
    if (subcategory) {
      entry.subs.set(subcategory, (entry.subs.get(subcategory) ?? 0) + 1);
    }
  }

  const buckets: CategoryBucket[] = [];
  for (const [key, entry] of map) {
    const isUncategorized = key === UNCATEGORIZED;
    buckets.push({
      name: isUncategorized ? uncategorizedLabel : key,
      isUncategorized,
      count: entry.count,
      subcategories: [...entry.subs.entries()]
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)),
    });
  }

  buckets.sort((a, b) => {
    if (a.isUncategorized !== b.isUncategorized) return a.isUncategorized ? 1 : -1;
    return b.count - a.count || a.name.localeCompare(b.name);
  });

  return buckets;
}

/** Filter predicate shared by the search box and the category rail. */
export function toolMatches(
  tool: Tool,
  query: string,
  bucketName: string | null,
  uncategorizedLabel: string
): boolean {
  const { category, subcategory, description } = parseToolTaxonomy(tool);

  if (bucketName) {
    const effective = category || uncategorizedLabel;
    if (effective !== bucketName) return false;
  }

  if (query) {
    const q = query.trim().toLowerCase();
    if (q) {
      const haystack = [
        tool.name,
        tool.title,
        description,
        category,
        subcategory,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(q)) return false;
    }
  }

  return true;
}

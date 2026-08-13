/**
 * add_snake_alias.js
 *
 * Adds snake_case alias fields to every `input` definition in a GraphQL SDL
 * string. Used to let eCan.ai client (which sends snake_case keys) talk to a
 * backend whose input SDL is camelCase.
 *
 * Why this exists:
 *   - The client local field naming (and the AppSync AWS GraphQL schema) is
 *     snake_case (`extra_data`, `supervisor_id`, …).
 *   - The CN cloudbase-graphql SDL was hand-written with camelCase
 *     (`extraData`, `supervisorId`, …).
 *   - GraphQL validation rejects unknown fields, so the SDL must accept both.
 *
 * What it does:
 *   - Parses the SDL with graphql-js.
 *   - For every InputObjectType field whose name is camelCase, computes the
 *     snake_case form. If the input already declares that snake_case field,
 *     nothing changes. Otherwise the snake_case alias is appended right after
 *     the original field, sharing the same type (including `!` non-null) and
 *     default value.
 *
 * What it does NOT do:
 *   - Touch `type` definitions (response shape is unaffected by request field
 *     names; clients parse responses by field name, not by request field name).
 *   - Touch Query / Mutation / Subscription args (clients pass only input
 *     objects into mutations; argument names stay camelCase in queries).
 *   - Add aliases for fields whose name is already snake_case (no-op).
 *   - Strip or rewrite existing SDL — purely additive.
 */

const { parse, print } = require('graphql');

function camelToSnake(name) {
  // avatarResourceId → avatar_resource_id
  // Already-snake fields (containing `_` or all-lowercase) are returned as-is.
  if (!/[A-Z]/.test(name)) return name;
  // Trailing all-caps abbreviations (ID, URL, URI, IP, OS, …) are kept as a
  // single token: "agentID" → "agent_id", NOT "agent_i_d". We only collapse
  // the run when the whole tail is uppercase AND length >= 2, so a single
  // trailing "I" in "agentI" still becomes "agent_i" (one capital = one token).
  const trailing = /([A-Z]{2,})$/.exec(name);
  if (trailing) {
    const head = name.slice(0, -trailing[1].length);
    const tail = trailing[1].toLowerCase();
    return head.replace(/[A-Z]/g, (ch) => '_' + ch.toLowerCase()) + '_' + tail;
  }
  return name.replace(/[A-Z]/g, (ch) => '_' + ch.toLowerCase());
}

/**
 * Build a synthetic snake_case alias field for an input field.
 * Mirrors the original's type expression and default value so the SDL is
 * semantically equivalent.
 */
function makeSnakeAliasField(fieldNode) {
  const snakeName = camelToSnake(fieldNode.name.value);
  // Reuse the original field node as a template; we only swap the name.
  return {
    ...fieldNode,
    name: { ...fieldNode.name, value: snakeName },
    // GraphQL forbids duplicate field descriptions — drop them on the alias.
    description: undefined,
  };
}

/**
 * Augment a parsed SDL document: add snake_case alias fields to every input.
 *
 * Returns a new DocumentNode; the input is not mutated.
 */
function addSnakeAliases(documentNode) {
  const seenInType = new Set(); // defensive: never alias twice even on rerun

  const newDefinitions = documentNode.definitions.map((def) => {
    if (def.kind !== 'InputObjectTypeDefinition') return def;
    const typeName = def.name.value;
    const existingFieldNames = new Set(
      def.fields.map((f) => f.name.value),
    );

    const newFields = [];
    for (const field of def.fields) {
      newFields.push(field);
      const originalName = field.name.value;
      const snakeName = camelToSnake(originalName);
      if (snakeName === originalName) continue;          // already snake_case
      if (existingFieldNames.has(snakeName)) continue;    // already aliased
      const dedupeKey = `${typeName}.${snakeName}`;
      if (seenInType.has(dedupeKey)) continue;
      seenInType.add(dedupeKey);
      newFields.push(makeSnakeAliasField(field));
      existingFieldNames.add(snakeName);
    }

    return { ...def, fields: newFields };
  });

  return { ...documentNode, definitions: newDefinitions };
}

/**
 * Convenience: take an SDL string (possibly a JS template literal — leading
 * newline is preserved), parse, augment, and re-stringify.
 */
function transformSdl(sdlString) {
  const parsed = parse(sdlString);
  const augmented = addSnakeAliases(parsed);
  return print(augmented);
}

module.exports = {
  camelToSnake,
  addSnakeAliases,
  transformSdl,
};

// Allow `node add_snake_alias.js <file>` to dump the augmented SDL for
// inspection without invoking the full index.js stack.
if (require.main === module) {
  const fs = require('node:fs');
  const path = require('node:path');
  const file = process.argv[2];
  if (!file) {
    console.error('usage: node add_snake_alias.js <sdl-file>');
    process.exit(2);
  }
  const sdl = fs.readFileSync(path.resolve(file), 'utf8');
  process.stdout.write(transformSdl(sdl));
}
/**
 * Aggregate all domain resolvers into a single resolvers map
 * suitable for createYoga({ schema: { typeDefs, resolvers } }).
 *
 * Each domain module exports `{ Query, Mutation, Subscription? }`; we deep-merge them.
 * Only the GraphQL operation roots are surfaced — module-level helpers (e.g. `TOPIC`)
 * stay private.
 */

const ROOT_KEYS = new Set(['Query', 'Mutation', 'Subscription']);

function merge(...sources) {
  const out = {};
  for (const src of sources) {
    if (!src) continue;
    for (const rootKey of ROOT_KEYS) {
      const rootVal = src[rootKey];
      if (!rootVal) continue;
      out[rootKey] = { ...(out[rootKey] || {}), ...rootVal };
    }
  }
  return out;
}

const types = require('./types');
const entities = require('./entities');
const relations = require('./relations');
const core = require('./core');
const cos = require('./cos');
const commerce = require('./commerce');
const scene = require('./scene');
const skillEditor = require('./skill-editor');
const misc = require('./misc');
const legacy = require('./legacy');
const capabilities = require('./capabilities');
const jobs = require('./jobs');
const subscriptions = require('./subscriptions');
const publishers = require('./publishers');

module.exports = merge(
  types,
  entities,
  relations,
  core,
  cos,
  commerce,
  scene,
  skillEditor,
  misc,
  legacy,
  capabilities,
  jobs,
  subscriptions,
  publishers
);
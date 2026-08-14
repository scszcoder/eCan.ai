/**
 * COS file operation resolvers (AppSync-compatible entry point).
 */

const { executeFileOps } = require('../storage/cos-file-ops');

async function reqFileOp(_, { fo }, { identity }) {
  const result = await executeFileOps({ owner: identity.sub, operations: fo });
  // AWSJSON is serialized as a JSON string by AppSync; retain that contract.
  return JSON.stringify(result);
}

module.exports = { Query: { reqFileOp } };
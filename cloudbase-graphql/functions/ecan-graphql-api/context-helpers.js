/**
 * Helpers shared across resolvers that need to assert ownership before mutation.
 */

const { GraphQLError } = require('graphql');

async function assertOwnedAgent(prismaClient, identity, agentId) {
  const agent = await prismaClient.agent.findFirst({
    where: { id: agentId, owner: identity.sub },
    select: { id: true },
  });
  if (!agent) {
    throw new GraphQLError('Agent not found', { extensions: { code: 'FORBIDDEN' } });
  }
}

module.exports = { assertOwnedAgent };
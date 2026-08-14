/**
 * Intl-compat legacy resolvers (Query + Mutation):
 *   Account / Bot / Mission / Order CRUD via LegacyRecord.
 */

const { queryEntity, queryOrganizations, removeEntities, saveEntities } = require('../compat/cn-entities');
const { getWanMessages, mutateApiKeys, queryApiKeys, queryLegacy, removeLegacy, saveLegacy, sendWanMessage } = require('../compat/cn-legacy');

module.exports = {
  Query: {
    queryKnowledges: (_, args, context) => queryEntity(context.prisma, context.identity, 'Knowledge', args),
    getKnowledges: (_, args, context) => queryEntity(context.prisma, context.identity, 'Knowledge', args),
    queryAvatarResources: (_, args, context) => queryEntity(context.prisma, context.identity, 'AvatarResource', args),
    getAvatarResources: (_, args, context) => queryEntity(context.prisma, context.identity, 'AvatarResource', args),
    querySkills: (_, args, context) => queryEntity(context.prisma, context.identity, 'Skill', args),
    queryOrganizations: (_, args, context) => queryOrganizations(context.prisma, context.identity, args),
    getOrganizations: (_, args, context) => queryOrganizations(context.prisma, context.identity, args),
    getBots: (_, { ids }, context) => queryLegacy(context.prisma, context.identity, 'bot', {}, ids),
    queryBots: (_, { qb }, context) => queryLegacy(context.prisma, context.identity, 'bot', qb),
    getManagerMissions: (_, { qm }, context) => queryLegacy(context.prisma, context.identity, 'mission', qm),
    queryMissions: (_, { qm }, context) => queryLegacy(context.prisma, context.identity, 'mission', qm?.[0] || {}),
    reqAccountInfo: (_, { ops }, context) => queryLegacy(context.prisma, context.identity, 'account', ops?.[0] || {}),
    reqOrderInfo: (_, { ops }, context) => queryLegacy(context.prisma, context.identity, 'order', ops?.[0] || {}),
    getWanMessage: (_, { ids }, context) => getWanMessages(context.prisma, context.identity, ids),
    queryAPIKeys: (_, { keys }, context) => queryApiKeys(context.prisma, context.identity, keys),
  },
  Mutation: {
    addKnowledges: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'Knowledge', input),
    updateKnowledges: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'Knowledge', input, true),
    removeKnowledges: (_, { input }, context) => removeEntities(context.prisma, context.identity, 'Knowledge', input),
    addAvatarResources: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'AvatarResource', input),
    updateAvatarResources: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'AvatarResource', input, true),
    removeAvatarResources: (_, { input }, context) => removeEntities(context.prisma, context.identity, 'AvatarResource', input),
    addSkills: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'Skill', input),
    updateSkills: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'Skill', input, true),
    removeSkills: (_, { input }, context) => removeEntities(context.prisma, context.identity, 'Skill', input),

    addAccts: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'account', input),
    updateAccts: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'account', input),
    removeAccts: (_, { input }, context) => removeLegacy(context.prisma, context.identity, 'account', input),
    addBots: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'bot', input),
    updateBots: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'bot', input),
    removeBots: (_, { input }, context) => removeLegacy(context.prisma, context.identity, 'bot', input),
    addMissions: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'mission', input),
    updateMissions: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'mission', input),
    removeMissions: (_, { input }, context) => removeLegacy(context.prisma, context.identity, 'mission', input),
    updateMissionsExStatus: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'mission', input),
    reportStatus: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'mission', input),
    makeOrder: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'order', input),
    makeBusinessOrders: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'order', input),
    updateBusinessOrders: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'order', input),
    removeBusinessOrders: (_, { input }, context) => removeLegacy(context.prisma, context.identity, 'order', input),
    sendWanMessage: (_, { input }, context) => sendWanMessage(context.prisma, context.identity, input),
    reqApiKey: (_, { ops }, context) => mutateApiKeys(context.prisma, context.identity, ops),
  },
};
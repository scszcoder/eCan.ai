/**
 * Scene & Story resolvers (Query + Mutation).
 */

const { queryScenes, saveScene, deleteScene, querySceneTemplates, queryStories, saveStory, initReqScene, readyReqScene, getSceneRequestStatus, publishSceneResult } = require('../services/cn-scene');

module.exports = {
  Query: {
    getScene: async (_, { id }, context) => { const r = JSON.parse(await queryScenes(context.prisma, context.identity, { scene_id: id })); return r[0] || null; },
    getScenes: (_, { input }, context) => queryScenes(context.prisma, context.identity, input),
    queryScenes: (_, { input }, context) => queryScenes(context.prisma, context.identity, input),
    getSceneTemplates: async (_, { emotion, style }, context) => querySceneTemplates(context.prisma, context.identity, emotion, style),
    getStory: async (_, { id }, context) => { const r = JSON.parse(await queryStories(context.prisma, context.identity, null, 1)); return r.items.find((s) => s.id === id) || null; },
    getStories: async (_, { acctSiteID, limit, nextToken }, context) => JSON.parse(await queryStories(context.prisma, context.identity, acctSiteID, limit, nextToken)),
    listStories: async (_, { acctSiteID, limit, nextToken }, context) => JSON.parse(await queryStories(context.prisma, context.identity, acctSiteID, limit, nextToken)),
    getSceneRequestStatus: (_, { request_id }, context) => getSceneRequestStatus(context.prisma, context.identity, request_id),
  },
  Mutation: {
    reqScene: (_, { input }, context) => initReqScene(context.prisma, context.identity, input),
    initReqScene: (_, { input }, context) => initReqScene(context.prisma, context.identity, input),
    readyReqScene: (_, { input }, context) => readyReqScene(context.prisma, context.identity, input),
    updateScene: (_, { input }, context) => saveScene(context.prisma, context.identity, input),
    deleteScene: (_, { id }, context) => deleteScene(context.prisma, context.identity, { id }),
    updateStory: (_, { input }, context) => saveStory(context.prisma, context.identity, input),
    publishSceneResult: (_, { input }, context) => publishSceneResult(context.prisma, context.identity, input),
  },
};
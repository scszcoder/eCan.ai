/**
 * Skill Editor resolvers (Query + Mutation):
 *   file list / read / open / editor cache / scaffold / copy / breakpoints
 * plus the Skill Relations layer (compat/cn-relations).
 */

const {
  listSkillFiles, readSkillFile, openSkillFile, writeSkillFile,
  saveEditorCache, getEditorCache, clearEditorCache,
  setSkillBreakpoints, clearSkillBreakpoints,
  scaffoldSkill, copySkillTo,
} = require('../services/cn-skill-editor');
const { upsertRelations, removeRelations } = require('../compat/cn-relations');

module.exports = {
  Query: {
    listSkillFiles: (_, { prefix, limit, nextToken, userId }, context) =>
      listSkillFiles(context.prisma, context.identity, { prefix, limit, nextToken, userId }),
    readSkillFile: (_, { filePath, userId }, context) =>
      readSkillFile(context.prisma, context.identity, { filePath, userId }),
    openSkillFile: (_, { filePath, skillName, userId }, context) =>
      openSkillFile(context.prisma, context.identity, { filePath, skillName, userId }),
    getEditorCache: (_, { userId }, context) =>
      getEditorCache(context.prisma, context.identity, userId),
  },
  Mutation: {
    writeSkillFile: (_, { input }, context) => writeSkillFile(context.prisma, context.identity, input),
    saveEditorCache: (_, { input }, context) => saveEditorCache(context.prisma, context.identity, input),
    clearEditorCache: (_, { userId }, context) => clearEditorCache(context.prisma, context.identity, userId),
    scaffoldSkill: (_, { input }, context) => scaffoldSkill(context.prisma, context.identity, input),
    copySkillTo: (_, { input }, context) => copySkillTo(context.prisma, context.identity, input),
    setSkillBreakpoints: (_, { node_name, username }, context) =>
      setSkillBreakpoints(context.prisma, context.identity, node_name, username),
    clearSkillBreakpoints: (_, { node_name, username }, context) =>
      clearSkillBreakpoints(context.prisma, context.identity, node_name, username),

    addAgentSkillToolRels: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'SkillTool', input),
    updateAgentSkillToolRels: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'SkillTool', input),
    removeAgentSkillToolRels: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'SkillTool', input),
    addAgentSkillKnowledgeRels: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'SkillKnowledge', input),
    updateAgentSkillKnowledgeRels: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'SkillKnowledge', input),
    removeAgentSkillKnowledgeRels: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'SkillKnowledge', input),
    addAgentTaskSkillRels: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'TaskSkill', input),
    updateAgentTaskSkillRels: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'TaskSkill', input),
    removeAgentTaskSkillRels: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'TaskSkill', input),
  },
};
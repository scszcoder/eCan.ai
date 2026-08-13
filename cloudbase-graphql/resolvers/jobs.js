/**
 * Job resolvers (Mutation only):
 *   Training / Puzzle / External skill / Vehicle reporting.
 */

const { confirmPuzzle, dequeueTasks, reportExternalSkill, reportVehicles, requestExternalSkill, requestPuzzle, requestTraining } = require('../services/cn-jobs');

module.exports = {
  Mutation: {
    dequeueTasks: (_, { input }, context) => dequeueTasks(context.prisma, context.identity, input),
    reportVehicles: (_, { input }, context) => reportVehicles(context.prisma, context.identity, input),
    requestRunExtSkill: (_, { input }, context) => requestExternalSkill(context.prisma, context.identity, input),
    reportRunExtSkillStatus: (_, { input }, context) => reportExternalSkill(context.prisma, context.identity, input),
    reqTrain: (_, { input }, context) => requestTraining(context.prisma, context.identity, input),
    reqPuzzleSolver: (_, { input }, context) => requestPuzzle(context.prisma, context.identity, input),
    confirmPuzzleSolver: (_, { input }, context) => confirmPuzzle(context.prisma, context.identity, input),
  },
};
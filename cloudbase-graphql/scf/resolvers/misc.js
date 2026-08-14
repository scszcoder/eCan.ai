/**
 * Misc resolvers (Query + Mutation):
 *   RAG / FB / Chats / Schedules / RegSteps / Screen reads / Machine LAN /
 *   Cloud A2A / Puzzle / Skill run control / SOAP / SIM / Passive browser /
 *   Account notifications / Task status.
 */

const {
  queryRAGs, getFB, queryChats, genSchedules, regSteps,
  reqMachineLanAddr, reqScreenTxtRead, reqScreenIconRead,
  getNodeStateSchema, getNodesPrompts, checkSkillExists,
  sendCloudA2AMessage, getA2AMessages,
  sendPuzzleSolution, requestPuzzleSolve,
  runSkill, stepRunSkill, pauseRunSkill, resumeRunSkill, cancelRunSkill, getSkillRunStatus,
  runTest,
  startSoap, stopSoap,
  setupSimStep, stepSim, simSseEvent, simTimerEvent, simWebhookEvent, simWebsocketEvent,
  testLanggraph2Flowgram,
  publishPassiveCommand, publishPassiveHello, publishPassiveStepResult,
  publishAccountNotification,
  injectSkillState, requestSkillState, loadSkillSchemas, loadSkillEditorContexts,
} = require('../services/cn-misc');

module.exports = {
  Query: {
    queryAgentSkillToolRels: (_, { input }, context) =>
      require('../compat/cn-relations').queryRelation(context.prisma, context.identity, 'SkillTool', { qb: input }),
    queryAgentSkillKnowledgeRels: (_, { input }, context) =>
      require('../compat/cn-relations').queryRelation(context.prisma, context.identity, 'SkillKnowledge', { qb: input }),
    queryAgentTaskSkillRels: (_, { input }, context) =>
      require('../compat/cn-relations').queryRelation(context.prisma, context.identity, 'TaskSkill', { qb: input }),
    getNodeStateSchema: (_, {}, context) => getNodeStateSchema(context.prisma, context.identity),
    getNodesPrompts: (_, { nodes }, context) => getNodesPrompts(context.prisma, context.identity, nodes),
    checkSkillExists: (_, { name }, context) => checkSkillExists(context.prisma, context.identity, name),
    genSchedules: (_, { settings }, context) => genSchedules(context.prisma, context.identity, settings),
    getFB: (_, { fb_reqs }, context) => getFB(context.prisma, context.identity, fb_reqs),
    getA2AMessages: (_, { channelId, limit, nextToken }, context) =>
      getA2AMessages(context.prisma, context.identity, channelId, limit, nextToken),
    queryCloudTaskRunId: (_, { input }, context) =>
      require('../services/cn-scene').queryCloudTaskRunId(context.prisma, context.identity, input),
    queryExtBotSkillRun: (_, { qbsr }, context) =>
      require('../services/cn-scene').queryExtBotSkillRun(context.prisma, context.identity, qbsr),
    queryRAGs: (_, { qs }, context) => queryRAGs(context.prisma, context.identity, qs),
    queryChats: (_, { msgs }, context) => queryChats(context.prisma, context.identity, msgs),
    regSteps: (_, { inSteps }, context) => regSteps(context.prisma, context.identity, inSteps),
    reqMachineLanAddr: (_, { mid }, context) => reqMachineLanAddr(context.prisma, context.identity, mid),
    reqScreenTxtRead: (_, { inScrn }, context) => reqScreenTxtRead(context.prisma, context.identity, inScrn),
    reqScreenIconRead: (_, { inScrn }, context) => reqScreenIconRead(context.prisma, context.identity, inScrn),
    queryApiKeys: (_, { input }, context) =>
      require('../compat/cn-legacy').queryApiKeys(context.prisma, context.identity, input),
    loadSkillEditorContexts: (_, { input }, context) => loadSkillEditorContexts(context.prisma, context.identity, input),
    getSkillRunStatus: (_, { runId, since }, context) => getSkillRunStatus(context.prisma, context.identity, runId, since),
  },
  Mutation: {
    runSkill: (_, { input }, context) => runSkill(context.prisma, context.identity, input),
    stepRunSkill: (_, { input }, context) => stepRunSkill(context.prisma, context.identity, input),
    pauseRunSkill: (_, { input }, context) => pauseRunSkill(context.prisma, context.identity, input),
    resumeRunSkill: (_, { input }, context) => resumeRunSkill(context.prisma, context.identity, input),
    cancelRunSkill: (_, { input }, context) => cancelRunSkill(context.prisma, context.identity, input),
    runTest: (_, { input }, context) => runTest(context.prisma, context.identity, input),
    sendCloudA2AMessage: (_, { input }, context) => sendCloudA2AMessage(context.prisma, context.identity, input),
    requestPuzzleSolve: (_, { input }, context) => requestPuzzleSolve(context.prisma, context.identity, input),
    sendPuzzleSolution: (_, { input }, context) => sendPuzzleSolution(context.prisma, context.identity, input),
    injectSkillState: (_, { skill, username }, context) => injectSkillState(context.prisma, context.identity, skill, username),
    loadSkillSchemas: (_, { skill, username }, context) => loadSkillSchemas(context.prisma, context.identity, skill, username),
    requestSkillState: (_, { skill, username }, context) => requestSkillState(context.prisma, context.identity, skill, username),
    startSoap: (_, { input }, context) => startSoap(context.prisma, context.identity, input),
    stopSoap: (_, { soap_id }, context) => stopSoap(context.prisma, context.identity, soap_id),
    setupSimStep: (_, { bundle }, context) => setupSimStep(context.prisma, context.identity, bundle),
    stepSim: (_, {}, context) => stepSim(context.prisma, context.identity),
    simSseEvent: (_, {}, context) => simSseEvent(context.prisma, context.identity),
    simTimerEvent: (_, {}, context) => simTimerEvent(context.prisma, context.identity),
    simWebhookEvent: (_, {}, context) => simWebhookEvent(context.prisma, context.identity),
    simWebsocketEvent: (_, {}, context) => simWebsocketEvent(context.prisma, context.identity),
    testLanggraph2Flowgram: (_, {}, context) => testLanggraph2Flowgram(context.prisma, context.identity),
    publishPassiveCommand: (_, { input }, context) => publishPassiveCommand(context.prisma, context.identity, input),
    publishPassiveHello: (_, { input }, context) => publishPassiveHello(context.prisma, context.identity, input),
    publishPassiveStepResult: (_, { input }, context) => publishPassiveStepResult(context.prisma, context.identity, input),
    publishAccountNotification: (_, { input }, context) => publishAccountNotification(context.prisma, context.identity, input),
    publishTaskStatus: (_, { input }, context) =>
      require('../services/cn-scene').publishTaskStatus(context.prisma, context.identity, input),
  },
};
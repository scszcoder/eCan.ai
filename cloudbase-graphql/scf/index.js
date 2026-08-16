/**
 * eCan.ai CN 版本后端
 * GraphQL Yoga + Prisma + PostgreSQL (JSONB)
 *
 * 部署到腾讯云 SCF (Serverless Cloud Function)
 *
 * 架构：
 *   App/前端 → HTTP → 云函数 → PostgreSQL (JSONB)
 *
 * 本地开发：
 *   - 本地不需要直连数据库
 *   - 直接调用已部署的云函数 API
 *   - 或使用 curl/Postman 测试 API
 */

const { createYoga, createSchema } = require('graphql-yoga');
const { TencentScheduler } = require('./scheduler/tencent-scheduler');
const { directTestHeaders, DIRECT_TEST_MODE, HTTP_TEST_MODE, resolveIdentity } = require('./auth');
const { getPrisma, ensureConnected } = require('./tcb-init');
const { attachWsBridge } = require('./services/ws-bridge-push');
const resolvers = require('./resolvers');
const { transformSdl } = require('./add_snake_alias');

// Cross-instance WS push: every event-bus.publish() is forwarded to the
// independent `ecan-graphql-ws` function so clients connected to a *different*
// SCF instance also receive the event. attachBridge is a no-op when secret
// is missing (local dev).
attachWsBridge();

let scheduler;
function getScheduler() {
  if (!scheduler) scheduler = new TencentScheduler();
  return scheduler;
}

// ============ GraphQL Schema (TypeScript-like SDL) ============

const typeDefs = `
scalar JSON

type Query {
  # Agents
  getAgents(input: AgentQueryInput): [Agent!]!
  queryAgents(input: AgentQueryInput): [Agent!]!
  
  # Skills
  getAgentSkills(input: SkillQueryInput): [AgentSkill!]!
  queryAgentSkills(input: SkillQueryInput): [AgentSkill!]!
  searchSkills(input: SkillSearchInput!): [AgentSkill!]!
  getSkillRatings(skillId: ID!, limit: Int, offset: Int): [SkillRating!]!
  listSkillOrders(input: SkillListOrdersInput!): [SkillOrder!]!
  
  # Tasks
  getAgentTasks(input: TaskQueryInput): [AgentTask!]!
  queryAgentTasks(input: TaskQueryInput): [AgentTask!]!
  
  # Vehicles
  getVehicles(input: VehicleQueryInput): [Vehicle!]!
  queryVehicles(input: VehicleQueryInput): [Vehicle!]!
  
  # Orgs
  getOrgs(input: OrgQueryInput): [Org!]!
  queryOrgs(input: OrgQueryInput): [Org!]!
  getOrgTree(rootId: ID): OrgTree
  getOrgAgentTree(rootId: ID): OrgTree
  
  # Prompts
  getPrompts(owner: String): [Prompt!]!
  queryPrompts(input: PromptQueryInput): [Prompt!]!
  
  # Avatars
  getAvatars(owner: String, resourceType: String): [Avatar!]!
  queryAvatars(input: AvatarQueryInput): [Avatar!]!
  
  # Knowledges
  getAgentKnowledges(owner: String, name: String): [AgentKnowledge!]!
  queryAgentKnowledges(input: KnowledgeQueryInput): [AgentKnowledge!]!
  
  # Tools
  getAgentTools(owner: String, name: String): [AgentTool!]!
  queryAgentTools(input: ToolQueryInput): [AgentTool!]!
  
  # Settings
  getSettings(ids: [ID!], username: String): [Setting!]!
  
  # Skill Editor Events
  getSkillEditorEvents(sessionId: String, since: String): [SkillEditorEvent!]!
  
  # getAllMine
  getAllMine(owner: String): GetAllMineResponse!

  # COS file operations (AppSync compatibility)
  reqFileOp(fo: [FileOp!]): JSON!
  
  # Relations
  queryAgentSkillRels(input: JSON): [AgentSkillRel!]!
  queryAgentTaskRels(input: JSON): [AgentTaskRel!]!
  queryAgentOrgRels(input: JSON): [AgentOrgRel!]!
  queryAgentSkillRelations(qb: String): JSON
  getAgentSkillRelations(ids: String): JSON
  queryAgentTaskRelations(qb: String): JSON
  getAgentTaskRelations(ids: String): JSON
  queryAgentToolRelations(qb: String): JSON
  getAgentToolRelations(ids: String): JSON
  querySkillToolRelations(qb: String): JSON
  getSkillToolRelations(ids: String): JSON
  querySkillKnowledgeRelations(qb: String): JSON
  getSkillKnowledgeRelations(ids: String): JSON
  queryTaskSkillRelations(qb: String): JSON
  getTaskSkillRelations(ids: String): JSON
  queryKnowledges(qb: String): JSON
  getKnowledges(ids: String): JSON
  queryAvatarResources(qb: String): JSON
  getAvatarResources(ids: String): JSON
  queryOrganizations(qb: String): JSON
  getOrganizations(ids: String): JSON
  querySkills(qs: JSON!): JSON!
  queryAgentEndpoints(org: String!, limit: Int, offset: Int): [AgentEndpoint]!
  getLongLLMTask(id: ID!): JSON!
  getSkillEditorChatSessions(userId: ID!): [SkillEditorChatSession]
  getSkillEditorChatHistory(sessionId: ID!, limit: Int, offset: Int): [SkillEditorChatMessage]
  getBots(ids: [ID!]): JSON!
  queryBots(qb: JSON!): JSON!
  getManagerMissions(qm: JSON!): JSON!
  queryMissions(qm: [MissionIdentifiers]!): JSON!
  reqAccountInfo(ops: [AcctOp!]): JSON!
  reqOrderInfo(ops: [OrderOp!]): JSON!
  getWanMessage(ids: [ID!]): [WanChatMessage]!
  queryAPIKeys(keys: [KeyInfo]!): JSON
  # Commerce
  getProducts(input: ProductQueryInput): [Product!]!
  queryProducts(input: ProductQueryInput): [Product!]!
  getWarehouses(input: WarehouseQueryInput): [Warehouse!]!
  queryWarehouses(input: WarehouseQueryInput): [Warehouse!]!
  getLabelFormats(input: LabelFormatQueryInput): [LabelFormat!]!
  queryLabelFormats(input: LabelFormatQueryInput): [LabelFormat!]!
  # Scene & Story
  getScene(id: ID!): Scene
  getScenes(input: JSON!): JSON!
  queryScenes(input: SceneQueryInput!): SceneConnection!
  getSceneTemplates(emotion: String, style: SceneStyle): [SceneTemplate!]!
  getSceneRequestStatus(request_id: ID!): ReqSceneResponse!
  getStory(id: ID!): Story
  getStories(acctSiteID: String, limit: Int, nextToken: String): StoryConnection!
  listStories(acctSiteID: String, limit: Int, nextToken: String): StoryConnection!
  # Skill Editor
  listSkillFiles(prefix: String, limit: Int, nextToken: String, userId: String): [SkillFileInfo!]!
  readSkillFile(filePath: String!, userId: String): [SkillFileContent]
  openSkillFile(filePath: String!, skillName: String, userId: String): SkillFileContent
  getEditorCache(userId: ID!): EditorCacheResponse
  # Misc
  queryAgentSkillToolRels(input: JSON): JSON!
  queryAgentSkillKnowledgeRels(input: JSON): JSON!
  queryAgentTaskSkillRels(input: JSON): JSON!
  getNodeStateSchema: NodeStateSchema!
  getNodesPrompts(nodes: [Node!]!): JSON!
  checkSkillExists(name: String!): CheckResult!
  genSchedules(settings: JSON!): JSON!
  getFB(fb_reqs: [FbReq!]!): JSON
  getA2AMessages(channelId: String!, limit: Int, nextToken: String): A2AMessageConnection!
  queryCloudTaskRunId(input: TaskRunQueryInput!): TaskStatus!
  queryExtBotSkillRun(qbsr: [SkillRunConfig!]): JSON!
  queryRAGs(qs: JSON!): JSON!
  queryChats(msgs: [ChatReq!]!): JSON
  regSteps(inSteps: [Step!]!): JSON!
  reqMachineLanAddr(mid: String): JSON!
  reqScreenTxtRead(inScrn: [ScreenImg!]!): JSON!
  reqScreenIconRead(inScrn: [ScreenImg!]!): [ScreenInfo]
  queryApiKeys(input: QueryApiKeyInput): QueryApiKeysResponse!
  loadSkillEditorContexts(input: SkillEditorContextRequestInput!): SkillEditorContextResponse!
  getSkillRunStatus(runId: ID!, since: String): [SkillRunEvent!]!
}

type Mutation {
  # Agents
  addAgents(input: [AgentInput!]!): [AgentMutationResult!]!
  updateAgents(input: [AgentUpdateInput!]!): [AgentMutationResult!]!
  removeAgents(ids: [ID!]!): [AgentMutationResult!]!
  
  # Skills
  addAgentSkills(input: [SkillInput!]!): [SkillMutationResult!]!
  updateAgentSkills(input: [SkillUpdateInput!]!): [SkillMutationResult!]!
  removeAgentSkills(ids: [ID!]!): [SkillMutationResult!]!

  # Skill marketplace
  rateSkill(input: RateSkillInput!): SkillRating!
  recordSkillInstall(input: RecordSkillInstallInput!): SkillInstall!
  removeSkillInstall(skillId: ID!): Boolean!
  createSkillOrder(input: CreateSkillOrderInput!): SkillOrder!
  updateSkillOrderStatus(input: UpdateSkillOrderStatusInput!): SkillOrder!
  
  # Tasks
  addAgentTasks(input: [TaskInput!]!): [TaskMutationResult!]!
  updateAgentTasks(input: [TaskUpdateInput!]!): [TaskMutationResult!]!
  removeAgentTasks(ids: [ID!]!): [TaskMutationResult!]!
  
  # Vehicles
  addVehicles(input: [VehicleInput!]!): [VehicleMutationResult!]!
  updateVehicles(input: [VehicleUpdateInput!]!): [VehicleMutationResult!]!
  removeVehicles(ids: [ID!]!): [VehicleMutationResult!]!
  
  # Orgs
  addOrgs(input: [OrgInput!]!): [OrgMutationResult!]!
  updateOrgs(input: [OrgUpdateInput!]!): [OrgMutationResult!]!
  removeOrgs(ids: [ID!]!): [OrgMutationResult!]!
  
  # Prompts
  addPrompts(input: [PromptInput!]!): [PromptMutationResult!]!
  updatePrompts(input: [PromptUpdateInput!]!): [PromptMutationResult!]!
  removePrompts(ids: [ID!]!): [PromptMutationResult!]!
  
  # Avatars
  addAvatars(input: [AvatarInput!]!): [AvatarMutationResult!]!
  updateAvatars(input: [AvatarUpdateInput!]!): [AvatarMutationResult!]!
  removeAvatars(ids: [ID!]!): [AvatarMutationResult!]!
  
  # Knowledges
  addAgentKnowledges(input: [KnowledgeInput!]!): [KnowledgeMutationResult!]!
  updateAgentKnowledges(input: [KnowledgeUpdateInput!]!): [KnowledgeMutationResult!]!
  removeAgentKnowledges(ids: [ID!]!): [KnowledgeMutationResult!]!
  
  # Tools
  addAgentTools(input: [ToolInput!]!): [ToolMutationResult!]!
  updateAgentTools(input: [ToolUpdateInput!]!): [ToolMutationResult!]!
  removeAgentTools(ids: [ID!]!): [ToolMutationResult!]!

  # WeChat silent refresh
  registerWeChatSession(input: RegisterWeChatSessionInput!): RegisterWeChatSessionResult!
  refreshWeChatToken(input: RefreshWeChatTokenInput!): RefreshWeChatTokenResult!
  
  # Settings
  updateSettings(input: [JSON!]!): String!
  
  # Skill Editor Events
  addSkillEditorEvent(input: SkillEditorEventInput!): SkillEditorEvent!
  runCloudTasks(input: [CloudTaskInput!]!): JSON!
  
  # Relations
  addAgentSkillRels(input: [JSON!]!): JSON!
  updateAgentSkillRels(input: [JSON!]!): JSON!
  removeAgentSkillRels(input: [JSON!]!): JSON!
  
  addAgentTaskRels(input: [JSON!]!): JSON!
  updateAgentTaskRels(input: [JSON!]!): JSON!
  removeAgentTaskRels(input: [JSON!]!): JSON!
  
  addAgentOrgRels(input: [JSON!]!): JSON!
  updateAgentOrgRels(input: [JSON!]!): JSON!
  removeAgentOrgRels(input: [JSON!]!): JSON!

  addAgentSkillRelations(input: [AgentSkillRelation]!): JSON
  updateAgentSkillRelations(input: [AgentSkillRelation]!): JSON
  removeAgentSkillRelations(input: [RemoveOrder]!): JSON
  addAgentTaskRelations(input: [AgentTaskRelation]!): JSON
  updateAgentTaskRelations(input: [AgentTaskRelation]!): JSON
  removeAgentTaskRelations(input: [RemoveOrder]!): JSON
  addAgentToolRelations(input: [AgentToolRelation]!): JSON
  updateAgentToolRelations(input: [AgentToolRelation]!): JSON
  removeAgentToolRelations(input: [RemoveOrder]!): JSON
  addSkillToolRelations(input: [SkillToolRelation]!): JSON
  updateSkillToolRelations(input: [SkillToolRelation]!): JSON
  removeSkillToolRelations(input: [RemoveOrder]!): JSON
  addSkillKnowledgeRelations(input: [SkillKnowledgeRelation]!): JSON
  updateSkillKnowledgeRelations(input: [SkillKnowledgeRelation]!): JSON
  removeSkillKnowledgeRelations(input: [RemoveOrder]!): JSON
  addTaskSkillRelations(input: [TaskSkillRelation]!): JSON
  updateTaskSkillRelations(input: [TaskSkillRelation]!): JSON
  removeTaskSkillRelations(input: [RemoveOrder]!): JSON
  addKnowledges(input: [Knowledge]!): JSON
  updateKnowledges(input: [Knowledge]!): JSON
  removeKnowledges(input: [RemoveOrder]!): JSON
  addAvatarResources(input: [AvatarResource]!): JSON
  updateAvatarResources(input: [AvatarResource]!): JSON
  removeAvatarResources(input: [RemoveOrder]!): JSON
  addSkills(input: [Skill]!): JSON!
  updateSkills(input: [Skill]!): JSON!
  removeSkills(input: [RemoveOrder]!): JSON!
  upsertAgentEndpoint(input: AgentEndpointInput!): AgentEndpoint
  deleteAgentEndpoint(id: ID!): AgentEndpoint
  sendA2AMessage(input: A2AMessageInput!): A2AMessage
  reqRAGStore(input: [RAGIN]!): JSON!
  startLongLLMTask(task_input: JSON!): JSON!
  endLongLLMTask(input: LongLLMTaskResultInput!): LongLLMTaskResult!
  createSkillEditorChatSession(input: SkillEditorChatSessionInput!): SkillEditorChatSession
  sendSkillEditorChatMessage(input: SkillEditorChatMessageInput!): SkillEditorChatMessageResponse
  cancelSkillEditorChatGeneration(sessionId: ID!): Boolean
  deleteSkillEditorChatSession(sessionId: ID!): Boolean
  publishSkillEditorStreamEvent(input: SkillEditorStreamEventInput!): SkillEditorEvent
  addAccts(input: [Account]!): JSON!
  updateAccts(input: [Account]!): JSON!
  removeAccts(input: [RemoveOrder]!): JSON!
  addBots(input: [Bot]!): JSON!
  updateBots(input: [Bot]!): JSON!
  removeBots(input: [RemoveOrder]!): JSON!
  addMissions(input: [Mission]!, settings: JSON!): JSON!
  updateMissions(input: [Mission]!): JSON!
  removeMissions(input: [RemoveOrder]!): JSON!
  updateMissionsExStatus(input: [SimpleMissionStatus]!): JSON!
  reportStatus(input: [MissionStatus]!): JSON!
  makeOrder(input: [Order]!): JSON!
  makeBusinessOrders(input: [Order]!): JSON!
  updateBusinessOrders(input: [Order]!): JSON!
  removeBusinessOrders(input: [RemoveBusinessOrder]!): JSON!
  sendWanMessage(input: WanChatMessageInput): WanChatMessage
  reqApiKey(ops: [KeyOp]!): JSON!
  dequeueTasks(input: [TaskOrder]!): JSON!
  reportVehicles(input: [VehicleInfo]!): JSON
  requestRunExtSkill(input: [SkillRun]): JSON!
  reportRunExtSkillStatus(input: [SkillRunStatus]): JSON!
  reqTrain(input: [Skill]!): JSON!
  reqPuzzleSolver(input: [PuzzleInput]!): Puzzle!
  confirmPuzzleSolver(input: [PuzzleResultInput]!): PuzzleResult!
  # Commerce
  addProducts(input: [ProductInput!]!): [Product!]!
  updateProducts(input: [ProductUpdateInput!]!): [Product!]!
  removeProducts(ids: [ID!]!): [MutationResult!]!
  addWarehouses(input: [WarehouseInput!]!): [Warehouse!]!
  updateWarehouses(input: [WarehouseUpdateInput!]!): [Warehouse!]!
  removeWarehouses(ids: [ID!]!): [MutationResult!]!
  addLabelFormats(input: [LabelFormatInput!]!): [LabelFormat!]!
  updateLabelFormats(input: [LabelFormatUpdateInput!]!): [LabelFormat!]!
  removeLabelFormats(ids: [ID!]!): [MutationResult!]!
  # Scene & Story
  reqScene(input: ReqSceneInput!): ReqSceneResponse!
  initReqScene(input: ReqSceneInput!): ReqSceneResponse!
  readyReqScene(input: ReadyReqSceneInput!): ReqSceneResponse!
  updateScene(input: SceneInput!): Scene
  deleteScene(id: ID!): Boolean!
  updateStory(input: StoryUpdateInput!): Story!
  publishSceneResult(input: SceneResultInput!): SceneResult!
  # Skill Editor
  writeSkillFile(input: [SkillFileInput!]): [SkillFileInfo]
  saveEditorCache(input: EditorCacheInput!): EditorCacheSaveResult
  clearEditorCache(userId: ID!): Boolean!
  scaffoldSkill(input: SkillScaffoldInput!): SkillScaffoldResult!
  copySkillTo(input: SkillCopyInput!): SkillCopyResult!
  setSkillBreakpoints(node_name: String!, username: String!): ActionResult!
  clearSkillBreakpoints(node_name: String!, username: String!): ActionResult!
  # Skill Relations
  addAgentSkillToolRels(input: [SkillToolRelation!]!): JSON!
  updateAgentSkillToolRels(input: [SkillToolRelation!]!): JSON!
  removeAgentSkillToolRels(input: [RelationIdInput!]!): JSON!
  addAgentSkillKnowledgeRels(input: [SkillKnowledgeRelation!]!): JSON!
  updateAgentSkillKnowledgeRels(input: [SkillKnowledgeRelation!]!): JSON!
  removeAgentSkillKnowledgeRels(input: [RelationIdInput!]!): JSON!
  addAgentTaskSkillRels(input: [TaskSkillRelation!]!): JSON!
  updateAgentTaskSkillRels(input: [TaskSkillRelation!]!): JSON!
  removeAgentTaskSkillRels(input: [RelationIdInput!]!): JSON!
  # Misc
  # Skill Run
  runSkill(input: RunSkillInput!): RunControlResult!
  stepRunSkill(input: RunControlInput!): RunControlResult!
  pauseRunSkill(input: RunControlInput!): RunControlResult!
  resumeRunSkill(input: RunControlInput!): RunControlResult!
  cancelRunSkill(input: RunControlInput!): RunControlResult!
  runTest(input: [TestInput!]!): JSON!
  sendCloudA2AMessage(input: A2AMessageInput!): A2AMessage!
  requestPuzzleSolve(input: [PuzzleInput]!): Puzzle!
  sendPuzzleSolution(input: PuzzleSolutionInput): PuzzleSolution
  injectSkillState(skill: JSON!, username: String!): ActionResult!
  loadSkillSchemas(skill: JSON!, username: String!): ActionResult!
  requestSkillState(skill: JSON!, username: String!): ActionResult!
  startSoap(input: StartSoapInput!): StartSoapResponse!
  stopSoap(soap_id: ID!): Boolean!
  setupSimStep(bundle: JSON!): RunControlResult!
  stepSim: RunControlResult!
  simSseEvent: RunControlResult!
  simTimerEvent: RunControlResult!
  simWebhookEvent: RunControlResult!
  simWebsocketEvent: RunControlResult!
  testLanggraph2Flowgram: RunControlResult!
  publishPassiveCommand(input: PassiveBrowserCommandEnvelopeInput!): PassiveBrowserCommandEnvelope!
  publishPassiveHello(input: PassiveBrowserHelloEnvelopeInput!): PassiveBrowserHelloEnvelope!
  publishPassiveStepResult(input: PassiveBrowserStepResultEnvelopeInput!): PassiveBrowserStepResultEnvelope!
  publishAccountNotification(input: AccountNotificationInput!): AccountNotification!
  publishTaskStatus(input: TaskStatusInput!): TaskStatus!

  # ===== P2.8: subscriptions that did not yet have a publish-side trigger =====
  # Each of the following mutations routes through the in-process event-bus to
  # the matching subscription. They do not write to the database — they exist
  # so that upstream services (or peers in another SCF instance) can deliver
  # synthesized events into the subscription stream.
  publishPuzzle(input: PuzzleInput!): Puzzle!
  publishPuzzleResult(input: PuzzleResultInput!): PuzzleResult!
  publishLongLLMTaskComplete(input: LongLLMTaskResultInput!): LongLLMTaskResult!
  publishStoryUpdate(input: StoryUpdateInput!): Story!
  publishSceneComplete(input: SceneResultInput!): SceneResult!
  publishAgentSceneEvent(input: SceneResultInput!): SceneResult!
}

# ============ Types ============

type Agent {
  id: ID!
  owner: String!
  name: String!
  description: String
  gender: String
  birthday: String
  avatarResourceId: String
  capabilities: JSON
  personalities: JSON
  rank: String
  status: String
  title: JSON
  supervisorId: String
  vehicleId: String
  url: String
  version: String
  orgId: String
  orgIds: JSON
  skills: JSON
  tasks: JSON
  extraData: JSON
  createdAt: String
  updatedAt: String
}

type AgentSkill {
  id: ID!
  owner: String!
  name: String!
  description: String
  category: String
  tags: JSON
  config: JSON
  capabilities: JSON
  limitations: JSON
  examples: JSON
  diagram: JSON
  inputModes: JSON
  outputModes: JSON
  askid: Int
  apps: JSON
  level: String
  price: Int
  priceModel: String
  source: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
  # Marketplace aggregates (added 2026-08-07).
  rating: Float
  ratingCount: Int
  installCount: Int
  publishedAt: String
  createdAt: String
  updatedAt: String
}

type AgentTask {
  id: ID!
  owner: String!
  name: String!
  description: String
  status: String
  priority: String
  taskType: String
  triggerType: String
  action: String
  duration: Int
  orgId: String
  objectives: JSON
  result: JSON
  schedule: JSON
  errorMessage: String
  metadata: JSON
  source: String
  createdAt: String
  updatedAt: String
}

type Vehicle {
  id: ID!
  owner: String!
  name: String!
  description: String
  vehicleType: String
  platform: String
  architecture: String
  environment: String
  status: String
  url: String
  hostname: String
  ipAddress: String
  port: Int
  accessToken: String
  sslEnabled: Boolean
  securityLevel: String
  location: String
  timezone: String
  capabilities: JSON
  limitations: JSON
  settings: JSON
  extraMetadata: JSON
  gpuInfo: JSON
  cpuCores: Int
  memoryGb: Float
  storageGb: Float
  maxConcurrentTasks: Int
  healthScore: Float
  uptimeSeconds: Float
  lastHeartbeat: String
  createdAt: String
  updatedAt: String
}

type Org {
  id: ID!
  name: String!
  description: String
  orgType: String
  parentId: String
  level: Int
  sortOrder: Int
  status: String
  settings: JSON
}

type OrgTree {
  id: ID!
  name: String!
  description: String
  orgType: String
  level: Int
  parentId: String
  sortOrder: Int
  status: String
  settings: JSON
  children: [OrgTree!]
  agents: [Agent!]
}

type Prompt {
  id: ID!
  owner: String!
  prompt: JSON!
  version: String
  createdAt: String
  updatedAt: String
}

type Avatar {
  id: ID!
  owner: String
  name: String
  description: String
  resourceType: String!
  imagePath: String
  videoPath: String
  imageHash: String
  videoHash: String
  cloudImageKey: String
  cloudVideoKey: String
  cloudImageUrl: String
  cloudVideoUrl: String
  cloudSynced: Boolean
  avatarMetadata: JSON
  isPublic: Boolean
  usageCount: Int
  lastUsedAt: String
  createdAt: String
  updatedAt: String
}

type AgentKnowledge {
  id: ID!
  owner: String!
  name: String!
  description: String
  content: String
  knowledgeType: String
  categories: JSON
  tags: JSON
  accessMethods: JSON
  limitations: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  settings: JSON
  config: JSON
  version: String
  createdAt: String
  updatedAt: String
}

type AgentTool {
  id: ID!
  owner: String!
  name: String!
  description: String
  toolType: String
  capabilities: JSON
  limitations: JSON
  dependencies: JSON
  settings: JSON
  config: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
  createdAt: String
  updatedAt: String
}

type Setting {
  id: ID!
  key: String!
  value: JSON!
  owner: String
}

type SkillEditorEvent {
  eventId: ID!
  owner: String!
  sessionId: String!
  flowgramId: String
  eventType: String!
  payload: JSON!
  timestamp: String!
}

type AgentEndpoint {
  id: ID!
  machineId: String!
  org: String!
  name: String
  role: String
  skills: String
  skillsHash: String
  a2aRelayChannel: String!
  lanHint: String
  ecanVer: String
  os: String
  lastSeen: String
  ttl: Int
}

type A2AMessage {
  id: ID!
  toAgentId: String!
  fromAgentId: String!
  org: String!
  payload: JSON!
  timestamp: String!
}

type LongLLMTaskResult {
  id: ID!
  acctSiteID: String
  agentID: String
  workType: String
  taskID: String
  status: String
  results: String
  timestamp: String
}

type SkillEditorChatSession {
  id: ID!
  name: String!
  flowgramId: ID
  createdAt: String!
  updatedAt: String!
}

type SkillEditorChatMessage {
  id: ID!
  role: String!
  content: String!
  timestamp: String!
  attachments: JSON
  metadata: JSON
}

type SkillEditorChatMessageResponse {
  sessionId: ID!
  sessionName: String!
  state: String!
  intent: String
  message: SkillEditorChatMessage!
  clarification: JSON
  plan: JSON
  flowgram: JSON
  validation: JSON
}

type MutationResult {
  id: ID
  success: Boolean!
  error: String
}

type WanChatMessage {
  id: ID
  chatID: String
  sender: String
  receiver: String
  type: String
  contents: String
  parameters: String
  msg: String
  options: JSON
  background: String
  timestamp: String
}

type Puzzle { pzid: ID!, request_id: String, type: String, puzzle_file: String, question: String, url: String, url_key: String, prize: Int, time_limit: Int, module: String, options: String }
type PuzzleResult { pzid: ID!, request_id: String, type: String, solver: String, result: String }

# Relations
type AgentSkillRel {
  id: ID!
  agentId: String!
  skillId: String!
  proficiencyLevel: Int
  experiencePoints: Int
  certificationLevel: Int
  usageCount: Int
  successRate: Float
  lastUsed: String
  status: String
  isFavorite: Boolean
  priority: Int
  config: JSON
}

type AgentTaskRel {
  id: ID!
  agentId: String!
  taskId: String!
  vehicleId: String
  status: String
  priority: Int
  progress: Float
  scheduledStart: String
  actualStart: String
  estimatedEnd: String
  actualEnd: String
  result: JSON
  errorMessage: String
  logs: String
  cpuUsage: Float
  memoryUsage: Float
  executionTime: Float
  executionContext: JSON
  retryCount: Int
  maxRetries: Int
}

type AgentOrgRel {
  id: ID!
  agentId: String!
  orgId: String!
  role: String
  accessLevel: String
  status: String
  permissions: JSON
  joinDate: String
  leaveDate: String
}

# Responses
type AgentMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type SkillMutationResult {
  id: ID
  success: Boolean!
  error: String
}

# Marketplace aggregates back onto AgentSkill (these fields are projected onto
# the underlying Prisma AgentSkill model).
# SkillRating: one row per (user, skill).
type SkillRating {
  id: ID!
  userId: String!
  skillId: String!
  score: Int!
  comment: String
  createdAt: String!
  updatedAt: String!
}

type SkillInstall {
  id: ID!
  userId: String!
  skillId: String!
  agentId: ID
  status: String!
  createdAt: String!
}

type SkillOrder {
  id: ID!
  buyerId: String!
  sellerId: String!
  skillId: String!
  priceCents: Int!
  priceModel: String
  status: String!
  metadata: JSON!
  createdAt: String!
  updatedAt: String!
}

type TaskMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type VehicleMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type OrgMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type PromptMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type AvatarMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type KnowledgeMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type ToolMutationResult {
  id: ID
  success: Boolean!
  error: String
}

# ============ WeChat Silent Refresh ============

# Input for registering a WeChat session on first login.
input RegisterWeChatSessionInput {
  # Current CloudBase access_token (JWT). Used to extract the openid via
  # CloudBase /auth/v1/user/me; NOT stored directly after minting the session token.
  wxAccessToken: String!
}

# Result of registering a WeChat session.
type RegisterWeChatSessionResult {
  # The custom session token (eCan refresh JWT). Store this and replay it on startup.
  sessionToken: String!
  # Seconds until the session token expires (30 days default).
  expiresIn: Int!
}

# Input for refreshing a WeChat session.
input RefreshWeChatTokenInput {
  # The custom session token obtained from registerWeChatSession.
  sessionToken: String!
}

# Result of refreshing a WeChat token.
type RefreshWeChatTokenResult {
  # A fresh CloudBase access_token (JWT). Store this in AuthManager.
  accessToken: String!
  # Seconds until this access_token expires (~10 minutes for WeChat).
  expiresIn: Int!
}

type GetAllMineResponse {
  acctInfo: JSON
  ordersInfo: [JSON!]!
  agents: [Agent!]!
  skills: [AgentSkill!]!
  tasks: [AgentTask!]!
  vehicles: [Vehicle!]!
  orgs: [Org!]!
  prompts: [Prompt!]!
  avatars: [Avatar!]!
  knowledges: [AgentKnowledge!]!
  tools: [AgentTool!]!
  settings: JSON
}

# Inputs
input AgentQueryInput {
  id: ID
  owner: String
  name: String
  status: String
}

input AgentInput {
  id: ID
  owner: String
  name: String!
  description: String
  gender: String
  birthday: String
  avatarResourceId: String
  capabilities: JSON
  personalities: JSON
  rank: String
  status: String
  title: JSON
  supervisorId: String
  vehicleId: String
  url: String
  version: String
  orgId: String
  orgIds: JSON
  skills: JSON
  tasks: JSON
  extraData: JSON
}

input AgentUpdateInput {
  id: ID!
  name: String
  description: String
  gender: String
  birthday: String
  avatarResourceId: String
  capabilities: JSON
  personalities: JSON
  rank: String
  status: String
  title: JSON
  supervisorId: String
  vehicleId: String
  url: String
  version: String
  orgId: String
  orgIds: JSON
  skills: JSON
  tasks: JSON
  extraData: JSON
}

input SkillQueryInput {
  id: ID
  owner: String
  name: String
  category: String
  # Public catalog mode. When true, returns skills where isPublic = true and
  # does not require an authenticated identity. Default is false (private).
  isPublic: Boolean
  # Tag filter. Default match mode is "any" (matches skills whose tags array
  # contains at least one of the supplied tags). Pass "all" to require every
  # tag.
  tags: [String!]
  tagMode: String
  limit: Int
  nextToken: String
  orderBy: String
}

input SkillSearchInput {
  q: String
  category: String
  tags: [String!]
  minRating: Float
  limit: Int
  offset: Int
}

input RateSkillInput {
  skillId: ID!
  score: Int!
  comment: String
}

input RecordSkillInstallInput {
  skillId: ID!
  agentId: ID
}

input CreateSkillOrderInput {
  skillId: ID!
  agentId: ID
  quantity: Int
}

input UpdateSkillOrderStatusInput {
  orderId: ID!
  status: String!
  metadata: JSON
}

input SkillListOrdersInput {
  role: String # "buyer" | "seller" | "skill" — defaults to buyer when omitted
  skillId: ID
  status: String
  limit: Int
  offset: Int
}

input SkillInput {
  id: ID
  owner: String
  name: String!
  description: String
  category: String
  tags: JSON
  config: JSON
  capabilities: JSON
  limitations: JSON
  examples: JSON
  diagram: JSON
  inputModes: JSON
  outputModes: JSON
  askid: Int
  apps: JSON
  level: String
  price: Int
  priceModel: String
  source: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
}

input SkillUpdateInput {
  id: ID!
  name: String
  description: String
  category: String
  tags: JSON
  config: JSON
  capabilities: JSON
  limitations: JSON
  examples: JSON
  diagram: JSON
  inputModes: JSON
  outputModes: JSON
  askid: Int
  apps: JSON
  level: String
  price: Int
  priceModel: String
  source: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
}

input TaskQueryInput {
  id: ID
  owner: String
  status: String
}

input TaskInput {
  id: ID
  owner: String
  name: String!
  description: String
  status: String
  priority: String
  taskType: String
  triggerType: String
  action: String
  duration: Int
  orgId: String
  objectives: JSON
  result: JSON
  schedule: JSON
  errorMessage: String
  metadata: JSON
}

input TaskUpdateInput {
  id: ID!
  name: String
  description: String
  status: String
  priority: String
  taskType: String
  triggerType: String
  action: String
  duration: Int
  orgId: String
  objectives: JSON
  result: JSON
  schedule: JSON
  errorMessage: String
  metadata: JSON
}

input VehicleQueryInput {
  id: ID
  owner: String
}

input VehicleInput {
  id: ID
  owner: String
  name: String!
  description: String
  vehicleType: String
  platform: String
  architecture: String
  environment: String
  status: String
  url: String
  hostname: String
  ipAddress: String
  port: Int
  accessToken: String
  sslEnabled: Boolean
  securityLevel: String
  location: String
  timezone: String
  capabilities: JSON
  limitations: JSON
  settings: JSON
  extraMetadata: JSON
  gpuInfo: JSON
  cpuCores: Int
  memoryGb: Float
  storageGb: Float
  maxConcurrentTasks: Int
  healthScore: Float
}

input VehicleUpdateInput {
  id: ID!
  name: String
  description: String
  vehicleType: String
  platform: String
  architecture: String
  environment: String
  status: String
  url: String
  hostname: String
  ipAddress: String
  port: Int
  accessToken: String
  sslEnabled: Boolean
  securityLevel: String
  location: String
  timezone: String
  capabilities: JSON
  limitations: JSON
  settings: JSON
  extraMetadata: JSON
  gpuInfo: JSON
  cpuCores: Int
  memoryGb: Float
  storageGb: Float
  maxConcurrentTasks: Int
  healthScore: Float
}

input OrgQueryInput {
  id: ID
  name: String
  orgType: String
  status: String
}

input OrgInput {
  id: ID
  name: String!
  description: String
  orgType: String
  parentId: String
  level: Int
  sortOrder: Int
  status: String
  settings: JSON
}

input OrgUpdateInput {
  id: ID!
  name: String
  description: String
  orgType: String
  parentId: String
  level: Int
  sortOrder: Int
  status: String
  settings: JSON
}

input PromptQueryInput {
  id: ID
  owner: String
  search: String
  version: String
}

input PromptInput {
  id: ID
  owner: String
  prompt: JSON!
  version: String
}

input PromptUpdateInput {
  id: ID!
  prompt: JSON
  version: String
}

input AvatarQueryInput {
  owner: String
  resourceType: String
}

input AvatarInput {
  id: ID
  owner: String
  name: String
  description: String
  resourceType: String
  imagePath: String
  videoPath: String
  imageHash: String
  videoHash: String
  cloudImageKey: String
  cloudVideoKey: String
  cloudImageUrl: String
  cloudVideoUrl: String
  cloudSynced: Boolean
  avatarMetadata: JSON
  isPublic: Boolean
  usageCount: Int
  lastUsedAt: String
}

input AvatarUpdateInput {
  id: ID!
  name: String
  description: String
  resourceType: String
  imagePath: String
  videoPath: String
  imageHash: String
  videoHash: String
  cloudImageKey: String
  cloudVideoKey: String
  cloudImageUrl: String
  cloudVideoUrl: String
  cloudSynced: Boolean
  avatarMetadata: JSON
  isPublic: Boolean
  usageCount: Int
  lastUsedAt: String
}

input KnowledgeQueryInput {
  id: ID
  owner: String
  name: String
}

input KnowledgeInput {
  id: ID
  owner: String
  name: String!
  description: String
  content: String
  knowledgeType: String
  categories: JSON
  tags: JSON
  accessMethods: JSON
  limitations: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  settings: JSON
  config: JSON
  version: String
}

input KnowledgeUpdateInput {
  id: ID!
  name: String
  description: String
  content: String
  knowledgeType: String
  categories: JSON
  tags: JSON
  accessMethods: JSON
  limitations: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  settings: JSON
  config: JSON
  version: String
}

input ToolQueryInput {
  id: ID
  owner: String
  name: String
}

input ToolInput {
  id: ID
  owner: String
  name: String!
  description: String
  toolType: String
  capabilities: JSON
  limitations: JSON
  dependencies: JSON
  settings: JSON
  config: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
}

input ToolUpdateInput {
  id: ID!
  name: String
  description: String
  toolType: String
  capabilities: JSON
  limitations: JSON
  dependencies: JSON
  settings: JSON
  config: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
}

input SkillEditorEventInput {
  owner: String
  sessionId: String!
  flowgramId: String
  eventType: String!
  payload: JSON
  timestamp: String
}

input FileOp {
  op: String!
  names: String!
  options: String
  expiresIn: Int
  contentType: String
}

input RemoveOrder {
  oid: ID!
  owner: String!
  reason: String!
}

input Knowledge {
  knid: ID!
  name: String
  owner: String
  description: String
  path: String
  status: String
  rag: String
  metadata: JSON
}

input AvatarResource {
  id: ID!
  owner: String
  resource_type: String
  name: String
  description: String
  image_path: String
  video_path: String
  image_hash: String
  video_hash: String
  cloud_image_url: String
  cloud_video_url: String
  cloud_image_key: String
  cloud_video_key: String
  cloud_synced: Boolean
  avatar_metadata: JSON
  usage_count: Int
  last_used_at: String
  is_public: Boolean
  created_at: String
  updated_at: String
}

input Skill {
  skid: ID!
  owner: String
  createdOn: String!
  platform: String
  app: String
  site: String
  site_name: String
  page: String
  name: String
  path: String
  main: String
  description: String!
  runtime: Int!
  price_model: String!
  price: Int!
  privacy: String
}

input AgentEndpointInput {
  id: ID!
  machineId: String!
  org: String!
  name: String
  role: String
  skills: String
  skillsHash: String
  a2aRelayChannel: String!
  lanHint: String
  ecanVer: String
  os: String
  ttl: Int
}

input RAGIN {
  fid: ID!
  pid: ID!
  file: String!
  type: String!
  format: String!
  options: JSON!
  version: String!
}

input LongLLMTaskResultInput {
  id: ID
  acctSiteID: String
  agentID: String
  workType: String
  taskID: String
  status: String
  results: String
}

input SkillEditorChatSessionInput {
  name: String
  flowgramId: ID
  userId: ID!
}

input SkillEditorChatMessageInput {
  sessionId: ID!
  content: String!
  attachments: JSON
  canvasContext: JSON
  clarificationResponses: JSON
  userId: ID!
  flowgramId: ID
}

input SkillEditorStreamEventInput {
  owner: ID!
  sessionId: ID!
  flowgramId: ID
  eventType: String!
  payload: JSON
}

input Account {
  actid: ID!
  user_name: String
  subid: String
  dob: String
  email: String
  phone: String
  addr: String
  ssn4: String
  sign_on_date: String
  last_actions: JSON
  pay_method1: String
  pay1_details: String
  pay_method2: String
  pay2_details: String
  pay_method3: String
  pay3_details: String
  subs: String
  fund: Int
  quota: Int
  states: String
}

input AcctOp { actid: ID!, op: String!, options: String! }
input OrderOp { oid: ID!, op: String, options: String }
input KeyInfo { aws_api_key: String, option: String }
input KeyOp { op: String, keys: String, options: String }

input Bot {
  bid: ID!
  owner: String
  roles: String
  org: String
  birthday: String
  gender: String
  interests: String
  status: String
  levels: String
  vehicle: String
  location: String!
}

input Mission {
  mid: ID!
  ticket: ID!
  owner: String
  botid: ID!
  cuspas: String
  search_kw: String
  search_cat: String
  status: String!
  trepeat: ID!
  store: String!
  asin: String!
  brand: String!
  mtype: String!
  esd: String!
  as_server: Int!
  skills: String!
  config: String!
}

input MissionIdentifiers {
  byowneruser: Boolean
  mid: ID
  ticket: ID
  botid: ID
  owner: String
  requester: String
  type: String
  config: String
  phrase: String
  pseudo_store: String
  skills: String
  esd_range: String
  status: String
  created_date_range: String
  test_mode: Boolean
}

input MissionStatus { mid: ID!, bid: ID, status: String, starttime: String, usage: String, endtime: String, nthretry: Int }
input SimpleMissionStatus { mid: ID!, status: String }

input Order {
  oid: ID!
  actid: ID!
  orderID: String
  products: [String]!
  description: String
  yek: String
  number: Int
  discount: Int
  discountType: String
  dealType: String
  unitPrice: Int
  total: Int
  payMethod: String
  beginDate: String
  endDate: String
  status: String
  transactions: String
}

input RemoveBusinessOrder { oid: ID!, owner: String!, reason: String!, products: [String]!, productTypes: [String]! }
input WanChatMessageInput { chatID: String, sender: String, receiver: String, type: String, contents: String, parameters: String }
input TaskOrder { vehicles: String! }
input VehicleInfo { vid: ID, vname: String!, owner: String, status: String, lastseen: String, functions: String, bids: String, hardware: String, software: String, ip: String, created_at: String }
input SkillRun { skid: ID!, requester_mid: ID!, owner: String, name: String, start: String, in_data: String, verbose: Boolean }
input SkillRunStatus { run_id: ID!, skid: ID!, runner_mid: ID!, runner_bid: ID!, requester: String, request_method: String, status: String, start_time: String, end_time: String, result_data: String! }
input PuzzleInput { pzid: ID!, request_id: String, type: String, puzzle_file: String, question: String, url: String, url_key: String, prize: Int, time_limit: Int, module: String, options: String }
input PuzzleResultInput { pzid: ID!, request_id: String, type: String, solver: String, result: String }
input RelationIdInput { oid: ID!, owner: String }

input AgentSkillRelation {
  agid: ID!
  skid: ID!
  owner: String!
  status: String
  langgraph: JSON
  proficiency: Int
  acquired_at: String
  created_at: String
  updated_at: String
}

input AgentTaskRelation {
  agid: ID!
  task_id: ID!
  owner: String!
  status: String
  vehicle_id: String
  assigned_at: String
  started_at: String
  completed_at: String
  created_at: String
  updated_at: String
}

input AgentToolRelation {
  agid: ID!
  tool_id: ID!
  owner: String!
  permission: String
  granted_at: String
  created_at: String
  updated_at: String
}

input SkillToolRelation {
  skill_id: ID!
  tool_id: ID!
  owner: String!
  usage_type: String
  required: Boolean
  created_at: String
  updated_at: String
}

input SkillKnowledgeRelation {
  skill_id: ID!
  knowledge_id: ID!
  owner: String!
  dependency_type: String
  usage_frequency: String
  importance: Int
  access_pattern: String
  knowledge_scope: JSON
  created_at: String
  updated_at: String
}

input TaskSkillRelation {
  task_id: ID!
  skill_id: ID!
  owner: String!
  required: Boolean
  proficiency_required: Int
  created_at: String
  updated_at: String
}

# ============ Commerce Types ============
type Dimensions {
  length: Float
  width: Float
  height: Float
}

type Address {
  street: String
  city: String
  state: String
  postal_code: String
  country: String
}

type Product {
  id: ID!
  name: String!
  sku: String!
  description: String
  barcode: String
  weight_grams: Int
  attributes: JSON
  dimensions_cm: Dimensions
  status: String
}

input ProductInput {
  id: ID
  name: String!
  sku: String!
  description: String
  barcode: String
  weight_grams: Int
  attributes: JSON
  dimensions_cm: DimensionsInput
  status: String
}

input ProductUpdateInput {
  id: ID!
  name: String
  sku: String
  description: String
  barcode: String
  weight_grams: Int
  attributes: JSON
  dimensions_cm: DimensionsInput
  status: String
}

input ProductQueryInput {
  id: ID
  name: String
  sku: String
  status: String
}

type Warehouse {
  id: ID!
  name: String!
  code: String
  contact_name: String
  contact_phone: String
  address: Address
  notes: String
  status: String
}

input WarehouseInput {
  id: ID
  name: String!
  code: String
  contact_name: String
  contact_phone: String
  address: AddressInput
  notes: String
  status: String
}

input WarehouseUpdateInput {
  id: ID!
  name: String
  code: String
  contact_name: String
  contact_phone: String
  address: AddressInput
  notes: String
  status: String
}

input WarehouseQueryInput {
  id: ID
  name: String
  code: String
  status: String
}

type LabelFormat {
  id: ID!
  name: String!
  carrier: String
  service: String
  size: String
  dpi: Int
  settings: JSON
  template_url: String
  status: String
}

input LabelFormatInput {
  id: ID
  name: String!
  carrier: String
  service: String
  size: String
  dpi: Int
  settings: JSON
  template_url: String
  status: String
}

input LabelFormatUpdateInput {
  id: ID!
  name: String
  carrier: String
  service: String
  size: String
  dpi: Int
  settings: JSON
  template_url: String
  status: String
}

input LabelFormatQueryInput {
  id: ID
  name: String
  carrier: String
  service: String
  status: String
}

# ============ Scene & Story Types ============
enum SceneStatus { active completed pending failed }
enum StoryStatus { active completed draft archived }
enum SceneStyle { professional friendly excited calm }
enum OutputFormat { video image audio text }

type Scene {
  scene_id: ID!
  id: ID!
  acctSiteID: String!
  label: String!
  description: String
  clip: String!
  images: [String!]!
  video: [String!]!
  thumbnails: [String!]!
  captions: [String]
  agent_ids: [String!]!
  status: SceneStatus!
  duration_ms: Int
  actions: JSON
  dialogs: JSON
  priority: Int
  n_repeat: Int
  trigger_events: [String]
  emotion: String
  style: SceneStyle
}

type SceneTemplate {
  id: ID!
  label: String!
  description: String
  emotion: String!
  preview_url: String
}

type SceneConnection {
  items: [Scene!]!
  nextToken: String
}

type ReqSceneResponse {
  request_id: String
  status: String
  message: String
  estimated_time_ms: Int
  ref_ul_links: [String!]
}

input SceneInput {
  scene_id: ID!
  id: ID
  acctSiteID: String!
  label: String!
  clip: String!
  images: [String!]!
  video: [String!]!
  thumbnails: [String!]!
  captions: [String]
  agent_ids: [String!]!
  status: SceneStatus!
  description: String
  duration_ms: Int
  actions: JSON
  dialogs: JSON
  priority: Int
  n_repeat: Int
  trigger_events: [String]
  emotion: String
  style: SceneStyle
}

input SceneQueryInput {
  acctSiteID: String!
  label: String
  agent_id: String
  emotion: String
  status: SceneStatus
  limit: Int
  nextToken: String
}

input SceneResultInput {
  request_id: ID!
  scene_id: ID!
  acctSiteID: String!
  agent_ids: [String!]!
  status: SceneStatus!
  description: String
  thumbnail: String
  video: [String!]
  duration_ms: Int
  emotion: String
  mind_state: String
  actions: JSON
  dialogs: JSON
  error: String
}

type SceneResult {
  request_id: ID!
  scene_id: ID!
  acctSiteID: String
  status: SceneStatus!
}

input ReqSceneInput {
  acctSiteID: String!
  agent_id: String!
  emotion: String
  style: SceneStyle
  description: String
  context: JSON
  duration_hint_ms: Int
  mind_state: String
  output_format: OutputFormat
  output_resolution: [Int]
  refs: [JSON]
}

input ReadyReqSceneInput {
  acctSiteID: String!
  request_id: ID!
  status: String
}

type Story {
  id: ID!
  acctSiteID: String
  title: String
  description: String
  status: StoryStatus
  agent_ids: [String!]
  scenes: JSON
  current_scene_index: Int
}

type StoryConnection {
  items: [Story!]!
  nextToken: String
}

input StoryUpdateInput {
  id: ID!
  acctSiteID: String
  title: String
  description: String
  status: StoryStatus
  agent_ids: [String!]
  scenes: JSON
  current_scene_index: Int
}

# ============ Skill Editor Types ============
type SkillFileInfo {
  fileName: String!
  filePath: String!
  fileSize: Int
  skillName: String
  updatedAt: String
}

type SkillFileContent {
  content: String!
  fileName: String!
  filePath: String!
  fileSize: Int
  skillName: String
}

input SkillFileInput {
  filePath: String!
  content: String!
  userId: String
}

type EditorCacheResponse {
  cacheData: JSON
  recentFiles: [RecentFileInfo!]!
}

input RecentFileInfoInput {
  fileName: String!
  filePath: String!
}

type RecentFileInfo {
  fileName: String!
  filePath: String!
}

type EditorCacheSaveResult {
  newFilePath: String
  renamed: Boolean
}

input EditorCacheInput {
  cacheData: JSON
  recentFiles: [RecentFileInfoInput!]
  timestamp: String
  version: String
}

input SkillEditorContextRequestInput {
  userId: ID!
  skillIds: [ID!]
  skillNames: [String!]
}

type SkillEditorContextItem {
  skillId: ID
  skillName: String
  context: JSON
  updatedAt: String
}

type SkillEditorContextResponse {
  items: [SkillEditorContextItem!]!
}

type SkillScaffoldResult {
  name: String
  skillRoot: String
  diagramPath: String
}

input SkillScaffoldInput {
  name: String!
  description: String
  kind: String
  skillJson: JSON
  bundleJson: JSON
  mappingJson: JSON
}

type SkillCopyResult {
  name: String
  skillRoot: String
  diagramPath: String
}

input SkillCopyInput {
  sourcePath: String!
  newName: String!
  skillJson: JSON
  bundleJson: JSON
  targetDir: String
}

# ============ Skill Run Types ============
type RunControlResult {
  runId: ID
  status: String
  message: String
  data: JSON
}

input RunControlInput {
  username: String
  skill: JSON
}

type SkillRunEvent {
  runId: ID
  status: String
  current_node: String
  this_node: String
  nodeState: JSON
  timestamp: String
}

input SkillRunConfig {
  run_id: ID!
  skid: ID!
  runner_mid: ID!
  runner_bid: ID!
  requester: String
}

input RunSkillInput {
  username: String
  skill: JSON
}

input TaskRunQueryInput {
  task_id: String
  host_name: String
  meta_data: JSON!
}

type TaskStatus {
  runID: ID
  status: JSON
  success: Boolean!
  error: String
  runner: String
}

input TaskStatusInput {
  runID: ID
  status: JSON
  success: Boolean!
  error: String
  runner: String
}

input TestInput {
  id: String!
  name: String!
  description: String
  input: JSON
}

# ============ Misc Types ============
type CheckResult {
  name: String!
  exists: Boolean!
}

type NodeStateSchema {
  schema: JSON!
  schemaVersion: String!
}

input Node {
  askid: String!
  name: String!
  situation: String!
}

input Step {
  type: String!
  data: String
  duration: String
  end_time: String
}

input ScreenImg {
  id: ID
  url: String
}

type ScreenInfo {
  id: ID!
  clickables: [Clickable!]!
}

type Clickable {
  x: Int
  y: Int
  label: String
}

input DimensionsInput {
  length: Float
  width: Float
  height: Float
}

input AddressInput {
  street: String
  city: String
  state: String
  postal_code: String
  country: String
}

input FbReq {
  orderID: String
  transactionID: String
  customerMail: String
  customerPhone: String
  product: String
  total: Int
  payType: String
  origin: String
  instructions: String
  number: Int
}

input ChatReq {
  msgID: String
  msg: String
  user: String
  background: String
  goals: String
  products: String
  options: String
  timeStamp: String
}

type QueryApiKeysResponse {
  items: [ApiKeyItem!]!
}

type ApiKeyItem {
  id: ID!
  name: String
  key: String
  createdAt: String
  revokedAt: String
}

input QueryApiKeyInput {
  id: ID
  name: String
}

# ============ A2A Types ============
input A2AMessageInput {
  channelId: String!
  sessionId: String!
  senderId: String!
  recipientId: String
  message: A2AMessageBodyInput!
  metadata: JSON
  historyLength: Int
  acceptedOutputModes: [String!]
}

input A2AMessageBodyInput {
  type: String!
  content: String
}

type A2AMessageConnection {
  items: [A2AMessage!]!
  nextToken: String
}

# ============ SOAP Types ============
type StartSoapResponse {
  soap_id: ID!
  status: String!
  message: String
}

input StartSoapInput {
  acctSiteID: String!
  agent_ids: [String!]!
  theme: String
  mood: String
  settings: JSON
}

# ============ Puzzle Types ============
type PuzzleSolution {
  request_id: String
  solver_id: String
  success: Boolean
}

input PuzzleSolutionInput {
  request_id: String
  solver_id: String
  solution: [JSON]
}

# ============ Passive Browser Types ============
type ActionResult {
  success: Boolean!
  message: String
  data: JSON
}

input PassiveBrowserCommandEnvelopeInput {
  clientId: ID!
  runId: ID!
  stepId: ID!
  command: JSON!
}

type PassiveBrowserCommandEnvelope {
  clientId: ID!
  runId: ID!
  stepId: ID!
  command: JSON!
}

input PassiveBrowserHelloEnvelopeInput {
  clientId: ID!
  runId: ID!
  hello: JSON!
}

type PassiveBrowserHelloEnvelope {
  clientId: ID!
  runId: ID!
  hello: JSON!
}

input PassiveBrowserStepResultEnvelopeInput {
  clientId: ID!
  runId: ID!
  stepId: ID!
  result: JSON!
  dom_tree: JSON
}

type PassiveBrowserStepResultEnvelope {
  clientId: ID!
  runId: ID!
  stepId: ID!
  result: JSON!
  dom_tree: JSON
}

# ============ Notification Types ============
type AccountNotification {
  id: ID
  owner: String!
  ntype: String!
  title: String
  message: String
  cta_url: String
  payload: JSON
  createdAt: String
}

input AccountNotificationInput {
  owner: String!
  ntype: String!
  title: String
  message: String
  cta_url: String
  payload: JSON
}

input CloudTaskInput {
  options: JSON!
  task_id: String
  task_name: String
}

# ============ Subscriptions ============
type Subscription {
  onMessageReceived(chatID: String!): WanChatMessage
  onA2AMessageReceived(channelId: String!): A2AMessage
  onAccountNotification(owner: String!): AccountNotification
  onSkillEditorStreamEvent(sessionId: String!): SkillEditorEvent
  onPassiveCommand(runId: ID!, clientId: ID): PassiveBrowserCommandEnvelope
  onPassiveHello(runId: ID!, clientId: ID): PassiveBrowserHelloEnvelope
  onPassiveStepResult(runId: ID!, clientId: ID): PassiveBrowserStepResultEnvelope
  onPuzzleReceived: Puzzle
  onPuzzleResultReceived(pzid: ID!): PuzzleResult
  onLongLLMTaskComplete(acctSiteID: String!): LongLLMTaskResult
  onSceneComplete(acctSiteID: String!): SceneResult
  onAgentSceneEvent(acctSiteID: String!): SceneResult
  onStoryUpdate(acctSiteID: String!): Story
  onTaskStatus(runID: ID!): TaskStatus
}
`;

// ============ Create Yoga Server ============
// graphql-yoga speaks HTTP and fetch out of the box. The SCF handler below
// routes HTTP requests (query/mutation) to this yoga instance. Subscriptions
// are served by the separate `ecan-graphql-ws` cloud function
// (graphql-ws / AppSync-compatible). See services/ws-protocol.js and
// services/ws-bridge-push.js for the bridge implementation.

const yoga = createYoga({
  schema: createSchema({ typeDefs: transformSdl(typeDefs), resolvers }),
  graphqlEndpoint: '/api/graphql',
  landingPage: true,
  cors: {
    origin: '*',
    methods: ['GET', 'POST', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Ecan-Http-Test-Owner', 'X-Ecan-Http-Test-Secret'],
  },
  context: async ({ request }) => {
    // Resolve identity first; do not force a DB connection here. Resolvers
    // that need prisma should call `getPrisma()` themselves — that way pure
    // pub/sub mutations (publishTaskStatus, etc.) work without DATABASE_URL
    // (e.g. local stack tests).
    const identity = await resolveIdentity(request);
    return {
      prisma: process.env.DATABASE_URL ? getPrisma() : null,
      identity,
      getScheduler,
    };
  },
  fetchAPI: { Response },
});

// ============ SCF Handler ============

exports.main = async (event, context) => {
  // Do not block response on event loop drainage. Combined with the SIGTERM handler
  // in tcb-init.js this gives SCF the cleanest possible freeze/terminate semantics.
  if (context && 'callbackWaitsForEmptyEventLoop' in context) {
    context.callbackWaitsForEmptyEventLoop = false;
  }

  // 适配 SCF 格式
  const isHttpEvent = event.httpMethod || event.method;

  if (!isHttpEvent && event?.action === 'direct_graphql_test') {
    const request = new Request('https://direct-invoke.local/api/graphql', {
      method: 'POST',
      headers: new Headers({
        'content-type': 'application/json',
        ...directTestHeaders(event.owner),
      }),
      body: JSON.stringify({ query: event.query, variables: event.variables || {} }),
    });
    const response = await yoga.fetch(request);
    return {
      statusCode: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body: await response.text(),
    };
  }

  if (!isHttpEvent && event?.action === 'direct_prompt_snapshot_test') {
    if (!DIRECT_TEST_MODE) throw new Error('Direct test mode is disabled');
    const promptSnapshots = require('./storage/prompt-snapshots');
    const snapshot = await promptSnapshots.getPromptSnapshot(event.owner, event.promptId);
    const revisions = await promptSnapshots.listPromptRevisions(event.owner, event.promptId);
    return {
      bucket: snapshot.bucket,
      key: snapshot.key,
      versionId: snapshot.versionId,
      etag: snapshot.etag,
      contentLength: snapshot.contentLength,
      snapshot: snapshot.snapshot,
      revisions: revisions.revisions,
    };
  }

  if (isHttpEvent) {
    // HTTP 触发
    // SCF API 触发请求格式：
    //   - event.path: 仅路径，不含 query string
    //   - event.queryStringParameters: object { key: value }
    //   - event.body: 字符串
    //   - event.headers: object
    const eventPath = event.path || '/api/graphql';
    const yogaPath = HTTP_TEST_MODE ? '/api/graphql' : eventPath;
    const url = new URL(yogaPath, `https://${event.headers?.host || 'localhost'}`);

    const request = new Request(url.toString(), {
      method: event.httpMethod || event.method,
      headers: new Headers(event.headers || {}),
      body: event.body || undefined,
    });

    const response = await yoga.fetch(request);
    const body = await response.text();

    return {
      statusCode: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body,
    };
  }

  if (event?.Type === 'Timer' && event.Message) {
    const payload = typeof event.Message === 'string' ? JSON.parse(event.Message) : event.Message;
    if (payload.action !== 'run_cloud_task' || !payload.owner_id || !payload.task_id) {
      throw new Error('Invalid CN scheduler timer payload');
    }
    const runId = await getScheduler().launch({ owner: String(payload.owner_id), taskId: String(payload.task_id), options: payload.options || {} });
    return { success: true, run_id: runId, task_id: String(payload.task_id) };
  }

  // 事件触发
  return { message: 'TCB GraphQL API Ready' };
};

// SCF invokes this exported cleanup with the same (`event`, `context`) signature when
// the platform is about to freeze or terminate the instance. Closing the Prisma pool
// here avoids handing a half-dead connection to the next instance that inherits warm state.
if (typeof exports.PreStop === 'undefined') {
  exports.PreStop = async () => {
    const { disconnect } = require('./tcb-init');
    await disconnect();
  };
}

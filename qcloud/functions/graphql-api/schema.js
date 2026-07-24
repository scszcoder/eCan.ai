/**
 * GraphQL Schema - 与 AWS AppSync 完全一致
 */

const typeDefs = `
scalar AWSDate
scalar AWSDateTime
scalar AWSEmail
scalar AWSJSON
scalar AWSPhone
scalar AWSTime
scalar AWSTimestamp
scalar AWSURL

type Agent {
  id: ID!
  name: String!
  owner: String!
  description: String
  gender: String
  title: AWSJSON
  rank: String
  birthday: AWSDate
  supervisor_id: String
  personalities: AWSJSON
  capabilities: AWSJSON
  status: String
  version: String
  url: String
  vehicle_id: String
  avatar_resource_id: String
  extra_data: AWSJSON
  created_at: AWSDateTime
  updated_at: AWSDateTime
}

input AgentInput {
  id: ID
  owner: String
  name: String!
  description: String
  gender: String
  title: AWSJSON
  rank: String
  birthday: AWSDate
  status: String
  vehicle_id: String
  avatar_resource_id: String
  extra_data: AWSJSON
}

type AgentResult { id: ID success: Boolean! error: String }

type AgentSkill {
  id: ID!
  askid: ID
  name: String!
  owner: String!
  skill_owner: String
  description: String
  version: String
  path: String
  source: String
  level: String
  config: AWSJSON
  diagram: AWSJSON
  tags: AWSJSON
  examples: AWSJSON
  inputModes: AWSJSON
  outputModes: AWSJSON
  apps: AWSJSON
  limitations: AWSJSON
  price: Int
  price_model: String
  public: Boolean
  rentable: Boolean
  created_at: AWSDateTime
  updated_at: AWSDateTime
}

input AgentSkillInput {
  askid: ID
  id: ID
  owner: String
  name: String!
  description: String
  version: String
  path: String
  source: String
  level: String
  config: AWSJSON
  diagram: AWSJSON
  tags: AWSJSON
  examples: AWSJSON
  price: Int
  public: Boolean
}

type AgentSkillResult { id: ID askid: String success: Boolean! error: String }

type AgentTask {
  id: ID!
  ataskid: ID
  name: String!
  owner: String!
  description: String
  org_id: String
  source: String
  priority: String
  status: String
  task_type: String
  trigger: String
  objectives: AWSJSON
  schedule: AWSJSON
  progress: Float
  result: AWSJSON
  error_message: String
  metadata: AWSJSON
  created_at: AWSDateTime
  updated_at: AWSDateTime
}

input AgentTaskInput {
  ataskid: ID
  id: ID
  owner: String
  name: String!
  description: String
  org_id: String
  priority: String
  status: String
  task_type: String
  trigger: String
  objectives: AWSJSON
  schedule: AWSJSON
}

type AgentTaskResult { id: ID success: Boolean! error: String }

type Vehicle {
  id: ID!
  name: String!
  owner: String!
  vehicle_type: String
  platform: String
  architecture: String
  ip_address: String
  hostname: String
  port: Int
  url: String
  cpu_cores: Int
  memory_gb: Float
  status: String
  capabilities: AWSJSON
  created_at: AWSDateTime
  updated_at: AWSDateTime
}

input VehicleInput {
  id: ID
  owner: String
  name: String!
  vehicle_type: String
  platform: String
  ip_address: String
  capabilities: AWSJSON
}

type VehicleResult { id: ID success: Boolean! error: String }

type Organization {
  id: ID!
  name: String!
  description: String
  parent_id: String
  org_type: String
  level: Int
  status: String
  settings: AWSJSON
  created_at: AWSDateTime
  updated_at: AWSDateTime
}

input OrganizationInput {
  id: ID
  name: String!
  description: String
  parent_id: String
  org_type: String
  settings: AWSJSON
}

type OrganizationResult { id: ID success: Boolean! error: String }

type Query {
  getAgents(owner: String!): [Agent]
  queryAgents(input: AWSJSON): [Agent]
  getAgentSkills(owner: String!): [AgentSkill]
  queryAgentSkills(input: AWSJSON): [AgentSkill]
  getAgentTasks(owner: String!): [AgentTask]
  queryAgentTasks(input: AWSJSON): [AgentTask]
  getVehicles(owner: String!): [Vehicle]
  queryVehicles(input: AWSJSON): [Vehicle]
  getOrgs(owner: String!): [Organization]
  queryOrgs(input: AWSJSON): [Organization]
  getSettings(key: String!): AWSJSON
  getStory(id: ID!): Story
  listStories(input: AWSJSON): [Story]
}

type Mutation {
  addAgents(input: [AgentInput!]!): [AgentResult]
  updateAgents(input: [AgentInput!]!): [AgentResult]
  removeAgents(input: [RemoveInput!]!): [RemoveResult]
  addAgentSkills(input: [AgentSkillInput!]!): [AgentSkillResult]
  updateAgentSkills(input: [AgentSkillInput!]!): [AgentSkillResult]
  removeAgentSkills(input: [RemoveInput!]!): [RemoveResult]
  addAgentTasks(input: [AgentTaskInput!]!): [AgentTaskResult]
  updateAgentTasks(input: [AgentTaskInput!]!): [AgentTaskResult]
  removeAgentTasks(input: [RemoveInput!]!): [RemoveResult]
  addVehicles(input: [VehicleInput!]!): [VehicleResult]
  updateVehicles(input: [VehicleInput!]!): [VehicleResult]
  removeVehicles(input: [RemoveInput!]!): [RemoveResult]
  addOrgs(input: [OrganizationInput!]!): [OrganizationResult]
  updateOrgs(input: [OrganizationInput!]!): [OrganizationResult]
  removeOrgs(input: [RemoveInput!]!): [RemoveResult]
  runSkill(input: AWSJSON!): RunSkillResult
  testLanggraph2Flowgram(input: AWSJSON!): AWSJSON
  updateSettings(key: String!, value: AWSJSON!): AWSJSON
  reqRAGStore(input: AWSJSON!): AWSJSON
}

type Subscription {
  onAgentUpdated(owner: String): Agent
  onAgentSkillUpdated(owner: String): AgentSkill
  onTaskStatusChanged(owner: String): AgentTask
  onVehicleStatusChanged(owner: String): Vehicle
}

type Story {
  id: ID!
  owner: String!
  name: String
  description: String
  content: AWSJSON
  metadata: AWSJSON
  status: String
  created_at: AWSDateTime
  updated_at: AWSDateTime
}

type RunSkillResult { success: Boolean! run_id: String error: String }
input RemoveInput { id: ID! }
type RemoveResult { id: ID success: Boolean! error: String }
`;

module.exports = typeDefs;

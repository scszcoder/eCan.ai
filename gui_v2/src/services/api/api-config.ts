/**
 * API 配置文件
 * 
 * 整合所有 GraphQL 查询和变更定义
 * 来源：webApi.ts 和 webIpcBridge.ts
 */

/**
 * 通信通道枚举
 */
export enum Channel {
  IPC = 'ipc',
  GRAPHQL = 'graphql'
}

/**
 * API 定义接口
 */
export interface APIDefinition {
  method: string;
  graphql?: {
    query?: string;
    mutation?: string;
    resultPath?: string;
  };
}

/**
 * GraphQL 查询定义
 */
export const GRAPHQL_QUERIES = {
  // ==================== Agent & User Data ====================
  GET_ALL_MINE: `
    query GetAllMine($owner: String, $userId: String) {
      getAllMine(owner: $owner, userId: $userId) {
        agents { id name owner description status rank supervisor_id avatar_resource_id title capabilities extra_data personalities url vehicle_id version created_at updated_at org_id org_ids skills tasks }
        tasks { id name description status priority owner org_id source task_type trigger_type metadata result schedule }
        skills { id name owner description level path public rentable source tags version }
        tools { id name owner description level tool_type status path public rentable version }
        knowledges { id name owner description knowledge_type level status tags path version }
        prompts { id owner prompt version created_at updated_at }
        orgs { id name description parent_id org_type level sort_order status settings }
        avatars { id name owner resource_type description cloud_image_url cloud_video_url is_public usage_count }
        vehicles { id name owner status vehicle_type location url platform }
        accountInfo
      }
    }
  `,

  GET_ORG_AGENT_TREE: `
    fragment OrgTreeNodeFields on OrgTree {
      id name description org_type level sort_order status parent_id
      agents { id name description status created_at updated_at owner avatar_resource_id org_id org_ids skills tasks }
    }
    query GetOrgAgentTree($rootId: ID, $username: String) {
      getOrgAgentTree(root_id: $rootId, username: $username) {
        ...OrgTreeNodeFields
        children {
          ...OrgTreeNodeFields
          children {
            ...OrgTreeNodeFields
            children { ...OrgTreeNodeFields }
          }
        }
      }
    }
  `,

  QUERY_ORGS: `
    query QueryOrgs($input: OrgQueryInput) {
      queryOrgs(input: $input) { id name description org_type }
    }
  `,

  // ==================== Tasks ====================
  GET_AGENT_TASKS: `
    query GetAgentTasks {
      getAgentTasks {
        id name description status priority owner org_id source task_type
        trigger_type objectives schedule metadata result error_message progress
      }
    }
  `,

  // ==================== Warehouse & Inventory ====================
  GET_WAREHOUSES: `
    query GetWarehouses($input: WarehouseQueryInput) {
      getWarehouses(input: $input) {
        id name code
        address { line1 line2 city state postal_code country }
        contact_name contact_phone status notes created_at updated_at
      }
    }
  `,

  GET_LABEL_FORMATS: `
    query GetLabelFormats($input: LabelFormatQueryInput) {
      getLabelFormats(input: $input) {
        id name unit sheet_width sheet_height label_width label_height
        top_margin left_margin rows cols row_pitch col_pitch _filepath _filename
      }
    }
  `,

  GET_PRODUCTS: `
    query GetProducts($input: ProductQueryInput) {
      getProducts(input: $input) {
        id sku name description barcode weight_grams
        dimensions_cm { length_cm width_cm height_cm }
        attributes status created_at updated_at
      }
    }
  `,

  GET_INVENTORIES: `
    query GetInventories($input: InventoryQueryInput) {
      getInventories(input: $input) {
        id warehouse_id product_id on_hand reserved available bin_location status updated_at
      }
    }
  `,

  // ==================== Skill Editor ====================
  GET_NODE_STATE_SCHEMA: `
    query GetNodeStateSchema {
      getNodeStateSchema { schemaVersion schema }
    }
  `,

  READ_SKILL_FILE: `
    query ReadSkillFile($filePath: String!, $userId: String) {
      readSkillFile(filePath: $filePath, userId: $userId) {
        content filePath fileName fileSize skillName
      }
    }
  `,

  OPEN_SKILL_FILE: `
    query OpenSkillFile($filePath: String!, $skillName: String, $userId: String) {
      openSkillFile(filePath: $filePath, skillName: $skillName, userId: $userId) {
        content filePath fileName fileSize skillName
      }
    }
  `,

  LIST_SKILL_FILES: `
    query ListSkillFiles($prefix: String, $limit: Int, $nextToken: String, $userId: String) {
      listSkillFiles(prefix: $prefix, limit: $limit, nextToken: $nextToken, userId: $userId) {
        filePath fileName fileSize skillName updatedAt
      }
    }
  `,

  CHECK_SKILL_EXISTS: `
    query CheckSkillExists($name: String!) {
      checkSkillExists(name: $name) { exists name }
    }
  `,

  GET_EDITOR_CACHE: `
    query GetEditorCache($userId: ID!) {
      getEditorCache(userId: $userId) {
        cacheData
        recentFiles { filePath fileName skillName updatedAt }
      }
    }
  `,

  GET_SKILL_RUN_STATUS: `
    query GetSkillRunStatus($runId: ID!, $since: AWSDateTime) {
      getSkillRunStatus(runId: $runId, since: $since) {
        runId status message data logs { timestamp level message data }
      }
    }
  `,

  GET_SKILL_EDITOR_EVENTS: `
    query GetSkillEditorEvents($sessionId: String!, $since: AWSDateTime) {
      getSkillEditorEvents(sessionId: $sessionId, since: $since) {
        eventId type data timestamp
      }
    }
  `,

  LOAD_SKILL_EDITOR_CONTEXTS: `
    query LoadSkillEditorContexts($input: SkillEditorContextRequestInput!) {
      loadSkillEditorContexts(input: $input) {
        items { skillId skillName context }
      }
    }
  `,

  GET_SKILL_EDITOR_CHAT_SESSIONS: `
    query GetSkillEditorChatSessions($userId: ID!) {
      getSkillEditorChatSessions(userId: $userId) {
        id name flowgramId createdAt updatedAt
      }
    }
  `,

  GET_SKILL_EDITOR_CHAT_HISTORY: `
    query GetSkillEditorChatHistory($sessionId: ID!, $limit: Int, $offset: Int) {
      getSkillEditorChatHistory(sessionId: $sessionId, limit: $limit, offset: $offset) {
        id role content timestamp attachments metadata
      }
    }
  `,

  // ==================== A2A Messages (Chat) ====================
  GET_A2A_MESSAGES: `
    query GetA2AMessages($channelId: String!, $limit: Int, $nextToken: String) {
      getA2AMessages(channelId: $channelId, limit: $limit, nextToken: $nextToken) {
        items {
          id
          channelId
          sessionId
          senderId
          recipientId
          timestamp
          message {
            role
            parts {
              type
              text
              metadata
            }
            metadata
          }
          metadata
          historyLength
          acceptedOutputModes
        }
        nextToken
      }
    }
  `,
};

/**
 * GraphQL 变更定义
 */
export const GRAPHQL_MUTATIONS = {
  // ==================== A2A Messages (Chat) ====================
  SEND_CLOUD_A2A_MESSAGE: `
    mutation SendCloudA2AMessage($input: A2AMessageInput!) {
      sendCloudA2AMessage(input: $input) {
        id
        channelId
        sessionId
        senderId
        recipientId
        timestamp
        message {
          role
          parts {
            type
            text
            metadata
          }
        }
      }
    }
  `,

  // ==================== Agent Management ====================
  ADD_AGENTS: `
    mutation AddAgents($input: [AgentInput!]!) {
      addAgents(input: $input) { id success error }
    }
  `,

  UPDATE_AGENTS: `
    mutation UpdateAgents($input: [AgentUpdateInput!]!) {
      updateAgents(input: $input) { id success error }
    }
  `,

  REMOVE_AGENTS: `
    mutation RemoveAgents($input: [ID!]!) {
      removeAgents(input: $input) { id success error }
    }
  `,

  // ==================== Skill Management ====================
  ADD_AGENT_SKILLS: `
    mutation AddAgentSkills($input: [SkillInput!]!) {
      addAgentSkills(input: $input) { id success error }
    }
  `,

  UPDATE_AGENT_SKILLS: `
    mutation UpdateAgentSkills($input: [SkillUpdateInput!]!) {
      updateAgentSkills(input: $input) { id success error }
    }
  `,

  REMOVE_AGENT_SKILLS: `
    mutation RemoveAgentSkills($input: [ID!]!) {
      removeAgentSkills(input: $input) { id success error }
    }
  `,

  // ==================== Task Management ====================
  ADD_AGENT_TASKS: `
    mutation AddAgentTasks($input: [TaskInput!]!) {
      addAgentTasks(input: $input) { id success error }
    }
  `,

  UPDATE_AGENT_TASKS: `
    mutation UpdateAgentTasks($input: [TaskUpdateInput!]!) {
      updateAgentTasks(input: $input) { id success error }
    }
  `,

  REMOVE_AGENT_TASKS: `
    mutation RemoveAgentTasks($input: [ID!]!) {
      removeAgentTasks(input: $input) { id success error }
    }
  `,

  // ==================== Tool Management ====================
  ADD_AGENT_TOOLS: `
    mutation AddAgentTools($input: [ToolInput!]!) {
      addAgentTools(input: $input) { id success error }
    }
  `,

  UPDATE_AGENT_TOOLS: `
    mutation UpdateAgentTools($input: [ToolUpdateInput!]!) {
      updateAgentTools(input: $input) { id success error }
    }
  `,

  REMOVE_AGENT_TOOLS: `
    mutation RemoveAgentTools($input: [ID!]!) {
      removeAgentTools(input: $input) { id success error }
    }
  `,

  // ==================== Knowledge Management ====================
  ADD_AGENT_KNOWLEDGES: `
    mutation AddAgentKnowledges($input: [KnowledgeInput!]!) {
      addAgentKnowledges(input: $input) { id success error }
    }
  `,

  UPDATE_AGENT_KNOWLEDGES: `
    mutation UpdateAgentKnowledges($input: [KnowledgeUpdateInput!]!) {
      updateAgentKnowledges(input: $input) { id success error }
    }
  `,

  REMOVE_AGENT_KNOWLEDGES: `
    mutation RemoveAgentKnowledges($input: [ID!]!) {
      removeAgentKnowledges(input: $input) { id success error }
    }
  `,

  // ==================== Prompts Management ====================
  ADD_PROMPTS: `
    mutation AddPrompts($input: [PromptInput!]!) {
      addPrompts(input: $input) { id success error }
    }
  `,

  UPDATE_PROMPTS: `
    mutation UpdatePrompts($input: [PromptUpdateInput!]!) {
      updatePrompts(input: $input) { id success error }
    }
  `,

  REMOVE_PROMPTS: `
    mutation RemovePrompts($input: [ID!]!) {
      removePrompts(input: $input) { id success error }
    }
  `,

  // ==================== Orgs Management ====================
  ADD_ORGS: `
    mutation AddOrgs($input: [OrgInput!]!) {
      addOrgs(input: $input) { id success error }
    }
  `,

  UPDATE_ORGS: `
    mutation UpdateOrgs($input: [OrgUpdateInput!]!) {
      updateOrgs(input: $input) { id success error }
    }
  `,

  REMOVE_ORGS: `
    mutation RemoveOrgs($input: [ID!]!) {
      removeOrgs(input: $input) { id success error }
    }
  `,

  // ==================== Vehicles Management ====================
  ADD_VEHICLES: `
    mutation AddVehicles($input: [VehicleInput!]!) {
      addVehicles(input: $input) { id success error }
    }
  `,

  UPDATE_VEHICLES: `
    mutation UpdateVehicles($input: [VehicleInput!]!) {
      updateVehicles(input: $input) { id success error }
    }
  `,

  REMOVE_VEHICLES: `
    mutation RemoveVehicles($input: [ID!]!) {
      removeVehicles(input: $input) { id success error }
    }
  `,

  // ==================== Warehouse Management ====================
  ADD_WAREHOUSES: `
    mutation AddWareHouses($input: [WarehouseInput!]!) {
      addWareHouses(input: $input) { id success error }
    }
  `,

  UPDATE_WAREHOUSES: `
    mutation UpdateWarehouses($input: [WarehouseUpdateInput!]!) {
      UpdateWarehouses(input: $input) { id success error }
    }
  `,

  REMOVE_WAREHOUSES: `
    mutation RemoveWareHouses($input: [ID!]!) {
      RemoveWareHouses(input: $input) { id success error }
    }
  `,

  // ==================== Label Formats Management ====================
  ADD_LABEL_FORMATS: `
    mutation AddLabelFormats($input: [LabelFormatInput!]!) {
      addLabelFormats(input: $input) { id success error }
    }
  `,

  UPDATE_LABEL_FORMATS: `
    mutation UpdateLabelFormats($input: [LabelFormatUpdateInput!]!) {
      UpdateLabelFormats(input: $input) { id success error }
    }
  `,

  REMOVE_LABEL_FORMATS: `
    mutation RemoveLabelFormats($input: [ID!]!) {
      RemoveLabelFormats(input: $input) { id success error }
    }
  `,

  // ==================== Products Management ====================
  ADD_PRODUCTS: `
    mutation AddProducts($input: [ProductInput!]!) {
      addProducts(input: $input) { id success error }
    }
  `,

  UPDATE_PRODUCTS: `
    mutation UpdateProducts($input: [ProductUpdateInput!]!) {
      updateProducts(input: $input) { id success error }
    }
  `,

  REMOVE_PRODUCTS: `
    mutation RemoveProducts($input: [ID!]!) {
      removeProducts(input: $input) { id success error }
    }
  `,

  // ==================== Inventories Management ====================
  ADD_INVENTORIES: `
    mutation AddInventories($input: [InventoryInput!]!) {
      addInventories(input: $input) { id success error }
    }
  `,

  UPDATE_INVENTORIES: `
    mutation UpdateInventories($input: [InventoryUpdateInput!]!) {
      updateInventories(input: $input) { id success error }
    }
  `,

  REMOVE_INVENTORIES: `
    mutation RemoveInventories($input: [ID!]!) {
      removeInventories(input: $input) { id success error }
    }
  `,

  // ==================== Skill Editor ====================
  WRITE_SKILL_FILE: `
    mutation WriteSkillFile($input: [SkillFileInput!]!) {
      writeSkillFile(input: $input) {
        filePath fileName fileSize skillName updatedAt
      }
    }
  `,

  SCAFFOLD_SKILL: `
    mutation ScaffoldSkill($input: SkillScaffoldInput!) {
      scaffoldSkill(input: $input) { skillRoot name diagramPath }
    }
  `,

  COPY_SKILL_TO: `
    mutation CopySkillTo($input: SkillCopyInput!) {
      copySkillTo(input: $input) { skillRoot name diagramPath }
    }
  `,

  SAVE_EDITOR_CACHE: `
    mutation SaveEditorCache($input: EditorCacheInput!) {
      saveEditorCache(input: $input) { renamed newFilePath }
    }
  `,

  CLEAR_EDITOR_CACHE: `
    mutation ClearEditorCache($userId: ID!) {
      clearEditorCache(userId: $userId)
    }
  `,

  // ==================== Skill Execution ====================
  RUN_SKILL: `
    mutation RunSkill($input: RunSkillInput!) {
      runSkill(input: $input) { runId status message data }
    }
  `,

  PAUSE_RUN_SKILL: `
    mutation PauseRunSkill($input: RunControlInput!) {
      pauseRunSkill(input: $input) { runId status message data }
    }
  `,

  RESUME_RUN_SKILL: `
    mutation ResumeRunSkill($input: RunControlInput!) {
      resumeRunSkill(input: $input) { runId status message data }
    }
  `,

  STEP_RUN_SKILL: `
    mutation StepRunSkill($input: RunControlInput!) {
      stepRunSkill(input: $input) { runId status message data }
    }
  `,

  CANCEL_RUN_SKILL: `
    mutation CancelRunSkill($input: RunControlInput!) {
      cancelRunSkill(input: $input) { runId status message data }
    }
  `,

  // ==================== Simulation ====================
  SETUP_SIM_STEP: `
    mutation SetupSimStep($bundle: AWSJSON!) {
      setupSimStep(bundle: $bundle) { runId status message data }
    }
  `,

  STEP_SIM: `
    mutation StepSim {
      stepSim { runId status message data }
    }
  `,

  TEST_LANGGRAPH2_FLOWGRAM: `
    mutation TestLanggraph2Flowgram {
      testLanggraph2Flowgram { runId status message data }
    }
  `,

  SIM_TIMER_EVENT: `
    mutation SimTimerEvent {
      simTimerEvent { runId status message data }
    }
  `,

  SIM_WEBSOCKET_EVENT: `
    mutation SimWebsocketEvent {
      simWebsocketEvent { runId status message data }
    }
  `,

  SIM_SSE_EVENT: `
    mutation SimSseEvent {
      simSseEvent { runId status message data }
    }
  `,

  SIM_WEBHOOK_EVENT: `
    mutation SimWebhookEvent {
      simWebhookEvent { runId status message data }
    }
  `,

  // ==================== Debugging ====================
  SET_SKILL_BREAKPOINTS: `
    mutation SetSkillBreakpoints($username: String!, $nodeName: String!) {
      setSkillBreakpoints(username: $username, node_name: $nodeName) {
        success message data
      }
    }
  `,

  CLEAR_SKILL_BREAKPOINTS: `
    mutation ClearSkillBreakpoints($username: String!, $nodeName: String!) {
      clearSkillBreakpoints(username: $username, node_name: $nodeName) {
        success message data
      }
    }
  `,

  REQUEST_SKILL_STATE: `
    mutation RequestSkillState($username: String!, $skill: AWSJSON!) {
      requestSkillState(username: $username, skill: $skill) {
        success message data
      }
    }
  `,

  INJECT_SKILL_STATE: `
    mutation InjectSkillState($username: String!, $skill: AWSJSON!) {
      injectSkillState(username: $username, skill: $skill) {
        success message data
      }
    }
  `,

  LOAD_SKILL_SCHEMAS: `
    mutation LoadSkillSchemas($username: String!, $skill: AWSJSON!) {
      loadSkillSchemas(username: $username, skill: $skill) {
        success message data
      }
    }
  `,

  // ==================== Chat ====================
  CREATE_SKILL_EDITOR_CHAT_SESSION: `
    mutation CreateSkillEditorChatSession($input: SkillEditorChatSessionInput!) {
      createSkillEditorChatSession(input: $input) {
        id name flowgramId createdAt updatedAt
      }
    }
  `,

  SEND_SKILL_EDITOR_CHAT_MESSAGE: `
    mutation SendSkillEditorChatMessage($input: SkillEditorChatMessageInput!) {
      sendSkillEditorChatMessage(input: $input) {
        sessionId sessionName state intent
        message { id role content timestamp attachments metadata }
        clarification plan flowgram validation
      }
    }
  `,

  CANCEL_SKILL_EDITOR_CHAT_GENERATION: `
    mutation CancelSkillEditorChatGeneration($sessionId: ID!) {
      cancelSkillEditorChatGeneration(sessionId: $sessionId)
    }
  `,

  DELETE_SKILL_EDITOR_CHAT_SESSION: `
    mutation DeleteSkillEditorChatSession($sessionId: ID!) {
      deleteSkillEditorChatSession(sessionId: $sessionId)
    }
  `,
};

/**
 * GraphQL 订阅定义
 */
export const GRAPHQL_SUBSCRIPTIONS = {
  // ==================== A2A Messages (Chat) ====================
  ON_A2A_MESSAGE_RECEIVED: `
    subscription OnA2AMessageReceived($channelId: String!) {
      onA2AMessageReceived(channelId: $channelId) {
        id
        channelId
        sessionId
        senderId
        recipientId
        timestamp
        message {
          role
          parts {
            type
            text
            metadata
          }
        }
        metadata
        historyLength
        acceptedOutputModes
      }
    }
  `,
};

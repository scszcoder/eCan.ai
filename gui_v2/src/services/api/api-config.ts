/**
 * API 配置文件
 * 
 * 整合所有 GraphQL 查询和变更定义
 * 来源：webApi.ts 和 webIpcBridge.ts
 */

/**
 * 通信通道枚举
 * - LOCAL: 本地 GraphQL 端点 (/graphql)，与本地 Python 后端通信
 * - CLOUD: 云端 GraphQL 端点 (AppSync)，与 AWS 云端通信
 */
export enum Channel {
  LOCAL = 'local',
  CLOUD = 'cloud'
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
        tools { id name owner description level tool_type status path public rentable version config settings capabilities limitations dependencies price price_model }
        knowledges { id name owner description knowledge_type level status tags path version }
        prompts { id owner prompt version created_at updated_at }
        orgs { id name description parent_id org_type level sort_order status settings }
        avatars { id name owner resource_type description cloud_image_url cloud_video_url is_public usage_count }
        vehicles { id name owner status vehicle_type location url platform }
        accountInfo
        settings
      }
    }
  `,

  // ==================== Settings ====================
  GET_SETTINGS: `
    query GetSettings($ids: [ID!], $username: String) {
      getSettings(ids: $ids, username: $username)
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

  QUERY_CLOUD_TASK_RUN_ID: `
    query QueryCloudTaskRunId($input: TaskRunQueryInput!) {
      queryCloudTaskRunId(input: $input) {
        id runID runner status success error timestamp
      }
    }
  `,

  // ==================== Relation Tables (RDS) ====================
  QUERY_AGENT_ORG_RELS: `
    query QueryAgentOrgRels($input: AWSJSON) {
      queryAgentOrgRels(input: $input)
    }
  `,

  QUERY_AGENT_SKILL_RELS: `
    query QueryAgentSkillRels($input: AWSJSON) {
      queryAgentSkillRels(input: $input)
    }
  `,

  QUERY_AGENT_TASK_RELS: `
    query QueryAgentTaskRels($input: AWSJSON) {
      queryAgentTaskRels(input: $input)
    }
  `,

  QUERY_AGENT_TASK_SKILL_RELS: `
    query QueryAgentTaskSkillRels($input: AWSJSON) {
      queryAgentTaskSkillRels(input: $input)
    }
  `,

  // Placeholders (not currently used by web UI)
  QUERY_AGENT_SKILL_TOOL_RELS: `
    query QueryAgentSkillToolRels($input: AWSJSON) {
      queryAgentSkillToolRels(input: $input)
    }
  `,

  QUERY_AGENT_SKILL_KNOWLEDGE_RELS: `
    query QueryAgentSkillKnowledgeRels($input: AWSJSON) {
      queryAgentSkillKnowledgeRels(input: $input)
    }
  `,

  // ==================== Skills Store ====================
  GET_PUBLIC_SKILLS: `
    query GetPublicSkills($owner: String) {
      getPublicSkills(owner: $owner) {
        id name owner description level path public rentable source tags version
      }
    }
  `,

  GET_SUBSCRIBED_SKILL_IDS: `
    query GetSubscribedSkillIds($owner: String) {
      getSubscribedSkillIds(owner: $owner)
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
        id name settings size status dpi carrier service template_url created_at updated_at
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

  LIST_SKILL_REVISIONS: `
    query ListSkillRevisions($input: SkillRevisionInput!) {
      listSkillRevisions(input: $input) {
        key fileName timestamp size lastModified
      }
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

  // ==================== Avatar Resources ====================
  QUERY_AVATAR_RESOURCES: `
    query QueryAvatars($input: AvatarQueryInput) {
      queryAvatars(input: $input) {
        id name owner resource_type description
        cloud_image_url cloud_video_url cloud_image_key cloud_video_key
        is_public usage_count image_hash image_path video_path
        presigned_image_url presigned_video_url
      }
    }
  `,

  GET_AVATAR_RESOURCES: `
    query GetAvatars {
      getAvatars {
        id name owner resource_type description
        cloud_image_url cloud_video_url cloud_image_key cloud_video_key
        is_public usage_count image_hash image_path video_path
        presigned_image_url presigned_video_url
      }
    }
  `,

  // ==================== RAG Document Management ====================
  RAG_QUERY: `
    query RAGQuery($input: RAGQueryInput!) {
      ragQuery(input: $input) {
        answer
        chunks { text score source metadata }
        query
        mode
      }
    }
  `,

  RAG_LIST_DOCS: `
    query RAGListDocs($pid: String) {
      ragListDocs(pid: $pid) {
        docKey fileName fileType fileSize uploadedAt status pid
      }
    }
  `,

  RAG_GET_INDEX_STATUS: `
    query RAGGetIndexStatus($pid: String) {
      ragGetIndexStatus(pid: $pid) {
        status message progress taskArn lastIndexedAt docCount chunkCount
      }
    }
  `,
};

/**
 * GraphQL 变更定义
 */
export const GRAPHQL_MUTATIONS = {
  // ==================== A2A Messages (Chat) ====================
  // ==================== Avatar Resources ====================
  ADD_AVATAR_RESOURCES: `
    mutation AddAvatars($input: [AvatarInput!]!) {
      addAvatars(input: $input) {
        id success error image_upload_url video_upload_url
      }
    }
  `,

  REMOVE_AVATAR_RESOURCES: `
    mutation RemoveAvatars($input: [ID!]!) {
      removeAvatars(input: $input) {
        id success error
      }
    }
  `,

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

  SEND_A2A_MESSAGE: `
    mutation SendA2AMessage($input: A2AMessageInput!) {
      sendA2AMessage(input: $input) {
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

  // ==================== API Key (Customer Support Chat Test) ====================
  REQ_API_KEY: `
    mutation ReqApiKey($input: CustomerInput) {
      reqApiKey(input: $input) {
        apiKey
        apiKeyId
        message
      }
    }
  `,

  // ==================== API Key Management (Account Page) ====================
  REQ_API_KEY_V2: `
    mutation ReqApiKey($input: CustomerInput) {
      reqApiKey(input: $input) {
        apiKey
        apiKeyId
        message
      }
    }
  `,

  QUERY_API_KEYS: `
    query QueryApiKeys($input: QueryApiKeyInput) {
      queryApiKeys(input: $input) {
        customerEmail
        status
      }
    }
  `,
  REMOVE_API_KEY: `
    mutation RemoveApiKey($input: [String!]!) {
      removeApiKey(input: $input)
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

  SUBSCRIBE_TO_SKILL: `
    mutation SubscribeToSkill($skillId: ID!, $owner: String) {
      subscribeToSkill(skillId: $skillId, owner: $owner) { id success error }
    }
  `,

  UNSUBSCRIBE_FROM_SKILL: `
    mutation UnsubscribeFromSkill($skillId: ID!, $owner: String) {
      unsubscribeFromSkill(skillId: $skillId, owner: $owner) { id success error }
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

  // ==================== Relation Tables (RDS) CRUD ====================
  ADD_AGENT_ORG_RELS: `
    mutation AddAgentOrgRels($input: [AgentOrgRelInput!]!) {
      addAgentOrgRels(input: $input)
    }
  `,

  REMOVE_AGENT_ORG_RELS: `
    mutation RemoveAgentOrgRels($input: [RelationIdInput!]!) {
      removeAgentOrgRels(input: $input)
    }
  `,

  ADD_AGENT_SKILL_RELS: `
    mutation AddAgentSkillRels($input: [AgentSkillRelInput!]!) {
      addAgentSkillRels(input: $input)
    }
  `,

  REMOVE_AGENT_SKILL_RELS: `
    mutation RemoveAgentSkillRels($input: [RelationIdInput!]!) {
      removeAgentSkillRels(input: $input)
    }
  `,

  ADD_AGENT_TASK_RELS: `
    mutation AddAgentTaskRels($input: [AgentTaskRelInput!]!) {
      addAgentTaskRels(input: $input)
    }
  `,

  REMOVE_AGENT_TASK_RELS: `
    mutation RemoveAgentTaskRels($input: [RelationIdInput!]!) {
      removeAgentTaskRels(input: $input)
    }
  `,

  ADD_AGENT_TASK_SKILL_RELS: `
    mutation AddAgentTaskSkillRels($input: [AgentTaskSkillRelInput!]!) {
      addAgentTaskSkillRels(input: $input)
    }
  `,

  REMOVE_AGENT_TASK_SKILL_RELS: `
    mutation RemoveAgentTaskSkillRels($input: [RelationIdInput!]!) {
      removeAgentTaskSkillRels(input: $input)
    }
  `,

  // Placeholders (not currently used by web UI)
  ADD_AGENT_SKILL_TOOL_RELS: `
    mutation AddAgentSkillToolRels($input: [AgentSkillToolRelInput!]!) {
      addAgentSkillToolRels(input: $input)
    }
  `,

  REMOVE_AGENT_SKILL_TOOL_RELS: `
    mutation RemoveAgentSkillToolRels($input: [RelationIdInput!]!) {
      removeAgentSkillToolRels(input: $input)
    }
  `,

  ADD_AGENT_SKILL_KNOWLEDGE_RELS: `
    mutation AddAgentSkillKnowledgeRels($input: [AgentSkillKnowledgeRelInput!]!) {
      addAgentSkillKnowledgeRels(input: $input)
    }
  `,

  REMOVE_AGENT_SKILL_KNOWLEDGE_RELS: `
    mutation RemoveAgentSkillKnowledgeRels($input: [RelationIdInput!]!) {
      removeAgentSkillKnowledgeRels(input: $input)
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
      addWareHouses(input: $input) { id name code contact_name contact_phone status notes created_at updated_at }
    }
  `,

  UPDATE_WAREHOUSES: `
    mutation UpdateWarehouses($input: [WarehouseUpdateInput!]!) {
      UpdateWarehouses(input: $input) { id name code contact_name contact_phone status notes created_at updated_at }
    }
  `,

  REMOVE_WAREHOUSES: `
    mutation RemoveWareHouses($ids: [ID!]!) {
      RemoveWareHouses(ids: $ids) { id success message }
    }
  `,

  // ==================== Label Formats Management ====================
  ADD_LABEL_FORMATS: `
    mutation AddLabelFormats($input: [LabelFormatInput!]!) {
      addLabelFormats(input: $input) { id name size settings status created_at updated_at }
    }
  `,

  UPDATE_LABEL_FORMATS: `
    mutation UpdateLabelFormats($input: [LabelFormatUpdateInput!]!) {
      UpdateLabelFormats(input: $input) { id name size settings status created_at updated_at }
    }
  `,

  REMOVE_LABEL_FORMATS: `
    mutation RemoveLabelFormats($ids: [ID!]!) {
      RemoveLabelFormats(ids: $ids) { id success message }
    }
  `,

  // ==================== Products Management ====================
  ADD_PRODUCTS: `
    mutation AddProducts($input: [ProductInput!]!) {
      addProducts(input: $input) { id name sku barcode description status attributes created_at updated_at }
    }
  `,

  UPDATE_PRODUCTS: `
    mutation UpdateProducts($input: [ProductUpdateInput!]!) {
      updateProducts(input: $input) { id name sku barcode description status attributes created_at updated_at }
    }
  `,

  REMOVE_PRODUCTS: `
    mutation RemoveProducts($ids: [ID!]!) {
      removeProducts(ids: $ids) { id success message }
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
      copySkillTo(input: $input) { skillRoot name diagramPath skillId }
    }
  `,

  // ==================== Skill Revisions ====================
  REVERT_SKILL_REVISION: `
    mutation RevertSkillRevision($input: RevertSkillRevisionInput!) {
      revertSkillRevision(input: $input) {
        success restoredFrom restoredTo size
      }
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
  // Note: Using inline input construction with $skill as direct AWSJSON variable
  // because AWSJSON inside input types doesn't serialize correctly via GraphQL variables
  RUN_SKILL: `
    mutation RunSkill($username: String, $skill: AWSJSON!, $meta_data: AWSJSON!) {
      runSkill(input: { username: $username, skill: $skill, meta_data: $meta_data }) { runId status message data }
    }
  `,

  PAUSE_RUN_SKILL: `
    mutation PauseRunSkill($username: String, $skill: AWSJSON) {
      pauseRunSkill(input: { username: $username, skill: $skill }) { runId status message data }
    }
  `,

  RESUME_RUN_SKILL: `
    mutation ResumeRunSkill($username: String, $skill: AWSJSON) {
      resumeRunSkill(input: { username: $username, skill: $skill }) { runId status message data }
    }
  `,

  STEP_RUN_SKILL: `
    mutation StepRunSkill($username: String, $skill: AWSJSON) {
      stepRunSkill(input: { username: $username, skill: $skill }) { runId status message data }
    }
  `,

  CANCEL_RUN_SKILL: `
    mutation CancelRunSkill($username: String, $skill: AWSJSON) {
      cancelRunSkill(input: { username: $username, skill: $skill }) { runId status message data }
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

  // ==================== Settings ====================
  UPDATE_SETTINGS: `
    mutation UpdateSettings($input: [AWSJSON]!) {
      updateSettings(input: $input)
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

  // ==================== RAG Document Management ====================
  RAG_REQUEST_UPLOAD_URLS: `
    mutation RAGRequestUploadURLs($input: [RAGUploadRequestInput!]!) {
      ragRequestUploadURLs(input: $input) {
        uploadUrl docKey expiresIn
      }
    }
  `,

  RAG_CONFIRM_UPLOADS: `
    mutation RAGConfirmUploads($docKeys: [String!]!, $pid: String) {
      ragConfirmUploads(docKeys: $docKeys, pid: $pid)
    }
  `,

  RAG_TRIGGER_INDEX: `
    mutation RAGTriggerIndex($pid: String) {
      ragTriggerIndex(pid: $pid) {
        status message taskArn lastIndexedAt docCount chunkCount
      }
    }
  `,

  RAG_DELETE_DOCS: `
    mutation RAGDeleteDocs($input: RAGDeleteDocsInput!) {
      ragDeleteDocs(input: $input)
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

import { appSyncRequest } from './appSyncClient';

export interface GetAllMineResponse {
  agents: any[];
  tasks: any[];
  skills: any[];
  tools: any[];
  knowledges: any[];
  prompts: any[];
  orgs: any;
  avatars: any[];
  vehicles: any[];
  accountInfo?: any;
}

const GET_ALL_MINE_QUERY = `
  query GetAllMine {
    getAllMine {
      agents { id name owner description status rank supervisor_id avatar_resource_id title capabilities extra_data personalities url vehicle_id version created_at updated_at }
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
`;

const GET_ORG_AGENT_TREE_QUERY = `
  fragment OrgTreeNodeFields on OrgTree {
    id
    name
    description
    org_type
    level
    sort_order
    status
    parent_id
    agents {
      id
      name
      description
      status
      created_at
      updated_at
      owner
      avatar_resource_id
    }
  }

  query GetOrgAgentTree($rootId: ID) {
    getOrgAgentTree(root_id: $rootId) {
      ...OrgTreeNodeFields
      children {
        ...OrgTreeNodeFields
        children {
          ...OrgTreeNodeFields
          children {
            ...OrgTreeNodeFields
          }
        }
      }
    }
  }
`;

const QUERY_ORGS_BY_NAME = `
  query QueryOrgs($input: OrgQueryInput) {
    queryOrgs(input: $input) {
      id
      name
      description
      org_type
    }
  }
`;

const GET_WAREHOUSES_QUERY = `
  query GetWarehouses($input: WarehouseQueryInput) {
    getWarehouses(input: $input) {
      id
      name
      code
      address {
        line1
        line2
        city
        state
        postal_code
        country
      }
      contact_name
      contact_phone
      status
      notes
      created_at
      updated_at
    }
  }
`;

const GET_LABEL_FORMATS_QUERY = `
  query GetLabelFormats($input: LabelFormatQueryInput) {
    getLabelFormats(input: $input) {
      id
      name
      unit
      sheet_width
      sheet_height
      label_width
      label_height
      top_margin
      left_margin
      rows
      cols
      row_pitch
      col_pitch
      _filepath
      _filename
    }
  }
`;

const GET_PRODUCTS_QUERY = `
  query GetProducts($input: ProductQueryInput) {
    getProducts(input: $input) {
      id
      sku
      name
      description
      barcode
      weight_grams
      dimensions_cm {
        length_cm
        width_cm
        height_cm
      }
      attributes
      status
      created_at
      updated_at
    }
  }
`;

const GET_INVENTORIES_QUERY = `
  query GetInventories($input: InventoryQueryInput) {
    getInventories(input: $input) {
      id
      warehouse_id
      product_id
      on_hand
      reserved
      available
      bin_location
      status
      updated_at
    }
  }
`;

const GET_NODE_STATE_SCHEMA_QUERY = `
  query GetNodeStateSchema {
    getNodeStateSchema {
      schemaVersion
      schema
    }
  }
`;

const READ_SKILL_FILE_QUERY = `
  query ReadSkillFile($filePath: String!) {
    readSkillFile(filePath: $filePath) {
      content
      filePath
      fileName
      fileSize
      skillName
    }
  }
`;

const OPEN_SKILL_FILE_QUERY = `
  query OpenSkillFile($filePath: String!, $skillName: String) {
    openSkillFile(filePath: $filePath, skillName: $skillName) {
      content
      filePath
      fileName
      fileSize
      skillName
    }
  }
`;

const LIST_SKILL_FILES_QUERY = `
  query ListSkillFiles($prefix: String, $limit: Int, $nextToken: String) {
    listSkillFiles(prefix: $prefix, limit: $limit, nextToken: $nextToken) {
      filePath
      fileName
      fileSize
      skillName
      updatedAt
    }
  }
`;

const CHECK_SKILL_EXISTS_QUERY = `
  query CheckSkillExists($name: String!) {
    checkSkillExists(name: $name) {
      exists
      name
    }
  }
`;

const GET_EDITOR_CACHE_QUERY = `
  query GetEditorCache($userId: ID!) {
    getEditorCache(userId: $userId) {
      cacheData
      recentFiles {
        filePath
        fileName
        skillName
        lastOpened
      }
    }
  }
`;

const GET_SKILL_RUN_STATUS_QUERY = `
  query GetSkillRunStatus($runId: ID!, $since: AWSDateTime) {
    getSkillRunStatus(runId: $runId, since: $since) {
      runId
      status
      current_node
      this_node
      nodeState
      timestamp
    }
  }
`;

const GET_SKILL_EDITOR_EVENTS_QUERY = `
  query GetSkillEditorEvents($sessionId: String!, $since: AWSDateTime) {
    getSkillEditorEvents(sessionId: $sessionId, since: $since) {
      eventId
      type
      timestamp
      sessionId
      payload
    }
  }
`;

const LOAD_SKILL_EDITOR_CONTEXTS_QUERY = `
  query LoadSkillEditorContexts($input: SkillEditorContextRequestInput!) {
    loadSkillEditorContexts(input: $input) {
      items {
        skillId
        skillName
        context
        updatedAt
      }
    }
  }
`;

const GET_SKILL_EDITOR_CHAT_SESSIONS_QUERY = `
  query GetSkillEditorChatSessions($userId: ID!) {
    getSkillEditorChatSessions(userId: $userId) {
      id
      name
      flowgramId
      createdAt
      updatedAt
    }
  }
`;

const GET_SKILL_EDITOR_CHAT_HISTORY_QUERY = `
  query GetSkillEditorChatHistory($sessionId: ID!, $limit: Int, $offset: Int) {
    getSkillEditorChatHistory(sessionId: $sessionId, limit: $limit, offset: $offset) {
      id
      role
      content
      timestamp
      attachments
      metadata
    }
  }
`;

const WRITE_SKILL_FILE_MUTATION = `
  mutation WriteSkillFile($input: [SkillFileInput!]!) {
    writeSkillFile(input: $input) {
      filePath
      fileName
      fileSize
      skillName
      updatedAt
    }
  }
`;

const SCAFFOLD_SKILL_MUTATION = `
  mutation ScaffoldSkill($input: SkillScaffoldInput!) {
    scaffoldSkill(input: $input) {
      skillRoot
      name
      diagramPath
    }
  }
`;

const COPY_SKILL_TO_MUTATION = `
  mutation CopySkillTo($input: SkillCopyInput!) {
    copySkillTo(input: $input) {
      skillRoot
      name
      diagramPath
    }
  }
`;

const SAVE_EDITOR_CACHE_MUTATION = `
  mutation SaveEditorCache($input: EditorCacheInput!) {
    saveEditorCache(input: $input) {
      renamed
      newFilePath
    }
  }
`;

const CLEAR_EDITOR_CACHE_MUTATION = `
  mutation ClearEditorCache($userId: ID!) {
    clearEditorCache(userId: $userId)
  }
`;

const RUN_SKILL_MUTATION = `
  mutation RunSkill($input: RunSkillInput!) {
    runSkill(input: $input) {
      runId
      status
      message
      data
    }
  }
`;

const PAUSE_RUN_SKILL_MUTATION = `
  mutation PauseRunSkill($input: RunControlInput!) {
    pauseRunSkill(input: $input) {
      runId
      status
      message
      data
    }
  }
`;

const RESUME_RUN_SKILL_MUTATION = `
  mutation ResumeRunSkill($input: RunControlInput!) {
    resumeRunSkill(input: $input) {
      runId
      status
      message
      data
    }
  }
`;

const STEP_RUN_SKILL_MUTATION = `
  mutation StepRunSkill($input: RunControlInput!) {
    stepRunSkill(input: $input) {
      runId
      status
      message
      data
    }
  }
`;

const CANCEL_RUN_SKILL_MUTATION = `
  mutation CancelRunSkill($input: RunControlInput!) {
    cancelRunSkill(input: $input) {
      runId
      status
      message
      data
    }
  }
`;

const SETUP_SIM_STEP_MUTATION = `
  mutation SetupSimStep($bundle: AWSJSON!) {
    setupSimStep(bundle: $bundle) {
      runId
      status
      message
      data
    }
  }
`;

const STEP_SIM_MUTATION = `
  mutation StepSim {
    stepSim {
      runId
      status
      message
      data
    }
  }
`;

const TEST_LANGGRAPH2_FLOWGRAM_MUTATION = `
  mutation TestLanggraph2Flowgram {
    testLanggraph2Flowgram {
      runId
      status
      message
      data
    }
  }
`;

const SIM_TIMER_EVENT_MUTATION = `
  mutation SimTimerEvent {
    simTimerEvent {
      runId
      status
      message
      data
    }
  }
`;

const SIM_WEBSOCKET_EVENT_MUTATION = `
  mutation SimWebsocketEvent {
    simWebsocketEvent {
      runId
      status
      message
      data
    }
  }
`;

const SIM_SSE_EVENT_MUTATION = `
  mutation SimSseEvent {
    simSseEvent {
      runId
      status
      message
      data
    }
  }
`;

const SIM_WEBHOOK_EVENT_MUTATION = `
  mutation SimWebhookEvent {
    simWebhookEvent {
      runId
      status
      message
      data
    }
  }
`;

const SET_SKILL_BREAKPOINTS_MUTATION = `
  mutation SetSkillBreakpoints($username: String!, $nodeName: String!) {
    setSkillBreakpoints(username: $username, node_name: $nodeName) {
      success
      message
      data
    }
  }
`;

const CLEAR_SKILL_BREAKPOINTS_MUTATION = `
  mutation ClearSkillBreakpoints($username: String!, $nodeName: String!) {
    clearSkillBreakpoints(username: $username, node_name: $nodeName) {
      success
      message
      data
    }
  }
`;

const REQUEST_SKILL_STATE_MUTATION = `
  mutation RequestSkillState($username: String!, $skill: AWSJSON!) {
    requestSkillState(username: $username, skill: $skill) {
      success
      message
      data
    }
  }
`;

const INJECT_SKILL_STATE_MUTATION = `
  mutation InjectSkillState($username: String!, $skill: AWSJSON!) {
    injectSkillState(username: $username, skill: $skill) {
      success
      message
      data
    }
  }
`;

const LOAD_SKILL_SCHEMAS_MUTATION = `
  mutation LoadSkillSchemas($username: String!, $skill: AWSJSON!) {
    loadSkillSchemas(username: $username, skill: $skill) {
      success
      message
      data
    }
  }
`;

const CREATE_SKILL_EDITOR_CHAT_SESSION_MUTATION = `
  mutation CreateSkillEditorChatSession($input: SkillEditorChatSessionInput!) {
    createSkillEditorChatSession(input: $input) {
      id
      name
      flowgramId
      createdAt
      updatedAt
    }
  }
`;

const SEND_SKILL_EDITOR_CHAT_MESSAGE_MUTATION = `
  mutation SendSkillEditorChatMessage($input: SkillEditorChatMessageInput!) {
    sendSkillEditorChatMessage(input: $input) {
      sessionId
      sessionName
      state
      intent
      message {
        id
        role
        content
        timestamp
        attachments
        metadata
      }
      clarification
      plan
      flowgram
      validation
    }
  }
`;

const CANCEL_SKILL_EDITOR_CHAT_GENERATION_MUTATION = `
  mutation CancelSkillEditorChatGeneration($sessionId: ID!) {
    cancelSkillEditorChatGeneration(sessionId: $sessionId)
  }
`;

const DELETE_SKILL_EDITOR_CHAT_SESSION_MUTATION = `
  mutation DeleteSkillEditorChatSession($sessionId: ID!) {
    deleteSkillEditorChatSession(sessionId: $sessionId)
  }
`;


export const webApi = {
  async getAllMine(): Promise<GetAllMineResponse> {
    const data = await appSyncRequest<{ getAllMine: GetAllMineResponse }>(GET_ALL_MINE_QUERY);
    return data.getAllMine;
  },

  async getOrgAgentTree(rootId?: string): Promise<any> {
    const data = await appSyncRequest<{ getOrgAgentTree: any }>(
      GET_ORG_AGENT_TREE_QUERY,
      { rootId }
    );
    return data.getOrgAgentTree;
  },

  async queryOrgsByName(companyName: string): Promise<any[]> {
    const trimmed = companyName.trim();
    if (!trimmed) return [];

    const data = await appSyncRequest<{ queryOrgs: any[] }>(
      QUERY_ORGS_BY_NAME,
      { input: { name: trimmed } }
    );

    return data.queryOrgs || [];
  },

  async getWarehouses(input?: Record<string, any>): Promise<any[]> {
    const data = await appSyncRequest<{ getWarehouses: any[] }>(
      GET_WAREHOUSES_QUERY,
      { input }
    );
    return data.getWarehouses || [];
  },

  async getLabelFormats(input?: Record<string, any>): Promise<any[]> {
    const data = await appSyncRequest<{ getLabelFormats: any[] }>(
      GET_LABEL_FORMATS_QUERY,
      { input }
    );
    return data.getLabelFormats || [];
  },

  async getProducts(input?: Record<string, any>): Promise<any[]> {
    const data = await appSyncRequest<{ getProducts: any[] }>(
      GET_PRODUCTS_QUERY,
      { input }
    );
    return data.getProducts || [];
  },

  async getInventories(input?: Record<string, any>): Promise<any[]> {
    const data = await appSyncRequest<{ getInventories: any[] }>(
      GET_INVENTORIES_QUERY,
      { input }
    );
    return data.getInventories || [];
  },

  async getNodeStateSchema(): Promise<any | null> {
    const data = await appSyncRequest<{ getNodeStateSchema: any }>(GET_NODE_STATE_SCHEMA_QUERY);
    return data.getNodeStateSchema || null;
  },

  async readSkillFile(filePath: string): Promise<any[] | null> {
    const data = await appSyncRequest<{ readSkillFile: any[] }>(READ_SKILL_FILE_QUERY, { filePath });
    return data.readSkillFile || null;
  },

  async openSkillFile(filePath: string, skillName?: string): Promise<any | null> {
    const data = await appSyncRequest<{ openSkillFile: any }>(OPEN_SKILL_FILE_QUERY, { filePath, skillName });
    return data.openSkillFile || null;
  },

  async listSkillFiles(prefix?: string, limit?: number, nextToken?: string): Promise<any[]> {
    const data = await appSyncRequest<{ listSkillFiles: any[] }>(LIST_SKILL_FILES_QUERY, {
      prefix,
      limit,
      nextToken,
    });
    return data.listSkillFiles || [];
  },

  async checkSkillExists(name: string): Promise<any | null> {
    const data = await appSyncRequest<{ checkSkillExists: any }>(CHECK_SKILL_EXISTS_QUERY, { name });
    return data.checkSkillExists || null;
  },

  async getEditorCache(userId: string): Promise<any | null> {
    const data = await appSyncRequest<{ getEditorCache: any }>(GET_EDITOR_CACHE_QUERY, { userId });
    return data.getEditorCache || null;
  },

  async getSkillRunStatus(runId: string, since?: string): Promise<any[]> {
    const data = await appSyncRequest<{ getSkillRunStatus: any[] }>(GET_SKILL_RUN_STATUS_QUERY, { runId, since });
    return data.getSkillRunStatus || [];
  },

  async getSkillEditorEvents(sessionId: string, since?: string): Promise<any[]> {
    const data = await appSyncRequest<{ getSkillEditorEvents: any[] }>(GET_SKILL_EDITOR_EVENTS_QUERY, {
      sessionId,
      since,
    });
    return data.getSkillEditorEvents || [];
  },

  async loadSkillEditorContexts(input: Record<string, any>): Promise<any[]> {
    const data = await appSyncRequest<{ loadSkillEditorContexts: { items: any[] } }>(
      LOAD_SKILL_EDITOR_CONTEXTS_QUERY,
      { input }
    );
    return data.loadSkillEditorContexts?.items || [];
  },

  async getSkillEditorChatSessions(userId: string): Promise<any[]> {
    const data = await appSyncRequest<{ getSkillEditorChatSessions: any[] }>(
      GET_SKILL_EDITOR_CHAT_SESSIONS_QUERY,
      { userId }
    );
    return data.getSkillEditorChatSessions || [];
  },

  async getSkillEditorChatHistory(sessionId: string, limit?: number, offset?: number): Promise<any[]> {
    const data = await appSyncRequest<{ getSkillEditorChatHistory: any[] }>(
      GET_SKILL_EDITOR_CHAT_HISTORY_QUERY,
      { sessionId, limit, offset }
    );
    return data.getSkillEditorChatHistory || [];
  },

  async writeSkillFile(input: Record<string, any> | Array<Record<string, any>>): Promise<any | null> {
    const payload = Array.isArray(input) ? input : [input];
    try {
      const data = await appSyncRequest<{ writeSkillFile: any[] }>(WRITE_SKILL_FILE_MUTATION, { input: payload });
      const result = data.writeSkillFile || [];
      return Array.isArray(input) ? result : (result[0] || null);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const normalized = message.toLowerCase();
      const isNullFilePathError =
        normalized.includes('cannot return null for non-nullable type') &&
        normalized.includes('skillfileinfo') &&
        normalized.includes('/writeskillfile/filepath');
      if (isNullFilePathError) {
        console.warn('[AppSyncClient] writeSkillFile returned null filePath. Using fallback response.', message);
        const fallback = payload.map((item) => {
          const filePath = String(item?.filePath || '').trim();
          const fileName = filePath.split('/').pop() || '';
          const content = item?.content;
          const fileSize = typeof content === 'string' ? content.length : undefined;
          return {
            filePath,
            fileName,
            fileSize,
            skillName: item?.skillName,
            updatedAt: new Date().toISOString(),
          };
        });
        return Array.isArray(input) ? fallback : (fallback[0] || null);
      }
      throw error;
    }
  },

  async scaffoldSkill(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ scaffoldSkill: any }>(SCAFFOLD_SKILL_MUTATION, { input });
    return data.scaffoldSkill || null;
  },

  async copySkillTo(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ copySkillTo: any }>(COPY_SKILL_TO_MUTATION, { input });
    return data.copySkillTo || null;
  },

  async saveEditorCache(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ saveEditorCache: any }>(SAVE_EDITOR_CACHE_MUTATION, { input });
    return data.saveEditorCache || null;
  },

  async clearEditorCache(userId: string): Promise<boolean> {
    const data = await appSyncRequest<{ clearEditorCache: boolean }>(CLEAR_EDITOR_CACHE_MUTATION, { userId });
    return !!data.clearEditorCache;
  },

  async runSkill(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ runSkill: any }>(RUN_SKILL_MUTATION, { input });
    return data.runSkill || null;
  },

  async pauseRunSkill(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ pauseRunSkill: any }>(PAUSE_RUN_SKILL_MUTATION, { input });
    return data.pauseRunSkill || null;
  },

  async resumeRunSkill(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ resumeRunSkill: any }>(RESUME_RUN_SKILL_MUTATION, { input });
    return data.resumeRunSkill || null;
  },

  async stepRunSkill(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ stepRunSkill: any }>(STEP_RUN_SKILL_MUTATION, { input });
    return data.stepRunSkill || null;
  },

  async cancelRunSkill(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ cancelRunSkill: any }>(CANCEL_RUN_SKILL_MUTATION, { input });
    return data.cancelRunSkill || null;
  },

  async setupSimStep(bundle: any): Promise<any | null> {
    const data = await appSyncRequest<{ setupSimStep: any }>(SETUP_SIM_STEP_MUTATION, { bundle });
    return data.setupSimStep || null;
  },

  async stepSim(): Promise<any | null> {
    const data = await appSyncRequest<{ stepSim: any }>(STEP_SIM_MUTATION);
    return data.stepSim || null;
  },

  async testLanggraph2Flowgram(): Promise<any | null> {
    const data = await appSyncRequest<{ testLanggraph2Flowgram: any }>(TEST_LANGGRAPH2_FLOWGRAM_MUTATION);
    return data.testLanggraph2Flowgram || null;
  },

  async simTimerEvent(): Promise<any | null> {
    const data = await appSyncRequest<{ simTimerEvent: any }>(SIM_TIMER_EVENT_MUTATION);
    return data.simTimerEvent || null;
  },

  async simWebsocketEvent(): Promise<any | null> {
    const data = await appSyncRequest<{ simWebsocketEvent: any }>(SIM_WEBSOCKET_EVENT_MUTATION);
    return data.simWebsocketEvent || null;
  },

  async simSseEvent(): Promise<any | null> {
    const data = await appSyncRequest<{ simSseEvent: any }>(SIM_SSE_EVENT_MUTATION);
    return data.simSseEvent || null;
  },

  async simWebhookEvent(): Promise<any | null> {
    const data = await appSyncRequest<{ simWebhookEvent: any }>(SIM_WEBHOOK_EVENT_MUTATION);
    return data.simWebhookEvent || null;
  },

  async setSkillBreakpoints(username: string, nodeName: string): Promise<any | null> {
    const data = await appSyncRequest<{ setSkillBreakpoints: any }>(SET_SKILL_BREAKPOINTS_MUTATION, {
      username,
      nodeName,
    });
    return data.setSkillBreakpoints || null;
  },

  async clearSkillBreakpoints(username: string, nodeName: string): Promise<any | null> {
    const data = await appSyncRequest<{ clearSkillBreakpoints: any }>(CLEAR_SKILL_BREAKPOINTS_MUTATION, {
      username,
      nodeName,
    });
    return data.clearSkillBreakpoints || null;
  },

  async requestSkillState(username: string, skill: any): Promise<any | null> {
    const data = await appSyncRequest<{ requestSkillState: any }>(REQUEST_SKILL_STATE_MUTATION, {
      username,
      skill,
    });
    return data.requestSkillState || null;
  },

  async injectSkillState(username: string, skill: any): Promise<any | null> {
    const data = await appSyncRequest<{ injectSkillState: any }>(INJECT_SKILL_STATE_MUTATION, {
      username,
      skill,
    });
    return data.injectSkillState || null;
  },

  async loadSkillSchemas(username: string, skill: any): Promise<any | null> {
    const data = await appSyncRequest<{ loadSkillSchemas: any }>(LOAD_SKILL_SCHEMAS_MUTATION, {
      username,
      skill,
    });
    return data.loadSkillSchemas || null;
  },

  async createSkillEditorChatSession(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ createSkillEditorChatSession: any }>(
      CREATE_SKILL_EDITOR_CHAT_SESSION_MUTATION,
      { input },
      undefined,
      'skill_editor.chat.create_session'
    );
    return data.createSkillEditorChatSession || null;
  },

  async sendSkillEditorChatMessage(input: Record<string, any>): Promise<any | null> {
    const data = await appSyncRequest<{ sendSkillEditorChatMessage: any }>(
      SEND_SKILL_EDITOR_CHAT_MESSAGE_MUTATION,
      { input },
      undefined,
      'skill_editor.chat.send_message'
    );
    return data.sendSkillEditorChatMessage || null;
  },

  async cancelSkillEditorChatGeneration(sessionId: string): Promise<boolean> {
    const data = await appSyncRequest<{ cancelSkillEditorChatGeneration: boolean }>(
      CANCEL_SKILL_EDITOR_CHAT_GENERATION_MUTATION,
      { sessionId },
      undefined,
      'skill_editor.chat.cancel_generation'
    );
    return !!data.cancelSkillEditorChatGeneration;
  },

  async deleteSkillEditorChatSession(sessionId: string): Promise<boolean> {
    const data = await appSyncRequest<{ deleteSkillEditorChatSession: boolean }>(
      DELETE_SKILL_EDITOR_CHAT_SESSION_MUTATION,
      { sessionId },
      undefined,
      'skill_editor.chat.delete_session'
    );
    return !!data.deleteSkillEditorChatSession;
  },
};

// /**
//  * API Client - 类型安全的 API 调用接口
//  * 
//  * 提供：
//  * 1. 类型安全的 API 方法
//  * 2. 统一的错误处理
//  * 3. 便捷的调用方式
//  */

// import { apiRouter } from './api-router';
// import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from './api-config';
// import type { APIResponse } from '../ipc/api';

// /**
//  * API 客户端
//  * 
//  * 封装所有业务 API 调用，提供类型安全的接口
//  */
// export class APIClient {
//   private static instance: APIClient;

//   private constructor() {}

//   /**
//    * 获取 API 客户端单例
//    */
//   public static getInstance(): APIClient {
//     if (!APIClient.instance) {
//       APIClient.instance = new APIClient();
//     }
//     return APIClient.instance;
//   }

//   // ==================== 系统 API ====================

//   /**
//    * 获取系统初始化进度
//    */
//   async getInitializationProgress(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_initialization_progress',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_ALL_MINE,
//           resultPath: 'getAllMine'
//         }
//       }
//     );
//   }

//   // ==================== 用户认证 API ====================

//   /**
//    * 用户登录
//    */
//   async login(username: string, password: string, machineRole: string, lang?: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       { method: 'login' },
//       { username, password, machine_role: machineRole, lang }
//     );
//   }

//   /**
//    * 用户登出
//    */
//   async logout(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'logout' });
//   }

//   /**
//    * Google 登录
//    */
//   async googleLogin(lang?: string, role?: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'google_login' }, { lang, role });
//   }

//   /**
//    * 获取上次登录信息
//    */
//   async getLastLoginInfo(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_last_login' });
//   }

//   // ==================== Agent 管理 API ====================

//   /**
//    * 获取所有数据
//    */
//   async getAll(username: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_all',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_ALL_MINE,
//           resultPath: 'getAllMine'
//         }
//       },
//       { username }
//     );
//   }

//   /**
//    * 获取组织 Agent 树
//    */
//   async getAllOrgAgents(username: string, companyName?: string): Promise<APIResponse<any>> {
//     let company = companyName;
//     if (!company) {
//       try {
//         company = localStorage.getItem('org_company_filter') || undefined;
//       } catch {
//         company = undefined;
//       }
//     }

//     const params = company ? { username, company } : { username };
//     return apiRouter.execute(
//       {
//         method: 'get_all_org_agents',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_ORG_AGENT_TREE,
//           resultPath: 'getOrgAgentTree'
//         }
//       },
//       params
//     );
//   }

//   /**
//    * 获取 Agents
//    */
//   async getAgents(username: string, agentIds?: string[]): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_agents',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_ALL_MINE,
//           resultPath: 'getAllMine.agents'
//         }
//       },
//       { username, agent_id: agentIds || [] }
//     );
//   }

//   /**
//    * 保存 Agent
//    */
//   async saveAgent(username: string, agent: any[]): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'save_agent',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.UPDATE_AGENTS,
//           resultPath: 'updateAgents'
//         }
//       },
//       { username, agent }
//     );
//   }

//   /**
//    * 新建 Agent
//    */
//   async newAgent(username: string, agent: any[]): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'new_agent',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.ADD_AGENTS,
//           resultPath: 'addAgents'
//         }
//       },
//       { username, agent }
//     );
//   }

//   /**
//    * 删除 Agent
//    */
//   async deleteAgent(username: string, agentIds: (string | number)[]): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'delete_agent',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.REMOVE_AGENTS,
//           resultPath: 'removeAgents'
//         }
//       },
//       { username, agent_id: agentIds }
//     );
//   }

//   // ==================== Skill 管理 API ====================

//   /**
//    * 获取 Agent Skills
//    */
//   async getAgentSkills(username: string, skillIds?: string[]): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_agent_skills',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_ALL_MINE,
//           resultPath: 'getAllMine.skills'
//         }
//       },
//       { username, skill_ids: skillIds || [] }
//     );
//   }

//   /**
//    * 读取 Skill 文件
//    */
//   async readSkillFile(filePath: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'read_skill_file',
//         graphql: {
//           query: GRAPHQL_QUERIES.READ_SKILL_FILE,
//           resultPath: 'readSkillFile'
//         }
//       },
//       { filePath }
//     );
//   }

//   /**
//    * 打开 Skill 文件
//    */
//   async openSkillFile(filePath: string, skillName?: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'open_skill_file',
//         graphql: {
//           query: GRAPHQL_QUERIES.OPEN_SKILL_FILE,
//           resultPath: 'openSkillFile'
//         }
//       },
//       { filePath, skillName }
//     );
//   }

//   /**
//    * 写入 Skill 文件
//    */
//   async writeSkillFile(filePath: string, content: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'write_skill_file',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.WRITE_SKILL_FILE,
//           resultPath: 'writeSkillFile'
//         }
//       },
//       { filePath, content }
//     );
//   }

//   /**
//    * 运行 Skill
//    */
//   async runSkill(username: string, skill: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'run_skill',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.RUN_SKILL,
//           resultPath: 'runSkill'
//         }
//       },
//       { username, skill }
//     );
//   }

//   /**
//    * 取消 Skill
//    */
//   async cancelRunSkill(username: string, skill: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'cancel_run_skill',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.CANCEL_RUN_SKILL,
//           resultPath: 'cancelRunSkill'
//         }
//       },
//       { username, skill }
//     );
//   }

//   /**
//    * 暂停 Skill
//    */
//   async pauseRunSkill(username: string, skill: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'pause_run_skill',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.PAUSE_RUN_SKILL,
//           resultPath: 'pauseRunSkill'
//         }
//       },
//       { username, skill }
//     );
//   }

//   /**
//    * 恢复 Skill
//    */
//   async resumeRunSkill(username: string, skill: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'resume_run_skill',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.RESUME_RUN_SKILL,
//           resultPath: 'resumeRunSkill'
//         }
//       },
//       { username, skill }
//     );
//   }

//   /**
//    * 单步执行 Skill
//    */
//   async stepRunSkill(username: string, skill: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'step_run_skill',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.STEP_RUN_SKILL,
//           resultPath: 'stepRunSkill'
//         }
//       },
//       { username, skill }
//     );
//   }

//   // ==================== Task 管理 API ====================

//   /**
//    * 获取 Agent Tasks
//    */
//   async getAgentTasks(username: string, taskIds?: string[]): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_agent_tasks',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_ALL_MINE,
//           resultPath: 'getAllMine.tasks'
//         }
//       },
//       { username, task_ids: taskIds || [] }
//     );
//   }

//   /**
//    * 保存 Agent Task
//    */
//   async saveAgentTask(username: string, taskInfo: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'save_agent_task',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_TASKS,
//           resultPath: 'updateAgentTasks'
//         }
//       },
//       { username, task_info: taskInfo }
//     );
//   }

//   /**
//    * 新建 Agent Task
//    */
//   async newAgentTask(username: string, taskInfo: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'new_agent_task',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.ADD_AGENT_TASKS,
//           resultPath: 'addAgentTasks'
//         }
//       },
//       { username, task_info: taskInfo }
//     );
//   }

//   /**
//    * 删除 Agent Task
//    */
//   async deleteAgentTask(username: string, taskId: string): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'delete_agent_task',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_TASKS,
//           resultPath: 'removeAgentTasks'
//         }
//       },
//       { username, task_id: taskId }
//     );
//   }

//   // ==================== 设置管理 API ====================

//   /**
//    * 获取设置
//    */
//   async getSettings(username: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_settings' }, { username });
//   }

//   /**
//    * 保存设置
//    */
//   async saveSettings(value: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'save_settings',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.UPDATE_AGENTS,
//           resultPath: 'updateAgents'
//         }
//       },
//       { value }
//     );
//   }

//   /**
//    * 获取 LLM Providers
//    */
//   async getLLMProviders(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_llm_providers' });
//   }

//   /**
//    * 设置默认 LLM
//    */
//   async setDefaultLLM(name: string, username: string, model?: string): Promise<APIResponse<any>> {
//     const params: any = { name, username };
//     if (model) params.model = model;
//     return apiRouter.execute({ method: 'set_default_llm' }, params);
//   }

//   /**
//    * 更新 LLM Provider
//    */
//   async updateLLMProvider(
//     name: string,
//     apiKey: string,
//     azureEndpoint?: string,
//     awsAccessKeyId?: string,
//     awsSecretAccessKey?: string
//   ): Promise<APIResponse<any>> {
//     const params: any = { name, api_key: apiKey };
//     if (azureEndpoint) params.azure_endpoint = azureEndpoint;
//     if (awsAccessKeyId) params.aws_access_key_id = awsAccessKeyId;
//     if (awsSecretAccessKey) params.aws_secret_access_key = awsSecretAccessKey;
//     return apiRouter.execute({ method: 'update_llm_provider' }, params);
//   }

//   // ==================== Warehouse 管理 API ====================

//   /**
//    * 获取 Warehouses
//    */
//   async getWarehouses(query?: any): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_warehouses',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_WAREHOUSES,
//           resultPath: 'getWarehouses'
//         }
//       },
//       { query }
//     );
//   }

//   /**
//    * 保存 Warehouse
//    */
//   async saveWarehouse(warehouse: any): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'save_warehouse',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.UPDATE_WAREHOUSES,
//           resultPath: 'UpdateWarehouses'
//         }
//       },
//       { warehouse }
//     );
//   }

//   /**
//    * 删除 Warehouse
//    */
//   async deleteWarehouse(id: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'delete_warehouse' }, { id });
//   }

//   // ==================== Product 管理 API ====================

//   /**
//    * 获取 Products
//    */
//   async getProducts(query?: any): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_products',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_PRODUCTS,
//           resultPath: 'getProducts'
//         }
//       },
//       { query }
//     );
//   }

//   /**
//    * 保存 Product
//    */
//   async saveProduct(product: any): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'save_product' }, { product });
//   }

//   /**
//    * 删除 Product
//    */
//   async deleteProduct(id: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'delete_product' }, { id });
//   }

//   // ==================== Inventory 管理 API ====================

//   /**
//    * 获取 Inventories
//    */
//   async getInventories(query?: any): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_inventories',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_INVENTORIES,
//           resultPath: 'getInventories'
//         }
//       },
//       { query }
//     );
//   }

//   /**
//    * 保存 Inventory
//    */
//   async saveInventory(inventory: any): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'save_inventory' }, { inventory });
//   }

//   /**
//    * 删除 Inventory
//    */
//   async deleteInventory(id: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'delete_inventory' }, { id });
//   }

//   // ==================== Vehicle 管理 API ====================

//   /**
//    * 获取 Vehicles
//    */
//   async getVehicles(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_vehicles' });
//   }

//   /**
//    * 添加 Vehicle
//    */
//   async addVehicle(vehicle: any): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'add_vehicle' }, vehicle);
//   }

//   /**
//    * 更新 Vehicle
//    */
//   async updateVehicle(vehicleId: number, updates: any): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'update_vehicle' }, { vehicle_id: vehicleId, ...updates });
//   }

//   /**
//    * 删除 Vehicle
//    */
//   async deleteVehicle(vehicleId: number): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'delete_vehicle' }, { vehicle_id: vehicleId });
//   }

//   /**
//    * 更新 Vehicle 状态
//    */
//   async updateVehicleStatus(vehicleId: number, status: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'update_vehicle_status' }, { vehicle_id: vehicleId, status });
//   }

//   // ==================== Tools 管理 API ====================

//   /**
//    * 获取 Tools
//    */
//   async getTools(username: string, toolIds?: string[]): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_tools',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_ALL_MINE,
//           resultPath: 'getAllMine.tools'
//         }
//       },
//       { username, tool_ids: toolIds || [] }
//     );
//   }

//   /**
//    * 新建 Tools
//    */
//   async newTools(username: string, tools: any[]): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'new_tools',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.ADD_AGENT_TOOLS,
//           resultPath: 'addAgentTools'
//         }
//       },
//       { username, tools }
//     );
//   }

//   /**
//    * 保存 Tools
//    */
//   async saveTools(username: string, tools: any[]): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'save_tools',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_TOOLS,
//           resultPath: 'updateAgentTools'
//         }
//       },
//       { username, tools }
//     );
//   }

//   /**
//    * 删除 Tools
//    */
//   async deleteTools(username: string, tools: any[]): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'delete_tools',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_TOOLS,
//           resultPath: 'removeAgentTools'
//         }
//       },
//       { username, tools }
//     );
//   }

//   /**
//    * 刷新 Tools Schemas
//    */
//   async refreshToolsSchemas(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'refresh_tools_schemas' });
//   }

//   // ==================== 认证扩展 API ====================

//   /**
//    * 用户注册
//    */
//   async signup(username: string, password: string, lang?: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'signup' }, { username, password, lang });
//   }

//   /**
//    * 忘记密码
//    */
//   async forgotPassword(username: string, lang?: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'forgot_password' }, { username, lang });
//   }

//   /**
//    * 确认忘记密码
//    */
//   async confirmForgotPassword(username: string, confirmCode: string, newPassword: string, lang?: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'confirm_forgot_password' }, { username, confirmCode, newPassword, lang });
//   }

//   // ==================== Skill 管理扩展 API ====================

//   /**
//    * 新建 Agent Skill
//    */
//   async newAgentSkill(username: string, skillInfo: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'new_agent_skill',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.ADD_AGENT_SKILLS,
//           resultPath: 'addAgentSkills'
//         }
//       },
//       { username, skill_info: skillInfo }
//     );
//   }

//   /**
//    * 删除 Agent Skill
//    */
//   async deleteAgentSkill(username: string, skillId: string): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'delete_agent_skill',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_SKILLS,
//           resultPath: 'removeAgentSkills'
//         }
//       },
//       { username, skill_id: skillId }
//     );
//   }

//   /**
//    * 获取公共 Skills
//    */
//   async getPublicSkills(username: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_public_skills' }, { username });
//   }

//   // ==================== Rerank 管理 API ====================

//   /**
//    * 获取 Rerank Providers
//    */
//   async getRerankProviders(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_rerank_providers' });
//   }

//   /**
//    * 设置默认 Rerank
//    */
//   async setDefaultRerank(name: string, username: string, model?: string): Promise<APIResponse<any>> {
//     const params: any = { name, username };
//     if (model) params.model = model;
//     return apiRouter.execute({ method: 'set_default_rerank' }, params);
//   }

//   /**
//    * 更新 Rerank Provider
//    */
//   async updateRerankProvider(name: string, apiKey: string, azureEndpoint?: string): Promise<APIResponse<any>> {
//     const params: any = { name, api_key: apiKey };
//     if (azureEndpoint) params.azure_endpoint = azureEndpoint;
//     return apiRouter.execute({ method: 'update_rerank_provider' }, params);
//   }

//   /**
//    * 设置 Rerank Provider Model
//    */
//   async setRerankProviderModel(name: string, model: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'set_rerank_provider_model' }, { name, model });
//   }

//   /**
//    * 删除 Rerank Provider Config
//    */
//   async deleteRerankProviderConfig(name: string, username: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'delete_rerank_provider_config' }, { name, username });
//   }

//   /**
//    * 获取 Rerank Provider API Key
//    */
//   async getRerankProviderApiKey(name: string, showFull: boolean = false): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_rerank_provider_api_key' }, { name, show_full: showFull });
//   }

//   /**
//    * 获取默认 Rerank
//    */
//   async getDefaultRerank(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_default_rerank' });
//   }

//   // ==================== Ollama API ====================

//   /**
//    * 获取 Ollama Models
//    */
//   async getOllamaModels(host: string, username?: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_ollama_models' }, { host, username });
//   }

//   // ==================== 测试 API ====================

//   /**
//    * 获取可用测试
//    */
//   async getAvailableTests(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_available_tests' });
//   }

//   // ==================== Editor API ====================

//   /**
//    * 获取 Callables
//    */
//   async getCallables(filter?: { text?: string; type?: 'system' | 'custom' }): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_callables' }, filter);
//   }

//   /**
//    * 获取 Editor Agents
//    */
//   async getEditorAgents(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_editor_agents' });
//   }

//   /**
//    * 获取 Editor Pending Sources
//    */
//   async getEditorPendingSources(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_editor_pending_sources' });
//   }

//   /**
//    * 获取 Node State Schema
//    */
//   async getNodeStateSchema(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'skill_editor.get_node_state_schema',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_NODE_STATE_SCHEMA,
//           resultPath: 'getNodeStateSchema'
//         }
//       }
//     );
//   }

//   /**
//    * 保存 Editor Cache
//    */
//   async saveEditorCache(cacheData: any): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'save_editor_cache',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.SAVE_EDITOR_CACHE,
//           resultPath: 'saveEditorCache'
//         }
//       },
//       { cacheData }
//     );
//   }

//   /**
//    * 加载 Editor Cache
//    */
//   async loadEditorCache(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'load_editor_cache',
//         graphql: {
//           query: GRAPHQL_QUERIES.GET_EDITOR_CACHE,
//           resultPath: 'getEditorCache'
//         }
//       }
//     );
//   }

//   // ==================== Org 管理 API ====================

//   /**
//    * 获取 Orgs
//    */
//   async getOrgs(username: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'get_orgs',
//         graphql: {
//           query: GRAPHQL_QUERIES.QUERY_ORGS,
//           resultPath: 'queryOrgs'
//         }
//       },
//       { username }
//     );
//   }

//   /**
//    * 更新 Org
//    */
//   async updateOrg(username: string, orgId: string, name?: string, description?: string, parentId?: string | null): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'update_org' }, { username, org_id: orgId, name, description, parent_id: parentId });
//   }

//   /**
//    * 删除 Org
//    */
//   async deleteOrg(username: string, orgId: string, force: boolean = false): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'delete_org' }, { username, org_id: orgId, force });
//   }

//   /**
//    * 获取 Org Agents
//    */
//   async getOrgAgents(username: string, orgId: string, includeDescendants?: boolean): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_org_agents' }, { username, org_id: orgId, include_descendants: includeDescendants });
//   }

//   /**
//    * 获取可绑定的 Agents
//    */
//   async getAvailableAgentsForBinding(username: string, orgId: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_available_agents_for_binding' }, { username, org_id: orgId });
//   }

//   // ==================== Browser Use Settings API ====================

//   /**
//    * 获取 Browser Use Settings
//    */
//   async getBrowserUseSettings(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_browser_use_settings' });
//   }

//   /**
//    * 保存 Browser Use Settings
//    */
//   async saveBrowserUseSettings(settings: any): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'save_browser_use_settings' }, settings);
//   }

//   // ==================== LLM 管理扩展 API ====================

//   /**
//    * 设置 LLM Provider Model
//    */
//   async setLLMProviderModel(name: string, model: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'set_llm_provider_model' }, { name, model });
//   }

//   /**
//    * 设置 LLM Provider Enable Thinking
//    */
//   async setLLMProviderEnableThinking(name: string, enableThinking: boolean): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'set_llm_provider_enable_thinking' }, { name, enable_thinking: enableThinking });
//   }

//   /**
//    * 删除 LLM Provider Config
//    */
//   async deleteLLMProviderConfig(name: string, username: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'delete_llm_provider_config' }, { name, username });
//   }

//   /**
//    * 获取 LLM Provider API Key
//    */
//   async getLLMProviderApiKey(name: string, showFull: boolean = false): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_llm_provider_api_key' }, { name, show_full: showFull });
//   }

//   /**
//    * 获取已配置的 LLM Providers
//    */
//   async getConfiguredLLMProviders(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_configured_llm_providers' });
//   }

//   /**
//    * 获取带凭证的 LLM Providers
//    */
//   async getLLMProvidersWithCredentials(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_llm_providers_with_credentials' });
//   }

//   // ==================== Embedding 管理扩展 API ====================

//   /**
//    * 获取 Embedding Providers
//    */
//   async getEmbeddingProviders(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_embedding_providers' });
//   }

//   /**
//    * 设置 Embedding Provider Model
//    */
//   async setEmbeddingProviderModel(name: string, model: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'set_embedding_provider_model' }, { name, model });
//   }

//   /**
//    * 删除 Embedding Provider Config
//    */
//   async deleteEmbeddingProviderConfig(name: string, username: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'delete_embedding_provider_config' }, { name, username });
//   }

//   /**
//    * 获取 Embedding Provider API Key
//    */
//   async getEmbeddingProviderApiKey(name: string, showFull: boolean = false): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_embedding_provider_api_key' }, { name, show_full: showFull });
//   }

//   /**
//    * 获取默认 Embedding
//    */
//   async getDefaultEmbedding(): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'get_default_embedding' });
//   }

//   // ==================== Skill 管理扩展 API ====================

//   /**
//    * 保存 Agent Skill
//    */
//   async saveAgentSkill(username: string, skillInfo: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'save_agent_skill',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_SKILLS,
//           resultPath: 'updateAgentSkills'
//         }
//       },
//       { username, skill_info: skillInfo }
//     );
//   }

//   /**
//    * 设置 Skill Breakpoints
//    */
//   async setSkillBreakpoints(username: string, nodeName: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'set_skill_breakpoints',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.SET_SKILL_BREAKPOINTS,
//           resultPath: 'setSkillBreakpoints'
//         }
//       },
//       { username, node_name: nodeName }
//     );
//   }

//   /**
//    * 清除 Skill Breakpoints
//    */
//   async clearSkillBreakpoints(username: string, nodeName: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'clear_skill_breakpoints',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.CLEAR_SKILL_BREAKPOINTS,
//           resultPath: 'clearSkillBreakpoints'
//         }
//       },
//       { username, node_name: nodeName }
//     );
//   }

//   /**
//    * 请求 Skill State
//    */
//   async requestSkillState(username: string, skill: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'request_skill_state',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.REQUEST_SKILL_STATE,
//           resultPath: 'requestSkillState'
//         }
//       },
//       { username, skill }
//     );
//   }

//   /**
//    * 注入 Skill State
//    */
//   async injectSkillState(username: string, skill: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'inject_skill_state',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.INJECT_SKILL_STATE,
//           resultPath: 'injectSkillState'
//         }
//       },
//       { username, skill }
//     );
//   }

//   /**
//    * 加载 Skill Schemas
//    */
//   async loadSkillSchemas(username: string, skill: any): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'load_skill_schemas',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.LOAD_SKILL_SCHEMAS,
//           resultPath: 'loadSkillSchemas'
//         }
//       },
//       { username, skill }
//     );
//   }

//   // ==================== Knowledge 管理扩展 API ====================

//   /**
//    * 保存 Knowledges
//    */
//   async saveKnowledges(values: any[]): Promise<APIResponse<void>> {
//     return apiRouter.execute(
//       {
//         method: 'save_knowledges',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_KNOWLEDGES,
//           resultPath: 'updateAgentKnowledges'
//         }
//       },
//       values
//     );
//   }

//   // ==================== Org 管理扩展 API ====================

//   /**
//    * 创建 Org
//    */
//   async createOrg(username: string, name: string, description?: string, parentId?: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'create_org' }, { username, name, description, parent_id: parentId });
//   }

//   /**
//    * 绑定 Agent 到 Org
//    */
//   async bindAgentToOrg(username: string, agentId: string, orgId: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'bind_agent_to_org' }, { username, agent_id: agentId, org_id: orgId });
//   }

//   /**
//    * 解绑 Agent 从 Org
//    */
//   async unbindAgentFromOrg(username: string, agentId: string, orgId: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'unbind_agent_from_org' }, { username, agent_id: agentId, org_id: orgId });
//   }

//   // ==================== Editor Cache API ====================

//   /**
//    * 清除 Editor Cache
//    */
//   async clearEditorCache(userId: string): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'clear_editor_cache',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.CLEAR_EDITOR_CACHE,
//           resultPath: 'clearEditorCache'
//         }
//       },
//       { userId }
//     );
//   }

//   // ==================== Callable 管理 API ====================

//   /**
//    * 管理 Callable
//    */
//   async manageCallable(action: string, data: any): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'manage_callable' }, { action, ...data });
//   }

//   // ==================== 测试 API ====================

//   /**
//    * 运行测试
//    */
//   async runTest(testName: string, params?: any): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'run_tests' }, { test_name: testName, ...params });
//   }

//   /**
//    * 运行单个测试
//    */
//   async runSingleTest(testName: string, params?: any): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'run_tests' }, { test_name: testName, ...params });
//   }

//   /**
//    * 停止测试
//    */
//   async stopTest(testName: string): Promise<APIResponse<any>> {
//     return apiRouter.execute({ method: 'stop_tests' }, { test_name: testName });
//   }

//   // ==================== Simulation API ====================

//   /**
//    * Setup Sim Step
//    */
//   async setupSimStep(bundle: any): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'setup_sim_step',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.SETUP_SIM_STEP,
//           resultPath: 'setupSimStep'
//         }
//       },
//       { bundle }
//     );
//   }

//   /**
//    * Step Sim
//    */
//   async stepSim(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'step_sim',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.STEP_SIM,
//           resultPath: 'stepSim'
//         }
//       }
//     );
//   }

//   /**
//    * Test Langgraph2 Flowgram
//    */
//   async testLanggraph2Flowgram(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'test_langgraph2flowgram',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.TEST_LANGGRAPH2_FLOWGRAM,
//           resultPath: 'testLanggraph2Flowgram'
//         }
//       }
//     );
//   }

//   /**
//    * Sim Timer Event
//    */
//   async simTimerEvent(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'sim_timer_event',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.SIM_TIMER_EVENT,
//           resultPath: 'simTimerEvent'
//         }
//       }
//     );
//   }

//   /**
//    * Sim Websocket Event
//    */
//   async simWebsocketEvent(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'sim_websocket_event',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.SIM_WEBSOCKET_EVENT,
//           resultPath: 'simWebsocketEvent'
//         }
//       }
//     );
//   }

//   /**
//    * Sim SSE Event
//    */
//   async simSseEvent(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'sim_sse_event',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.SIM_SSE_EVENT,
//           resultPath: 'simSseEvent'
//         }
//       }
//     );
//   }

//   /**
//    * Sim Webhook Event
//    */
//   async simWebhookEvent(): Promise<APIResponse<any>> {
//     return apiRouter.execute(
//       {
//         method: 'sim_webhook_event',
//         graphql: {
//           mutation: GRAPHQL_MUTATIONS.SIM_WEBHOOK_EVENT,
//           resultPath: 'simWebhookEvent'
//         }
//       }
//     );
//   }
// }

// /**
//  * 导出默认实例
//  */
// export const apiClient = APIClient.getInstance();

// /**
//  * 导出便捷函数（向后兼容）
//  */
// export function get_ipc_api(): APIClient {
//   return apiClient;
// }

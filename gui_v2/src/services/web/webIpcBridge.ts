import { appSyncRequest } from './appSyncClient';
import { webApi } from './webApi';
import type { APIResponse } from '../ipc/api';

type MutationResult = {
  id?: string;
  success?: boolean;
  error?: string;
};

const ADD_AGENTS_MUTATION = `
  mutation AddAgents($input: [AgentInput!]!) {
    addAgents(input: $input) { id success error }
  }
`;

const UPDATE_AGENTS_MUTATION = `
  mutation UpdateAgents($input: [AgentUpdateInput!]!) {
    updateAgents(input: $input) { id success error }
  }
`;

const REMOVE_AGENTS_MUTATION = `
  mutation RemoveAgents($input: [ID!]!) {
    removeAgents(input: $input) { id success error }
  }
`;

const ADD_AGENT_SKILLS_MUTATION = `
  mutation AddAgentSkills($input: [SkillInput!]!) {
    addAgentSkills(input: $input) { id success error }
  }
`;

const UPDATE_AGENT_SKILLS_MUTATION = `
  mutation UpdateAgentSkills($input: [SkillUpdateInput!]!) {
    updateAgentSkills(input: $input) { id success error }
  }
`;

const REMOVE_AGENT_SKILLS_MUTATION = `
  mutation RemoveAgentSkills($input: [ID!]!) {
    removeAgentSkills(input: $input) { id success error }
  }
`;

const ADD_AGENT_TASKS_MUTATION = `
  mutation AddAgentTasks($input: [TaskInput!]!) {
    addAgentTasks(input: $input) { id success error }
  }
`;

const UPDATE_AGENT_TASKS_MUTATION = `
  mutation UpdateAgentTasks($input: [TaskUpdateInput!]!) {
    updateAgentTasks(input: $input) { id success error }
  }
`;

const REMOVE_AGENT_TASKS_MUTATION = `
  mutation RemoveAgentTasks($input: [ID!]!) {
    removeAgentTasks(input: $input) { id success error }
  }
`;

const ADD_AGENT_TOOLS_MUTATION = `
  mutation AddAgentTools($input: [ToolInput!]!) {
    addAgentTools(input: $input) { id success error }
  }
`;

const UPDATE_AGENT_TOOLS_MUTATION = `
  mutation UpdateAgentTools($input: [ToolUpdateInput!]!) {
    updateAgentTools(input: $input) { id success error }
  }
`;

const REMOVE_AGENT_TOOLS_MUTATION = `
  mutation RemoveAgentTools($input: [ID!]!) {
    removeAgentTools(input: $input) { id success error }
  }
`;

const ADD_AGENT_KNOWLEDGES_MUTATION = `
  mutation AddAgentKnowledges($input: [KnowledgeInput!]!) {
    addAgentKnowledges(input: $input) { id success error }
  }
`;

const UPDATE_AGENT_KNOWLEDGES_MUTATION = `
  mutation UpdateAgentKnowledges($input: [KnowledgeUpdateInput!]!) {
    updateAgentKnowledges(input: $input) { id success error }
  }
`;

const REMOVE_AGENT_KNOWLEDGES_MUTATION = `
  mutation RemoveAgentKnowledges($input: [ID!]!) {
    removeAgentKnowledges(input: $input) { id success error }
  }
`;

const ADD_PROMPTS_MUTATION = `
  mutation AddPrompts($input: [PromptInput!]!) {
    addPrompts(input: $input) { id success error }
  }
`;

const UPDATE_PROMPTS_MUTATION = `
  mutation UpdatePrompts($input: [PromptUpdateInput!]!) {
    updatePrompts(input: $input) { id success error }
  }
`;

const REMOVE_PROMPTS_MUTATION = `
  mutation RemovePrompts($input: [ID!]!) {
    removePrompts(input: $input) { id success error }
  }
`;

const ADD_ORGS_MUTATION = `
  mutation AddOrgs($input: [OrgInput!]!) {
    addOrgs(input: $input) { id success error }
  }
`;

const UPDATE_ORGS_MUTATION = `
  mutation UpdateOrgs($input: [OrgUpdateInput!]!) {
    updateOrgs(input: $input) { id success error }
  }
`;

const REMOVE_ORGS_MUTATION = `
  mutation RemoveOrgs($input: [ID!]!) {
    removeOrgs(input: $input) { id success error }
  }
`;

const ADD_VEHICLES_MUTATION = `
  mutation AddVehicles($input: [VehicleInput!]!) {
    addVehicles(input: $input) { id success error }
  }
`;

const UPDATE_VEHICLES_MUTATION = `
  mutation UpdateVehicles($input: [VehicleInput!]!) {
    updateVehicles(input: $input) { id success error }
  }
`;

const REMOVE_VEHICLES_MUTATION = `
  mutation RemoveVehicles($input: [ID!]!) {
    removeVehicles(input: $input) { id success error }
  }
`;

const normalizeArray = <T>(value: T | T[] | undefined | null): T[] => {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
};

const mergeMutationIds = <T extends Record<string, any>>(items: T[], results: MutationResult[] | undefined) => {
  if (!results || results.length === 0) return items;
  return items.map((item, index) => {
    const id = results[index]?.id;
    return id ? { ...item, id } : item;
  });
};

const extractMutationError = (results: MutationResult[] | undefined) => {
  const failed = results?.find(r => r?.success === false || r?.error);
  return failed?.error || (failed?.success === false ? 'Mutation failed' : undefined);
};

const createEmptyOrgTreeRoot = () => ({
  id: 'root',
  name: 'Organizations',
  description: 'Root',
  org_type: 'company',
  level: 0,
  sort_order: 0,
  status: 'active',
  parent_id: null,
  children: [],
  agents: [],
});

const buildTreeFromOrgs = (orgs: any[]) => {
  const nodeMap = new Map<string, any>();
  const roots: any[] = [];

  orgs.forEach((org) => {
    nodeMap.set(org.id, { ...org, children: [], agents: [] });
  });

  nodeMap.forEach((node) => {
    if (node.parent_id && nodeMap.has(node.parent_id)) {
      nodeMap.get(node.parent_id).children.push(node);
    } else {
      roots.push(node);
    }
  });

  if (roots.length === 1) return roots[0];

  return {
    id: 'root',
    name: 'Root',
    description: 'Root',
    org_type: 'root',
    level: 0,
    sort_order: 0,
    status: 'active',
    children: roots,
    agents: [],
  };
};

const runMutation = async <T>(mutation: string, variables: Record<string, any>, field: string): Promise<T> => {
  const data = await appSyncRequest<Record<string, T>>(mutation, variables);
  return data[field];
};

export async function handleWebIpcRequest<T>(method: string, params?: any): Promise<APIResponse<T> | null> {
  switch (method) {
    case 'get_all': {
      const allMine = await webApi.getAllMine();
      return { success: true, data: allMine as any };
    }
    case 'get_all_org_agents': {
      const treeRoot = await webApi.getOrgAgentTree();
      const safeRoot = treeRoot || createEmptyOrgTreeRoot();
      return { success: true, data: { orgs: safeRoot, message: 'ok' } as any };
    }
    case 'get_orgs': {
      const allMine = await webApi.getAllMine();
      return { success: true, data: { orgs: allMine.orgs } as any };
    }
    case 'get_agents': {
      const allMine = await webApi.getAllMine();
      const ids = normalizeArray<string>(params?.agent_id);
      const agents = ids.length ? allMine.agents.filter(a => ids.includes(a.id)) : allMine.agents;
      return { success: true, data: { agents } as any };
    }
    case 'get_agent_tasks': {
      const allMine = await webApi.getAllMine();
      const ids = normalizeArray<string>(params?.task_ids);
      const tasks = ids.length ? allMine.tasks.filter(t => ids.includes(t.id)) : allMine.tasks;
      return { success: true, data: { tasks } as any };
    }
    case 'get_agent_skills': {
      const allMine = await webApi.getAllMine();
      const ids = normalizeArray<string>(params?.skill_ids);
      const skills = ids.length ? allMine.skills.filter(s => ids.includes(s.id)) : allMine.skills;
      return { success: true, data: { skills } as any };
    }
    case 'get_tools': {
      const allMine = await webApi.getAllMine();
      const ids = normalizeArray<string>(params?.tool_ids);
      const tools = ids.length ? allMine.tools.filter(t => ids.includes(t.id)) : allMine.tools;
      return { success: true, data: { tools } as any };
    }
    case 'get_vehicles': {
      const allMine = await webApi.getAllMine();
      return { success: true, data: { vehicles: allMine.vehicles } as any };
    }
    case 'new_agent': {
      const agents = normalizeArray<any>(params?.agent);
      const results = await runMutation<MutationResult[]>(ADD_AGENTS_MUTATION, { input: agents }, 'addAgents');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds(agents, results);
      return { success: true, data: { agents: merged } as any };
    }
    case 'save_agent': {
      const agents = normalizeArray<any>(params?.agent);
      const results = await runMutation<MutationResult[]>(UPDATE_AGENTS_MUTATION, { input: agents }, 'updateAgents');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds(agents, results);
      return { success: true, data: { agents: merged } as any };
    }
    case 'delete_agent': {
      const ids = normalizeArray<string | number>(params?.agent_id).map(String);
      const results = await runMutation<MutationResult[]>(REMOVE_AGENTS_MUTATION, { input: ids }, 'removeAgents');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: ids } as any };
    }
    case 'new_agent_skill': {
      const skill = params?.skill_info ?? params;
      const results = await runMutation<MutationResult[]>(ADD_AGENT_SKILLS_MUTATION, { input: [skill] }, 'addAgentSkills');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([skill], results)[0];
      return { success: true, data: { data: merged, skills: [merged] } as any };
    }
    case 'save_agent_skill': {
      const skill = params?.skill_info ?? params;
      const results = await runMutation<MutationResult[]>(UPDATE_AGENT_SKILLS_MUTATION, { input: [skill] }, 'updateAgentSkills');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([skill], results)[0];
      return { success: true, data: { data: merged, skills: [merged] } as any };
    }
    case 'delete_agent_skill': {
      const id = String(params?.skill_id ?? params?.id ?? '');
      const results = await runMutation<MutationResult[]>(REMOVE_AGENT_SKILLS_MUTATION, { input: [id] }, 'removeAgentSkills');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true } as any;
    }
    case 'new_agent_task': {
      const task = params?.task_info ?? params;
      const results = await runMutation<MutationResult[]>(ADD_AGENT_TASKS_MUTATION, { input: [task] }, 'addAgentTasks');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([task], results)[0];
      return { success: true, data: { task_id: merged?.id, id: merged?.id, task: merged } as any };
    }
    case 'save_agent_task': {
      const task = params?.task_info ?? params;
      const results = await runMutation<MutationResult[]>(UPDATE_AGENT_TASKS_MUTATION, { input: [task] }, 'updateAgentTasks');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([task], results)[0];
      return { success: true, data: { task_id: merged?.id, id: merged?.id, task: merged } as any };
    }
    case 'delete_agent_task': {
      const id = String(params?.task_id ?? params?.id ?? '');
      const results = await runMutation<MutationResult[]>(REMOVE_AGENT_TASKS_MUTATION, { input: [id] }, 'removeAgentTasks');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true } as any;
    }
    case 'new_tools': {
      const tools = normalizeArray<any>(params?.tools ?? params);
      const results = await runMutation<MutationResult[]>(ADD_AGENT_TOOLS_MUTATION, { input: tools }, 'addAgentTools');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds(tools, results);
      return { success: true, data: { tools: merged } as any };
    }
    case 'save_tools': {
      const tools = normalizeArray<any>(params?.tools ?? params);
      const results = await runMutation<MutationResult[]>(UPDATE_AGENT_TOOLS_MUTATION, { input: tools }, 'updateAgentTools');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds(tools, results);
      return { success: true, data: { tools: merged } as any };
    }
    case 'delete_tools': {
      const tools = normalizeArray<any>(params?.tools ?? params);
      const ids = tools.map((tool: any) => String(tool?.id ?? tool)).filter(Boolean);
      const results = await runMutation<MutationResult[]>(REMOVE_AGENT_TOOLS_MUTATION, { input: ids }, 'removeAgentTools');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: ids } as any };
    }
    case 'new_knowledges': {
      const knowledges = normalizeArray<any>(params);
      const results = await runMutation<MutationResult[]>(ADD_AGENT_KNOWLEDGES_MUTATION, { input: knowledges }, 'addAgentKnowledges');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds(knowledges, results);
      return { success: true, data: { knowledges: merged } as any };
    }
    case 'save_knowledges': {
      const knowledges = normalizeArray<any>(params);
      const results = await runMutation<MutationResult[]>(UPDATE_AGENT_KNOWLEDGES_MUTATION, { input: knowledges }, 'updateAgentKnowledges');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds(knowledges, results);
      return { success: true, data: { knowledges: merged } as any };
    }
    case 'delete_knowledges': {
      const values = normalizeArray<any>(params);
      const ids = values.map((item: any) => String(item?.id ?? item)).filter(Boolean);
      const results = await runMutation<MutationResult[]>(REMOVE_AGENT_KNOWLEDGES_MUTATION, { input: ids }, 'removeAgentKnowledges');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: ids } as any };
    }
    case 'create_org': {
      const org = {
        name: params?.name,
        description: params?.description,
        parent_id: params?.parent_id,
        org_type: params?.organization_type ?? params?.org_type,
      };
      const results = await runMutation<MutationResult[]>(ADD_ORGS_MUTATION, { input: [org] }, 'addOrgs');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([org], results)[0];
      return { success: true, data: { orgs: [merged] } as any };
    }
    case 'update_org': {
      const org = {
        id: params?.organization_id ?? params?.id,
        name: params?.name,
        description: params?.description,
        parent_id: params?.parent_id,
      };
      const results = await runMutation<MutationResult[]>(UPDATE_ORGS_MUTATION, { input: [org] }, 'updateOrgs');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([org], results)[0];
      return { success: true, data: { orgs: [merged] } as any };
    }
    case 'delete_org': {
      const id = String(params?.organization_id ?? params?.id ?? '');
      const results = await runMutation<MutationResult[]>(REMOVE_ORGS_MUTATION, { input: [id] }, 'removeOrgs');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: [id] } as any };
    }
    case 'add_vehicle': {
      const vehicle = params ?? {};
      const results = await runMutation<MutationResult[]>(ADD_VEHICLES_MUTATION, { input: [vehicle] }, 'addVehicles');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([vehicle], results)[0];
      return { success: true, data: { vehicle: merged, id: merged?.id } as any };
    }
    case 'update_vehicle':
    case 'update_vehicle_status': {
      const vehicle = { ...(params || {}) };
      const results = await runMutation<MutationResult[]>(UPDATE_VEHICLES_MUTATION, { input: [vehicle] }, 'updateVehicles');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([vehicle], results)[0];
      return { success: true, data: { vehicle: merged } as any };
    }
    case 'delete_vehicle': {
      const id = String(params?.vehicle_id ?? params?.id ?? '');
      const results = await runMutation<MutationResult[]>(REMOVE_VEHICLES_MUTATION, { input: [id] }, 'removeVehicles');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: [id] } as any };
    }
    case 'add_prompts': {
      const prompts = normalizeArray<any>(params?.input ?? params?.prompts ?? params);
      const results = await runMutation<MutationResult[]>(ADD_PROMPTS_MUTATION, { input: prompts }, 'addPrompts');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds(prompts, results);
      return { success: true, data: { prompts: merged } as any };
    }
    case 'update_prompts': {
      const prompts = normalizeArray<any>(params?.input ?? params?.prompts ?? params);
      const results = await runMutation<MutationResult[]>(UPDATE_PROMPTS_MUTATION, { input: prompts }, 'updatePrompts');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds(prompts, results);
      return { success: true, data: { prompts: merged } as any };
    }
    case 'remove_prompts': {
      const ids = normalizeArray<any>(params?.input ?? params?.ids ?? params).map((item: any) => String(item?.id ?? item));
      const results = await runMutation<MutationResult[]>(REMOVE_PROMPTS_MUTATION, { input: ids }, 'removePrompts');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: ids } as any };
    }
    default:
      return null;
  }
}
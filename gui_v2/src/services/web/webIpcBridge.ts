import { appSyncRequest } from './appSyncClient';
import { webApi } from './webApi';
import type { APIResponse } from '../ipc/api';
import { detectPlatform } from '../../config/platform';

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

const ADD_WAREHOUSES_MUTATION = `
  mutation AddWareHouses($input: [WarehouseInput!]!) {
    addWareHouses(input: $input) { id success error }
  }
`;

const UPDATE_WAREHOUSES_MUTATION = `
  mutation UpdateWarehouses($input: [WarehouseUpdateInput!]!) {
    UpdateWarehouses(input: $input) { id success error }
  }
`;

const REMOVE_WAREHOUSES_MUTATION = `
  mutation RemoveWareHouses($input: [ID!]!) {
    RemoveWareHouses(input: $input) { id success error }
  }
`;

const ADD_LABEL_FORMATS_MUTATION = `
  mutation AddLabelFormats($input: [LabelFormatInput!]!) {
    addLabelFormats(input: $input) { id success error }
  }
`;

const UPDATE_LABEL_FORMATS_MUTATION = `
  mutation UpdateLabelFormats($input: [LabelFormatUpdateInput!]!) {
    UpdateLabelFormats(input: $input) { id success error }
  }
`;

const REMOVE_LABEL_FORMATS_MUTATION = `
  mutation RemoveLabelFormats($input: [ID!]!) {
    RemoveLabelFormats(input: $input) { id success error }
  }
`;

const ADD_PRODUCTS_MUTATION = `
  mutation AddProducts($input: [ProductInput!]!) {
    addProducts(input: $input) { id success error }
  }
`;

const UPDATE_PRODUCTS_MUTATION = `
  mutation UpdateProducts($input: [ProductUpdateInput!]!) {
    updateProducts(input: $input) { id success error }
  }
`;

const REMOVE_PRODUCTS_MUTATION = `
  mutation RemoveProducts($input: [ID!]!) {
    removeProducts(input: $input) { id success error }
  }
`;

const ADD_INVENTORIES_MUTATION = `
  mutation AddInventories($input: [InventoryInput!]!) {
    addInventories(input: $input) { id success error }
  }
`;

const UPDATE_INVENTORIES_MUTATION = `
  mutation UpdateInventories($input: [InventoryUpdateInput!]!) {
    updateInventories(input: $input) { id success error }
  }
`;

const REMOVE_INVENTORIES_MUTATION = `
  mutation RemoveInventories($input: [ID!]!) {
    removeInventories(input: $input) { id success error }
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

const parseAddress = (raw: any) => {
  if (!raw) return {};
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }
  return typeof raw === 'object' ? raw : {};
};

const mapWarehouseFromApi = (w: any) => {
  const address = parseAddress(w?.address);
  const contactName = w?.contact_name || '';
  const [contactFirstName = '', ...rest] = String(contactName).trim().split(' ');
  const contactLastName = rest.join(' ');
  return {
    id: String(w?.id ?? ''),
    name: w?.name ?? '',
    city: address.city ?? '',
    state: address.state ?? '',
    contactFirstName,
    contactLastName,
    phone: w?.contact_phone ?? '',
    email: address.email ?? '',
    messagingPlatform: address.messagingPlatform ?? '',
    messagingId: address.messagingId ?? '',
    address1: address.line1 ?? address.address1 ?? '',
    address2: address.line2 ?? address.address2 ?? '',
    addressCity: address.city ?? '',
    addressState: address.state ?? '',
    addressZip: address.postal_code ?? address.zip ?? '',
    costDescription: w?.notes ?? '',
  };
};

const mapWarehouseToApi = (w: any) => {
  const address = {
    line1: w?.address1 ?? '',
    line2: w?.address2 ?? '',
    city: w?.addressCity ?? w?.city ?? '',
    state: w?.addressState ?? w?.state ?? '',
    postal_code: w?.addressZip ?? '',
  };
  return {
    id: w?.id,
    name: w?.name,
    code: w?.code ?? w?.id,
    address,
    contact_name: [w?.contactFirstName, w?.contactLastName].filter(Boolean).join(' '),
    contact_phone: w?.phone ?? '',
    status: w?.status ?? 'active',
    notes: w?.costDescription ?? '',
  };
};

const mapProductFromApi = (p: any) => {
  const attrs = (() => {
    if (!p?.attributes) return {};
    if (typeof p.attributes === 'string') {
      try {
        return JSON.parse(p.attributes);
      } catch {
        return {};
      }
    }
    return typeof p.attributes === 'object' ? p.attributes : {};
  })();

  return {
    id: String(p?.id ?? p?.sku ?? ''),
    nickName: p?.name ?? p?.sku ?? '',
    title: p?.name ?? '',
    features: p?.description ?? '',
    sizeL: attrs.sizeL ?? '',
    sizeW: attrs.sizeW ?? '',
    sizeH: attrs.sizeH ?? '',
    weightOz: attrs.weightOz ?? '',
    fragile: !!attrs.fragile,
    batteryInside: !!attrs.batteryInside,
    chemical: !!attrs.chemical,
    flammable: !!attrs.flammable,
    city: attrs.city,
    state: attrs.state,
    inventories: Array.isArray(attrs.inventories) ? attrs.inventories : [],
    dropShippers: Array.isArray(attrs.dropShippers) ? attrs.dropShippers : [],
    media: Array.isArray(attrs.media) ? attrs.media : [],
    suppliers: Array.isArray(attrs.suppliers) ? attrs.suppliers : [],
    platforms: Array.isArray(attrs.platforms) ? attrs.platforms : [],
  };
};

const mapProductToApi = (p: any) => {
  const attrs = {
    sizeL: p?.sizeL ?? '',
    sizeW: p?.sizeW ?? '',
    sizeH: p?.sizeH ?? '',
    weightOz: p?.weightOz ?? '',
    fragile: !!p?.fragile,
    batteryInside: !!p?.batteryInside,
    chemical: !!p?.chemical,
    flammable: !!p?.flammable,
    city: p?.city,
    state: p?.state,
    inventories: p?.inventories ?? [],
    dropShippers: p?.dropShippers ?? [],
    media: p?.media ?? [],
    suppliers: p?.suppliers ?? [],
    platforms: p?.platforms ?? [],
  };
  return {
    id: p?.id,
    sku: p?.id,
    name: p?.title || p?.nickName || p?.id,
    description: p?.features ?? '',
    attributes: attrs,
    status: p?.status ?? 'active',
  };
};

const toEpochMs = (value: any) => {
  if (typeof value === 'number') return value;
  if (!value) return Date.now();
  const parsed = Date.parse(String(value));
  return Number.isNaN(parsed) ? Date.now() : parsed;
};

const mapChatSessionFromApi = (session: any) => ({
  id: String(session?.id ?? ''),
  name: session?.name ?? '',
  flowgramId: session?.flowgramId ?? session?.flowgram_id ?? undefined,
  messages: [],
  createdAt: toEpochMs(session?.createdAt),
  updatedAt: toEpochMs(session?.updatedAt ?? session?.createdAt),
});

const mapChatMessageFromApi = (message: any) => ({
  id: String(message?.id ?? ''),
  role: message?.role ?? 'assistant',
  content: message?.content ?? '',
  timestamp: toEpochMs(message?.timestamp),
  attachments: message?.attachments ?? undefined,
  metadata: message?.metadata ?? undefined,
});

const parseMaybeAwsJson = (value: any): any => {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return value;
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return value;
    }
  }
  return value;
};

const normalizeClarification = (value: any): any[] | undefined => {
  const parsed = parseMaybeAwsJson(value);
  if (Array.isArray(parsed)) return parsed;
  if (parsed && Array.isArray(parsed.questions)) return parsed.questions;
  return undefined;
};

const mapChatResponseFromApi = (resp: any) => ({
  sessionId: resp?.sessionId ?? '',
  sessionName: resp?.sessionName ?? '',
  state: resp?.state ?? 'idle',
  intent: resp?.intent ?? undefined,
  message: mapChatMessageFromApi(resp?.message ?? {}),
  clarification: normalizeClarification(resp?.clarification),
  plan: parseMaybeAwsJson(resp?.plan) ?? undefined,
  flowgram: parseMaybeAwsJson(resp?.flowgram) ?? undefined,
  validation: parseMaybeAwsJson(resp?.validation) ?? undefined,
});

const sanitizeAwsJson = (value: any): any => {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value, (_key, v) => {
    if (v === undefined) return undefined;
    if (typeof v === 'function') return undefined;
    if (typeof v === 'bigint') return v.toString();
    if (v instanceof Map) return Object.fromEntries(v);
    if (v instanceof Set) return Array.from(v);
    if (v instanceof Date) return v.toISOString();
    return v;
  }));
};

const serializeAwsJson = (value: any): string | undefined => {
  if (value === undefined) return undefined;
  if (typeof value === 'string') return value;
  return JSON.stringify(sanitizeAwsJson(value));
};

const parseAwsJson = (value: any): any => {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return value;
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return value;
    }
  }
  return value;
};

const runMutation = async <T>(mutation: string, variables: Record<string, any>, field: string): Promise<T> => {
  const data = await appSyncRequest<Record<string, T>>(mutation, variables);
  return data[field];
};

export async function handleWebIpcRequest<T>(method: string, params?: any): Promise<APIResponse<T> | null> {
  switch (method) {
    case 'get_initialization_progress': {
      return {
        success: true,
        data: {
          ui_ready: true,
          critical_services_ready: true,
          async_init_complete: true,
          fully_ready: true,
          sync_init_complete: true,
          message: 'Web mode: backend ready'
        } as any
      };
    }
    case 'get_available_tests': {
      return { success: true, data: [] as any };
    }
    case 'get_all': {
      const allMine = await webApi.getAllMine();
      return { success: true, data: allMine as any };
    }
    case 'get_all_org_agents': {
      const company = (params?.company || params?.companyName || params?.company_name || '').trim();
      const rootId = (params?.root_id || params?.rootId || params?.org_id || params?.orgId || undefined) as
        | string
        | undefined;

      if (company) {
        const matches = await webApi.queryOrgsByName(company);
        const match = matches[0];
        if (!match?.id) {
          return {
            success: false,
            error: {
              code: 'COMPANY_NOT_FOUND',
              message: 'Company not found'
            }
          } as any;
        }

        const treeRoot = await webApi.getOrgAgentTree(match.id);
        const safeRoot = treeRoot || createEmptyOrgTreeRoot();
        return { success: true, data: { orgs: safeRoot, message: 'ok' } as any };
      }

      const treeRoot = await webApi.getOrgAgentTree(rootId);
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
    case 'get_settings': {
      const allMine = await webApi.getAllMine();
      return { success: true, data: { settings: allMine.accountInfo ?? null } as any };
    }
    case 'get_warehouses': {
      const warehouses = await webApi.getWarehouses(params?.query);
      const mapped = (warehouses || []).map(mapWarehouseFromApi);
      return { success: true, data: { warehouses: mapped } as any };
    }
    case 'save_warehouse': {
      const rawWarehouse = params?.warehouse ?? params;
      const warehouse = mapWarehouseToApi(rawWarehouse);
      const hasId = !!warehouse?.id;
      const results = await runMutation<MutationResult[]>(
        hasId ? UPDATE_WAREHOUSES_MUTATION : ADD_WAREHOUSES_MUTATION,
        { input: [warehouse] },
        hasId ? 'UpdateWarehouses' : 'addWareHouses'
      );
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([warehouse], results)[0];
      return { success: true, data: { warehouse: mapWarehouseFromApi(merged) } as any };
    }
    case 'delete_warehouse': {
      const id = String(params?.id ?? '');
      const results = await runMutation<MutationResult[]>(REMOVE_WAREHOUSES_MUTATION, { input: [id] }, 'RemoveWareHouses');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: [id] } as any };
    }
    case 'get_products': {
      const products = await webApi.getProducts(params?.query);
      const mapped = (products || []).map(mapProductFromApi);
      return { success: true, data: { products: mapped } as any };
    }
    case 'get_inventories': {
      const inventories = await webApi.getInventories(params?.query);
      return { success: true, data: { inventories } as any };
    }
    case 'save_product': {
      const rawProduct = params?.product ?? params;
      const product = mapProductToApi(rawProduct);
      const hasId = !!product?.id;
      const results = await runMutation<MutationResult[]>(
        hasId ? UPDATE_PRODUCTS_MUTATION : ADD_PRODUCTS_MUTATION,
        { input: [product] },
        hasId ? 'updateProducts' : 'addProducts'
      );
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([product], results)[0];
      return { success: true, data: { product: mapProductFromApi(merged) } as any };
    }
    case 'delete_product': {
      const id = String(params?.id ?? '');
      const results = await runMutation<MutationResult[]>(REMOVE_PRODUCTS_MUTATION, { input: [id] }, 'removeProducts');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: [id] } as any };
    }
    case 'save_inventory': {
      const inventory = params?.inventory ?? params;
      const hasId = !!inventory?.id;
      const results = await runMutation<MutationResult[]>(
        hasId ? UPDATE_INVENTORIES_MUTATION : ADD_INVENTORIES_MUTATION,
        { input: [inventory] },
        hasId ? 'updateInventories' : 'addInventories'
      );
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([inventory], results)[0];
      return { success: true, data: { inventory: merged } as any };
    }
    case 'delete_inventory': {
      const id = String(params?.id ?? '');
      const results = await runMutation<MutationResult[]>(REMOVE_INVENTORIES_MUTATION, { input: [id] }, 'removeInventories');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { removed: [id] } as any };
    }
    case 'label_config.get_all': {
      const formats = await webApi.getLabelFormats(params?.query);
      return { success: true, data: { system_configs: [], user_configs: formats } as any };
    }
    case 'label_config.save': {
      const config = params?.config ?? {};
      const hasId = !!config?.id;
      const results = await runMutation<MutationResult[]>(
        hasId ? UPDATE_LABEL_FORMATS_MUTATION : ADD_LABEL_FORMATS_MUTATION,
        { input: [config] },
        hasId ? 'UpdateLabelFormats' : 'addLabelFormats'
      );
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      const merged = mergeMutationIds([config], results)[0];
      return { success: true, data: { config: merged } as any };
    }
    case 'label_config.delete': {
      const id = String(params?.id ?? '');
      const results = await runMutation<MutationResult[]>(REMOVE_LABEL_FORMATS_MUTATION, { input: [id] }, 'RemoveLabelFormats');
      const error = extractMutationError(results);
      if (error) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: error } };
      }
      return { success: true, data: { deleted: true, id } as any };
    }
    case 'label_config.check_name': {
      const name = String(params?.name ?? '').trim();
      const excludeId = params?.exclude_id ? String(params.exclude_id) : undefined;
      if (!name) return { success: true, data: { exists: false, name } as any };
      const matches = await webApi.getLabelFormats({ name });
      const exists = matches.some((f) => f?.name === name && (!excludeId || f?.id !== excludeId));
      return { success: true, data: { exists, name } as any };
    }
    case 'save_settings': {
      return { success: false, error: { code: 'NOT_SUPPORTED', message: 'save_settings is not supported in web mode yet.' } };
    }
    case 'skill_editor.get_node_state_schema': {
      const schema = await webApi.getNodeStateSchema();
      if (!schema) {
        return { success: false, error: { code: 'NOT_FOUND', message: 'Node state schema not found.' } } as any;
      }
      return { success: true, data: schema as any };
    }
    case 'read_skill_file': {
      const filePath = String(params?.filePath ?? params?.path ?? '');
      if (!filePath) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'filePath is required.' } } as any;
      }
      const content = await webApi.readSkillFile(filePath);
      const list = Array.isArray(content) ? content : content ? [content] : [];
      const normalized = String(filePath).replace(/\\/g, '/');
      const match = list.find((item) => String(item?.filePath || '').replace(/\\/g, '/') === normalized) || list[0];
      if (!match) {
        return { success: false, error: { code: 'NOT_FOUND', message: 'Skill file not found.' } } as any;
      }
      return { success: true, data: match as any };
    }
    case 'open_skill_file': {
      const filePath = String(params?.filePath ?? params?.path ?? '');
      const skillName = params?.skillName ? String(params.skillName) : undefined;
      if (!filePath) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'filePath is required.' } } as any;
      }
      const content = await webApi.openSkillFile(filePath, skillName);
      if (!content) {
        return { success: false, error: { code: 'NOT_FOUND', message: 'Skill file not found.' } } as any;
      }
      return { success: true, data: content as any };
    }
    case 'write_skill_file': {
      const filePath = String(params?.filePath ?? '');
      const content = params?.content ?? '';
      if (!filePath) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'filePath is required.' } } as any;
      }
      const info = await webApi.writeSkillFile({ filePath, content });
      if (!info) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: 'writeSkillFile failed.' } } as any;
      }
      return { success: true, data: { ...info, success: true } as any };
    }
    case 'skills.scaffold': {
      const checkOnly = !!params?.checkOnly;
      const name = String(params?.name ?? '').trim();
      if (!name) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'name is required.' } } as any;
      }
      if (checkOnly) {
        const result = await webApi.checkSkillExists(name);
        return { success: true, data: result || { exists: false, name } } as any;
      }
      const input = {
        name,
        description: params?.description,
        kind: params?.kind,
        skillJson: params?.skillJson,
        bundleJson: params?.bundleJson,
        mappingJson: params?.mappingJson,
      };
      const result = await webApi.scaffoldSkill(input);
      if (!result) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: 'scaffoldSkill failed.' } } as any;
      }
      return { success: true, data: result as any };
    }
    case 'skills.copyTo': {
      const sourcePath = String(params?.sourcePath ?? '');
      const newName = String(params?.newName ?? '').trim();
      if (!sourcePath || !newName) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'sourcePath and newName are required.' } } as any;
      }
      const input = {
        sourcePath,
        newName,
        targetDir: params?.targetDir,
        skillJson: params?.skillJson,
        bundleJson: params?.bundleJson,
      };
      const result = await webApi.copySkillTo(input);
      if (!result) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: 'copySkillTo failed.' } } as any;
      }
      return { success: true, data: result as any };
    }
    case 'save_editor_cache': {
      const cacheData = params?.cacheData ?? params?.input ?? params;
      const result = await webApi.saveEditorCache(cacheData || {});
      if (!result) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: 'saveEditorCache failed.' } } as any;
      }
      return { success: true, data: result as any };
    }
    case 'load_editor_cache': {
      const userId = String(params?.userId ?? params?.username ?? 'default');
      const result = await webApi.getEditorCache(userId);
      return { success: true, data: result || { cacheData: null, recentFiles: [] } } as any;
    }
    case 'clear_editor_cache': {
      const userId = String(params?.userId ?? params?.username ?? 'default');
      const cleared = await webApi.clearEditorCache(userId);
      return { success: true, data: { cleared } as any };
    }
    case 'run_skill': {
      const input = { username: params?.username, skill: params?.skill };
      const result = await webApi.runSkill(input);
      return { success: true, data: result as any };
    }
    case 'cancel_run_skill': {
      const input = { username: params?.username, skill: params?.skill };
      const result = await webApi.cancelRunSkill(input);
      return { success: true, data: result as any };
    }
    case 'pause_run_skill': {
      const input = { username: params?.username, skill: params?.skill };
      const result = await webApi.pauseRunSkill(input);
      return { success: true, data: result as any };
    }
    case 'resume_run_skill': {
      const input = { username: params?.username, skill: params?.skill };
      const result = await webApi.resumeRunSkill(input);
      return { success: true, data: result as any };
    }
    case 'step_run_skill': {
      const input = { username: params?.username, skill: params?.skill };
      const result = await webApi.stepRunSkill(input);
      return { success: true, data: result as any };
    }
    case 'set_skill_breakpoints': {
      const username = String(params?.username ?? '');
      const nodeName = String(params?.node_name ?? params?.nodeName ?? '');
      if (!username || !nodeName) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'username and node_name are required.' } } as any;
      }
      const result = await webApi.setSkillBreakpoints(username, nodeName);
      return { success: true, data: result as any };
    }
    case 'clear_skill_breakpoints': {
      const username = String(params?.username ?? '');
      const nodeName = String(params?.node_name ?? params?.nodeName ?? '');
      if (!username || !nodeName) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'username and node_name are required.' } } as any;
      }
      const result = await webApi.clearSkillBreakpoints(username, nodeName);
      return { success: true, data: result as any };
    }
    case 'request_skill_state': {
      const username = String(params?.username ?? '');
      const skill = params?.skill ?? {};
      if (!username) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'username is required.' } } as any;
      }
      const result = await webApi.requestSkillState(username, skill);
      return { success: true, data: result as any };
    }
    case 'inject_skill_state': {
      const username = String(params?.username ?? '');
      const skill = params?.skill ?? {};
      if (!username) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'username is required.' } } as any;
      }
      const result = await webApi.injectSkillState(username, skill);
      return { success: true, data: result as any };
    }
    case 'load_skill_schemas': {
      const username = String(params?.username ?? '');
      const skill = params?.skill ?? {};
      if (!username) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'username is required.' } } as any;
      }
      const result = await webApi.loadSkillSchemas(username, skill);
      return { success: true, data: result as any };
    }
    case 'setup_sim_step': {
      const result = await webApi.setupSimStep(params?.bundle ?? null);
      return { success: true, data: result as any };
    }
    case 'step_sim': {
      const result = await webApi.stepSim();
      return { success: true, data: result as any };
    }
    case 'test_langgraph2flowgram': {
      const result = await webApi.testLanggraph2Flowgram();
      return { success: true, data: result as any };
    }
    case 'sim_timer_event': {
      const result = await webApi.simTimerEvent();
      return { success: true, data: result as any };
    }
    case 'sim_websocket_event': {
      const result = await webApi.simWebsocketEvent();
      return { success: true, data: result as any };
    }
    case 'sim_sse_event': {
      const result = await webApi.simSseEvent();
      return { success: true, data: result as any };
    }
    case 'sim_webhook_event': {
      const result = await webApi.simWebhookEvent();
      return { success: true, data: result as any };
    }
    case 'skill_editor.chat.create_session': {
      const input = {
        name: params?.name,
        flowgramId: params?.flowgramId,
        userId: params?.userId ?? params?.username,
      };
      const session = await webApi.createSkillEditorChatSession(input);
      if (!session) {
        return { success: false, error: { code: 'MUTATION_FAILED', message: 'createSkillEditorChatSession failed.' } } as any;
      }
      return { success: true, data: { session: mapChatSessionFromApi(session) } as any };
    }
    case 'skill_editor.chat.get_sessions': {
      const userId = String(params?.userId ?? params?.username ?? 'default');
      const sessions = await webApi.getSkillEditorChatSessions(userId);
      return { success: true, data: { sessions: (sessions || []).map(mapChatSessionFromApi) } as any };
    }
    case 'skill_editor.chat.get_history': {
      const sessionId = String(params?.sessionId ?? '');
      if (!sessionId) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'sessionId is required.' } } as any;
      }
      const messages = await webApi.getSkillEditorChatHistory(sessionId, params?.limit, params?.offset);
      return { success: true, data: { messages: (messages || []).map(mapChatMessageFromApi) } as any };
    }
    case 'skill_editor.chat.send_message': {
      const input = {
        sessionId: params?.sessionId,
        name: params?.name,
        flowgramId: params?.flowgramId,
        content: params?.content,
        attachments: serializeAwsJson(params?.attachments),
        canvasContext: serializeAwsJson(params?.canvasContext),
        clarificationResponses: serializeAwsJson(params?.clarificationResponses),
        userId: params?.userId ?? params?.username,
      };
      try {
        const response = await webApi.sendSkillEditorChatMessage(input);
        if (!response) {
          return { success: false, error: { code: 'MUTATION_FAILED', message: 'sendSkillEditorChatMessage failed.' } } as any;
        }
        return { success: true, data: mapChatResponseFromApi(response) as any };
      } catch (error) {
        console.error('[WebIpcBridge] sendSkillEditorChatMessage error:', error);
        return {
          success: false,
          error: {
            code: 'WEB_API_ERROR',
            message: error instanceof Error ? error.message : 'sendSkillEditorChatMessage failed.'
          }
        } as any;
      }
    }
    case 'skill_editor.context.load': {
      const input = {
        userId: params?.userId ?? params?.username,
        skillNames: params?.skillNames,
        skillIds: params?.skillIds,
      };
      if (!input.userId) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'userId is required.' } } as any;
      }
      try {
        const items = await webApi.loadSkillEditorContexts(input);
        const normalized = (items || []).map((item: any) => ({
          ...item,
          context: parseAwsJson(item?.context),
        }));
        return { success: true, data: { items: normalized } as any };
      } catch (error) {
        console.error('[WebIpcBridge] loadSkillEditorContexts error:', error);
        return {
          success: false,
          error: {
            code: 'WEB_API_ERROR',
            message: error instanceof Error ? error.message : 'loadSkillEditorContexts failed.'
          }
        } as any;
      }
    }
    case 'skill_editor.chat.cancel_generation': {
      const sessionId = String(params?.sessionId ?? '');
      if (!sessionId) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'sessionId is required.' } } as any;
      }
      const cancelled = await webApi.cancelSkillEditorChatGeneration(sessionId);
      return { success: true, data: { cancelled } as any };
    }
    case 'skill_editor.chat.delete_session': {
      const sessionId = String(params?.sessionId ?? '');
      if (!sessionId) {
        return { success: false, error: { code: 'INVALID_PARAMS', message: 'sessionId is required.' } } as any;
      }
      const deleted = await webApi.deleteSkillEditorChatSession(sessionId);
      return { success: true, data: { deleted } as any };
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
    // Phase 1: LLM Providers via HTTP
    case 'get_llm_providers': {
      const query = `query GetLlmProviders { getLlmProviders { providers message } }`;
      const data = await appSyncRequest<{ getLlmProviders: { providers: any[]; message: string } }>(query);
      return { success: true, data: data.getLlmProviders as any };
    }
    case 'get_embedding_providers': {
      const query = `query GetEmbeddingProviders { getEmbeddingProviders { providers message } }`;
      const data = await appSyncRequest<{ getEmbeddingProviders: { providers: any[]; message: string } }>(query);
      return { success: true, data: data.getEmbeddingProviders as any };
    }
    case 'get_rerank_providers': {
      const query = `query GetRerankProviders { getRerankProviders { providers message } }`;
      const data = await appSyncRequest<{ getRerankProviders: { providers: any[]; message: string } }>(query);
      return { success: true, data: data.getRerankProviders as any };
    }
    // Phase 1: Settings via HTTP
    case 'get_settings': {
      const query = `query GetSettings { getSettings { settings message } }`;
      const data = await appSyncRequest<{ getSettings: { settings: any; message: string } }>(query);
      return { success: true, data: data.getSettings as any };
    }
    case 'save_settings': {
      const query = `mutation SaveSettings($input: SettingsInput!) { saveSettings(input: $input) { success message } }`;
      const data = await appSyncRequest<{ saveSettings: { success: boolean; message: string } }>(query, { input: { settings: params?.settings ?? params } });
      return { success: data.saveSettings?.success ?? false, data: data.saveSettings as any };
    }
    // Phase 1: Initialization Progress via HTTP
    case 'get_initialization_progress': {
      const query = `query GetInitializationProgress { getInitializationProgress { ui_ready critical_services_ready async_init_complete fully_ready sync_init_complete message } }`;
      const data = await appSyncRequest<{ getInitializationProgress: any }>(query);
      return { success: true, data: data.getInitializationProgress as any };
    }
    default:
      return null;
  }
}
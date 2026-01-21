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

export const webApi = {
  async getAllMine(): Promise<GetAllMineResponse> {
    const data = await appSyncRequest<{ getAllMine: GetAllMineResponse }>(GET_ALL_MINE_QUERY);
    return data.getAllMine;
  },

  async getOrgAgentTree(rootId?: string): Promise<any> {
    const data = await appSyncRequest<{ getOrgAgentTree: any }>(GET_ORG_AGENT_TREE_QUERY, { rootId });
    return data.getOrgAgentTree;
  },
};

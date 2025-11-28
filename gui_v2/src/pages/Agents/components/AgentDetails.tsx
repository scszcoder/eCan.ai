import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { App, Button, Card, Col, DatePicker, Form, Input, Radio, Row, Select, Tag, Tooltip, TreeSelect, Modal } from 'antd';
import { EditOutlined, SaveOutlined, InfoCircleOutlined, DeleteOutlined, CloseOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { useOrgStore } from '@/stores/orgStore';
import { useTaskStore, useSkillStore, useVehicleStore, useAgentStore } from '@/stores';
import { get_ipc_api } from '@/services/ipc_api';
import { StyledFormItem } from '@/components/Common/StyledForm';
import { AvatarManager, AvatarData } from '@/components/Avatar';
import { useEffectOnActive } from 'keepalive-for-react';
import { useDeleteConfirm } from '@/components/Common/DeleteConfirmModal';

type Gender = 'gender_options.male' | 'gender_options.female';

interface AgentDetailsForm {
  id?: string;
  name?: string;
  gender?: Gender;
  birthday?: Dayjs | null;
  owner?: string;
  personalities?: string[];  // Unified naming: personality_traits → personalities
  title?: string[];
  org_id?: string; // Organization ID (single selection)
  supervisor_id?: string; // Supervisor ID (single selection)
  tasks?: string[];
  skills?: string[];
  vehicle_id?: string | null;
  description?: string; // Agent description
  extra_data?: string; // Extra data/notes
}

// Predefined personality trait options (using i18n keys)
const knownPersonalities = [
  'personality.friendly',
  'personality.analytical',
  'personality.creative',
  'personality.efficient',
  'personality.empathetic',
  'personality.patient',
  'personality.detail_oriented',
  'personality.proactive',
  'personality.collaborative',
  'personality.innovative'
];

// 预Definition的职称选项（使用国际化 key）
const knownTitles = [
  'title.engineer',
  'title.manager',
  'title.analyst',
  'title.designer',
  'title.operator',
  'title.developer',
  'title.architect',
  'title.consultant',
  'title.specialist',
  'title.coordinator'
];

// Tasks and skills will be sourced from global store to link with Tasks/Skills pages
// We keep fallback arrays in case store is empty to avoid empty UI when no data loaded yet
const knownTasks = ['task_001', 'task_002', 'task_003'];
const knownSkills = ['skill_001', 'skill_002', 'skill_003'];

const AgentDetails: React.FC = () => {
  const { message } = App.useApp();
  const showDeleteConfirm = useDeleteConfirm();
  const navigate = useNavigate();
  const location = useLocation();
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  
  // ScrollPositionSave
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  
  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
  useEffectOnActive(
    () => {
      const container = scrollContainerRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
        });
      }
      
      return () => {
        const container = scrollContainerRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
        }
      };
    },
    []
  );
  // Support两种新建模式：/agents/add 和 /agents/details/new
  const isNew = id === 'new' || location.pathname === '/agents/add';
  const username = useUserStore((s: any) => s.username);
  
  // 从QueryParameter中Get orgId（Used forSave后返回）
  const searchParams = new URLSearchParams(location.search);
  const defaultOrgId = searchParams.get('orgId');

  // Get vehicles List
  const { items: vehicles, fetchItems: fetchVehicles } = useVehicleStore();

  // 计算本机 vehicle ID（假设本机是 hostname 为 localhost 或 name Include "本机" 的）
  const localVehicleId = useMemo(() => {
    if (!vehicles || vehicles.length === 0) return null;
    // 优先查找 hostname 为 localhost 的
    const localVehicle = vehicles.find((v: any) =>
      v.hostname === 'localhost' ||
      v.name?.includes('本机') ||
      v.ip === '127.0.0.1' ||
      v.ip === '0.0.0.0'
    );
    return localVehicle?.id || vehicles[0]?.id || null;
  }, [vehicles]);

  // 使用专用的 taskStore 和 skillStore
  const storeTasks = useTaskStore((state) => state.items);
  const storeSkills = useSkillStore((state) => state.items);
  const setTasks = useTaskStore((state) => state.setItems);
  const setSkills = useSkillStore((state) => state.setItems);
  
  // Get组织Data
  const { treeOrgs, setAllOrgAgents, shouldFetchData, setLoading: setOrgLoading, setError: setOrgError } = useOrgStore();
  
  // Get agentStore Used for读取最新的 agent Data
  const getAgentById = useAgentStore((state) => state.getAgentById);

  // Build options for selects with full object data for tooltips
  // Save完整的task和skill对象Map，Used forDisplayDetailedInformation
  const taskMap = useMemo(() => {
    const map = new Map();
    (storeTasks || []).forEach((t: any) => {
      const key = t.name || t.skill;
      if (key) map.set(key, t);
    });
    return map;
  }, [storeTasks]);

  const skillMap = useMemo(() => {
    const map = new Map();
    (storeSkills || []).forEach((s: any) => {
      if (s.name) map.set(s.name, s);
    });
    return map;
  }, [storeSkills]);

  // For tasks, use task name or skill; for skills, use skill.name.
  const taskOptions = useMemo(() => {
    const taskNames = (storeTasks || [])
      .map((t: any) => t.name || t.skill)
      .filter(Boolean);
    const unique = Array.from(new Set(taskNames));
    return unique.length > 0 ? unique : knownTasks;
  }, [storeTasks]);

  const skillOptions = useMemo(() => {
    const names = (storeSkills || [])
      .map((s: any) => s.name)
      .filter(Boolean);
    // 使用 Set 去重，确保没有重复的Name
    const unique = Array.from(new Set(names));
    return unique.length > 0 ? unique : knownSkills;
  }, [storeSkills]);

  // 构建组织树形Data供TreeSelect使用（避免LoopReference）
  const organizationTreeData = useMemo(() => {
    const buildTreeData = (node: any, parentPath: string = ''): any => {
      if (!node || !node.id) return null; // Add id Check
      
      // 构建When前节点的完整Path
      const currentPath = parentPath ? `${parentPath} / ${node.name}` : node.name;
      
      // 只提取必要的Field，避免LoopReference
      const treeNode: any = {
        title: node.name || node.id, // 确保有 title
        value: node.id,
        key: node.id,
        fullPath: currentPath, // Storage完整Path，Used for选中后Display
      };
      
      // RecursiveProcess子节点，只传递必要的Data
      if (node.children && Array.isArray(node.children) && node.children.length > 0) {
        treeNode.children = node.children
          .filter((child: any) => child && child.id) // Filter掉无效节点
          .map((child: any) => {
            // 为每个子节点Create简化的对象，只Include必要Field
            const simplifiedChild = {
              id: child.id,
              name: child.name,
              children: child.children
            };
            return buildTreeData(simplifiedChild, currentPath);
          })
          .filter(Boolean);
      }
      
      return treeNode;
    };

    if (treeOrgs && treeOrgs.length > 0) {
      // Create根节点的简化Version
      const rootNode = {
        id: treeOrgs[0].id,
        name: treeOrgs[0].name,
        children: treeOrgs[0].children
      };
      const data = [buildTreeData(rootNode)].filter(Boolean);
      return data;
    }
    return [];
  }, [treeOrgs]);

  // GetWhen前层级及以上的Allagents（Used for上级Select）
  const [supervisorTreeData, setSupervisorTreeData] = useState<any[]>([]);

  // Get vehicles List
  useEffect(() => {
    if (username) {
      fetchVehicles(username).catch((error: any) => {
        console.error('[AgentDetails] Failed to fetch vehicles:', error);
      });
    }
  }, [username, fetchVehicles]);

  // Get组织Name的HelperFunction
  const getOrgName = useCallback((orgId: string) => {
    const findOrgName = (node: any, targetId: string): string | null => {
      if (node.id === targetId) {
        return node.name;
      }
      if (node.children && Array.isArray(node.children)) {
        for (const child of node.children) {
          const found = findOrgName(child, targetId);
          if (found) return found;
        }
      }
      return null;
    };

    if (treeOrgs && treeOrgs.length > 0) {
      const orgName = findOrgName(treeOrgs[0], orgId);
      if (orgName) return orgName;
    }
    
    // 回退到翻译键
    return t(orgId) || orgId;
  }, [treeOrgs, t]);

  // Proactively fetch tasks/skills if empty so dropdowns populate without visiting their pages first
  useEffect(() => {
    const api = get_ipc_api();
    const fetchIfNeeded = async () => {
      try {
        let uname = username;
        if (!uname) {
          const loginInfo = await api.getLastLoginInfo<{ last_login: { username: string } }>();
          if (loginInfo?.success) {
            uname = loginInfo.data?.last_login?.username;
          }
        }
        if (uname) {
          if (!storeTasks || storeTasks.length === 0) {
            const res = await api.getAgentTasks<{ tasks: any[] }>(uname, []);
            if (res?.success && res.data?.tasks) setTasks(res.data.tasks as any);
          }
          if (!storeSkills || storeSkills.length === 0) {
            const res2 = await api.getAgentSkills<{ skills: any[] }>(uname, []);
            if (res2?.success && res2.data?.skills) setSkills(res2.data.skills as any);
          }
        }
      } catch (e) {
        // silent fail; UI will use fallbacks
      }
    };
    fetchIfNeeded();
  }, [username, storeTasks?.length, storeSkills?.length, setTasks, setSkills]);

  const [form] = Form.useForm<AgentDetailsForm>();
  const [editMode, setEditMode] = useState(isNew);
  const [loading, setLoading] = useState(false);
  // Initialize selectedOrgId 为 defaultOrgId（If存在）
  const [selectedOrgId, setSelectedOrgId] = useState<string | undefined>(defaultOrgId || undefined);
  // Avatar Status
  const [avatarData, setAvatarData] = useState<AvatarData | undefined>();

  // Ensure we have a stable agentId for AvatarDisplay even before form finishes loading
  const watchedFormId = Form.useWatch('id', form);
  const resolvedAgentId = (id as string) || (watchedFormId as string) || '';
  
  // 确定Page模式：view（查看）、edit（Edit）、create（新增）
  const pageMode = useMemo(() => {
    if (isNew) return 'create';
    return editMode ? 'edit' : 'view';
  }, [isNew, editMode]);

  // 主动Load组织Data（If未Load）
  useEffect(() => {
    const loadOrgData = async () => {
      if (!username) return;
      
      // If已有Data且不NeedRefresh，则跳过
      if (treeOrgs && treeOrgs.length > 0 && !shouldFetchData()) {
        // 即使使用CacheData，也要确保新建模式下SettingsDefault组织
        if (isNew && defaultOrgId) {
          const currentOrg = form.getFieldValue('org_id');
          if (!currentOrg || currentOrg !== defaultOrgId) {
            form.setFieldsValue({ org_id: defaultOrgId });
            setSelectedOrgId(defaultOrgId);
          }
        }
        return;
      }

      try {
        setOrgLoading(true);
        const api = get_ipc_api();
        const response = await api.getAllOrgAgents(username) as any;

        if (response?.success && response.data?.orgs) {
          setAllOrgAgents(response.data);

          // DataLoadCompleted后，If是新建模式且有Default组织，SettingsDefaultValue
          if (isNew && defaultOrgId) {
            // 使用 setTimeout 确保在组织树DataUpdate后再SettingsFormValue
            setTimeout(() => {
              form.setFieldsValue({ org_id: defaultOrgId });
              setSelectedOrgId(defaultOrgId);
            }, 100);
          }
        } else {
          console.error('[AgentDetails] Failed to load org data:', response);
          setOrgError(response?.error?.message || 'Failed to load organization data');
        }
      } catch (e) {
        console.error('[AgentDetails] Error loading org data:', e);
        setOrgError('Error loading organization data');
      } finally {
        setOrgLoading(false);
      }
    };
    
    loadOrgData();
  }, [username, treeOrgs, shouldFetchData, setAllOrgAgents, setOrgLoading, setOrgError, isNew, defaultOrgId, form]);

  // 从IPCGetagentData（Edit模式）
  // Add一个 ref 来跟踪是否刚刚Save过
  const justSavedRef = useRef(false);
  
  useEffect(() => {
    const fetchAgentData = async () => {
      if (isNew || !id || !username) return;
      
      // If刚刚Save过，跳过这次Get（因为Data已经通过 agentStore Update了）
      if (justSavedRef.current) {
        justSavedRef.current = false;
        return;
      }
      
      try {
        setLoading(true);
        const api = get_ipc_api();
        const response = await api.getAgents(username, [id]) as any;
        
        if (response?.success && response.data?.agents && Array.isArray(response.data.agents) && response.data.agents.length > 0) {
          const agent = response.data.agents[0];

          // UpdateFormData
          // 优先使用 agent 自身的 org_id，If没有则使用 URL Parameter中的 defaultOrgId
          const orgId = agent.org_id || agent.organization || defaultOrgId || '';
          
          // Convert skills and tasks from objects to names (for Select component)
          // Skills/tasks from backend are objects with {id, name, ...}
          const skillNames = (agent.skills || []).map((s: any) => {
            if (typeof s === 'string') return s;
            // Try multiple fields: name, skill_name, id
            return s.name || s.skill_name || s.id || String(s);
          }).filter(Boolean);  // Remove empty values
          
          const taskNames = (agent.tasks || []).map((t: any) => {
            if (typeof t === 'string') return t;
            // Try multiple fields: name, task_name, id
            return t.name || t.task_name || t.id || String(t);
          }).filter(Boolean);  // Remove empty values
          
          // Extract extra_data: if it's an object, get notes; if string, use as is
          let extraDataText = '';
          if (agent.extra_data) {
            if (typeof agent.extra_data === 'object') {
              extraDataText = agent.extra_data.notes || '';
            } else {
              extraDataText = agent.extra_data;
            }
          } else if (agent.metadata) {
            extraDataText = agent.metadata;
          }
          
          // Ensure title and personalities are arrays
          const titleArray = Array.isArray(agent.title) ? agent.title : (agent.title ? [agent.title] : []);
          const personalitiesArray = Array.isArray(agent.personalities) ? agent.personalities : (agent.personalities ? [agent.personalities] : []);
          
          form.setFieldsValue({
            id: agent.card?.id || agent.id,
            name: agent.card?.name || agent.name,
            gender: agent.gender || 'gender_options.male',
            birthday: agent.birthday ? dayjs(agent.birthday) : null,
            owner: agent.owner || username,
            personalities: personalitiesArray,  // Use personalities (unified naming)
            title: titleArray,
            org_id: orgId,
            supervisor_id: agent.supervisor_id || '',
            tasks: taskNames,
            skills: skillNames,
            vehicle_id: agent.vehicle_id || agent.vehicle || localVehicleId || '',
            description: agent.description || '',
            extra_data: extraDataText
          });
          // Settings选中的组织ID以Display完整Path
          if (orgId) {
            setSelectedOrgId(orgId);
          }
          
          // Settings Avatar Data - 保留完整的Data结构
          if (agent.avatar?.imageUrl) {
            setAvatarData({
              type: agent.avatar.type || 'system',
              imageUrl: agent.avatar.imageUrl,
              videoUrl: agent.avatar.videoPath || agent.avatar.videoUrl || '',
              thumbnailUrl: agent.avatar.thumbnailUrl || agent.avatar.imageUrl || '',
              id: agent.avatar.id || agent.avatar_resource_id || '',
              hash: agent.avatar.hash || ''
            });
          }
          
          // 从 AgentCard Edit进入时，自动进入Edit模式
          setEditMode(true);
        } else {
          // If没有找到 agent Data，DisplayError
          message.error(t('pages.agents.fetch_failed') || 'Agent not found');
        }
      } catch (e) {
        console.error('Failed to fetch agent data:', e);
        message.error(t('pages.agents.fetch_failed') || 'Failed to fetch agent data');
      } finally {
        setLoading(false);
      }
    };

    fetchAgentData();
  }, [id, isNew, username, form, message, t, defaultOrgId]);

  // 不再使用 initialValues，改为在 useEffect 中逐个SettingsField，避免LoopReferenceWarning

  // 使用 useEffect 来Settings初始FormValue（仅新建模式）
  useEffect(() => {
    if (isNew) {
      // 只有在组织树DataLoadCompleted后才SettingsFormValue
      if (organizationTreeData.length > 0) {
        // 使用 setTimeout DelaySettings，确保在下一个EventLoop中Execute
        const timeoutId = setTimeout(() => {
          try {
            // Create completely independent initial values object to avoid any possible references
            const initialValues: Partial<AgentDetailsForm> = {
              id: '',
              name: '',
              gender: 'gender_options.male' as Gender,
              birthday: dayjs(),
              owner: username || t('common.owner') || 'owner',
              personalities: [], // Use personalities (unified naming)
              title: [], // New array
              org_id: defaultOrgId || '',
              supervisor_id: '',
              tasks: [], // New array
              skills: [], // New array
              vehicle_id: localVehicleId || '',
              description: '',
              extra_data: ''
            };

            // Use setFieldsValue to set all values at once
            form.setFieldsValue(initialValues);
            setEditMode(true);

            // Set selected organization
            if (defaultOrgId) {
              setSelectedOrgId(defaultOrgId);
            }
          } catch (error) {
            console.error('[AgentDetails] Error setting initial values:', error);
          }
        }, 0);

        // Cleanup function
        return () => clearTimeout(timeoutId);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNew, defaultOrgId, organizationTreeData.length, username, localVehicleId]);

  // Monitor defaultOrgId changes to ensure selectedOrgId is synchronized
  useEffect(() => {
    // Only set default if current selection is empty to avoid overwriting user selection
    const currentOrg = form.getFieldValue('org_id');
    if (isNew && defaultOrgId && !currentOrg && organizationTreeData.length > 0) {
      setSelectedOrgId(defaultOrgId);
      // Also update form field
      form.setFieldValue('org_id', defaultOrgId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultOrgId, isNew, organizationTreeData.length]);

  // Get supervisor candidates (agents from current and parent organizations)
  useEffect(() => {
    const fetchAgentsForSupervisor = async () => {
      if (!treeOrgs || treeOrgs.length === 0) return;
      
      try {
        // Get agents from currently selected organization
        const currentOrgId = form.getFieldValue('org_id') || defaultOrgId;
        
        if (!currentOrgId) {
          setSupervisorTreeData([]);
          return;
        }
        
        const currentOrgIds = [currentOrgId]; // Convert to array for compatibility with subsequent logic
        
        // Find organization node and return path from root to target node (only return id and name to avoid circular references)
        const findOrgPath = (node: any, targetId: string, path: Array<{id: string, name: string}> = []): Array<{id: string, name: string}> | null => {
          const simplifiedNode = { id: node.id, name: node.name };
          const currentPath = [...path, simplifiedNode];
          
          if (node.id === targetId) return currentPath;
          
          if (node.children && Array.isArray(node.children)) {
            for (const child of node.children) {
              const found = findOrgPath(child, targetId, currentPath);
              if (found) return found;
            }
          }
          return null;
        };
        
        // 根据组织 ID Get完整的组织节点（从原始 treeOrgs 中查找）
        const getOrgNodeById = (root: any, orgId: string): any => {
          if (root.id === orgId) return root;
          if (root.children && Array.isArray(root.children)) {
            for (const child of root.children) {
              const found = getOrgNodeById(child, orgId);
              if (found) return found;
            }
          }
          return null;
        };
        
        // 构建上级Select的树形Data（按组织分组）
        const buildAgentTree = (orgId: string, orgName: string): any => {
          // 从原始树中Get组织节点
          const orgNode = getOrgNodeById(treeOrgs[0], orgId);
          const agents = orgNode?.agents || [];

          if (agents.length === 0) return null;

          // 只提取必要的Field，避免LoopReference，Filter掉无效节点
          const agentNodes = agents
            .filter((agent: any) => agent && agent.id) // Filter掉无效的 agent
            .map((agent: any) => ({
              title: agent.name || agent.id,
              value: agent.id,
              key: agent.id,
              isLeaf: true,
            }));

          return {
            title: orgName,
            value: `org-${orgId}`,
            key: `org-${orgId}`,
            selectable: false,
            children: agentNodes,
          };
        };
        
        const treeData: any[] = [];
        const processedOrgIds = new Set<string>();
        
        // 对每个选中的组织，Get其到根节点的Path（IncludeAll父级组织）
        for (const orgId of currentOrgIds) {
          const orgPath = findOrgPath(treeOrgs[0], orgId);

          if (orgPath) {
            // 为Path上的每个组织构建agent树（从根到When前节点）
            for (const simplifiedOrg of orgPath) {
              // 避免重复Add
              if (!processedOrgIds.has(simplifiedOrg.id)) {
                processedOrgIds.add(simplifiedOrg.id);
                const tree = buildAgentTree(simplifiedOrg.id, simplifiedOrg.name);
                if (tree) {
                  treeData.push(tree);
                }
              }
            }
          }
        }

        setSupervisorTreeData(treeData);
      } catch (e) {
        console.error('Failed to fetch agents for supervisor selection:', e);
      }
    };
    
    fetchAgentsForSupervisor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, defaultOrgId, treeOrgs.length]);

  // 多选TagEdit器 - 使用 Select mode="tags" Implementation友好交互
  // Support预Definition选项（国际化）和UserCustomInput
  const TagsEditor: React.FC<{
    value?: string[];
    onChange?: (value: string[]) => void;
    options: string[];
    disabled?: boolean;
    placeholder?: string;
    isOrgField?: boolean;
    'aria-label'?: string;
    id?: string;
    dataMap?: Map<string, any>;  // Used forDisplayDetailedInformation的DataMap
    dataType?: 'task' | 'skill';  // DataType，Used forDisplay不同的DetailedInformation
  }> = ({ value, onChange, options, disabled, placeholder, isOrgField, 'aria-label': ariaLabel, id, dataMap, dataType }) => {
    // DetailedInformationModalStatus
    const [detailModalVisible, setDetailModalVisible] = React.useState(false);
    const [selectedDetailItem, setSelectedDetailItem] = React.useState<any>(null);
    // GetDisplay文本
    // If是预Definition选项（如 personality.friendly），Display国际化翻译
    // If是UserCustomInput，直接Display原文
    const getDisplayText = useCallback((val: string) => {
      if (!val) return '';

      if (isOrgField) {
        return getOrgName(val);
      }

      // Check是否是预Definition的国际化 key（Include . 的格式）
      if (val.includes('.')) {
        const translated = t(val);

        // If翻译Success（翻译Result不等于原 key），返回翻译
        if (translated && translated !== val) {
          return translated;
        }
        // If翻译Failed，返回 key 的最后一部分作为后备（如 friendly）
        const parts = val.split('.');
        return parts[parts.length - 1];
      }

      // 否则直接返回原Value（UserCustomInput）
      return val;
    }, [isOrgField, getOrgName, t]);

    // 使用 useMemo Cache选项，避免重复计算
    const selectOptions = useMemo(() => {
      return options.map((opt, index) => {
        const displayText = getDisplayText(opt);
        return {
          label: displayText,  // 下拉List中Display的文本（翻译后）
          value: opt,          // 实际Storage的Value（国际化 key）
          key: `option-${index}-${opt}`,  // 使用索引+Value确保唯一性（索引在前更Reliable）
          title: ''            // 清空title，避免原生tooltip
        };
      });
    }, [options, getDisplayText]);

    // ProcessSelect变化 - WhenUserSelect预Definition选项时，Storage国际化 key；CustomInput时，Storage原文
    const handleChange = useCallback((newValue: string[]) => {
      if (!onChange) return;

      // Process每个Value：Check是否是翻译文本，If是则Convert回国际化 key
      const processedValues = newValue.map(val => {
        // Check是否已经是国际化 key
        if (val.includes('.')) {
          return val;
        }

        // Check是否是翻译文本，NeedConvert回国际化 key
        const matchedOption = selectOptions.find(opt => opt.label === val);
        if (matchedOption) {
          return matchedOption.value;
        }

        // 否则是UserCustomInput，直接返回
        return val;
      });

      onChange(processedValues);
    }, [onChange, selectOptions]);

    return (
      <>
      <Select
        id={id}
        mode="tags"
        style={{ width: '100%' }}
        placeholder={placeholder}
        value={Array.isArray(value) ? value : []}
        onChange={handleChange}
        disabled={disabled}
        maxTagCount="responsive"
        showSearch
        allowClear
        tokenSeparators={[',']}
        aria-label={ariaLabel}
        // SearchFilter - Support模糊Searchlabel和value
        filterOption={(input, option) => {
          if (!input) return true;
          const searchText = input.toLowerCase();
          const label = (option?.label || '').toString().toLowerCase();
          const value = (option?.value || '').toString().toLowerCase();
          return label.includes(searchText) || value.includes(searchText);
        }}
        // 下拉框Positioning - 避免遮挡Input框
        popupMatchSelectWidth={false}
        listHeight={400}
        placement="bottomLeft"
        // TagRender - AddtooltipDisplayDescription
        tagRender={(props) => {
          const { value: tagValue, closable, onClose } = props;
          const displayText = getDisplayText(tagValue as string);
          const isCustom = tagValue && typeof tagValue === 'string' && !tagValue.includes('.');
          const itemData = dataMap?.get(tagValue as string);
          const description = itemData?.description || '';

          const tagContent = (
            <Tag
              key={`tag-${tagValue}`}  // ✅ Add key
              color={isCustom ? 'green' : 'blue'}
              closable={closable && !disabled}
              onClose={onClose}
              style={{ marginRight: 3, cursor: itemData ? 'pointer' : 'default' }}
              onClick={(e) => {
                if (itemData) {
                  e.stopPropagation();
                  setSelectedDetailItem(itemData);
                  setDetailModalVisible(true);
                }
              }}
            >
              {displayText}
            </Tag>
          );

          // If有DescriptionInformation，Addtooltip
          if (description && dataMap) {
            return (
              <Tooltip 
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ flex: 1 }}>{description}</div>
                    <InfoCircleOutlined 
                      style={{ fontSize: 14, cursor: 'pointer', color: '#40a9ff' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedDetailItem(itemData);
                        setDetailModalVisible(true);
                      }}
                    />
                  </div>
                }
                mouseEnterDelay={0.3}
              >
                {tagContent}
              </Tooltip>
            );
          }

          return tagContent;
        }}
        // 下拉选项Configuration - 使用Cache的选项
        options={selectOptions}
        // Custom下拉选项Render - AddtooltipDisplayDescription
        optionRender={(option) => {
          const itemData = dataMap?.get(option.value as string);
          const description = itemData?.description || '';
          
          if (description && dataMap) {
            return (
              <Tooltip
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ flex: 1 }}>{description}</div>
                    <InfoCircleOutlined 
                      style={{ fontSize: 14, cursor: 'pointer', color: '#40a9ff' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedDetailItem(itemData);
                        setDetailModalVisible(true);
                      }}
                    />
                  </div>
                }
                placement="right"
                mouseEnterDelay={0.3}
              >
                <div style={{ padding: '4px 0', width: '100%' }}>{option.label}</div>
              </Tooltip>
            );
          }
          
          return <div style={{ padding: '4px 0' }}>{option.label}</div>;
        }}
        // DisabledSelect自带的titleProperty，避免tooltip冲突
        optionFilterProp="label"
        // 不使用 getPopupContainer，让下拉框自然Positioning，避免遮挡
        // 不Display下拉箭头，更像Input框
        suffixIcon={null}
        // 自动Get焦点时不自动Open下拉框
        open={undefined}
      />
      
      {/* DetailedInformationModal */}
      {dataMap && selectedDetailItem && (
        <Modal
          title={dataType === 'task' ? t('pages.tasks.details', 'Task Details') : t('pages.skills.details', 'Skill Details')}
          open={detailModalVisible}
          onCancel={() => setDetailModalVisible(false)}
          footer={[
            <Button key="close" onClick={() => setDetailModalVisible(false)}>
              {t('common.close', 'Close')}
            </Button>
          ]}
          width={600}
          centered
        >
          <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
            {/* Name */}
            <div style={{ marginBottom: 16 }}>
              <strong>{t('common.name', 'Name')}:</strong>{' '}
              <span style={{ color: selectedDetailItem.name || selectedDetailItem.skill ? 'inherit' : '#999' }}>
                {selectedDetailItem.name || selectedDetailItem.skill || '-'}
              </span>
            </div>
            
            {/* Description */}
            <div style={{ marginBottom: 16 }}>
              <strong>{t('common.description', 'Description')}:</strong>
              <div style={{ marginTop: 8, padding: 12, background: 'rgba(0,0,0,0.02)', borderRadius: 4, color: selectedDetailItem.description ? 'inherit' : '#999' }}>
                {selectedDetailItem.description || '-'}
              </div>
            </div>
            
            {/* Task特有Field */}
            {dataType === 'task' && (
              <>
                <div style={{ marginBottom: 16 }}>
                  <strong>{t('pages.tasks.priorityLabel', 'Priority')}:</strong>{' '}
                  <span style={{ color: selectedDetailItem.priority ? 'inherit' : '#999' }}>
                    {selectedDetailItem.priority || '-'}
                  </span>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <strong>{t('pages.tasks.triggerLabel', 'Trigger')}:</strong>{' '}
                  <span style={{ color: selectedDetailItem.trigger ? 'inherit' : '#999' }}>
                    {selectedDetailItem.trigger || '-'}
                  </span>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <strong>{t('pages.tasks.statusLabel', 'Status')}:</strong>{' '}
                  <span style={{ color: selectedDetailItem.status ? 'inherit' : '#999' }}>
                    {selectedDetailItem.status || '-'}
                  </span>
                </div>
              </>
            )}
            
            {/* Skill特有Field */}
            {dataType === 'skill' && (
              <>
                <div style={{ marginBottom: 16 }}>
                  <strong>{t('pages.skills.level', 'Level')}:</strong>{' '}
                  <span style={{ color: selectedDetailItem.level !== undefined && selectedDetailItem.level !== null ? 'inherit' : '#999' }}>
                    {selectedDetailItem.level !== undefined && selectedDetailItem.level !== null ? selectedDetailItem.level : '-'}
                  </span>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <strong>{t('pages.skills.statusLabel', 'Status')}:</strong>{' '}
                  <span style={{ color: selectedDetailItem.status ? 'inherit' : '#999' }}>
                    {selectedDetailItem.status || '-'}
                  </span>
                </div>
              </>
            )}
            
            {/* Metadata */}
            <div style={{ marginBottom: 16 }}>
              <strong>{t('common.metadata', 'Metadata')}:</strong>
              <pre style={{ marginTop: 8, padding: 12, background: 'rgba(0,0,0,0.02)', borderRadius: 4, fontSize: 12, overflowX: 'auto', color: selectedDetailItem.metadata ? 'inherit' : '#999' }}>
                {selectedDetailItem.metadata ? JSON.stringify(selectedDetailItem.metadata, null, 2) : '-'}
              </pre>
            </div>
          </div>
        </Modal>
      )}
    </>
    );
  };



  const handleDelete = async () => {
    if (!id || !username) return;
    
    const agentName = form.getFieldValue('name') || 'this agent';
    
    showDeleteConfirm({
      title: t('pages.agents.deleteConfirmTitle', 'Delete Agent'),
      message: t('pages.agents.deleteConfirmMessage', `Are you sure you want to delete "${agentName}"? This action cannot be undone.`),
      okText: t('common.delete', 'Delete'),
      cancelText: t('common.cancel', 'Cancel'),
      onOk: async () => {
        try {
          setLoading(true);
          const api = get_ipc_api();
          const response = await api.deleteAgent(username, [id]);
          
          if (response.success) {
            message.success(t('pages.agents.deleteSuccess', 'Agent deleted successfully'));
            
            // 从 agentStore 中Remove已Delete的 agent
            const { removeAgent } = useAgentStore.getState();
            removeAgent(id);
            
            // 同时从 orgStore 中Remove
            const { removeAgentFromOrg } = useOrgStore.getState();
            removeAgentFromOrg(id);
            
            // Refresh组织和 agent Data
            try {
              const api = get_ipc_api();
              const refreshResponse = await api.getAllOrgAgents(username);
              if (refreshResponse?.success && refreshResponse.data) {
                useOrgStore.getState().setAllOrgAgents(refreshResponse.data as any);
              }
            } catch (error) {
              console.error('[AgentDetails] Error refreshing org data after delete:', error);
            }
            
            // 跳转回agentsList页
            navigate('/agents');
          } else {
            message.error(response.error?.message || t('pages.agents.deleteError', 'Failed to delete agent'));
          }
        } catch (error) {
          console.error('[AgentDetails] Delete error:', error);
          message.error(t('pages.agents.deleteError', 'Failed to delete agent'));
        } finally {
          setLoading(false);
        }
      },
    });
  };
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      
      // Convert skills and tasks from names to IDs only
      const skillIds = (values.skills || []).map((skillName: string) => {
        const skill = skillMap.get(skillName);
        return skill ? skill.id : null;
      }).filter(id => id !== null);
      
      const taskIds = (values.tasks || []).map((taskName: string) => {
        const task = taskMap.get(taskName);
        return task ? task.id : null;
      }).filter(id => id !== null);
      
      // Serialize dayjs and metadata
      const payload = {
        ...values,
        id: values.id || id,  // 确保Include id Field
        birthday: values.birthday ? (values.birthday as Dayjs).toISOString() : null,
        skills: skillIds,  // 只Send ID 数组
        tasks: taskIds,    // 只Send ID 数组
        // Avatar Data - Send avatar_resource_id 而not完整的 avatar Data
        avatar_resource_id: avatarData?.id || null
      };
      setLoading(true);
      const api = get_ipc_api();
      const res = isNew
        ? await api.newAgent(username, [payload])
        : await api.saveAgent(username, [payload]);
      setLoading(false);
      if (res.success) {
        message.success(t('common.saved_successfully') || 'Saved');
        
        // 策略：先用返回的DataFastUpdate UI，然后Refresh完整Data确保一致性
        let savedAgentData: any = null;
        try {
          const responseData = res.data as any;
          
          // 第一步：使用返回的 agent Data立即Update UI（FastResponse）
          if (responseData?.agents && Array.isArray(responseData.agents) && responseData.agents.length > 0) {
            savedAgentData = responseData.agents[0];
            console.log('[AgentDetails] Step 1: Using updated agent from response:', savedAgentData.id);
            
            // TemporaryUpdate agentStore 中的这个 agent（仅Used for立即Display）
            const agentStore = useAgentStore.getState();
            const currentAgents = agentStore.agents;
            const agentIndex = currentAgents.findIndex((a: any) => a.id === savedAgentData.id);
            
            if (agentIndex !== -1) {
              const newAgents = [...currentAgents];
              newAgents[agentIndex] = savedAgentData;
              agentStore.setAgents(newAgents);
              console.log('[AgentDetails] Temporarily updated agent in agentStore for immediate UI update');
            }
          }
          
          // 第二步：等待BackendData完全Update后，Refresh完整的组织和 agent Data
          // 这样Can确保：
          // 1. 组织关系正确（If agent Move到了不同组织）
          // 2. 统计Data正确（组织的 agent Count等）
          // 3. All关联Data都是最新的
          console.log('[AgentDetails] Step 2: Waiting for backend to complete, then refresh all data...');
          await new Promise(resolve => setTimeout(resolve, 500)); // 增加Delay确保BackendCompleted
          
          const refreshResponse = await api.getAllOrgAgents(username);
          
          if (refreshResponse?.success && refreshResponse.data) {
            // 这会Update orgStore 和 agentStore，确保AllData一致
            useOrgStore.getState().setAllOrgAgents(refreshResponse.data as any);
            console.log('[AgentDetails] Step 2 completed: All org and agent data refreshed');
          } else {
            console.error('[AgentDetails] Failed to refresh org data:', refreshResponse);
          }
        } catch (error) {
          console.error('[AgentDetails] Error updating agent data:', error);
        }
        
        // If是Create模式，跳转到 agent List或组织Page
        if (isNew) {
          // AddDelay确保Data已经Update到 store
          await new Promise(resolve => setTimeout(resolve, 100));
          
          const orgId = form.getFieldValue('org_id');
          if (orgId) {
            // 跳转到该组织的Page，使用 replace 强制Refresh
            navigate(`/agents/organization/${orgId}`, { replace: true });
          } else {
            // 跳转到 agents 根Page
            navigate('/agents', { replace: true });
          }
          return;
        }
        
        // If是Edit模式，使用Save返回的DataUpdateForm（保留在EditPage）
        if (!isNew && id) {
          // 优先使用 savedAgentData（来自 save_agent Response），避免从 store Get可能的旧Data
          try {
            let updatedAgent = savedAgentData;
            
            // If没有 savedAgentData（不Should发生），fallback 到 store
            if (!updatedAgent) {
              console.warn('[AgentDetails] No savedAgentData, trying to get from agentStore...');
              updatedAgent = getAgentById(id) as any;
            }
            
            if (updatedAgent) {
              console.log('[AgentDetails] Updating form with agent data:', updatedAgent.id);
              
              // Convert skills and tasks from objects to names (for Select component)
              // Skills/tasks from backend are objects with {id, name, ...}
              const skillNames = (updatedAgent.skills || []).map((s: any) => {
                if (typeof s === 'string') return s;
                // Try multiple fields: name, skill_name, id
                return s.name || s.skill_name || s.id || String(s);
              }).filter(Boolean);  // Remove empty values
              
              const taskNames = (updatedAgent.tasks || []).map((t: any) => {
                if (typeof t === 'string') return t;
                // Try multiple fields: name, task_name, id
                return t.name || t.task_name || t.id || String(t);
              }).filter(Boolean);  // Remove empty values
              
              // Extract extra_data: if it's an object, get notes; if string, use as is
              let extraDataText = '';
              if (updatedAgent.extra_data) {
                if (typeof updatedAgent.extra_data === 'object') {
                  extraDataText = updatedAgent.extra_data.notes || '';
                } else {
                  extraDataText = updatedAgent.extra_data;
                }
              }
              
              const formData = {
                id: updatedAgent.card?.id || updatedAgent.id,
                name: updatedAgent.card?.name || updatedAgent.name,
                description: updatedAgent.description || updatedAgent.card?.description || '',
                gender: updatedAgent.gender || 'gender_options.male',
                birthday: updatedAgent.birthday ? dayjs(updatedAgent.birthday) : null,
                owner: updatedAgent.owner || username,
                personalities: updatedAgent.personalities || [],
                title: updatedAgent.title || [],
                org_id: updatedAgent.org_id || '',
                supervisor_id: updatedAgent.supervisor_id || '',
                tasks: taskNames,
                skills: skillNames,
                vehicle_id: updatedAgent.vehicle_id || '',
                extra_data: extraDataText
              };
              
              form.setFieldsValue(formData);
              
              // Update组织SelectStatus（Used forDisplay完整Path）
              if (updatedAgent.org_id) {
                setSelectedOrgId(updatedAgent.org_id);
              }
              
              // Update Avatar Data - 保留完整的 avatar Data结构
              if (updatedAgent.avatar) {
                setAvatarData({
                  type: updatedAgent.avatar.type || 'system',
                  imageUrl: updatedAgent.avatar.imageUrl || '',
                  videoUrl: updatedAgent.avatar.videoPath || updatedAgent.avatar.videoUrl || '',
                  thumbnailUrl: updatedAgent.avatar.thumbnailUrl || updatedAgent.avatar.imageUrl || '',
                  id: updatedAgent.avatar.id || updatedAgent.avatar_resource_id || '',
                  hash: updatedAgent.avatar.hash || ''
                });
              }
              
              // Settings标志，防止 useEffect 重新GetData
              justSavedRef.current = true;
            } else {
              console.warn('[AgentDetails] ⚠️ Agent not found in agentStore, falling back to API call');
              // If store 中没有Data，fallback 到 API 调用
              const api = get_ipc_api();
              const refreshResponse = await api.getAgents(username, [id]) as any;
              
              if (refreshResponse?.success && refreshResponse.data?.agents && refreshResponse.data.agents.length > 0) {
                const apiAgent = refreshResponse.data.agents[0];
                
                // Convert并UpdateForm（使用相同的逻辑）
                const skillNames = (apiAgent.skills || []).map((s: any) => {
                  if (typeof s === 'string') return s;
                  return s.name || s.skill_name || s.id || String(s);
                }).filter(Boolean);
                
                const taskNames = (apiAgent.tasks || []).map((t: any) => {
                  if (typeof t === 'string') return t;
                  return t.name || t.task_name || t.id || String(t);
                }).filter(Boolean);
                
                let extraDataText = '';
                if (apiAgent.extra_data) {
                  if (typeof apiAgent.extra_data === 'object') {
                    extraDataText = apiAgent.extra_data.notes || '';
                  } else {
                    extraDataText = apiAgent.extra_data;
                  }
                }
                
                const formData = {
                  id: apiAgent.card?.id || apiAgent.id,
                  name: apiAgent.card?.name || apiAgent.name,
                  description: apiAgent.description || apiAgent.card?.description || '',
                  gender: apiAgent.gender || 'gender_options.male',
                  birthday: apiAgent.birthday ? dayjs(apiAgent.birthday) : null,
                  owner: apiAgent.owner || username,
                  personalities: apiAgent.personalities || [],
                  title: apiAgent.title || [],
                  org_id: apiAgent.org_id || '',
                  supervisor_id: apiAgent.supervisor_id || '',
                  tasks: taskNames,
                  skills: skillNames,
                  vehicle_id: apiAgent.vehicle_id || '',
                  extra_data: extraDataText
                };
                
                form.setFieldsValue(formData);
                
                if (apiAgent.org_id) {
                  setSelectedOrgId(apiAgent.org_id);
                }
                
                if (apiAgent.avatar?.imageUrl) {
                  setAvatarData({
                    type: apiAgent.avatar.type || 'system',
                    imageUrl: apiAgent.avatar.imageUrl,
                    videoUrl: apiAgent.avatar.videoPath || apiAgent.avatar.videoUrl || '',
                    thumbnailUrl: apiAgent.avatar.thumbnailUrl || apiAgent.avatar.imageUrl || '',
                    id: apiAgent.avatar.id || apiAgent.avatar_resource_id || '',
                    hash: apiAgent.avatar.hash || ''
                  });
                }
                
                console.log('[AgentDetails] ✅ Updated form from API fallback');
              }
            }
          } catch (error) {
            console.error('[AgentDetails] ❌ Error refreshing agent data:', error);
          }
        }
        
        // ✅ 保持在Edit模式，AllowUser继续Edit
        // setEditMode(false);  // ← Remove这行，保持Edit模式
        
        if (isNew) {
          // After creation, navigate back to the OrgNavigator page with refresh flag
          const orgId = values.org_id;
          if (orgId && orgId !== 'root') {
            // 跳转到对应组织的navigatorPage，AddTime戳强制Refresh
            navigate(`/agents/organization/${orgId}?refresh=${Date.now()}`);
          } else {
            // 跳转到根navigatorPage，AddTime戳强制Refresh
            navigate(`/agents?refresh=${Date.now()}`);
          }
        }
      } else {
        message.error(res.error?.message || t('common.save_failed') || 'Save failed');
      }
    } catch (e: any) {
      message.error(e?.message || t('common.validation_failed') || 'Validation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <style>{`
        .resizable-textarea .ant-input {
          resize: vertical !important;
          min-height: 200px !important;
          overflow: auto !important;
        }
        .resizable-textarea textarea {
          resize: vertical !important;
          min-height: 200px !important;
          overflow: auto !important;
        }
        .agent-basic-info-section {
          display: flex;
          gap: 40px;
          margin-bottom: 24px;
          align-items: center;
        }
        .agent-basic-info-left {
          flex: 1;
        }
        .agent-basic-info-left .ant-form-item {
          margin-bottom: 0;
        }
        .agent-basic-info-left .ant-form-item-label {
          padding-bottom: 4px;
        }
        .agent-basic-info-left .ant-form-item-label > label {
          height: auto;
        }
        .agent-basic-info-right {
          flex-shrink: 0;
          width: 280px;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
      `}</style>
      <div style={{ padding: 12, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Card style={{ flex: 1, minHeight: 0, overflow: 'hidden', marginTop: '16px' }} styles={{ body: { padding: 12, height: '100%', overflow: 'hidden' } }}>
          <div ref={scrollContainerRef} style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden', paddingRight: 8 }}>
          <Form
            form={form}
            layout="vertical"
            style={{ maxWidth: '100%' }}
            autoComplete="off"
            role="form"
            aria-label={t('pages.agents.form_label') || 'Agent Details Form'}
            initialValues={{
              skills: [],
              tasks: [],
              personalities: [],
              title: []
            }}
          >
            {/* Basic Info Section with Avatar on the right */}
            <div className="agent-basic-info-section">
              <div className="agent-basic-info-left">
                {/* Name - with label on top */}
                <Form.Item 
                  name="name" 
                  label={t('common.name') || 'Name'}
                  htmlFor="agent-name"
                  rules={[{ required: true, message: t('common.please_input_name') || 'Please input name' }]}
                  style={{ marginBottom: 0 }}
                >
                  <Input
                    id="agent-name"
                    placeholder={t('common.name') || 'Name'}
                    disabled={!editMode}
                    autoComplete="name"
                    aria-label={t('common.name') || 'Name'}
                    aria-required="true"
                  />
                </Form.Item>
              </div>
              
              <div className="agent-basic-info-right">
                <AvatarManager
                  username={username || 'default'}
                  value={avatarData}
                  onChange={setAvatarData}
                  showVideo={true}
                  agentId={resolvedAgentId}
                />
                {/* Agent ID box for quick reference */}
                <div
                  style={{
                    marginTop: 8,
                    width: '100%',
                    padding: '8px 10px',
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: 6,
                    color: 'rgba(255,255,255,0.85)',
                    fontSize: 12
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Agent ID</div>
                  <div style={{
                    fontFamily: 'monospace',
                    wordBreak: 'break-all',
                    userSelect: 'text'
                  }}>
                    {(form.getFieldValue('id') as string) || id || ''}
                  </div>
                </div>
              </div>
            </div>
            
            {/* Divider */}
            <div style={{ 
              height: '1px', 
              background: 'linear-gradient(to right, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.3), rgba(255, 255, 255, 0.1))',
              margin: '24px 0'
            }} />
            <Row gutter={[12, 0]} style={{ margin: 0 }}>
              {/* 第一行：Owner 和 Gender */}
              <Col span={12}>
                <StyledFormItem name="owner" label={t('common.owner') || 'Owner'} htmlFor="agent-owner">
                  <Input
                    id="agent-owner"
                    placeholder={t('common.owner') || 'Owner'}
                    disabled={pageMode !== 'create'}
                    autoComplete="username"
                    aria-label={t('common.owner') || 'Owner'}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ 
                    paddingBottom: 8,
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'rgba(255, 255, 255, 0.95)',
                    letterSpacing: '0.3px'
                  }}>
                    {t('common.gender') || 'Gender'}
                  </div>
                  <Form.Item name="gender" noStyle>
                    <Radio.Group 
                      disabled={!editMode} 
                      aria-label={t('common.gender') || 'Gender'}
                    >
                      <Radio value="gender_options.male">{t('common.gender_options.male') || 'Male'}</Radio>
                      <Radio value="gender_options.female">{t('common.gender_options.female') || 'Female'}</Radio>
                    </Radio.Group>
                  </Form.Item>
                </div>
              </Col>
              
              {/* 第二行：Description */}
              <Col span={24}>
                <StyledFormItem name="description" label={t('pages.agents.description') || 'Description'} htmlFor="agent-description">
                  <Input.TextArea
                    id="agent-description"
                    rows={3}
                    disabled={!editMode}
                    autoComplete="off"
                    placeholder={t('pages.agents.description_placeholder') || 'Enter agent description'}
                    aria-label={t('pages.agents.description') || 'Description'}
                    className="resizable-textarea"
                    style={{ minHeight: '80px', resize: 'vertical' }}
                  />
                </StyledFormItem>
              </Col>

              {/* 第二行：Birthday 和 Vehicle */}
              <Col span={12}>
                <StyledFormItem name="birthday" label={t('common.birthday') || 'Birthday'} htmlFor="agent-birthday">
                  <DatePicker
                    id="agent-birthday"
                    style={{ width: '100%' }}
                    disabled={!editMode}
                    getPopupContainer={() => document.body}
                    placement="bottomLeft"
                    aria-label={t('common.birthday') || 'Birthday'}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem name="vehicle_id" label={t('pages.agents.vehicle') || 'Vehicle'} htmlFor="agent-vehicle">
                  <Select
                    id="agent-vehicle"
                    disabled={!editMode}
                    allowClear
                    placeholder={t('common.select_vehicle') || 'Select vehicle'}
                    options={vehicles.map((v: any, index: number) => ({
                      key: v.id || `vehicle-${index}`,  // Add唯一 key
                      value: v.id,
                      label: `${v.name || v.id}${v.ip ? ` (${v.ip})` : ''}`
                    }))}
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                    aria-label={t('pages.agents.vehicle') || 'Vehicle'}
                  />
                </StyledFormItem>
              </Col>

              {/* 第五行：Organization 和 Supervisor */}
              <Col span={12}>
                <StyledFormItem
                  name="org_id"
                  label={t('pages.agents.organization') || 'Organization'}
                  rules={[{ required: true, message: t('common.please_select_organization') || 'Please select organization' }]}
                  htmlFor="agent-organization"
                >
                  <TreeSelect
                    id="agent-organization"
                    treeData={organizationTreeData}
                    disabled={!editMode}
                    placeholder={t('common.select_organization') || 'Select organization'}
                    style={{ width: '100%' }}
                    treeDefaultExpandAll
                    allowClear
                    showSearch
                    treeNodeFilterProp="title"
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                    aria-label={t('pages.agents.organization') || 'Organization'}
                    aria-required="true"
                    onChange={(value) => {
                      setSelectedOrgId(value as string);
                    }}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="supervisor_id"
                  label={t('pages.agents.supervisors') || 'Supervisor'}
                  htmlFor="agent-supervisor"
                >
                  <TreeSelect
                    id="agent-supervisor"
                    treeData={supervisorTreeData}
                    disabled={!editMode}
                    placeholder={t('common.select_supervisor') || 'Select supervisor'}
                    style={{ width: '100%' }}
                    treeDefaultExpandAll
                    allowClear
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                    aria-label={t('pages.agents.supervisors') || 'Supervisor'}
                  />
                </StyledFormItem>
              </Col>

              {/* 第六行：Skills（Required）和 Tasks - 移到 Organization 后面 */}
              <Col span={12}>
                <StyledFormItem
                  name="skills"
                  label={t('pages.agents.skills') || 'Skills'}
                  htmlFor="agent-skills"
                  rules={[
                    {
                      required: true,
                      message: t('pages.agents.skills_required') || 'Please select at least one skill',
                    },
                    {
                      validator: (_, value) => {
                        if (!value || value.length === 0) {
                          return Promise.reject(new Error(t('pages.agents.skills_required') || 'Please select at least one skill'));
                        }
                        return Promise.resolve();
                      },
                    },
                  ]}
                >
                  <TagsEditor
                    id="agent-skills"
                    options={skillOptions}
                    disabled={!editMode}
                    placeholder={t('common.select_skill') || 'Select skills'}
                    aria-label={t('pages.agents.skills') || 'Skills'}
                    dataMap={skillMap}
                    dataType="skill"
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="tasks"
                  label={t('pages.agents.tasks') || 'Tasks'}
                  htmlFor="agent-tasks"
                >
                  <TagsEditor
                    id="agent-tasks"
                    options={taskOptions}
                    disabled={!editMode}
                    placeholder={t('common.select_task') || 'Select tasks'}
                    aria-label={t('pages.agents.tasks') || 'Tasks'}
                    dataMap={taskMap}
                    dataType="task"
                  />
                </StyledFormItem>
              </Col>

              {/* 第七行：Personality 和 Title */}
              <Col span={12}>
                <StyledFormItem
                  name="personalities"
                  label={t('pages.agents.personality') || 'Personality'}
                  htmlFor="agent-personality"
                >
                  <TagsEditor
                    id="agent-personality"
                    options={knownPersonalities}
                    disabled={!editMode}
                    placeholder={t('common.select_personality') || 'Select personality traits'}
                    aria-label={t('pages.agents.personality') || 'Personality'}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="title"
                  label={t('pages.agents.title') || 'Title'}
                  htmlFor="agent-title"
                >
                  <TagsEditor
                    id="agent-title"
                    options={knownTitles}
                    disabled={!editMode}
                    placeholder={t('common.select_title') || 'Select titles'}
                    aria-label={t('pages.agents.title') || 'Title'}
                  />
                </StyledFormItem>
              </Col>

              {/* 第八行：Extra Data */}
              <Col span={24}>
                <StyledFormItem 
                  name="extra_data" 
                  label={t('pages.agents.extra_data') || 'Extra Data / Notes'} 
                  htmlFor="agent-extra-data"
                  tooltip={t('pages.agents.extra_data_tooltip') || 'Must be valid JSON format (e.g., {"key": "value"}) or plain text'}
                  validateTrigger={['onChange', 'onBlur']}
                  rules={[
                    {
                      validator: (_, value) => {
                        // Allow空Value
                        if (!value || value.trim() === '') {
                          return Promise.resolve();
                        }
                        
                        // Must是有效的 JSON 格式
                        try {
                          JSON.parse(value);
                          return Promise.resolve();
                        } catch (e) {
                          return Promise.reject(
                            new Error(
                              t('pages.agents.extra_data_invalid_json') || 
                              'Invalid JSON format. Please enter valid JSON (e.g., {"key": "value"})'
                            )
                          );
                        }
                      },
                    },
                  ]}
                >
                  <Input.TextArea
                    id="agent-extra-data"
                    rows={4}
                    disabled={!editMode}
                    autoComplete="off"
                    placeholder={t('pages.agents.extra_data_placeholder') || 'Enter valid JSON (e.g., {"notes": "text"}) or plain text'}
                    aria-label={t('pages.agents.extra_data') || 'Extra Data'}
                    className="resizable-textarea"
                    style={{ minHeight: '100px', resize: 'vertical' }}
                  />
                </StyledFormItem>
              </Col>
            </Row>
          </Form>
          </div>
        </Card>

        {/* OperationButton区域 - 固定在Bottom，不随FormScroll */}
        <div 
          style={{ 
            marginTop: '16px',
            padding: '16px 0',
            position: 'sticky',
            bottom: 0,
            zIndex: 100,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 12
          }}
        >
          {/* 新增模式：DisplayClose和SaveButton */}
          {pageMode === 'create' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || 'Close'}
              </Button>
              <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave} size="large">
                {t('common.create') || 'Create'}
              </Button>
            </>
          )}
          
          {/* 查看模式：DisplayClose、Delete和EditButton */}
          {pageMode === 'view' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || 'Close'}
              </Button>
              <Button icon={<DeleteOutlined />} danger onClick={handleDelete} size="large">
                {t('common.delete') || 'Delete'}
              </Button>
              <Button icon={<EditOutlined />} type="default" onClick={() => setEditMode(true)} size="large">
                {t('common.edit') || 'Edit'}
              </Button>
            </>
          )}
          
          {/* Edit模式：DisplayClose、Cancel和SaveButton */}
          {pageMode === 'edit' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || 'Close'}
              </Button>
              <Button onClick={() => {
                setEditMode(false);
                // 重新LoadData
                if (!isNew && id && username) {
                  const api = get_ipc_api();
                  api.getAgents(username, [id]).then((response: any) => {
                    if (response?.success && response.data?.agents?.[0]) {
                      const agent = response.data.agents[0];
                      const orgId = agent.org_id || agent.organization || '';
                      form.setFieldsValue({
                        id: agent.card?.id || agent.id,
                        name: agent.card?.name || agent.name,
                        gender: agent.gender || 'gender_options.male',
                        birthday: agent.birthday ? dayjs(agent.birthday) : null,
                        owner: agent.owner || username,
                        personalities: agent.personalities || [],  // Use personalities (unified naming)
                        title: agent.title || [],
                        org_id: orgId,
                        supervisor_id: agent.supervisor_id || '',
                        tasks: agent.tasks || [],
                        skills: agent.skills || [],
                        vehicle_id: agent.vehicle_id || agent.vehicle || localVehicleId || '',
                        description: agent.description || '',
                        extra_data: agent.extra_data || agent.metadata || ''  // Compatible旧Field metadata
                      });
                      // Settings选中的组织ID
                      if (orgId) {
                        setSelectedOrgId(orgId);
                      }
                    }
                  });
                }
              }} size="large">
                {t('common.cancel') || 'Cancel'}
              </Button>
              <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave} size="large">
                {t('common.save') || 'Save'}
              </Button>
            </>
          )}
        </div>
      </div>
    </>
  );
};

export default AgentDetails;

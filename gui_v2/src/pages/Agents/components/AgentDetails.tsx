import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { App, Button, Card, Col, DatePicker, Form, Input, Modal, Radio, Row, Select, Tag, Tooltip, TreeSelect } from 'antd';
import { EditOutlined, SaveOutlined, InfoCircleOutlined, DeleteOutlined, CloseOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { useOrgStore } from '@/stores/orgStore';
import { useTaskStore, useSkillStore, useVehicleStore, useAgentStore } from '@/stores';
import { get_ipc_api } from '@/services/ipc_api';
import { StyledFormItem } from '@/components/Common/StyledForm';

type Gender = 'gender_options.male' | 'gender_options.female';

interface AgentDetailsForm {
  id?: string;
  name?: string;
  gender?: Gender;
  birthday?: Dayjs | null;
  owner?: string;
  personality_traits?: string[];
  title?: string[];
  org_id?: string; // 组织ID（单选）
  supervisor_id?: string; // 上级ID（单选）
  tasks?: string[];
  skills?: string[];
  vehicle_id?: string | null;
  description?: string; // Agent描述
  extra_data?: string; // 额外数据/备注
}

// 预定义的性格特征选项（使用国际化 key）
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

// 预定义的职称选项（使用国际化 key）
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
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const { id } = useParams();
  const location = useLocation();
  // 支持两种新建模式：/agents/add 和 /agents/details/new
  const isNew = id === 'new' || location.pathname === '/agents/add';
  const username = useUserStore((s: any) => s.username);

  // 从查询参数中获取 orgId
  const searchParams = new URLSearchParams(location.search);
  const defaultOrgId = searchParams.get('orgId');

  // 获取 vehicles 列表
  const { items: vehicles, fetchItems: fetchVehicles } = useVehicleStore();

  // 计算本机 vehicle ID（假设本机是 hostname 为 localhost 或 name 包含 "本机" 的）
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
  
  // 获取组织数据
  const { treeOrgs, setAllOrgAgents, shouldFetchData, setLoading: setOrgLoading, setError: setOrgError } = useOrgStore();

  // Build options for selects with full object data for tooltips
  // 保存完整的task和skill对象映射，用于显示详细信息
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
    // 使用 Set 去重，确保没有重复的名称
    const unique = Array.from(new Set(names));
    return unique.length > 0 ? unique : knownSkills;
  }, [storeSkills]);

  // 构建组织树形数据供TreeSelect使用（避免循环引用）
  const organizationTreeData = useMemo(() => {
    const buildTreeData = (node: any, parentPath: string = ''): any => {
      if (!node) return null;
      
      // 构建当前节点的完整路径
      const currentPath = parentPath ? `${parentPath} / ${node.name}` : node.name;
      
      // 只提取必要的字段，避免循环引用
      const treeNode: any = {
        title: node.name, // 树形结构只显示节点名
        value: node.id,
        key: node.id,
        fullPath: currentPath, // 存储完整路径，用于选中后显示
      };
      
      // 递归处理子节点，只传递必要的数据
      if (node.children && Array.isArray(node.children) && node.children.length > 0) {
        treeNode.children = node.children
          .map((child: any) => {
            // 为每个子节点创建简化的对象，只包含必要字段
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
      // 创建根节点的简化版本
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

  // 获取当前层级及以上的所有agents（用于上级选择）
  const [supervisorTreeData, setSupervisorTreeData] = useState<any[]>([]);

  // 获取 vehicles 列表
  useEffect(() => {
    if (username) {
      fetchVehicles(username).catch((error: any) => {
        console.error('[AgentDetails] Failed to fetch vehicles:', error);
      });
    }
  }, [username, fetchVehicles]);

  // 获取组织名称的辅助函数
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

  // 根据组织ID获取完整路径
  const getOrgFullPath = useCallback((orgId: string): string => {
    const findNodePath = (node: any, targetId: string, parentPath: string = ''): string | null => {
      const currentPath = parentPath ? `${parentPath} / ${node.name}` : node.name;
      
      if (node.id === targetId) {
        return currentPath;
      }
      
      if (node.children && Array.isArray(node.children)) {
        for (const child of node.children) {
          const found = findNodePath(child, targetId, currentPath);
          if (found) return found;
        }
      }
      return null;
    };

    if (treeOrgs && treeOrgs.length > 0) {
      const path = findNodePath(treeOrgs[0], orgId);
      if (path) return path;
    }
    
    return getOrgName(orgId);
  }, [treeOrgs, getOrgName]);

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
  // 初始化 selectedOrgId 为 defaultOrgId（如果存在）
  const [selectedOrgId, setSelectedOrgId] = useState<string | undefined>(defaultOrgId || undefined);
  
  // 确定页面模式：view（查看）、edit（编辑）、create（新增）
  const pageMode = useMemo(() => {
    if (isNew) return 'create';
    return editMode ? 'edit' : 'view';
  }, [isNew, editMode]);

  // 主动加载组织数据（如果未加载）
  useEffect(() => {
    const loadOrgData = async () => {
      if (!username) return;
      
      // 如果已有数据且不需要刷新，则跳过
      if (treeOrgs && treeOrgs.length > 0 && !shouldFetchData()) {
        // 即使使用缓存数据，也要确保新建模式下设置默认组织
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

          // 数据加载完成后，如果是新建模式且有默认组织，设置默认值
          if (isNew && defaultOrgId) {
            // 使用 setTimeout 确保在组织树数据更新后再设置表单值
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

  // 从IPC获取agent数据（编辑模式）
  useEffect(() => {
    const fetchAgentData = async () => {
      if (isNew || !id || !username) return;

      console.log('[AgentDetails] Fetching agent data for ID:', id);
      
      try {
        setLoading(true);
        const api = get_ipc_api();
        const response = await api.getAgents(username, [id]) as any;

        console.log('[AgentDetails] Received response:', response);
        
        if (response?.success && response.data?.agents && Array.isArray(response.data.agents) && response.data.agents.length > 0) {
          const agent = response.data.agents[0];
          console.log('[AgentDetails] Loading agent:', { 
            id: agent.id || agent.card?.id, 
            name: agent.name || agent.card?.name,
            fullAgent: agent 
          });

          // 更新表单数据
          // 优先使用 agent 自身的 org_id，如果没有则使用 URL 参数中的 defaultOrgId
          const orgId = agent.org_id || agent.organization || defaultOrgId || '';
          
          // Convert skills and tasks from objects to names (for Select component)
          const skillNames = (agent.skills || []).map((s: any) => 
            typeof s === 'string' ? s : s.name || s
          );
          const taskNames = (agent.tasks || []).map((t: any) => 
            typeof t === 'string' ? t : t.name || t
          );
          
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
          
          form.setFieldsValue({
            id: agent.card?.id || agent.id,
            name: agent.card?.name || agent.name,
            gender: agent.gender || 'gender_options.male',
            birthday: agent.birthday ? dayjs(agent.birthday) : null,
            owner: agent.owner || username,
            personality_traits: agent.personality_traits || agent.personalities || [],
            title: agent.title || [],
            org_id: orgId,
            supervisor_id: agent.supervisor_id || (Array.isArray(agent.supervisors) && agent.supervisors.length > 0 ? agent.supervisors[0] : ''),
            tasks: taskNames,
            skills: skillNames,
            vehicle_id: agent.vehicle_id || agent.vehicle || localVehicleId || '',
            description: agent.description || '',
            extra_data: extraDataText
          });
          // 设置选中的组织ID以显示完整路径
          if (orgId) {
            setSelectedOrgId(orgId);
          }
          
          // 从 AgentCard 编辑进入时，自动进入编辑模式
          setEditMode(true);
        } else {
          // 如果没有找到 agent 数据，显示错误
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

  // 不再使用 initialValues，改为在 useEffect 中逐个设置字段，避免循环引用警告

  // 使用 useEffect 来设置初始表单值（仅新建模式）
  useEffect(() => {
    if (isNew) {
      // 只有在组织树数据加载完成后才设置表单值
      if (organizationTreeData.length > 0) {
        // 使用 setTimeout 延迟设置，确保在下一个事件循环中执行
        const timeoutId = setTimeout(() => {
          try {
            // 创建完全独立的初始值对象，避免任何可能的引用
            const initialValues: Partial<AgentDetailsForm> = {
              id: '',
              name: '',
              gender: 'gender_options.male' as Gender,
              birthday: dayjs(),
              owner: username || t('common.owner') || 'owner',
              personality_traits: [], // 新数组
              title: [], // 新数组
              org_id: defaultOrgId || '',
              supervisor_id: '',
              tasks: [], // 新数组
              skills: [], // 新数组
              vehicle_id: localVehicleId || '',
              description: '',
              extra_data: ''
            };

            // 使用 setFieldsValue 一次性设置所有值
            form.setFieldsValue(initialValues);
            setEditMode(true);

            // 设置选中的组织
            if (defaultOrgId) {
              setSelectedOrgId(defaultOrgId);
            }
          } catch (error) {
            console.error('[AgentDetails] Error setting initial values:', error);
          }
        }, 0);

        // 清理函数
        return () => clearTimeout(timeoutId);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNew, defaultOrgId, organizationTreeData.length, username, localVehicleId]);

  // 监听 defaultOrgId 变化，确保 selectedOrgId 同步更新
  useEffect(() => {
    if (isNew && defaultOrgId && selectedOrgId !== defaultOrgId && organizationTreeData.length > 0) {
      setSelectedOrgId(defaultOrgId);
      // 同时更新表单字段
      form.setFieldValue('org_id', defaultOrgId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultOrgId, isNew, selectedOrgId, organizationTreeData.length]);

  // 获取上级候选数据（当前组织及父级组织的agents）
  useEffect(() => {
    const fetchAgentsForSupervisor = async () => {
      if (!treeOrgs || treeOrgs.length === 0) return;
      
      try {
        // 获取当前选中组织的agents
        const currentOrgId = form.getFieldValue('org_id') || defaultOrgId;
        
        if (!currentOrgId) {
          setSupervisorTreeData([]);
          return;
        }
        
        const currentOrgIds = [currentOrgId]; // 转为数组以兼容后续逻辑
        
        // 查找组织节点并返回从根到目标节点的路径（只返回 id 和 name，避免循环引用）
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
        
        // 根据组织 ID 获取完整的组织节点（从原始 treeOrgs 中查找）
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
        
        // 构建上级选择的树形数据（按组织分组）
        const buildAgentTree = (orgId: string, orgName: string): any => {
          // 从原始树中获取组织节点
          const orgNode = getOrgNodeById(treeOrgs[0], orgId);
          const agents = orgNode?.agents || [];

          if (agents.length === 0) return null;

          // 只提取必要的字段，避免循环引用
          const agentNodes = agents.map((agent: any) => ({
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
        
        // 对每个选中的组织，获取其到根节点的路径（包含所有父级组织）
        for (const orgId of currentOrgIds) {
          const orgPath = findOrgPath(treeOrgs[0], orgId);

          if (orgPath) {
            // 为路径上的每个组织构建agent树（从根到当前节点）
            for (const simplifiedOrg of orgPath) {
              // 避免重复添加
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

  // 多选标签编辑器 - 使用 Select mode="tags" 实现友好交互
  // 支持预定义选项（国际化）和用户自定义输入
  const TagsEditor: React.FC<{
    value?: string[];
    onChange?: (value: string[]) => void;
    options: string[];
    disabled?: boolean;
    placeholder?: string;
    isOrgField?: boolean;
    'aria-label'?: string;
    id?: string;
    dataMap?: Map<string, any>;  // 用于显示详细信息的数据映射
    dataType?: 'task' | 'skill';  // 数据类型，用于显示不同的详细信息
  }> = ({ value, onChange, options, disabled, placeholder, isOrgField, 'aria-label': ariaLabel, id, dataMap, dataType }) => {
    // 详细信息Modal状态
    const [detailModalVisible, setDetailModalVisible] = React.useState(false);
    const [selectedDetailItem, setSelectedDetailItem] = React.useState<any>(null);
    // 获取显示文本
    // 如果是预定义选项（如 personality.friendly），显示国际化翻译
    // 如果是用户自定义输入，直接显示原文
    const getDisplayText = useCallback((val: string) => {
      if (!val) return '';

      if (isOrgField) {
        return getOrgName(val);
      }

      // 检查是否是预定义的国际化 key（包含 . 的格式）
      if (val.includes('.')) {
        const translated = t(val);

        // 如果翻译成功（翻译结果不等于原 key），返回翻译
        if (translated && translated !== val) {
          return translated;
        }
        // 如果翻译失败，返回 key 的最后一部分作为后备（如 friendly）
        const parts = val.split('.');
        return parts[parts.length - 1];
      }

      // 否则直接返回原值（用户自定义输入）
      return val;
    }, [isOrgField, getOrgName, t]);

    // 使用 useMemo 缓存选项，避免重复计算
    const selectOptions = useMemo(() => {
      return options.map((opt, index) => {
        const displayText = getDisplayText(opt);
        return {
          label: displayText,  // 下拉列表中显示的文本（翻译后）
          value: opt,          // 实际存储的值（国际化 key）
          key: `option-${index}-${opt}`,  // 使用索引+值确保唯一性（索引在前更可靠）
          title: ''            // 清空title，避免原生tooltip
        };
      });
    }, [options, getDisplayText]);

    // 处理选择变化 - 当用户选择预定义选项时，存储国际化 key；自定义输入时，存储原文
    const handleChange = useCallback((newValue: string[]) => {
      if (!onChange) return;

      // 处理每个值：检查是否是翻译文本，如果是则转换回国际化 key
      const processedValues = newValue.map(val => {
        // 检查是否已经是国际化 key
        if (val.includes('.')) {
          return val;
        }

        // 检查是否是翻译文本，需要转换回国际化 key
        const matchedOption = selectOptions.find(opt => opt.label === val);
        if (matchedOption) {
          return matchedOption.value;
        }

        // 否则是用户自定义输入，直接返回
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
        value={value}
        onChange={handleChange}
        disabled={disabled}
        maxTagCount="responsive"
        showSearch
        allowClear
        tokenSeparators={[',']}
        aria-label={ariaLabel}
        // 搜索过滤 - 支持模糊搜索label和value
        filterOption={(input, option) => {
          if (!input) return true;
          const searchText = input.toLowerCase();
          const label = (option?.label || '').toString().toLowerCase();
          const value = (option?.value || '').toString().toLowerCase();
          return label.includes(searchText) || value.includes(searchText);
        }}
        // 下拉框定位 - 避免遮挡输入框
        popupMatchSelectWidth={false}
        listHeight={400}
        placement="bottomLeft"
        // 标签渲染 - 添加tooltip显示描述
        tagRender={(props) => {
          const { value: tagValue, closable, onClose } = props;
          const displayText = getDisplayText(tagValue as string);
          const isCustom = tagValue && typeof tagValue === 'string' && !tagValue.includes('.');
          const itemData = dataMap?.get(tagValue as string);
          const description = itemData?.description || '';

          const tagContent = (
            <Tag
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

          // 如果有描述信息，添加tooltip
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
        // 下拉选项配置 - 使用缓存的选项
        options={selectOptions}
        // 自定义下拉选项渲染 - 添加tooltip显示描述
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
        // 禁用Select自带的title属性，避免tooltip冲突
        optionFilterProp="label"
        // 不使用 getPopupContainer，让下拉框自然定位，避免遮挡
        // 不显示下拉箭头，更像输入框
        suffixIcon={null}
        // 自动获取焦点时不自动打开下拉框
        open={undefined}
      />
      
      {/* 详细信息Modal */}
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
            {/* 名称 */}
            <div style={{ marginBottom: 16 }}>
              <strong>{t('common.name', 'Name')}:</strong>{' '}
              <span style={{ color: selectedDetailItem.name || selectedDetailItem.skill ? 'inherit' : '#999' }}>
                {selectedDetailItem.name || selectedDetailItem.skill || '-'}
              </span>
            </div>
            
            {/* 描述 */}
            <div style={{ marginBottom: 16 }}>
              <strong>{t('common.description', 'Description')}:</strong>
              <div style={{ marginTop: 8, padding: 12, background: 'rgba(0,0,0,0.02)', borderRadius: 4, color: selectedDetailItem.description ? 'inherit' : '#999' }}>
                {selectedDetailItem.description || '-'}
              </div>
            </div>
            
            {/* Task特有字段 */}
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
            
            {/* Skill特有字段 */}
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
    
    modal.confirm({
      title: t('pages.agents.deleteConfirmTitle', 'Delete Agent'),
      content: t('pages.agents.deleteConfirmMessage', 'Are you sure you want to delete this agent? This action cannot be undone.'),
      okText: t('common.delete', 'Delete'),
      okType: 'danger',
      cancelText: t('common.cancel', 'Cancel'),
      centered: true,
      onOk: async () => {
        try {
          setLoading(true);
          const api = get_ipc_api();
          const response = await api.deleteAgent(username, [id]);
          
          if (response.success) {
            message.success(t('pages.agents.deleteSuccess', 'Agent deleted successfully'));
            // 从 agentStore 中移除已删除的 agent
            const { removeAgent } = useAgentStore.getState();
            removeAgent(id);
            // 同时从 orgStore 中移除
            const { removeAgentFromOrg } = useOrgStore.getState();
            removeAgentFromOrg(id);
            // 跳转回agents列表页
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
        birthday: values.birthday ? (values.birthday as Dayjs).toISOString() : null,
        skills: skillIds,  // 只发送 ID 数组
        tasks: taskIds,    // 只发送 ID 数组
      };
      setLoading(true);
      const api = get_ipc_api();
      const res = isNew
        ? await api.newAgent(username, [payload])
        : await api.saveAgent(username, [payload]);
      setLoading(false);
      if (res.success) {
        message.success(t('common.saved_successfully') || 'Saved');
        
        // 保存成功后，立即刷新组织和代理数据
        try {
          const api = get_ipc_api();
          const refreshResponse = await api.getAllOrgAgents(username);
          
          if (refreshResponse?.success && refreshResponse.data) {
            // 手动更新 OrgStore 中的数据
            useOrgStore.getState().setAllOrgAgents(refreshResponse.data as any);
          }
        } catch (error) {
          console.error('[AgentDetails] Error refreshing org data:', error);
        }
        
        // 如果是编辑模式，重新获取 agent 数据更新表单
        if (!isNew && id) {
          try {
            const api = get_ipc_api();
            const refreshResponse = await api.getAgents(username, [id]) as any;
            
            if (refreshResponse?.success && refreshResponse.data?.agents && refreshResponse.data.agents.length > 0) {
              const updatedAgent = refreshResponse.data.agents[0];
              
              // Convert skills and tasks from objects to names (for Select component)
              const skillNames = (updatedAgent.skills || []).map((s: any) => 
                typeof s === 'string' ? s : s.name || s
              );
              const taskNames = (updatedAgent.tasks || []).map((t: any) => 
                typeof t === 'string' ? t : t.name || t
              );
              
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
                description: updatedAgent.description || '',
                gender: updatedAgent.gender || 'gender_options.male',
                birthday: updatedAgent.birthday ? dayjs(updatedAgent.birthday) : null,
                owner: updatedAgent.owner || username,
                personality_traits: updatedAgent.personality_traits || updatedAgent.personalities || [],
                title: updatedAgent.title || [],
                org_id: updatedAgent.org_id || '',
                supervisor_id: updatedAgent.supervisor_id || '',
                tasks: taskNames,
                skills: skillNames,
                vehicle_id: updatedAgent.vehicle_id || '',
                extra_data: extraDataText
              };
              
              form.setFieldsValue(formData);
            }
          } catch (error) {
            console.error('[AgentDetails] Error refreshing agent data:', error);
          }
        }
        
        // 更新完表单后再切换到查看模式
        setEditMode(false);
        
        if (isNew) {
          // After creation, navigate back to the OrgNavigator page with refresh flag
          const orgId = values.org_id;
          if (orgId && orgId !== 'root') {
            // 跳转到对应组织的navigator页面，添加时间戳强制刷新
            navigate(`/agents/organization/${orgId}?refresh=${Date.now()}`);
          } else {
            // 跳转到根navigator页面，添加时间戳强制刷新
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
      `}</style>
      <div style={{ padding: 12, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Card style={{ flex: 1, minHeight: 0, overflow: 'hidden', marginTop: '16px' }} styles={{ body: { padding: 12, height: '100%', overflow: 'hidden' } }}>
          <div style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden', paddingRight: 8 }}>
          <Form
            form={form}
            layout="vertical"
            style={{ maxWidth: '100%' }}
            autoComplete="off"
            role="form"
            aria-label={t('pages.agents.form_label') || 'Agent Details Form'}
          >
            <Row gutter={[12, 0]} style={{ margin: 0 }}>
              {/* 第一行：ID（只在编辑时显示）和 Name */}
              {!isNew && (
                <Col span={12}>
                  <StyledFormItem name="id" label="ID" htmlFor="agent-id">
                    <Input
                      id="agent-id"
                      readOnly
                      autoComplete="off"
                      aria-label="Agent ID"
                    />
                  </StyledFormItem>
                </Col>
              )}
              <Col span={isNew ? 24 : 12}>
                <StyledFormItem name="name" label={t('common.name') || 'Name'} rules={[{ required: true, message: t('common.please_input_name') || 'Please input name' }]} htmlFor="agent-name">
                  <Input
                    id="agent-name"
                    placeholder={t('common.name') || 'Name'}
                    disabled={!editMode}
                    autoComplete="name"
                    aria-label={t('common.name') || 'Name'}
                    aria-required="true"
                  />
                </StyledFormItem>
              </Col>

              {/* 第二行：描述（提前到前面） */}
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

              {/* 第三行：Owner 和 Gender */}
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

              {/* 第四行：Birthday 和 Vehicle */}
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
                    options={vehicles.map((v: any) => ({
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

              {/* 第六行：Personality 和 Title */}
              <Col span={12}>
                <StyledFormItem
                  name="personality_traits"
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

              {/* 第七行：Tasks 和 Skills */}
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

              {/* 第八行：Extra Data */}
              <Col span={24}>
                <StyledFormItem name="extra_data" label={t('pages.agents.extra_data') || 'Extra Data / Notes'} htmlFor="agent-extra-data">
                  <Input.TextArea
                    id="agent-extra-data"
                    rows={4}
                    disabled={!editMode}
                    autoComplete="off"
                    placeholder={t('pages.agents.extra_data_placeholder') || 'Enter additional notes or extra data'}
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

        {/* 操作按钮区域 - 固定在底部，不随表单滚动 */}
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
          {/* 新增模式：显示关闭和保存按钮 */}
          {pageMode === 'create' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || '关闭'}
              </Button>
              <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave} size="large">
                {t('common.create') || '创建'}
              </Button>
            </>
          )}
          
          {/* 查看模式：显示关闭、删除和编辑按钮 */}
          {pageMode === 'view' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || '关闭'}
              </Button>
              <Button icon={<DeleteOutlined />} danger onClick={handleDelete} size="large">
                {t('common.delete') || '删除'}
              </Button>
              <Button icon={<EditOutlined />} type="default" onClick={() => setEditMode(true)} size="large">
                {t('common.edit') || '编辑'}
              </Button>
            </>
          )}
          
          {/* 编辑模式：显示关闭、取消和保存按钮 */}
          {pageMode === 'edit' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || '关闭'}
              </Button>
              <Button onClick={() => {
                setEditMode(false);
                // 重新加载数据
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
                        personality_traits: agent.personality_traits || agent.personalities || [],
                        title: agent.title || [],
                        org_id: orgId,
                        supervisor_id: agent.supervisor_id || (Array.isArray(agent.supervisors) && agent.supervisors.length > 0 ? agent.supervisors[0] : ''),
                        tasks: agent.tasks || [],
                        skills: agent.skills || [],
                        vehicle_id: agent.vehicle_id || agent.vehicle || localVehicleId || '',
                        description: agent.description || '',
                        extra_data: agent.extra_data || agent.metadata || ''  // 兼容旧字段 metadata
                      });
                      // 设置选中的组织ID
                      if (orgId) {
                        setSelectedOrgId(orgId);
                      }
                    }
                  });
                }
              }} size="large">
                {t('common.cancel') || '取消'}
              </Button>
              <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave} size="large">
                {t('common.save') || '保存'}
              </Button>
            </>
          )}
        </div>
      </div>
    </>
  );
};

export default AgentDetails;

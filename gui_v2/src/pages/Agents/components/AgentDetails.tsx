import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { App, Button, Card, Col, DatePicker, Divider, Form, Input, Radio, Row, Select, Tag, TreeSelect } from 'antd';
import { EditOutlined, SaveOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { useOrgStore } from '@/stores/orgStore';
import { useTaskStore, useSkillStore } from '@/stores';
import { get_ipc_api } from '@/services/ipc_api';

type Gender = 'gender_options.male' | 'gender_options.female';

interface AgentDetailsForm {
  id?: string;
  agent_id?: string;
  name?: string;
  gender?: Gender;
  birthday?: Dayjs | null;
  owner?: string;
  personality?: string[];
  title?: string[];
  organization?: string; // 改为单选
  supervisors?: string[];
  tasks?: string[];
  skills?: string[];
  vehicle?: string | null;
  metadata?: string;
}

const knownPersonalities = ['personality.friendly', 'personality.analytical', 'personality.creative', 'personality.efficient', 'personality.empathetic'];
const knownTitles = ['title.engineer', 'title.manager', 'title.analyst', 'title.designer', 'title.operator'];
// Tasks and skills will be sourced from global store to link with Tasks/Skills pages
// We keep fallback arrays in case store is empty to avoid empty UI when no data loaded yet
const knownTasks = ['task_001', 'task_002', 'task_003'];
const knownSkills = ['skill_001', 'skill_002', 'skill_003'];
const knownVehicles = ['本机', 'HostA (10.0.0.1)', 'HostB (10.0.0.2)', 'HostC (10.0.0.3)'];

const AgentDetails: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams();
  const location = useLocation();
  // 支持两种新建模式：/agents/add 和 /agents/details/new
  const isNew = id === 'new' || location.pathname === '/agents/add';
  const username = useUserStore((s: any) => s.username);
  
  // 从查询参数中获取 orgId
  const searchParams = new URLSearchParams(location.search);
  const defaultOrgId = searchParams.get('orgId');
  console.log('[AgentDetails] URL search params:', location.search);
  console.log('[AgentDetails] defaultOrgId from URL:', defaultOrgId);
  const { message } = App.useApp();

  // 使用专用的 taskStore 和 skillStore
  const storeTasks = useTaskStore((state) => state.items);
  const storeSkills = useSkillStore((state) => state.items);
  const setTasks = useTaskStore((state) => state.setItems);
  const setSkills = useSkillStore((state) => state.setItems);
  
  // 获取组织数据
  const { treeOrgs, setAllOrgAgents, shouldFetchData, loading: orgLoading, setLoading: setOrgLoading, setError: setOrgError } = useOrgStore();

  // Build options for selects. ListEditor expects string[] options.
  // For tasks, use task.skill; for skills, use skill.name.
  const taskOptions = useMemo(() => {
    const skills = (storeTasks || [])
      .map((t: any) => t.skill)
      .filter(Boolean);
    const unique = Array.from(new Set(skills));
    return unique.length > 0 ? unique : knownTasks;
  }, [storeTasks]);

  const skillOptions = useMemo(() => {
    const names = (storeSkills || [])
      .map((s: any) => s.name)
      .filter(Boolean);
    const unique = Array.from(new Set(names));
    return unique.length > 0 ? unique : knownSkills;
  }, [storeSkills]);

  // 构建组织树形数据供TreeSelect使用
  const organizationTreeData = useMemo(() => {
    const buildTreeData = (node: any, parentPath: string = ''): any => {
      if (!node) return null;
      
      // 构建当前节点的完整路径
      const currentPath = parentPath ? `${parentPath} / ${node.name}` : node.name;
      
      const treeNode: any = {
        title: node.name, // 树形结构只显示节点名
        value: node.id,
        key: node.id,
        fullPath: currentPath, // 存储完整路径，用于选中后显示
      };
      
      if (node.children && Array.isArray(node.children) && node.children.length > 0) {
        treeNode.children = node.children.map((child: any) => buildTreeData(child, currentPath)).filter(Boolean);
      }
      
      return treeNode;
    };

    if (treeOrgs && treeOrgs.length > 0) {
      const data = [buildTreeData(treeOrgs[0])].filter(Boolean);
      console.log('[AgentDetails] Organization tree data:', data);
      return data;
    }
    console.log('[AgentDetails] No organization tree data available');
    return [];
  }, [treeOrgs]);

  // 获取当前层级及以上的所有agents（用于上级选择）
  const [supervisorTreeData, setSupervisorTreeData] = useState<any[]>([]);

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
            const res = await api.getTasks<{ tasks: any[] }>(uname, []);
            if (res?.success && res.data?.tasks) setTasks(res.data.tasks as any);
          }
          if (!storeSkills || storeSkills.length === 0) {
            const res2 = await api.getSkills<{ skills: any[] }>(uname, []);
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
  const [agentData, setAgentData] = useState<any>(null);
  const [selectedOrgId, setSelectedOrgId] = useState<string | undefined>(undefined);
  
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
        console.log('[AgentDetails] Using cached org data');
        // 即使使用缓存数据，也要确保新建模式下设置默认组织
        if (isNew && defaultOrgId) {
          const currentOrg = form.getFieldValue('organization');
          if (!currentOrg) {
            console.log('[AgentDetails] Setting default org from cache:', defaultOrgId);
            form.setFieldsValue({ organization: defaultOrgId });
          }
        }
        return;
      }
      
      try {
        setOrgLoading(true);
        console.log('[AgentDetails] Loading org data...');
        const api = get_ipc_api();
        const response = await api.getAllOrgAgents(username) as any;
        
        if (response?.success && response.data?.orgs) {
          console.log('[AgentDetails] Org data loaded successfully:', response.data);
          setAllOrgAgents(response.data);
          
          // 数据加载完成后，如果是新建模式且有默认组织，设置默认值
          if (isNew && defaultOrgId) {
            console.log('[AgentDetails] Setting default org after load:', defaultOrgId);
            form.setFieldsValue({ organization: defaultOrgId });
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
  
  // 动态标题
  const pageTitle = useMemo(() => {
    if (pageMode === 'create') {
      return t('pages.agents.create_agent') || '新增 Agent';
    }
    return t('pages.agents.agent_details') || '代理详情';
  }, [pageMode, t]);

  // 从IPC获取agent数据（编辑模式）
  useEffect(() => {
    const fetchAgentData = async () => {
      if (isNew || !id || !username) return;
      
      try {
        setLoading(true);
        const api = get_ipc_api();
        const response = await api.getAgents(username, [id]) as any;
        
        if (response?.success && response.data?.agents && Array.isArray(response.data.agents) && response.data.agents.length > 0) {
          const agent = response.data.agents[0];
          setAgentData(agent);
          
          // 更新表单数据
          const orgId = agent.organization || '';
          form.setFieldsValue({
            id: agent.card?.id || agent.id,
            agent_id: agent.card?.id || agent.id,
            name: agent.card?.name || agent.name,
            gender: agent.gender || 'gender_options.male',
            birthday: agent.birthday ? dayjs(agent.birthday) : null,
            owner: agent.owner || username,
            personality: agent.personalities || [],
            title: agent.title || [],
            organization: orgId,
            supervisors: agent.supervisors || [],
            tasks: agent.tasks || [],
            skills: agent.skills || [],
            vehicle: agent.vehicle || '本机',
            metadata: agent.metadata ? JSON.stringify(agent.metadata, null, 2) : ''
          });
          // 设置选中的组织ID以显示完整路径
          if (orgId) {
            setSelectedOrgId(orgId);
          }
        }
      } catch (e) {
        console.error('Failed to fetch agent data:', e);
        message.error(t('pages.agents.fetch_failed') || 'Failed to fetch agent data');
      } finally {
        setLoading(false);
      }
    };
    
    fetchAgentData();
  }, [id, isNew, username, form, message, t]);

  // 使用 useMemo 来初始化表单值（仅用于新建模式）
  const initialValues: AgentDetailsForm = useMemo(() => {
    if (isNew) {
      return {
        id: '',
        agent_id: '',
        name: '',
        gender: 'gender_options.male' as Gender,
        birthday: dayjs(), // 默认当前日期
        owner: username || t('common.owner') || 'owner',
        personality: [],
        title: [],
        organization: defaultOrgId || '', // 设置默认组织（单选）
        supervisors: [],
        tasks: [],
        skills: [],
        vehicle: '本机',
        metadata: ''
      };
    }
    return {};
  }, [isNew, username, t, defaultOrgId]);

  // 使用 useEffect 来设置初始表单值（仅新建模式）
  useEffect(() => {
    if (isNew) {
      console.log('[AgentDetails] Setting initial values for new agent:', initialValues);
      console.log('[AgentDetails] defaultOrgId:', defaultOrgId);
      form.setFieldsValue(initialValues);
      setEditMode(true);
      // 设置选中的组织
      if (defaultOrgId) {
        setSelectedOrgId(defaultOrgId);
      }
    }
  }, [form, initialValues, isNew, defaultOrgId]);

  // 获取上级候选数据（当前组织及父级组织的agents）
  useEffect(() => {
    const fetchAgentsForSupervisor = async () => {
      if (!treeOrgs || treeOrgs.length === 0) return;
      
      try {
        // 获取当前选中组织的agents
        const currentOrgId = form.getFieldValue('organization') || defaultOrgId;
        
        if (!currentOrgId) {
          setSupervisorTreeData([]);
          return;
        }
        
        const currentOrgIds = [currentOrgId]; // 转为数组以兼容后续逻辑
        
        // 查找组织节点并返回从根到目标节点的路径
        const findOrgPath = (node: any, targetId: string, path: any[] = []): any[] | null => {
          const currentPath = [...path, node];
          if (node.id === targetId) return currentPath;
          
          if (node.children && Array.isArray(node.children)) {
            for (const child of node.children) {
              const found = findOrgPath(child, targetId, currentPath);
              if (found) return found;
            }
          }
          return null;
        };
        
        // 构建上级选择的树形数据（按组织分组）
        const buildAgentTree = (orgNode: any): any => {
          const agents = orgNode?.agents || [];
          
          if (agents.length === 0) return null;
          
          const agentNodes = agents.map((agent: any) => ({
            title: agent.name || agent.id,
            value: agent.id,
            key: `agent-${agent.id}`,
            isLeaf: true,
          }));
          
          return {
            title: orgNode?.name || orgNode.id,
            value: `org-${orgNode.id}`,
            key: `org-${orgNode.id}`,
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
            console.log(`[AgentDetails] Org path for ${orgId}:`, orgPath.map(n => n.name));
            
            // 为路径上的每个组织构建agent树（从根到当前节点）
            for (const orgNode of orgPath) {
              // 避免重复添加
              if (!processedOrgIds.has(orgNode.id)) {
                processedOrgIds.add(orgNode.id);
                const tree = buildAgentTree(orgNode);
                if (tree) {
                  treeData.push(tree);
                }
              }
            }
          }
        }
        
        console.log('[AgentDetails] Supervisor tree data:', treeData);
        setSupervisorTreeData(treeData);
      } catch (e) {
        console.error('Failed to fetch agents for supervisor selection:', e);
      }
    };
    
    fetchAgentsForSupervisor();
  }, [form, defaultOrgId, treeOrgs]);

  // 多选标签编辑器 - 使用 Select mode="tags" 实现友好交互
  const TagsEditor: React.FC<{
    value?: string[];
    onChange?: (value: string[]) => void;
    options: string[];
    disabled?: boolean;
    placeholder?: string;
    isOrgField?: boolean;
  }> = ({ value, onChange, options, disabled, placeholder, isOrgField }) => {
    // 获取显示文本
    const getDisplayText = useCallback((val: string) => {
      return isOrgField ? getOrgName(val) : (t(val) || val);
    }, [isOrgField, getOrgName, t]);

    return (
      <Select
        mode="tags"
        style={{ width: '100%' }}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        maxTagCount="responsive"
        showSearch
        allowClear
        tokenSeparators={[',']}
        tagRender={(props) => {
          const { value: tagValue, closable, onClose } = props;
          return (
            <Tag
              color="blue"
              closable={closable && !disabled}
              onClose={onClose}
              style={{ marginRight: 3 }}
            >
              {getDisplayText(tagValue as string)}
            </Tag>
          );
        }}
        options={options.map(opt => ({
          label: getDisplayText(opt),
          value: opt
        }))}
        getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
        filterOption={(input, option) => {
          const displayText = getDisplayText(option?.value as string);
          return displayText.toLowerCase().includes(input.toLowerCase());
        }}
      />
    );
  };


  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      // Serialize dayjs and metadata
      const payload = {
        ...values,
        birthday: values.birthday ? (values.birthday as Dayjs).toISOString() : null,
        metadata: values.metadata,
      };
      setLoading(true);
      const api = get_ipc_api();
      const res = isNew
        ? await api.newAgents(username, [payload])
        : await api.saveAgents(username, [payload]);
      setLoading(false);
      if (res.success) {
        message.success(t('common.saved_successfully') || 'Saved');
        setEditMode(false);
        if (isNew) {
          // After creation, navigate back to agents list or to the new detail page
          navigate('/agents');
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
    <div style={{ padding: 16, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ marginBottom: 16 }}>
          <span style={{ fontSize: 18, fontWeight: 600 }}>
            {pageTitle}
            {isNew && defaultOrgId && (
              <span style={{ fontSize: 14, fontWeight: 400, color: 'rgba(255, 255, 255, 0.65)', marginLeft: 8 }}>
                - {getOrgName(defaultOrgId)}
              </span>
            )}
          </span>
        </div>

      <Card style={{ flex: 1, minHeight: 0, overflow: 'hidden' }} styles={{ body: { padding: 16, height: '100%', overflow: 'hidden' } }}>
        <div style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden' }}>
          <Form form={form} layout="vertical" style={{ maxWidth: '100%' }}>
            <Row gutter={[16, 16]} style={{ margin: 0 }}>
              {/* ID 和 Agent ID：新增时不显示，查看/编辑时只读 */}
              {!isNew && (
                <>
                  <Col span={12}>
                    <Form.Item name="id" label={t('common.id') || 'ID'}>
                      <Input readOnly />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="agent_id" label={t('pages.agents.agent_id') || 'Agent ID'}>
                      <Input readOnly />
                    </Form.Item>
                  </Col>
                </>
              )}

              <Col span={12}>
                <Form.Item name="name" label={t('common.name') || 'Name'} rules={[{ required: true, message: t('common.please_input_name') || 'Please input name' }]}>
                  <Input placeholder={t('common.name') || 'Name'} disabled={!editMode} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="owner" label={t('common.owner') || 'Owner'}>
                  {/* Owner: 新增时可以修改，编辑时只读 */}
                  <Input placeholder={t('common.owner') || 'Owner'} disabled={pageMode !== 'create'} />
                </Form.Item>
              </Col>

              <Col span={12}>
                <Form.Item name="gender" label={t('common.gender') || 'Gender'}>
                  <Radio.Group disabled={!editMode}>
                    <Radio value="gender_options.male">{t('common.gender_options.male') || 'Male'}</Radio>
                    <Radio value="gender_options.female">{t('common.gender_options.female') || 'Female'}</Radio>
                  </Radio.Group>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="birthday" label={t('common.birthday') || 'Birthday'}>
                  <DatePicker
                    style={{ width: '100%' }}
                    disabled={!editMode}
                    getPopupContainer={() => document.body}
                    placement="bottomLeft"
                  />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item 
                  name="personality" 
                  label={t('pages.agents.personality') || 'Personality'}
                >
                  <TagsEditor
                    options={knownPersonalities}
                    disabled={!editMode}
                    placeholder={t('common.select_personality') || 'Select personality traits'}
                  />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item 
                  name="title" 
                  label={t('pages.agents.title') || 'Title'}
                >
                  <TagsEditor
                    options={knownTitles}
                    disabled={!editMode}
                    placeholder={t('common.select_title') || 'Select titles'}
                  />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item 
                  name="organization" 
                  label={t('pages.agents.organization') || 'Organization'}
                  rules={[{ required: true, message: t('common.please_select_organization') || 'Please select organization' }]}
                >
                  <TreeSelect
                    treeData={organizationTreeData}
                    disabled={!editMode}
                    placeholder={t('common.select_organization') || 'Select organization'}
                    style={{ width: '100%' }}
                    treeDefaultExpandAll
                    allowClear
                    showSearch
                    treeNodeFilterProp="title"
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                    onChange={(value) => {
                      setSelectedOrgId(value as string);
                    }}
                  />
                </Form.Item>
                {/* 显示选中组织的完整路径 */}
                {selectedOrgId && (
                  <div style={{ marginTop: -16, marginBottom: 16, fontSize: 12, color: '#666' }}>
                    完整路径：{getOrgFullPath(selectedOrgId)}
                  </div>
                )}
              </Col>

              <Col span={24}>
                <Form.Item 
                  name="supervisors" 
                  label={t('pages.agents.supervisors') || 'Supervisors'}
                >
                  <TreeSelect
                    treeData={supervisorTreeData}
                    disabled={!editMode}
                    placeholder={t('common.select_supervisor') || 'Select supervisors'}
                    treeCheckable
                    showCheckedStrategy={TreeSelect.SHOW_CHILD}
                    style={{ width: '100%' }}
                    maxTagCount="responsive"
                    treeDefaultExpandAll
                    allowClear
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                  />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item 
                  name="tasks" 
                  label={t('pages.agents.tasks') || 'Tasks'}
                >
                  <TagsEditor
                    options={taskOptions}
                    disabled={!editMode}
                    placeholder={t('common.select_task') || 'Select tasks'}
                  />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item 
                  name="skills" 
                  label={t('pages.agents.skills') || 'Skills'}
                >
                  <TagsEditor
                    options={skillOptions}
                    disabled={!editMode}
                    placeholder={t('common.select_skill') || 'Select skills'}
                  />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item name="vehicle" label={t('pages.agents.vehicle') || 'Vehicle'}>
                  <Select
                    disabled={!editMode}
                    allowClear
                    placeholder={t('common.select_vehicle') || 'Select vehicle'}
                    options={knownVehicles.map(v => ({ value: v, label: v }))}
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}

                  />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item name="metadata" label={t('pages.agents.metadata') || 'Metadata'}>
                  <Input.TextArea rows={6} style={{ resize: 'both' }} disabled={!editMode} />
                </Form.Item>
              </Col>

              {/* 按钮区域 - 放在表单内部 */}
              <Col span={24}>
                <Divider style={{ margin: '16px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
                  {/* 新增模式：只显示保存按钮 */}
                  {pageMode === 'create' && (
                    <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave}>
                      {t('common.create') || '创建'}
                    </Button>
                  )}
                  
                  {/* 查看模式：显示编辑按钮 */}
                  {pageMode === 'view' && (
                    <Button icon={<EditOutlined />} type="default" onClick={() => setEditMode(true)}>
                      {t('common.edit') || '编辑'}
                    </Button>
                  )}
                  
                  {/* 编辑模式：显示取消和保存按钮 */}
                  {pageMode === 'edit' && (
                    <>
                      <Button onClick={() => {
                        setEditMode(false);
                        // 重新加载数据
                        if (!isNew && id && username) {
                          const api = get_ipc_api();
                          api.getAgents(username, [id]).then((response: any) => {
                            if (response?.success && response.data?.agents?.[0]) {
                              const agent = response.data.agents[0];
                              const orgId = agent.organization || '';
                              form.setFieldsValue({
                                id: agent.card?.id || agent.id,
                                agent_id: agent.card?.id || agent.id,
                                name: agent.card?.name || agent.name,
                                gender: agent.gender || 'gender_options.male',
                                birthday: agent.birthday ? dayjs(agent.birthday) : null,
                                owner: agent.owner || username,
                                personality: agent.personalities || [],
                                title: agent.title || [],
                                organization: orgId,
                                supervisors: agent.supervisors || [],
                                tasks: agent.tasks || [],
                                skills: agent.skills || [],
                                vehicle: agent.vehicle || '本机',
                                metadata: agent.metadata ? JSON.stringify(agent.metadata, null, 2) : ''
                              });
                              // 设置选中的组织ID
                              if (orgId) {
                                setSelectedOrgId(orgId);
                              }
                            }
                          });
                        }
                      }}>
                        {t('common.cancel') || '取消'}
                      </Button>
                      <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave}>
                        {t('common.save') || '保存'}
                      </Button>
                    </>
                  )}
                </div>
              </Col>
            </Row>
          </Form>
        </div>
        </Card>
      </div>
  );
};

export default AgentDetails;

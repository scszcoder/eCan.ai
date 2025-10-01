import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { App, Button, Card, Col, DatePicker, Divider, Form, Input, Radio, Row, Select, Space, Tag, Tooltip } from 'antd';
import { ArrowLeftOutlined, EditOutlined, SaveOutlined, PlusOutlined } from '@ant-design/icons';
import { Dayjs } from 'dayjs';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { useOrgStore } from '@/stores/orgStore';
import { useAppDataStore } from '@/stores/appDataStore';
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
  organizations?: string[];
  supervisors?: string[];
  subordinates?: string[];
  tasks?: string[];
  skills?: string[];
  vehicle?: string | null;
  metadata?: string;
}

const knownPersonalities = ['personality.friendly', 'personality.analytical', 'personality.creative', 'personality.efficient', 'personality.empathetic'];
const knownTitles = ['title.engineer', 'title.manager', 'title.analyst', 'title.designer', 'title.operator'];
const knownOrganizations = ['organization.rd', 'organization.sales', 'organization.marketing', 'organization.hr', 'organization.ops'];
const knownSupervisors = ['agent_super_1', 'agent_super_2'];
const knownSubordinates = ['agent_sub_1', 'agent_sub_2'];
// Tasks and skills will be sourced from global store to link with Tasks/Skills pages
// We keep fallback arrays in case store is empty to avoid empty UI when no data loaded yet
const knownTasks = ['task_001', 'task_002', 'task_003'];
const knownSkills = ['skill_001', 'skill_002', 'skill_003'];
const knownVehicles = ['HostA (10.0.0.1)', 'HostB (10.0.0.2)', 'HostC (10.0.0.3)'];

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
  const { message } = App.useApp();

  // Pull tasks and skills from global app data store (populated by Tasks/Skills pages)
  // TODO: 将来迁移到专用的 taskStore 和 skillStore
  const storeTasks = useAppDataStore((state) => state.tasks);
  const storeSkills = useAppDataStore((state) => state.skills);
  const setTasks = useAppDataStore((state) => state.setTasks);
  const setSkills = useAppDataStore((state) => state.setSkills);
  
  // 获取组织数据
  const { treeOrgs } = useOrgStore();

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

  // 构建组织选项 - 从树形结构中提取所有组织
  const organizationOptions = useMemo(() => {
    const extractOrgs = (node: any): string[] => {
      let orgs: string[] = [];
      if (node.id && node.name) {
        orgs.push(node.id);
      }
      if (node.children && Array.isArray(node.children)) {
        node.children.forEach((child: any) => {
          orgs = orgs.concat(extractOrgs(child));
        });
      }
      return orgs;
    };

    if (treeOrgs && treeOrgs.length > 0) {
      const allOrgIds = extractOrgs(treeOrgs[0]);
      return allOrgIds.length > 0 ? allOrgIds : knownOrganizations;
    }
    return knownOrganizations;
  }, [treeOrgs]);

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
  const [selectValues, setSelectValues] = useState<Record<string, string | undefined>>({});
  const [isNavigating, setIsNavigating] = useState(false);
  
  const goBack = useCallback(async () => {
    if (isNavigating) return; // Prevent multiple rapid clicks
    setIsNavigating(true);
    try {
      await navigate('/agents', { replace: true }); // Navigate to parent route
    } finally {
      setIsNavigating(false);
    }
  }, [navigate, isNavigating]);

  // 使用 useMemo 来初始化表单值，确保 Form 实例正确连接
  const initialValues: AgentDetailsForm = useMemo(() => {
    if (isNew) {
      return {
        id: '',
        agent_id: '',
        name: '',
        gender: 'gender_options.male' as Gender,
        birthday: null,
        owner: username || t('common.owner') || 'owner',
        personality: [],
        title: [],
        organizations: defaultOrgId ? [defaultOrgId] : [], // 设置默认组织
        supervisors: [],
        subordinates: [],
        tasks: [],
        skills: [],
        vehicle: null,
        metadata: ''
      };
    } else {
      return {
        id: id,
        agent_id: id,
        name: `${t('common.agent') || 'Agent'} ${id}`,
        gender: 'gender_options.male' as Gender,
        birthday: null,
        owner: username || t('common.owner') || 'owner',
        personality: ['personality.friendly'],
        title: ['title.engineer'],
        organizations: ['organization.rd'],
        supervisors: [],
        subordinates: [],
        tasks: [],
        skills: [],
        vehicle: null,
        metadata: `{\n  "${t('common.note') || 'note'}": "${t('common.sample') || 'sample'}"\n}`
      };
    }
  }, [id, isNew, username, t, defaultOrgId]);

  // 使用 useEffect 来设置表单值，但只在组件挂载后执行一次
  useEffect(() => {
    form.setFieldsValue(initialValues);
    setEditMode(isNew);
  }, [form, initialValues, isNew]);

  // 将ListEditor改为受控组件
  const ListEditor: React.FC<{
    label: string;
    items: string[] | undefined;
    setItems: (arr: string[]) => void;
    options: string[];
    editable: boolean;
    onEdit?: (id: string) => void;
  }> = ({ label, items, setItems, options, editable, onEdit }) => {
    const selectValue = selectValues[label] || undefined;
    const setSelectValue = (value: string | undefined) => {
      setSelectValues(prev => ({ ...prev, [label]: value }));
    };
    
    return (
      <div>
        <Space wrap size={[8, 8]}>
          {(items || []).map((v) => (
            <Tag key={`${label}-${v}`} closable={editable} onClose={() => setItems((items || []).filter(i => i !== v))}>
              <Space size={4}>
                <span>{label === (t('pages.agents.organization') || 'Organization') ? getOrgName(v) : (t(v) || v)}</span>
                {onEdit && (
                  <Tooltip title={t('common.edit_item', { item: label }) || `Edit ${label}`}> 
                    <Button size="small" type="text" icon={<EditOutlined />} onClick={() => onEdit(v)} />
                  </Tooltip>
                )}
              </Space>
            </Tag>
          ))}
        </Space>
        <div style={{ marginTop: 8 }}>
          <Space>
            <Button icon={<PlusOutlined />} disabled={!editable} onClick={() => {
              if (selectValue && !(items || []).includes(selectValue)) {
                setItems([...(items || []), selectValue]);
                setSelectValue(undefined);
              }
            }}>{t('common.add') || 'Add'}</Button>
            <Select
              style={{ minWidth: 220 }}
              value={selectValue}
              onChange={setSelectValue}
              disabled={!editable}
              options={options.map(o => ({ 
                value: o, 
                label: label === (t('pages.agents.organization') || 'Organization') ? getOrgName(o) : (t(o) || o)
              }))}
              placeholder={t('common.select_item', { item: label }) || `Select ${label}`}
              getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}

            />
          </Space>
        </div>
      </div>
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
        <Space align="center" size={12} style={{ marginBottom: 16 }}>
        <Button 
          icon={<ArrowLeftOutlined />} 
          onClick={goBack} 
          title={t('common.back') || 'Back'} 
          aria-label={t('common.back') || 'Back'}
          loading={isNavigating}
          disabled={isNavigating}
        />
        <span style={{ fontSize: 18, fontWeight: 600 }}>
          {t('pages.agents.agent_details') || 'Agent Details'}
          {isNew && defaultOrgId && (
            <span style={{ fontSize: 14, fontWeight: 400, color: 'rgba(255, 255, 255, 0.65)', marginLeft: 8 }}>
              - {getOrgName(defaultOrgId)}
            </span>
          )}
        </span>
        </Space>

      <Card style={{ flex: 1, minHeight: 0, overflow: 'hidden' }} styles={{ body: { padding: 16, height: '100%', overflow: 'hidden' } }}>
        <div style={{ height: '100%', overflowY: 'auto' }}>
          <Form form={form} layout="vertical">
            <Row gutter={[16, 16]}>
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

              <Col span={12}>
                <Form.Item name="name" label={t('common.name') || 'Name'} rules={[{ required: true, message: t('common.please_input_name') || 'Please input name' }]}>
                  <Input placeholder={t('common.name') || 'Name'} disabled={!editMode} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="owner" label={t('common.owner') || 'Owner'}>
                  <Input placeholder={t('common.owner') || 'Owner'} disabled />
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
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('pages.agents.personality') || 'Personality'}</div>
                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.personality !== cur.personality}>
                    {() => (
                      <ListEditor
                        label={t('pages.agents.personality') || 'Personality'}
                        items={form.getFieldValue('personality')}
                        setItems={(arr) => form.setFieldsValue({ personality: arr })}
                        options={knownPersonalities}
                        editable={editMode}
                        onEdit={(id) => navigate(`/personalities/details/${id}`)}
                      />
                    )}
                </Form.Item>
                </div>
              </Col>

              <Col span={24}>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('pages.agents.title') || 'Title'}</div>
                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.title !== cur.title}>
                    {() => (
                      <ListEditor
                        label={t('pages.agents.title') || 'Title'}
                        items={form.getFieldValue('title')}
                        setItems={(arr) => form.setFieldsValue({ title: arr })}
                        options={knownTitles}
                        editable={editMode}
                        onEdit={(id) => navigate(`/titles/details/${id}`)}
                      />
                    )}
                </Form.Item>
                </div>
              </Col>

              <Col span={24}>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('pages.agents.organizations') || 'Organizations'}</div>
                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.organizations !== cur.organizations}>
                    {() => (
                      <ListEditor
                        label={t('pages.agents.organization') || 'Organization'}
                        items={form.getFieldValue('organizations')}
                        setItems={(arr) => form.setFieldsValue({ organizations: arr })}
                        options={organizationOptions}
                        editable={editMode}
                        onEdit={(id) => navigate(`/orgs/details/${id}`)}
                      />
                    )}
                </Form.Item>
                </div>
              </Col>

              <Col span={24}>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('pages.agents.supervisors') || 'Supervisors'}</div>
                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.supervisors !== cur.supervisors}>
                    {() => (
                      <ListEditor
                        label={t('pages.agents.supervisor') || 'Supervisor'}
                        items={form.getFieldValue('supervisors')}
                        setItems={(arr) => form.setFieldsValue({ supervisors: arr })}
                        options={knownSupervisors}
                        editable={editMode}
                        onEdit={(id) => navigate(`/supervisors/details/${id}`)}
                      />
                    )}
                </Form.Item>
                </div>
              </Col>

              <Col span={24}>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('pages.agents.subordinates') || 'Subordinates'}</div>
                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.subordinates !== cur.subordinates}>
                    {() => (
                      <ListEditor
                        label={t('pages.agents.subordinate') || 'Subordinate'}
                        items={form.getFieldValue('subordinates')}
                        setItems={(arr) => form.setFieldsValue({ subordinates: arr })}
                        options={knownSubordinates}
                        editable={editMode}
                        onEdit={(id) => navigate(`/subordinates/details/${id}`)}
                      />
                    )}
                </Form.Item>
                </div>
              </Col>

              <Col span={24}>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('pages.agents.tasks') || 'Tasks'}</div>
                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.tasks !== cur.tasks}>
                    {() => (
                      <ListEditor
                        label={t('pages.agents.task') || 'Task'}
                        items={form.getFieldValue('tasks')}
                        setItems={(arr) => form.setFieldsValue({ tasks: arr })}
                        options={taskOptions}
                        editable={true}
                        onEdit={() => navigate(`/tasks`)}
                      />
                    )}
                </Form.Item>
                </div>
              </Col>

              <Col span={24}>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('pages.agents.skills') || 'Skills'}</div>
                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.skills !== cur.skills}>
                    {() => (
                      <ListEditor
                        label={t('pages.agents.skill') || 'Skill'}
                        items={form.getFieldValue('skills')}
                        setItems={(arr) => form.setFieldsValue({ skills: arr })}
                        options={skillOptions}
                        editable={true}
                        onEdit={() => navigate(`/skills`)}
                      />
                    )}
                </Form.Item>
                </div>
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
            </Row>
          </Form>
        </div>

          <Divider />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button icon={<EditOutlined />} type="default" disabled={editMode} onClick={() => setEditMode(true)}>
              {t('common.edit') || 'Edit'}
            </Button>
            {editMode && (
              <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave}>
                {t('common.save') || 'Save'}
              </Button>
            )}
          </div>
        </Card>
      </div>
  );
};

export default AgentDetails;

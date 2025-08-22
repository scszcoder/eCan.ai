import React, { useEffect, useMemo, useState } from 'react';
import { App, Button, Card, Col, DatePicker, Divider, Form, Input, Radio, Row, Select, Space, Tag, Tooltip } from 'antd';
import { ArrowLeftOutlined, CloseOutlined, EditOutlined, SaveOutlined, PlusOutlined, ToolOutlined, FileTextOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';
import type { Agent } from '../types';

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
const knownTasks = ['task_001', 'task_002', 'task_003'];
const knownSkills = ['skill_001', 'skill_002', 'skill_003'];
const knownVehicles = ['HostA (10.0.0.1)', 'HostB (10.0.0.2)', 'HostC (10.0.0.3)'];

const AgentDetails: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams();
  const isNew = id === 'new';
  const username = useUserStore((s: any) => s.username);
  const { message } = App.useApp();

  const [form] = Form.useForm<AgentDetailsForm>();
  const [editMode, setEditMode] = useState(isNew);
  const [loading, setLoading] = useState(false);
  const [selectValues, setSelectValues] = useState<Record<string, string | undefined>>({});

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
        organizations: [],
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
  }, [id, isNew, username, t]);

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
                <span>{t(v) || v}</span>
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
              options={options.map(o => ({ value: o, label: t(o) || o }))}
              placeholder={t('common.select_item', { item: label }) || `Select ${label}`}
            />
          </Space>
        </div>
      </div>
    );
  };

  const disabled = !editMode;

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

  const goBack = () => navigate('/agents');

  return (
    <App>
      <div style={{ padding: 16 }}>
        <Space align="center" size={12} style={{ marginBottom: 16 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={goBack} title={t('common.back') || 'Back'} aria-label={t('common.back') || 'Back'} />
          <span style={{ fontSize: 18, fontWeight: 600 }}>{t('pages.agents.agent_details') || 'Agent Details'}</span>
        </Space>

        <Card>
          <Form form={form} layout="vertical" disabled={!editMode}>
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
                  <DatePicker style={{ width: '100%' }} disabled={!editMode} />
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
                        options={knownOrganizations}
                        editable={editMode}
                        onEdit={(id) => navigate(`/organizations/details/${id}`)}
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
                        options={knownTasks}
                        editable={editMode}
                        onEdit={(id) => navigate(`/tasks/details/${id}`)}
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
                        options={knownSkills}
                        editable={editMode}
                        onEdit={(id) => navigate(`/skills/details/${id}`)}
                      />
                    )}
                  </Form.Item>
                </div>
              </Col>

              <Col span={24}>
                <Form.Item name="vehicle" label={t('pages.agents.vehicle') || 'Vehicle'}>
                  <Select disabled={!editMode} allowClear placeholder={t('common.select_vehicle') || 'Select vehicle'} options={knownVehicles.map(v => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item name="metadata" label={t('pages.agents.metadata') || 'Metadata'}>
                  <Input.TextArea rows={6} style={{ resize: 'both' }} disabled={!editMode} />
                </Form.Item>
              </Col>
            </Row>
          </Form>

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
    </App>
  );
};

export default AgentDetails;

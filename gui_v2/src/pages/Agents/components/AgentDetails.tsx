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

const listEditor = (
  label: string,
  items: string[] | undefined,
  setItems: (arr: string[]) => void,
  options: string[],
  editable: boolean,
  onEdit?: (id: string) => void
) => {
  const [selectValue, setSelectValue] = useState<string | undefined>();
  const { t } = useTranslation();
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

  // Initialize form: if new, set blank defaults; otherwise set sample/existing values
  useEffect(() => {
    if (isNew) {
      const init: AgentDetailsForm = {
        id: undefined,
        agent_id: undefined,
        name: '',
        gender: 'gender_options.male',
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
      form.setFieldsValue(init);
      setEditMode(true);
    } else {
      const init: AgentDetailsForm = {
        id: id,
        agent_id: id,
        name: `${t('common.agent') || 'Agent'} ${id}`,
        gender: 'gender_options.male',
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
      form.setFieldsValue(init);
      setEditMode(false);
    }
  }, [id, isNew, username, form, t]);

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
          <Button icon={<ArrowLeftOutlined />} onClick={goBack} />
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
                <Form.Item label={t('pages.agents.personality') || 'Personality'} name="personality" valuePropName="value">
                  {listEditor(t('pages.agents.personality') || 'Personality', form.getFieldValue('personality'), (arr) => form.setFieldsValue({ personality: arr }), knownPersonalities, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label={t('pages.agents.title') || 'Title'} name="title" valuePropName="value">
                  {listEditor(t('pages.agents.title') || 'Title', form.getFieldValue('title'), (arr) => form.setFieldsValue({ title: arr }), knownTitles, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label={t('pages.agents.organizations') || 'Organizations'} name="organizations" valuePropName="value">
                  {listEditor(t('pages.agents.organization') || 'Organization', form.getFieldValue('organizations'), (arr) => form.setFieldsValue({ organizations: arr }), knownOrganizations, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label={t('pages.agents.supervisors') || 'Supervisors'} name="supervisors" valuePropName="value">
                  {listEditor(t('pages.agents.supervisor') || 'Supervisor', form.getFieldValue('supervisors'), (arr) => form.setFieldsValue({ supervisors: arr }), knownSupervisors, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label={t('pages.agents.subordinates') || 'Subordinates'} name="subordinates" valuePropName="value">
                  {listEditor(t('pages.agents.subordinate') || 'Subordinate', form.getFieldValue('subordinates'), (arr) => form.setFieldsValue({ subordinates: arr }), knownSubordinates, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label={t('pages.agents.tasks') || 'Tasks'} name="tasks" valuePropName="value">
                  {listEditor(t('pages.agents.task') || 'Task', form.getFieldValue('tasks'), (arr) => form.setFieldsValue({ tasks: arr }), knownTasks, editMode, (taskId) => navigate(`/tasks/details/${taskId}`))}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label={t('pages.agents.skills') || 'Skills'} name="skills" valuePropName="value">
                  {listEditor(t('pages.agents.skill') || 'Skill', form.getFieldValue('skills'), (arr) => form.setFieldsValue({ skills: arr }), knownSkills, editMode, (skillId) => navigate(`/skills/details/${skillId}`))}
                </Form.Item>
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

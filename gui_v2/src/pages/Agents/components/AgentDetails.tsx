import React, { useEffect, useMemo, useState } from 'react';
import { App, Button, Card, Col, DatePicker, Divider, Form, Input, Radio, Row, Select, Space, Tag, Tooltip } from 'antd';
import { ArrowLeftOutlined, CloseOutlined, EditOutlined, SaveOutlined, PlusOutlined, ToolOutlined, FileTextOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';
import type { Agent } from '../types';

type Gender = 'Male' | 'Female';

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

const knownPersonalities = ['Friendly', 'Analytical', 'Creative', 'Efficient', 'Empathetic'];
const knownTitles = ['Engineer', 'Manager', 'Analyst', 'Designer', 'Operator'];
const knownOrganizations = ['R&D', 'Sales', 'Marketing', 'HR', 'Ops'];
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
  return (
    <div>
      <Space wrap size={[8, 8]}>
        {(items || []).map((v) => (
          <Tag key={`${label}-${v}`} closable={editable} onClose={() => setItems((items || []).filter(i => i !== v))}>
            <Space size={4}>
              <span>{v}</span>
              {onEdit && (
                <Tooltip title={`Edit ${label}`}> 
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
          }}>Add</Button>
          <Select
            style={{ minWidth: 220 }}
            value={selectValue}
            onChange={setSelectValue}
            disabled={!editable}
            options={options.map(o => ({ value: o, label: o }))}
            placeholder={`Select ${label}`}
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
        gender: 'Male',
        birthday: null,
        owner: username || 'owner',
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
        name: `Agent ${id}`,
        gender: 'Male',
        birthday: null,
        owner: username || 'owner',
        personality: ['Friendly'],
        title: ['Engineer'],
        organizations: ['R&D'],
        supervisors: [],
        subordinates: [],
        tasks: [],
        skills: [],
        vehicle: null,
        metadata: '{\n  "note": "sample"\n}'
      };
      form.setFieldsValue(init);
      setEditMode(false);
    }
  }, [id, isNew, username, form]);

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
        message.error(res.error?.message || 'Save failed');
      }
    } catch (e: any) {
      message.error(e?.message || 'Validation failed');
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
          <span style={{ fontSize: 18, fontWeight: 600 }}>{t('Agent Details')}</span>
        </Space>

        <Card>
          <Form form={form} layout="vertical" disabled={!editMode}>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Form.Item name="id" label="ID">
                  <Input readOnly />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="agent_id" label="Agent ID">
                  <Input readOnly />
                </Form.Item>
              </Col>

              <Col span={12}>
                <Form.Item name="name" label="Name" rules={[{ required: true, message: 'Please input name' }]}>
                  <Input placeholder="Name" disabled={!editMode} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="owner" label="Owner">
                  <Input placeholder="Owner" disabled />
                </Form.Item>
              </Col>

              <Col span={12}>
                <Form.Item name="gender" label="Gender">
                  <Radio.Group disabled={!editMode}>
                    <Radio value="Male">Male</Radio>
                    <Radio value="Female">Female</Radio>
                  </Radio.Group>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="birthday" label="Birthday">
                  <DatePicker style={{ width: '100%' }} disabled={!editMode} />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label="Personality" name="personality" valuePropName="value">
                  {listEditor('Personality', form.getFieldValue('personality'), (arr) => form.setFieldsValue({ personality: arr }), knownPersonalities, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label="Title" name="title" valuePropName="value">
                  {listEditor('Title', form.getFieldValue('title'), (arr) => form.setFieldsValue({ title: arr }), knownTitles, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label="Organizations" name="organizations" valuePropName="value">
                  {listEditor('Organization', form.getFieldValue('organizations'), (arr) => form.setFieldsValue({ organizations: arr }), knownOrganizations, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label="Supervisors" name="supervisors" valuePropName="value">
                  {listEditor('Supervisor', form.getFieldValue('supervisors'), (arr) => form.setFieldsValue({ supervisors: arr }), knownSupervisors, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label="Subordinates" name="subordinates" valuePropName="value">
                  {listEditor('Subordinate', form.getFieldValue('subordinates'), (arr) => form.setFieldsValue({ subordinates: arr }), knownSubordinates, editMode)}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label="Tasks" name="tasks" valuePropName="value">
                  {listEditor('Task', form.getFieldValue('tasks'), (arr) => form.setFieldsValue({ tasks: arr }), knownTasks, editMode, (taskId) => navigate(`/tasks/details/${taskId}`))}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item label="Skills" name="skills" valuePropName="value">
                  {listEditor('Skill', form.getFieldValue('skills'), (arr) => form.setFieldsValue({ skills: arr }), knownSkills, editMode, (skillId) => navigate(`/skills/details/${skillId}`))}
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item name="vehicle" label="Vehicle">
                  <Select disabled={!editMode} allowClear placeholder="Select vehicle" options={knownVehicles.map(v => ({ value: v, label: v }))} />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item name="metadata" label="Metadata">
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

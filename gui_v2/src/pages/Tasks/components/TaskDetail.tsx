import {
  DeleteOutlined,
  OrderedListOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  StopOutlined,
  EditOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Card, Space, Typography, Form, Input, Row, Col, Select, DatePicker, message } from 'antd';
import { useTranslation } from 'react-i18next';
import React from 'react';
import { Task } from '../types';
import dayjs from 'dayjs';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';

const { Title, Text } = Typography;

const DEFAULT_TASK = {
  id: '',
  name: '',
  description: '',
  priority: 'medium',
  trigger: 'schedule',
  schedule: {
    repeat_type: 'none',
    repeat_number: 1,
    repeat_unit: 'by hours',
    start_date_time: dayjs(),
    end_date_time: undefined as any,
    time_out: 3600,
  },
  objectives: '',
  metadata: {},
};

const PRIORITY_OPTIONS = ['low', 'medium', 'high', 'urgent'];
const TRIGGER_OPTIONS = ['schedule', 'human chat', 'agent message'];
const REPEAT_OPTIONS = [
  'none',
  'by seconds',
  'by minutes',
  'by hours',
  'by days',
  'by weeks',
  'by months',
  'by years',
];

interface TaskDetailProps {
  task: Task | null | object;
  isNew?: boolean;
  onSave?: () => void;
  onCancel?: () => void;
}

type ExtendedTask = Task & {
  ataskid?: string | number;
  name?: string;
  owner?: string;
  description?: string;
  latest_version?: string;
  objectives?: string;
  metadata_text?: string; // stringified metadata for editing
};

export const TaskDetail: React.FC<TaskDetailProps> = ({ task = {} as any, isNew = false, onSave, onCancel }) => {
  const { t } = useTranslation();
  const username = useUserStore((s) => s.username) || '';
  const [form] = Form.useForm<ExtendedTask>();
  const [editMode, setEditMode] = React.useState(isNew);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (task) {
      const metaStr = task.metadata ? JSON.stringify(task.metadata, null, 2) : '';
      form.setFieldsValue({
        id: (task as any).id as any,
        ataskid: (task as any).ataskid,
        name: (task as any).name,
        owner: (task as any).owner,
        description: (task as any).description,
        latest_version: (task as any).latest_version,
        priority: (task as any).priority,
        trigger: (task as any).trigger,
        schedule: {
          repeat_type: (task as any).schedule?.repeat_type,
          repeat_number: (task as any).schedule?.repeat_number,
          repeat_unit: (task as any).schedule?.repeat_unit,
          start_date_time: (task as any).schedule?.start_date_time ? dayjs((task as any).schedule?.start_date_time) : undefined,
          end_date_time: (task as any).schedule?.end_date_time ? dayjs((task as any).schedule?.end_date_time) : undefined,
          time_out: (task as any).schedule?.time_out,
        },
        objectives: (task as any).objectives,
        metadata_text: metaStr,
      } as any);
    } else {
      form.resetFields();
      setEditMode(false);
    }
  }, [task, form]);

  const handleCancel = () => {
    form.resetFields();
    setEditMode(false);
    if (isNew && onCancel) {
      onCancel();
    }
  };

  const handleEdit = () => setEditMode(true);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const payload: any = {
        id: (values as any).id,
        ataskid: (values as any).ataskid || undefined,
        name: (values as any).name || 'New Task',
        owner: username,
        description: (values as any).description || '',
        latest_version: (values as any).latest_version || '1.0.0',
        priority: (values as any).priority || 'medium',
        trigger: (values as any).trigger || 'manual',
        schedule: {
          repeat_type: (values as any).schedule?.repeat_type || 'none',
          repeat_number: (values as any).schedule?.repeat_number || 1,
          repeat_unit: (values as any).schedule?.repeat_unit || 'hours',
          start_date_time: (values as any).schedule?.start_date_time ? 
            (values as any).schedule.start_date_time.toISOString() : 
            new Date().toISOString(),
          end_date_time: (values as any).schedule?.end_date_time ? 
            (values as any).schedule.end_date_time.toISOString() : 
            null,
          time_out: (values as any).schedule?.time_out || 3600,
        },
        objectives: (values as any).objectives || '',
        metadata: (values as any).metadata_text ? 
          JSON.parse((values as any).metadata_text) : {},
      };

      setSaving(true);
      const api = get_ipc_api();
      const response = isNew
        ? await api.newTasks(username, [payload])
        : await api.saveTasks(username, [payload]);
      
      if (response.success) {
        message.success(t(isNew ? 'common.createSuccess' : 'common.saveSuccess'));
        setEditMode(false);
        if (onSave) onSave();
      } else {
        message.error(response.error?.message || 
          t(isNew ? 'common.createFailed' : 'common.saveFailed'));
      }
    } catch (error) {
      console.error(`Error ${isNew ? 'creating' : 'saving'} task:`, error);
      message.error(t(isNew ? 'common.createFailed' : 'common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  // Always show the form, even for new/empty tasks
  const displayTask = isNew ? DEFAULT_TASK : (task || {});

  return (
    <div style={{ maxHeight: '100%', overflow: 'auto', padding: '16px' }}>
      <Form
        form={form}
        layout="vertical"
        initialValues={displayTask}
        onFinish={handleSave}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <Card>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Space align="start">
                <Avatar size={64} icon={<OrderedListOutlined />} />
                <div style={{ flex: 1 }}>
                  <Form.Item name="name" label={t('pages.tasks.name')} rules={[{ required: true }]}>
                    <Input placeholder={t('pages.tasks.namePlaceholder')} />
                  </Form.Item>
                  {!isNew && <Text type="secondary">ID: {(task as any).id}</Text>}
                </div>
              </Space>

              <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
                <Col span={12}>
                  <Form.Item label="ID" name="id">
                    <Input readOnly />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="ATask ID" name="ataskid">
                    <Input readOnly />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t('common.owner', 'Owner')} name="owner">
                    <Input readOnly />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t('pages.tasks.latestVersion', 'Latest Version')} name="latest_version">
                    <Input readOnly />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Form.Item label={t('common.description', 'Description')} name="description">
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t('pages.tasks.priorityLabel', 'Priority')} name="priority">
                    <Select options={PRIORITY_OPTIONS.map(v => ({ value: v, label: v }))} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label={t('pages.tasks.triggerLabel', 'Trigger')} name="trigger">
                    <Select options={TRIGGER_OPTIONS.map(v => ({ value: v, label: v }))} />
                  </Form.Item>
                </Col>

                <Col span={24}>
                  <Card size="small" title={t('pages.tasks.scheduleDetails', 'Schedule')}>
                    <Row gutter={[16, 8]}>
                      <Col span={8}>
                        <Form.Item label={t('pages.tasks.scheduleRepeatTypeLabel', 'Repeat Type')} name={["schedule", "repeat_type"]}>
                          <Select options={REPEAT_OPTIONS.map(v => ({ value: v, label: v }))} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label={t('pages.tasks.scheduleRepeatNumberLabel', 'Repeat Number')} name={["schedule", "repeat_number"]}>
                          <Input type="number" min={1} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label={t('pages.tasks.scheduleRepeatUnitLabel', 'Repeat Unit')} name={["schedule", "repeat_unit"]}>
                          <Select options={REPEAT_OPTIONS.filter(v => v !== 'none').map(v => ({ value: v, label: v }))} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label={t('pages.tasks.scheduleStartTimeLabel', 'Start Date Time')} name={["schedule", "start_date_time"]}>
                          <DatePicker showTime style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label={t('pages.tasks.scheduleEndTimeLabel', 'End Date Time (Optional)')} name={["schedule", "end_date_time"]}>
                          <DatePicker showTime style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label={t('pages.tasks.scheduleTimeoutLabel', 'Timeout (seconds)')} name={["schedule", "time_out"]}>
                          <Input type="number" min={60} step={60} />
                        </Form.Item>
                      </Col>
                    </Row>
                  </Card>
                </Col>

                <Col span={24}>
                  <Form.Item label={t('pages.tasks.objectives', 'Objectives')} name="objectives">
                    <Input.TextArea rows={4} placeholder={t('pages.tasks.objectivesPlaceholder', 'Describe the task objectives in detail')} />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Form.Item 
                    label={t('pages.tasks.metadata', 'Metadata (JSON)')} 
                    name="metadata_text"
                    rules={[{
                      validator: (_, value) => {
                        if (!value) return Promise.resolve();
                        try {
                          JSON.parse(value);
                          return Promise.resolve();
                        } catch (e) {
                          return Promise.reject(new Error('Invalid JSON'));
                        }
                      }
                    }]}
                  >
                    <Input.TextArea 
                      rows={4} 
                      style={{ fontFamily: 'monospace' }}
                      placeholder={JSON.stringify({ key: 'value' }, null, 2)}
                    />
                  </Form.Item>
                </Col>
              </Row>
            </Space>
          </Card>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <Button type="primary" icon={<PlayCircleOutlined />} disabled={isNew || editMode}>
              {t('common.run')}
            </Button>
            <Button danger icon={<StopOutlined />} disabled={isNew || editMode}>
              {t('common.stop')}
            </Button>
            {!editMode && !isNew && (
              <Button 
                type="primary" 
                onClick={handleEdit} 
                icon={<EditOutlined />}
              >
                {t('common.edit')}
              </Button>
            )}
            {editMode && (
              <>
                <Button 
                  type="primary" 
                  htmlType="submit" 
                  icon={<SaveOutlined />} 
                  loading={saving}
                  disabled={saving}
                >
                  {isNew ? t('common.create') : t('common.save')}
                </Button>
                <Button 
                  onClick={handleCancel} 
                  style={{ marginLeft: 8 }} 
                  disabled={saving}
                >
                  {t('common.cancel')}
                </Button>
              </>
            )}
          </div>
        </Space>
      </Form>
    </div>
  );
};
import {
  DeleteOutlined,
  OrderedListOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Card, Space, Typography, Form, Input, Row, Col, Select, DatePicker, message } from 'antd';
import { useTranslation } from 'react-i18next';
import React from 'react';
import { Task } from '../types';
import dayjs from 'dayjs';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';

const { Title, Text } = Typography;

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
  task: Task | null;
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

export const TaskDetail: React.FC<TaskDetailProps> = ({ task }) => {
  const { t } = useTranslation();
  const username = useUserStore((s) => s.username) || '';
  const [form] = Form.useForm<ExtendedTask>();
  const [editMode, setEditMode] = React.useState(false);

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

  const handleEdit = () => setEditMode(true);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const payload: any = {
        id: (values as any).id,
        ataskid: (values as any).ataskid,
        name: (values as any).name,
        owner: (values as any).owner,
        description: (values as any).description,
        latest_version: (values as any).latest_version,
        priority: (values as any).priority,
        trigger: (values as any).trigger,
        schedule: {
          repeat_type: (values as any).schedule?.repeat_type,
          repeat_number: (values as any).schedule?.repeat_number,
          repeat_unit: (values as any).schedule?.repeat_unit,
          start_date_time: (values as any).schedule?.start_date_time ? (values as any).schedule.start_date_time.toISOString() : null,
          end_date_time: (values as any).schedule?.end_date_time ? (values as any).schedule.end_date_time.toISOString() : null,
          time_out: (values as any).schedule?.time_out,
        },
        objectives: (values as any).objectives,
      };
      // metadata as JSON if valid
      const metaText = (values as any).metadata_text;
      if (metaText) {
        try {
          payload.metadata = JSON.parse(metaText);
        } catch {
          payload.metadata = metaText; // keep as string if not JSON
        }
      }

      const resp = await get_ipc_api().saveTasks(username, [payload]);
      if (resp.success) {
        message.success(t('common.saved', 'Saved'));
        setEditMode(false);
      } else {
        message.error(resp.error?.message || 'Save failed');
      }
    } catch (e) {
      if (e instanceof Error) message.error(e.message);
    }
  };

  if (!task) {
    return <Text type="secondary">{t('pages.tasks.selectTask')}</Text>;
  }

  return (
    <div style={{ maxHeight: '100%', overflow: 'auto' }}>
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <Space align="start">
          <Avatar size={64} icon={<OrderedListOutlined />} />
          <div>
            <Title level={4} style={{ margin: 0 }}>{(task as any).name || task.skill}</Title>
            <Text type="secondary">ID: {(task as any).id}</Text>
          </div>
        </Space>

        <Card>
          <Form form={form} layout="vertical" disabled={!editMode}>
            <Row gutter={[16, 8]}>
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
                <Form.Item label={t('common.name', 'Name')} name="name">
                  <Input />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label={t('common.owner', 'Owner')} name="owner">
                  <Input readOnly />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item label={t('common.description', 'Description')} name="description">
                  <Input.TextArea rows={6} style={{ overflowX: 'auto', overflowY: 'auto', whiteSpace: 'pre' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label={t('pages.tasks.latestVersion', 'Latest Version')} name="latest_version">
                  <Input readOnly />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Row gutter={16}>
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
                </Row>
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
                        <Input />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label={t('pages.tasks.scheduleRepeatUnitLabel', 'Repeat Unit')} name={["schedule", "repeat_unit"]}>
                        <Select options={REPEAT_OPTIONS.map(v => ({ value: v, label: v }))} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label={t('pages.tasks.scheduleStartTimeLabel', 'Start Date Time')} name={["schedule", "start_date_time"]}>
                        <DatePicker showTime style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label={t('pages.tasks.scheduleEndTimeLabel', 'End Date Time')} name={["schedule", "end_date_time"]}>
                        <DatePicker showTime style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label={t('pages.tasks.scheduleTimeoutLabel', 'Timeout')} name={["schedule", "time_out"]}>
                        <Input addonAfter={t('pages.tasks.secondsLabel', 'seconds')} />
                      </Form.Item>
                    </Col>
                  </Row>
                </Card>
              </Col>

              <Col span={24}>
                <Form.Item label={t('pages.tasks.objectives', 'Objectives')} name="objectives">
                  <Input.TextArea rows={6} style={{ overflowX: 'auto', overflowY: 'auto', whiteSpace: 'pre' }} />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item label={t('pages.tasks.metadata', 'Metadata')} name="metadata_text">
                  <Input.TextArea rows={6} style={{ overflowX: 'auto', overflowY: 'auto', whiteSpace: 'pre' }} />
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </Card>

        {/* Buttons at bottom */}
        <Space>
          <Button type="primary" icon={<PlayCircleOutlined />}>{t('common.run')}</Button>
          <Button danger icon={<StopOutlined />}>{t('common.stop')}</Button>
          <Button onClick={handleEdit} disabled={editMode}>{t('common.edit', 'Edit')}</Button>
          {editMode && (
            <Button type="primary" onClick={handleSave}>{t('common.save', 'Save')}</Button>
          )}
          <Button icon={<SettingOutlined />}>{t('common.settings')}</Button>
          <Button danger icon={<DeleteOutlined />}>{t('common.delete')}</Button>
        </Space>
      </Space>
    </div>
  );
};
import {
  EditOutlined,
  SaveOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { Button, Space, Form, Input, Row, Col, Select, DatePicker, App } from 'antd';
import { useTranslation } from 'react-i18next';
import React from 'react';
import { Task } from '../types';
import dayjs from 'dayjs';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useSkillStore } from '@/stores';
import {
  StyledFormItem,
  StyledCard,
  FormContainer,
  ButtonContainer,
  buttonStyle,
  primaryButtonStyle
} from '@/components/Common/StyledForm';

// Typography components (currently unused but available for future use)
// const { Text, Title } = Typography;

const DEFAULT_TASK = {
  id: '',
  name: '',
  description: '',
  priority: 'none',
  trigger: 'schedule',
  schedule: {
    repeat_type: 'none',
    repeat_number: 1,
    repeat_unit: 'by hours',
    start_date_time: dayjs(),
    end_date_time: undefined as any,
    time_out: 3600,
  },
  metadata: {},
};

const PRIORITY_OPTIONS = ['none', 'low', 'medium', 'high', 'urgent'];
const TRIGGER_OPTIONS = [
  'schedule',
  'human chat',
  'agent message',
  'chat_queue',
  'a2a_queue',
  'manual',
  'interaction',
  'message',
];
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
  metadata_text?: string; // stringified metadata for editing
};

// Helper to safely convert to dayjs object
const toDayjs = (date: string | Date | null | undefined) => {
  if (!date) return undefined;
  // Handle custom date format "YYYY-MM-DD HH:mm:ss:SSS"
  const customFormat = "YYYY-MM-DD HH:mm:ss:SSS";
  let d = dayjs(date, customFormat, true); // Strict parsing
  if (!d.isValid()) {
    // Fallback to default parsing for standard formats like ISO 8601
    d = dayjs(date);
  }
  return d.isValid() ? d : undefined;
};

export const TaskDetail: React.FC<TaskDetailProps> = ({ task: rawTask = {} as any, isNew = false, onSave, onCancel }) => {
  const { message } = App.useApp();

  // Pre-process the task data to ensure dates are valid Dayjs objects or undefined
  const task = React.useMemo(() => {
    if (!rawTask || Object.keys(rawTask).length === 0) {
      return isNew ? DEFAULT_TASK : null;
    }
    const processedSchedule = {
      ...((rawTask as any).schedule || {}),
      start_date_time: toDayjs((rawTask as any).schedule?.start_date_time),
      end_date_time: toDayjs((rawTask as any).schedule?.end_date_time),
    };
    return {
      ...rawTask,
      schedule: processedSchedule,
      // Ensure priority is 'none' if it's null or undefined
      priority: (rawTask as any).priority || 'none',
    };
  }, [rawTask, isNew]);
  const { t } = useTranslation();
  const username = useUserStore((s) => s.username) || '';
  const [form] = Form.useForm<ExtendedTask>();
  const [editMode, setEditMode] = React.useState(isNew);
  const [saving, setSaving] = React.useState(false);
  // skills store and fetch-on-mount if needed
  const skills = useSkillStore((s) => s.items);
  const setSkills = useSkillStore((s) => s.setItems);

  React.useEffect(() => {
    const api = get_ipc_api();
    const ensureSkills = async () => {
      try {
        let uname = username;
        if (!uname) {
          const loginInfo = await api.getLastLoginInfo<{ last_login: { username: string } }>();
          if (loginInfo?.success) uname = loginInfo.data?.last_login?.username || '';
        }
        if (uname && (!skills || skills.length === 0)) {
          const res = await api.getSkills<{ skills: any[] }>(uname, []);
          if (res?.success && res.data?.skills) setSkills(res.data.skills as any);
        }
      } catch (e) {
        // silent fail
      }
    };
    ensureSkills();
  }, [username, skills?.length, setSkills]);

  React.useEffect(() => {
    if (task) {
      const metaStr = (task as any).metadata ? JSON.stringify((task as any).metadata, null, 2) : '';

      // 使用 name 字段，如果不存在则使用 skill 字段作为后备
      const taskName = (task as any).name || (task as any).skill || '';

      // 使用 description 字段，如果不存在则使用 metadata 中的描述作为后备
      const taskDescription = (task as any).description
        || (task as any).metadata?.description
        || '';

      // 确保所有字段都正确设置
      const formValues = {
        ...(task as any),
        name: taskName,  // 使用 name 或 skill
        description: taskDescription,  // 使用 description 或其他后备字段
        metadata_text: metaStr,
      };

      form.setFieldsValue(formValues);
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

  const handleEdit = () => {
    console.log('[TaskDetail] Edit button clicked, setting editMode to true');
    setEditMode(true);
  };

  // Debug: Monitor editMode changes
  React.useEffect(() => {
    console.log('[TaskDetail] editMode changed:', editMode, 'isNew:', isNew, 'formDisabled:', !editMode && !isNew);
  }, [editMode, isNew]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const payload: any = {
        id: (values as any).id,
        name: (values as any).name || t('pages.tasks.newTaskName', 'New Task'),
        owner: username,
        description: (values as any).description || '',
        latest_version: (values as any).latest_version || '1.0.0',
        priority: (values as any).priority || 'medium',
        trigger: (values as any).trigger || 'manual',
        skill: (values as any).skill || '',
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
        metadata: (values as any).metadata_text ?
          JSON.parse((values as any).metadata_text) : {},
      };

      setSaving(true);
      const api = get_ipc_api();
      const response = isNew
        ? await api.newAgentTask(username, payload)
        : await api.saveAgentTask(username, payload);
      
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

  // Removed: handleDelete, handleDuplicate, handleRun, handleStop
  // TaskDetail now only supports view and edit operations

  // If no task is selected, show empty state
  if (!task && !isNew) {
    return (
      <FormContainer>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center', 
          height: '100%',
          color: '#999'
        }}>
          {t('pages.tasks.selectTask', '请选择一个任务')}
        </div>
      </FormContainer>
    );
  }

  return (
    <FormContainer>
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSave}
        disabled={!editMode && !isNew}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={24}>
          <StyledCard>
            <Space direction="vertical" style={{ width: '100%' }} size={24}>
              <div style={{ marginBottom: '16px' }}>
                <StyledFormItem
                  name="name"
                  label={t('pages.tasks.name')}
                  rules={[{ required: true }]}
                  style={{ marginBottom: 0 }}
                >
                  <Input
                    placeholder={t('pages.tasks.namePlaceholder')}
                    size="large"
                  />
                </StyledFormItem>
              </div>

              <Row gutter={[24, 0]} style={{ marginTop: '16px' }}>
                <Col span={12}>
                  <StyledFormItem label={t('pages.tasks.taskId', '任务 ID')} name="id" htmlFor="task-id">
                    <Input id="task-id" readOnly aria-label={t('pages.tasks.taskId', '任务 ID')} />
                  </StyledFormItem>
                </Col>
                <Col span={12}>
                  <StyledFormItem label={t('pages.tasks.latestVersion', 'Latest Version')} name="latest_version" htmlFor="task-version">
                    <Input id="task-version" readOnly aria-label={t('pages.tasks.latestVersion', 'Latest Version')} />
                  </StyledFormItem>
                </Col>
                <Col span={12}>
                  <StyledFormItem label={t('common.owner', 'Owner')} name="owner" htmlFor="task-owner">
                    <Input id="task-owner" readOnly aria-label={t('common.owner', 'Owner')} />
                  </StyledFormItem>
                </Col>
                <Col span={12}>
                  <StyledFormItem label={t('pages.tasks.priorityLabel', 'Priority')} name="priority" htmlFor="task-priority">
                    <Select
                      id="task-priority"
                      allowClear
                      size="large"
                      onChange={(value) => {
                        if (value === null || value === undefined) {
                          form.setFieldsValue({ priority: 'none' });
                        }
                      }}
                      options={PRIORITY_OPTIONS.map(v => ({ value: v, label: t(`pages.tasks.priority.${v}`, v) }))}
                      aria-label={t('pages.tasks.priorityLabel', 'Priority')}
                    />
                  </StyledFormItem>
                </Col>
                <Col span={12}>
                  <StyledFormItem label={t('pages.tasks.triggerLabel', 'Trigger')} name="trigger" htmlFor="task-trigger">
                    <Select
                      id="task-trigger"
                      size="large"
                      options={TRIGGER_OPTIONS.map(v => ({ value: v, label: t(`pages.tasks.trigger.${v}`, v) }))}
                      aria-label={t('pages.tasks.triggerLabel', 'Trigger')}
                    />
                  </StyledFormItem>
                </Col>
                <Col span={24}>
                  <StyledFormItem label={t('common.description', 'Description')} name="description" htmlFor="task-description">
                    <Input.TextArea
                      id="task-description"
                      rows={4}
                      placeholder={t('pages.tasks.descriptionPlaceholder', 'Enter task description...')}
                      aria-label={t('common.description', 'Description')}
                    />
                  </StyledFormItem>
                </Col>
                <Col span={24}>
                  <StyledFormItem label={t('pages.tasks.skill', 'Skill')} name="skill" htmlFor="task-skill">
                    {editMode || isNew ? (
                      <Select
                        id="task-skill"
                        allowClear
                        showSearch
                        size="large"
                        placeholder={t('pages.tasks.skillPlaceholder', 'Select a skill')}
                        options={(skills || []).map((s: any) => ({ value: s.name, label: s.name }))}
                        filterOption={(input, option) =>
                          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                        }
                        aria-label={t('pages.tasks.skill', 'Skill')}
                      />
                    ) : (
                      <Input id="task-skill" readOnly aria-label={t('pages.tasks.skill', 'Skill')} />
                    )}
                  </StyledFormItem>
                </Col>

                <Col span={24}>
                  <StyledCard
                    size="small"
                    title={t('pages.tasks.scheduleDetails', 'Schedule')}
                    style={{
                      marginTop: '16px',
                      background: 'rgba(64, 169, 255, 0.05)',
                      borderColor: 'rgba(64, 169, 255, 0.2)'
                    }}
                  >
                    <Row gutter={[16, 16]}>
                      {/* Repeat Settings Row */}
                      <Col span={24}>
                        <div style={{ 
                          padding: '12px', 
                          background: 'rgba(255, 255, 255, 0.02)', 
                          borderRadius: '8px',
                          border: '1px solid rgba(255, 255, 255, 0.05)'
                        }}>
                          <div style={{ 
                            marginBottom: '12px', 
                            fontSize: '13px', 
                            fontWeight: 500, 
                            color: 'rgba(255, 255, 255, 0.65)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px'
                          }}>
                            {t('pages.tasks.repeatSettings', '重复设置')}
                          </div>
                          <Row gutter={[12, 12]}>
                            <Col span={8}>
                              <StyledFormItem label={t('pages.tasks.scheduleRepeatTypeLabel', 'Repeat Type')} name={["schedule", "repeat_type"]} htmlFor="task-repeat-type">
                                <Select
                                  id="task-repeat-type"
                                  size="large"
                                  options={REPEAT_OPTIONS.map(v => ({ value: v, label: t(`pages.tasks.repeatType.${v}`, v) }))}
                                  aria-label={t('pages.tasks.scheduleRepeatTypeLabel', 'Repeat Type')}
                                />
                              </StyledFormItem>
                            </Col>
                            <Col span={8}>
                              <StyledFormItem label={t('pages.tasks.scheduleRepeatNumberLabel', 'Repeat Number')} name={["schedule", "repeat_number"]} htmlFor="task-repeat-number">
                                <Input
                                  id="task-repeat-number"
                                  size="large"
                                  type="number"
                                  min={1}
                                  aria-label={t('pages.tasks.scheduleRepeatNumberLabel', 'Repeat Number')}
                                />
                              </StyledFormItem>
                            </Col>
                            <Col span={8}>
                              <StyledFormItem label={t('pages.tasks.scheduleRepeatUnitLabel', 'Repeat Unit')} name={["schedule", "repeat_unit"]} htmlFor="task-repeat-unit">
                                <Select
                                  id="task-repeat-unit"
                                  size="large"
                                  options={REPEAT_OPTIONS.filter(v => v !== 'none').map(v => ({ value: v, label: t(`pages.tasks.repeatType.${v}`, v) }))}
                                  aria-label={t('pages.tasks.scheduleRepeatUnitLabel', 'Repeat Unit')}
                                />
                              </StyledFormItem>
                            </Col>
                          </Row>
                        </div>
                      </Col>

                      {/* Time Settings Row */}
                      <Col span={24}>
                        <div style={{ 
                          padding: '12px', 
                          background: 'rgba(255, 255, 255, 0.02)', 
                          borderRadius: '8px',
                          border: '1px solid rgba(255, 255, 255, 0.05)'
                        }}>
                          <div style={{ 
                            marginBottom: '12px', 
                            fontSize: '13px', 
                            fontWeight: 500, 
                            color: 'rgba(255, 255, 255, 0.65)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px'
                          }}>
                            {t('pages.tasks.timeSettings', '时间设置')}
                          </div>
                          <Row gutter={[12, 12]}>
                            <Col span={12}>
                              <StyledFormItem label={t('pages.tasks.scheduleStartTimeLabel', 'Start Date Time')} name={["schedule", "start_date_time"]} htmlFor="task-start-time">
                                <DatePicker
                                  id="task-start-time"
                                  size="large"
                                  showTime
                                  style={{ width: '100%' }}
                                  aria-label={t('pages.tasks.scheduleStartTimeLabel', 'Start Date Time')}
                                />
                              </StyledFormItem>
                            </Col>
                            <Col span={12}>
                              <StyledFormItem label={t('pages.tasks.scheduleEndTimeLabel', 'End Date Time (Optional)')} name={["schedule", "end_date_time"]} htmlFor="task-end-time">
                                <DatePicker
                                  id="task-end-time"
                                  size="large"
                                  showTime
                                  style={{ width: '100%' }}
                                  aria-label={t('pages.tasks.scheduleEndTimeLabel', 'End Date Time (Optional)')}
                                />
                              </StyledFormItem>
                            </Col>
                            <Col span={12}>
                              <StyledFormItem label={t('pages.tasks.scheduleTimeoutLabel', 'Timeout (seconds)')} name={["schedule", "time_out"]} htmlFor="task-timeout">
                                <Input
                                  id="task-timeout"
                                  size="large"
                                  type="number"
                                  min={60}
                                  step={60}
                                  aria-label={t('pages.tasks.scheduleTimeoutLabel', 'Timeout (seconds)')}
                                />
                              </StyledFormItem>
                            </Col>
                          </Row>
                        </div>
                      </Col>
                    </Row>
                  </StyledCard>
                </Col>

                <Col span={24}>
                  <StyledFormItem
                    label={t('pages.tasks.metadata', 'Metadata (JSON)')}
                    name="metadata_text"
                    rules={[{
                      validator: (_, value) => {
                        if (!value) return Promise.resolve();
                        try {
                          JSON.parse(value);
                          return Promise.resolve();
                        } catch (e) {
                          return Promise.reject(new Error(t('pages.tasks.invalidJson', 'Invalid JSON')));
                        }
                      }
                    }]}
                  >
                    <Input.TextArea
                      rows={8}
                      placeholder={JSON.stringify({ key: 'value' }, null, 2)}
                      style={{
                        fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                        fontSize: '13px',
                        lineHeight: '1.6'
                      }}
                    />
                  </StyledFormItem>
                </Col>
              </Row>
            </Space>
          </StyledCard>

          <ButtonContainer>
            {/* 编辑模式：显示保存和取消按钮 */}
            {editMode && (
              <>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SaveOutlined />}
                  loading={saving}
                  disabled={saving}
                  size="large"
                  style={primaryButtonStyle}
                >
                  {t('common.save')}
                </Button>
                <Button
                  onClick={handleCancel}
                  disabled={saving}
                  icon={<CloseOutlined />}
                  size="large"
                  style={buttonStyle}
                >
                  {t('common.cancel')}
                </Button>
              </>
            )}

            {/* 查看模式：只显示编辑按钮 */}
            {!editMode && !isNew && (
              <Button
                type="primary"
                onClick={handleEdit}
                icon={<EditOutlined />}
                size="large"
                style={primaryButtonStyle}
                disabled={false}
              >
                {t('common.edit')}
              </Button>
            )}
          </ButtonContainer>
        </Space>
      </Form>
    </FormContainer>
  );
};
import {
  EditOutlined,
  SaveOutlined,
  CloseOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { Button, Space, Form, Input, Row, Col, Select, DatePicker, App } from 'antd';
import { useTranslation } from 'react-i18next';
import React, { useRef } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Task } from '../types';
import dayjs from 'dayjs';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useSkillStore } from '@/stores';
import { useDeleteConfirm } from '@/components/Common/DeleteConfirmModal';
import {
  StyledFormItem,
  StyledCard,
  FormContainer,
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
  onSave?: (taskId?: string) => void; // 修改：支持传递新创建的task ID
  onCancel?: () => void;
  onDelete?: () => void;
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

export const TaskDetail: React.FC<TaskDetailProps> = ({ task: rawTask = {} as any, isNew = false, onSave, onCancel, onDelete }) => {
  const { message } = App.useApp();
  const showDeleteConfirm = useDeleteConfirm();
  
  // ScrollPositionSave
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);

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
          const res = await api.getAgentSkills<{ skills: any[] }>(uname, []);
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

      // 使用 name Field，If不存在则使用 skill Field作为后备
      const taskName = (task as any).name || (task as any).skill || '';

      // 使用 description Field，If不存在则使用 metadata 中的Description作为后备
      const taskDescription = (task as any).description
        || (task as any).metadata?.description
        || '';

      // 确保AllField都正确Settings
      const formValues = {
        ...(task as any),
        name: taskName,  // 使用 name 或 skill
        description: taskDescription,  // 使用 description 或其他后备Field
        metadata_text: metaStr,
      };

      form.setFieldsValue(formValues);
    } else {
      form.resetFields();
      setEditMode(false);
    }
  }, [task, form]);

  const handleCancel = () => {
    if (isNew) {
      // 新建模式：清空Form并Notification父ComponentClose面板
      form.resetFields();
      if (onCancel) {
        onCancel();
      }
    } else {
      // Edit模式：Restore原始Data并退出Edit模式（不Close面板）
      if (task) {
        const metaStr = (task as any).metadata ? JSON.stringify((task as any).metadata, null, 2) : '';
        const taskName = (task as any).name || (task as any).skill || '';
        const taskDescription = (task as any).description
          || (task as any).metadata?.description
          || '';
        
        const formValues = {
          ...(task as any),
          name: taskName,
          description: taskDescription,
          metadata_text: metaStr,
        };
        
        form.setFieldsValue(formValues);
      }
      setEditMode(false);
      // Edit模式下不调用 onCancel，保持面板Open
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
        // 传递新创建的task ID给父组件
        if (onSave) {
          // API返回的task_id在response.data.task_id
          const newTaskId = isNew ? response.data?.task_id || response.data?.id || response.data?.task?.id || payload.id : undefined;
          console.log('[TaskDetail] 保存成功，Task ID:', newTaskId);
          console.log('[TaskDetail] API响应数据:', response.data);
          onSave(newTaskId);
        }
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

  const handleDelete = () => {
    if (!task || isNew) return;

    showDeleteConfirm({
      title: t('pages.tasks.deleteConfirmTitle', 'Delete Task'),
      message: t('pages.tasks.deleteConfirmMessage', `Are you sure you want to delete "${(task as any)?.name}"? This action cannot be undone.`),
      warningText: t('pages.tasks.deleteWarning', '此Operation无法撤销'),
      okText: t('common.delete', 'Delete'),
      cancelText: t('common.cancel', 'Cancel'),
      onOk: async () => {
        try {
          const api = get_ipc_api();
          const resp = await api.deleteAgentTask(username, String((task as any).id));
          
          if (resp.success) {
            message.success(t('pages.tasks.deleteSuccess', 'Task deleted successfully'));
            // Call onDelete callback to close detail page
            if (onDelete) {
              onDelete();
            } else if (onSave) {
              // Fallback to onSave if no onDelete callback
              onSave();
            }
          } else {
            message.error(resp.error?.message || t('pages.tasks.deleteError', 'Failed to delete task'));
          }
        } catch (error) {
          console.error('[TaskDetail] Delete error:', error);
          message.error(t('pages.tasks.deleteError', 'Failed to delete task'));
        }
      },
    });
  };

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
          {t('pages.tasks.selectTask', '请Select一个任务')}
        </div>
      </FormContainer>
    );
  }

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

  return (
    <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <FormContainer ref={scrollContainerRef} style={{ flex: 1, overflowY: 'auto', paddingBottom: '20px' }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          disabled={!editMode && !isNew}
        >
          <Space direction="vertical" style={{ width: '100%' }} size={24}>
              <div style={{ marginBottom: '16px' }}>
                <StyledFormItem
                  name="name"
                  label={t('pages.tasks.name')}
                  rules={[{ required: true }]}
                  style={{ marginBottom: 0 }}
                  htmlFor="task-name"
                >
                  <Input
                    id="task-name"
                    placeholder={t('pages.tasks.namePlaceholder')}
                    size="large"
                    autoComplete="off"
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
                      size="large"
                      autoComplete="off"
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
                        options={(skills || []).map((s: any) => ({ 
                          key: s.id || s.name,  // Use unique ID as key
                          value: s.name, 
                          label: s.name 
                        }))}
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
                            {t('pages.tasks.repeatSettings', '重复Settings')}
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
                                  autoComplete="off"
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
                            {t('pages.tasks.timeSettings', 'TimeSettings')}
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
                                  autoComplete="off"
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
                    htmlFor="task-metadata"
                    tooltip={t('pages.tasks.metadata_tooltip') || 'Must be valid JSON format (e.g., {"key": "value"}) or plain text'}
                    validateTrigger={['onChange', 'onBlur']}
                    rules={[{
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
                              t('pages.tasks.invalidJson') || 
                              'Invalid JSON format. Please enter valid JSON (e.g., {"key": "value"})'
                            )
                          );
                        }
                      }
                    }]}
                  >
                    <Input.TextArea
                      id="task-metadata"
                      rows={8}
                      placeholder={JSON.stringify({ key: 'value' }, null, 2)}
                      autoComplete="off"
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
        </Form>
      </FormContainer>

      {/* Fixed Action Buttons - Outside FormContainer, won't scroll */}
      <div style={{
          flexShrink: 0,
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '12px',
          padding: '16px 24px',
          background: 'transparent',
          borderTop: '1px solid rgba(255, 255, 255, 0.05)'
        }}>
          {/* Edit/新建模式：DisplaySave和CancelButton */}
          {(editMode || isNew) && (
            <>
              <Button
                type="primary"
                onClick={() => form.submit()}
                loading={saving}
                disabled={saving}
                icon={<SaveOutlined />}
                size="large"
                style={primaryButtonStyle}
              >
                {isNew ? t('common.create') : t('common.save')}
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

          {/* 查看模式：DisplayEdit和DeleteButton */}
          {!editMode && !isNew && task && (
            <>
              <Button
                type="primary"
                onClick={handleEdit}
                icon={<EditOutlined />}
                size="large"
                style={primaryButtonStyle}
              >
                {t('common.edit')}
              </Button>
              <Button
                danger
                onClick={handleDelete}
                icon={<DeleteOutlined />}
                size="large"
                style={buttonStyle}
              >
                {t('common.delete', 'Delete')}
              </Button>
            </>
          )}
        </div>
      </div>
    );
  };
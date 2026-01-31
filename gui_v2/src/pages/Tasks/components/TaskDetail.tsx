import {
  EditOutlined,
  SaveOutlined,
  CloseOutlined,
  DeleteOutlined,
  LockOutlined,
  PlusOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import { Button, Space, Form, Input, Row, Col, Select, DatePicker, App, Checkbox } from 'antd';
import { useTranslation } from 'react-i18next';
import React, { useRef } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Task } from '../types';
import dayjs from 'dayjs';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useSkillStore } from '@/stores/domain/skillStore';
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

// Generate a unique task ID
const generateTaskId = () => `task_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`; 

const DEFAULT_TASK = {
  id: '',
  name: '',
  description: '',
  cloud_based: false,
  priority: 'none',
  trigger: 'schedule',
  skills: [] as string[],  // Support multiple skills
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
  onSave?: (taskId?: string) => void; // ä¿®æ”¹ï¼šæ”¯æŒä¼ é€’æ–°åˆ›å»ºçš„task ID
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
  skills?: string[];  // Support multiple skills
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

  // Extract only id and name to avoid circular reference in deep comparison
  const skillsSimplified = React.useMemo(() => {
    const result = (skills || []).map((s: any) => ({ id: s.id, name: s.name }));
    console.log('[TaskDetail] skillsSimplified updated:', result.length, 'skills');
    return result;
  }, [skills]);  // Depend on skills to ensure updates when store changes

  // Memoize skill options to avoid circular reference warnings
  const skillOptions = React.useMemo(() => {
    console.log('[TaskDetail] Building skillOptions from', skillsSimplified.length, 'skills');
    return skillsSimplified.map((s) => ({ 
      key: s.id || s.name,
      value: s.name, 
      label: s.name 
    }));
  }, [skillsSimplified]);

  // Fetch skills on mount - always fetch to ensure we have the latest
  React.useEffect(() => {
    const api = get_ipc_api();
    const ensureSkills = async () => {
      try {
        let uname = username;
        if (!uname) {
          const loginInfo = await api.getLastLoginInfo<{ last_login: { username: string } }>();
          if (loginInfo?.success) uname = loginInfo.data?.last_login?.username || '';
        }
        if (uname) {
          console.log('[TaskDetail] Fetching skills for user:', uname);
          const res = await api.getAgentSkills<any[]>(uname, []);
          // API returns skills array directly in res.data (not res.data.skills)
          // due to resultPath: 'getAllMine.skills' in api config
          const skillsData = res?.data?.skills || res?.data;
          if (res?.success && Array.isArray(skillsData) && skillsData.length > 0) {
            console.log('[TaskDetail] Loaded skills:', skillsData.length);
            setSkills(skillsData as any);
          } else {
            console.warn('[TaskDetail] No skills returned or error:', res);
          }
        }
      } catch (e) {
        console.error('[TaskDetail] Error fetching skills:', e);
      }
    };
    ensureSkills();
  }, [username, setSkills]);

  React.useEffect(() => {
    if (task) {
      // Skill comes directly from task (loaded from relationship table)
      const taskSkill = (task as any).skill || '';
      const taskSkills = (task as any).skills || (taskSkill ? [taskSkill] : []);
      
      // Metadata is clean (no skill stored in it anymore)
      const metadata = (task as any).metadata || {};
      const metaStr = Object.keys(metadata).length > 0 ? JSON.stringify(metadata, null, 2) : '';

      // ä½¿ç”¨ name Fieldï¼ŒIfä¸å­˜åœ¨åˆ™ä½¿ç”¨ skill Fieldä½œä¸ºåŽå¤‡
      const taskName = (task as any).name || taskSkill || '';

      // ä½¿ç”¨ description Fieldï¼ŒIfä¸å­˜åœ¨åˆ™ä½¿ç”¨ metadata ä¸­çš„Descriptionä½œä¸ºåŽå¤‡
      const taskDescription = (task as any).description
        || (task as any).metadata?.description
        || '';

      // ç¡®ä¿AllFieldéƒ½æ­£ç¡®Settings
      // For new tasks, auto-generate ID and set owner
      const taskId = isNew ? generateTaskId() : (task as any).id;
      const taskOwner = isNew ? username : ((task as any).owner || username);

      const formValues = {
        ...(task as any),
        id: taskId,
        owner: taskOwner,
        name: taskName,
        description: taskDescription,
        skills: taskSkills,  // Multiple skills support
        metadata_text: metaStr,
      };

      form.setFieldsValue(formValues);
    } else {
      form.resetFields();
      setEditMode(false);
    }
  }, [task, form, isNew, username]);

  const handleCancel = () => {
    if (isNew) {
      // æ–°å»ºæ¨¡å¼ï¼šæ¸…ç©ºFormå¹¶Notificationçˆ¶ComponentCloseé¢æ¿
      form.resetFields();
      if (onCancel) {
        onCancel();
      }
    } else {
      // Editæ¨¡å¼ï¼šRestoreåŽŸå§‹Dataå¹¶é€€å‡ºEditæ¨¡å¼ï¼ˆä¸Closeé¢æ¿ï¼‰
      if (task) {
        const metaStr = (task as any).metadata ? JSON.stringify((task as any).metadata, null, 2) : '';
        const taskName = (task as any).name || (task as any).skill || '';
        const taskDescription = (task as any).description
          || (task as any).metadata?.description
          || '';
        
        const formValues = {
          ...(task as any),
          id: (task as any).id,
          owner: (task as any).owner || username,
          name: taskName,
          description: taskDescription,
          metadata_text: metaStr,
        };
        
        form.setFieldsValue(formValues);
      }
      setEditMode(false);
      // Editæ¨¡å¼ä¸‹ä¸è°ƒç”¨ onCancelï¼Œä¿æŒé¢æ¿Open
    }
  };

  // Check if task is code-generated (read-only)
  const isCodeGenerated = React.useMemo(() => {
    if (!task) return false;
    const t = task as any;
    // Check source field first
    if (t.source === 'code') return true;
    // Check ID prefix as fallback
    if (t.id && typeof t.id === 'string' && t.id.startsWith('code-task-')) return true;
    return false;
  }, [task]);

  const handleEdit = () => {
    if (isCodeGenerated) {
        message.warning(t('pages.tasks.readOnlyCodeGenerated') || 'This task is code-generated and read-only');
    }
    setEditMode(true);
  };


  const handleSave = async () => {
    try {
      const values = await form.validateFields();

      // Get skills array from form values and filter out empty values
      const skillNames = ((values as any).skills || []).filter((s: string) => s && s.trim());
      // Find skill objects by name (use simplified skills to avoid circular refs)
      const skillObjs = skillNames.map((name: string) => skillsSimplified.find(s => s.name === name)).filter(Boolean);

      const payload: any = {
        id: (values as any).id,
        name: (values as any).name || t('pages.tasks.newTaskName', 'New Task'),
        owner: (values as any).owner || username,
        description: (values as any).description || '',
        cloud_based: !!(values as any).cloud_based,
        latest_version: (values as any).latest_version || '1.0.0',
        priority: (values as any).priority || 'medium',
        trigger: (values as any).trigger || 'manual',
        skills: skillNames,  // Pass skills array
        skill_ids: skillObjs.map((s: any) => s?.id).filter(Boolean),  // Pass skill IDs for backend
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

      if (!payload || typeof payload !== 'object' || !payload.name) {
        message.error(t('common.createFailed') + ': Invalid task data.');
        return;
      }

      setSaving(true);
      const api = get_ipc_api();
      const response = isNew
        ? await api.newAgentTask(username, payload)
        : await api.saveAgentTask(username, payload);

      if (response.success) {
        message.success(t(isNew ? 'common.createSuccess' : 'common.saveSuccess'));
        setEditMode(false);
        // ä¼ é€’æ–°åˆ›å»ºçš„task IDç»™çˆ¶ç»„ä»¶
        if (onSave) {
          // API返回的是数组格式 [{id, success, error}]，需要从第一个元素获取ID
          const responseData = (response as any).data;
          let newTaskId: string | undefined;
          if (isNew) {
            // Handle array response format from addAgentTasks: [{id, success, error}]
            if (Array.isArray(responseData) && responseData.length > 0) {
              newTaskId = responseData[0]?.id;
            } else if (responseData?.task_id) {
              newTaskId = responseData.task_id;
            } else if (responseData?.id) {
              newTaskId = responseData.id;
            } else if (responseData?.task?.id) {
              newTaskId = responseData.task.id;
            } else {
              newTaskId = payload.id;
            }
          }
          console.log('[TaskDetail] ä¿å­˜æˆåŠŸï¼ŒTask ID:', newTaskId);
          console.log('[TaskDetail] APIå"åº"æ•°æ®:', responseData);
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
      warningText: t('pages.tasks.deleteWarning', 'æ­¤Operationæ— æ³•æ’¤é”€'),
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
          {t('pages.tasks.selectTask', 'è¯·Selectä¸€ä¸ªä»»åŠ¡')}
        </div>
      </FormContainer>
    );
  }

  // ä½¿ç”¨ useEffectOnActive åœ¨ComponentActiveæ—¶RestoreScrollPosition
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
                  <StyledFormItem label={t('pages.tasks.taskId', 'ä»»åŠ¡ ID')} name="id" htmlFor="task-id">
                    <Input id="task-id" readOnly aria-label={t('pages.tasks.taskId', 'ä»»åŠ¡ ID')} />
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
                <Col span={12}>
                  <StyledFormItem
                    label={t('pages.tasks.cloudRun', 'Cloud Run')}
                    name="cloud_based"
                    valuePropName="checked"
                  >
                    <Checkbox>{t('pages.tasks.cloudRun', 'Cloud Run')}</Checkbox>
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
                  <Form.List name="skills">
                    {(fields, { add, remove }) => (
                      <>
                        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
                          <span style={{ fontWeight: 500, color: 'rgba(255, 255, 255, 0.85)' }}>
                            {t('pages.tasks.skills', 'Associated Skills')}
                          </span>
                          {(editMode || isNew) && (
                            <Button
                              type="link"
                              onClick={() => add('')}
                              icon={<PlusOutlined />}
                              style={{ marginLeft: 8 }}
                            >
                              {t('common.add', 'Add')}
                            </Button>
                          )}
                        </div>
                        {fields.length === 0 && (
                          <div style={{ color: 'rgba(255, 255, 255, 0.45)', marginBottom: 16 }}>
                            {t('pages.tasks.noSkillsAssociated', 'No skills associated. Click Add to associate a skill.')}
                          </div>
                        )}
                        {fields.map(({ key, name, ...restField }) => (
                          <div key={key} style={{ display: 'flex', alignItems: 'center', marginBottom: 8, gap: 8 }}>
                            <Form.Item
                              {...restField}
                              name={name}
                              style={{ flex: 1, marginBottom: 0 }}
                            >
                              {editMode || isNew ? (
                                <Select
                                  showSearch
                                  allowClear
                                  size="large"
                                  placeholder={t('pages.tasks.selectSkill', 'Select a skill')}
                                  options={skillOptions}
                                  filterOption={(input, option) =>
                                    (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                                  }
                                />
                              ) : (
                                <Input readOnly size="large" />
                              )}
                            </Form.Item>
                            {(editMode || isNew) && fields.length > 0 && (
                              <MinusCircleOutlined
                                onClick={() => remove(name)}
                                style={{ color: '#ff4d4f', fontSize: 18, cursor: 'pointer' }}
                              />
                            )}
                          </div>
                        ))}
                      </>
                    )}
                  </Form.List>
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
                            {t('pages.tasks.repeatSettings', 'é‡å¤Settings')}
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
                        // Allowç©ºValue
                        if (!value || value.trim() === '') {
                          return Promise.resolve();
                        }
                        
                        // Mustæ˜¯æœ‰æ•ˆçš„ JSON æ ¼å¼
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
          {/* Edit/æ–°å»ºæ¨¡å¼ï¼šDisplaySaveå’ŒCancelButton */}
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

          {/* æŸ¥çœ‹æ¨¡å¼ï¼šDisplayEditå’ŒDeleteButton */}
          {!editMode && !isNew && task && (
            <>
              {isCodeGenerated ? (
                 <Button
                   icon={<LockOutlined />}
                   disabled
                   size="large"
                   style={{ 
                     ...buttonStyle, 
                     color: 'rgba(255, 255, 255, 0.6)', 
                     borderColor: 'rgba(255, 255, 255, 0.2)',
                     background: 'rgba(255, 255, 255, 0.05)',
                     cursor: 'not-allowed'
                   }}
                 >
                   {t('pages.tasks.readOnlyCodeGenerated') || 'Read-only: Code Generated'}
                 </Button>
              ) : (
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
            </>
          )}
        </div>
      </div>
    );
  };

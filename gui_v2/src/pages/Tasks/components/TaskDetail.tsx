import {
  EditOutlined,
  SaveOutlined,
  CloseOutlined,
  DeleteOutlined,
  LockOutlined,
  PlusOutlined,
  MinusCircleOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  HistoryOutlined,
  SettingOutlined,
  InfoCircleOutlined,
  LeftOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { Button, Space, Form, Input, Row, Col, Select, DatePicker, App, Checkbox, Segmented, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import React, { useRef, useState, useEffect } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Task } from '../types';
import dayjs from 'dayjs';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useSkillStore } from '@/stores/domain/skillStore';
import { useTaskStore } from '@/stores/domain/taskStore';
import { useDeleteConfirm } from '@/components/Common/DeleteConfirmModal';
import {
  StyledFormItem,
  StyledCard,
  FormContainer,
  buttonStyle,
  primaryButtonStyle
} from '@/components/Common/StyledForm';
import styled from '@emotion/styled';
import { keyframes } from '@emotion/react';

const pulseAnimation = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
`;

// Generate a unique task ID
const generateTaskId = () => `task_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;

const DEFAULT_TASK = {
  id: '',
  name: '',
  description: '',
  task_type: 'local',
  priority: 'none',
  trigger: ['schedule'] as string[],
  skills: [] as string[],
  schedule: {
    repeat_type: 'none',
    repeat_number: 1,
    repeat_unit: 'by hours',
    start_date_time: dayjs(),
    end_date_time: undefined as any,
    time_out: 3600,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  },
  metadata: {},
};

const TASK_TYPE_OPTIONS = ['local', 'cloud', 'hybrid_cloud'];

const TIMEZONE_OPTIONS = [
  'UTC',
  'America/New_York',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Australia/Sydney',
];

const PRIORITY_OPTIONS = ['none', 'low', 'medium', 'high', 'urgent'];
const TRIGGER_OPTIONS = [
  'schedule',
  'message',
  'auto',
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

// Styled Components
const DetailContainer = styled.div`
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;

  /* Compact form overrides — only inside the task detail drawer */
  .ant-form-item {
    margin-bottom: 8px !important;
  }
  .ant-form-item-label {
    padding-bottom: 4px !important;
  }
  .ant-form-item-label > label {
    font-size: 12px !important;
  }

  .ant-input-affix-wrapper,
  .ant-input:not(.ant-input-affix-wrapper .ant-input):not(textarea),
  .ant-input-number,
  .ant-input-number-input,
  .ant-picker,
  .ant-input-password {
    min-height: 32px !important;
  }
  .ant-input-affix-wrapper {
    min-height: 32px !important;
  }
  .ant-select-single .ant-select-selector {
    height: 32px !important;
  }
  .ant-select-single .ant-select-selection-item,
  .ant-select-single .ant-select-selection-placeholder {
    line-height: 30px !important;
  }
  .ant-select-multiple .ant-select-selector {
    min-height: 32px !important;
    height: 32px !important;
  }
  .ant-select-multiple .ant-select-selection-item,
  .ant-select-multiple .ant-select-selection-placeholder {
    height: 20px !important;
    line-height: 18px !important;
  }
  .ant-input-textarea textarea.ant-input {
    padding: 8px 10px !important;
  }
`;

const StatusBarRow = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
`;

const StatusBarSpacer = styled.div`
  flex: 1;
`;

const StatusBadge = styled.div<{ $status: string }>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  background: ${props => {
    switch (props.$status.toLowerCase()) {
      case 'running':
      case 'working':
        return 'rgba(24, 144, 255, 0.15)';
      case 'ready':
      case 'completed':
        return 'rgba(82, 196, 26, 0.15)';
      case 'failed':
      case 'error':
        return 'rgba(255, 77, 79, 0.15)';
      case 'pending':
      case 'submitted':
        return 'rgba(114, 46, 209, 0.15)';
      default:
        return 'rgba(140, 140, 140, 0.15)';
    }
  }};
  border: 1px solid ${props => {
    switch (props.$status.toLowerCase()) {
      case 'running':
      case 'working':
        return 'rgba(24, 144, 255, 0.3)';
      case 'ready':
      case 'completed':
        return 'rgba(82, 196, 26, 0.3)';
      case 'failed':
      case 'error':
        return 'rgba(255, 77, 79, 0.3)';
      case 'pending':
      case 'submitted':
        return 'rgba(114, 46, 209, 0.3)';
      default:
        return 'rgba(140, 140, 140, 0.3)';
    }
  }};
`;

const StatusDot = styled.div<{ $status: string }>`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${props => {
    switch (props.$status.toLowerCase()) {
      case 'running':
      case 'working':
        return '#1890FF';
      case 'ready':
      case 'completed':
        return '#52C41A';
      case 'failed':
      case 'error':
        return '#FF4D4F';
      case 'pending':
      case 'submitted':
        return '#722ed1';
      default:
        return '#8C8C8C';
    }
  }};
  ${props => (props.$status.toLowerCase() === 'running' || props.$status.toLowerCase() === 'working') && `
    animation: ${pulseAnimation} 2s ease-in-out infinite;
  `}
`;

const TabSection = styled.div`
  padding: 0 12px;
  margin-bottom: 6px;
`;

const StatsGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 12px;
  margin-bottom: 6px;
`;

const StatItem = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  transition: all 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.05);
  }
`;

const StatLabel = styled.span`
  font-size: 11px;
  color: var(--text-secondary);
`;

const StatValue = styled.span<{ $color?: string }>`
  font-size: 12px;
  line-height: 1.2;
  font-weight: 600;
  color: ${props => props.$color || 'var(--text-primary)'};
`;

const InfoItem = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);

  .anticon {
    color: var(--primary-color);
  }
`;

interface TaskDetailProps {
  task: Task | null | object;
  isNew?: boolean;
  onSave?: (taskId?: string) => void;
  onCancel?: () => void;
  onDelete?: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}

type ExtendedTask = Task & {
  ataskid?: string | number;
  name?: string;
  owner?: string;
  description?: string;
  latest_version?: string;
  metadata_text?: string;
  skills?: string[];
};

// Skill Select
const SkillSelect = ({
  value,
  onChange,
  skillOptions,
  placeholder,
}: {
  value?: string;
  onChange?: (v: string | undefined) => void;
  skillOptions: { value: any; label: string }[];
  placeholder: string;
}) => {
  const knownIds = React.useMemo(
    () => new Set(skillOptions.map((o) => String(o.value))),
    [skillOptions],
  );
  const selectVal = value && !knownIds.has(String(value)) ? undefined : value;
  return (
    <Select
      showSearch
      allowClear
      placeholder={placeholder}
      options={skillOptions}
      value={selectVal}
      onChange={onChange}
      filterOption={(input, option) =>
        (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
      }
    />
  );
};

// Helper to safely convert to dayjs object
const toDayjs = (date: string | Date | null | undefined) => {
  if (!date) return undefined;
  const customFormat = "YYYY-MM-DD HH:mm:ss:SSS";
  let d = dayjs(date, customFormat, true);
  if (!d.isValid()) {
    d = dayjs(date);
  }
  return d.isValid() ? d : undefined;
};

export const TaskDetail: React.FC<TaskDetailProps> = ({ task: rawTask = {} as any, isNew = false, onSave, onCancel, onDelete, onPrev, onNext, hasPrev = false, hasNext = false }) => {
  const { message } = App.useApp();
  const showDeleteConfirm = useDeleteConfirm();

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);

  const task = React.useMemo(() => {
    if (!rawTask || Object.keys(rawTask).length === 0) {
      return isNew ? DEFAULT_TASK : null;
    }
    const raw = rawTask as any;
    const processedSchedule = {
      repeat_type: raw.schedule?.repeat_type || 'none',
      repeat_number: raw.schedule?.repeat_number || 1,
      repeat_unit: raw.schedule?.repeat_unit || 'by hours',
      start_date_time: toDayjs(raw.schedule?.start_date_time),
      end_date_time: toDayjs(raw.schedule?.end_date_time),
      time_out: raw.schedule?.time_out || 3600,
    };
    return {
      id: raw.id,
      name: raw.name,
      description: raw.description,
      owner: raw.owner,
      agent_id: raw.agent_id || raw.agentId,
      latest_version: raw.latest_version,
      priority: raw.priority || 'none',
      trigger: raw.trigger,
      skill_ids: raw.skill_ids,
      skill_names: raw.skill_names,
      cloud_based: raw.cloud_based,
      status: raw.status,
      state: raw.state,
      metadata: raw.metadata,
      schedule: processedSchedule,
    };
  }, [rawTask, isNew]);

  const { t } = useTranslation();
  const username = useUserStore((s) => s.username) || '';
  const [form] = Form.useForm<ExtendedTask>();
  const [editMode, setEditMode] = useState(isNew);
  const [saving, setSaving] = useState(false);
  const [refreshingStatus, setRefreshingStatus] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [latestStatus, setLatestStatus] = useState<string>('');
  const [_currentTrigger, setCurrentTrigger] = useState<string[]>(['schedule']);
  const [currentTaskType, setCurrentTaskType] = useState<string>('local');
  const [activeTab, setActiveTab] = useState<string>('basic');

  const skills = useSkillStore((s) => s.items);
  const setSkills = useSkillStore((s) => s.setItems);
  const allTasks = useTaskStore((s) => s.items);

  const localTaskOptions = React.useMemo(() => {
    const currentId = task ? (task as any).id : '';
    return (allTasks || [])
      .filter((t: any) => {
        const tt = t.task_type || t.metadata?.task_type || 'local';
        return tt === 'local' && t.id !== currentId;
      })
      .map((t: any) => ({ value: t.id, label: t.name || t.id }));
  }, [allTasks, task]);

  const skillsKey = React.useMemo(() => (skills || []).length, [skills?.length]);

  const skillsSimplified = React.useMemo(() => {
    return (skills || []).map((s: any) => ({ id: s.id, name: s.name }));
  }, [skillsKey]);

  const skillOptions = React.useMemo(() => {
    return skillsSimplified.map((s) => ({
      key: s.id,
      value: s.id,
      label: s.name,
    }));
  }, [skillsSimplified]);

  // Fetch skills on mount
  React.useEffect(() => {
    const api = get_ipc_api();
    const ensureSkills = async () => {
      try {
        let uname = username;
        if (!uname) {
          const loginInfo = await api.getLastLoginInfo();
          uname = (loginInfo?.success && (loginInfo.data as any)?.last_login?.username) || '';
        }
        if (uname) {
          const res = await api.getAgentSkills(uname, []);
          const skillsData = Array.isArray(res?.data) ? res.data : ((res?.data as any)?.skills || []);
          if (res?.success && Array.isArray(skillsData) && skillsData.length > 0) {
            const sanitizedSkills = skillsData.map((skill: any) => ({
              id: skill.id,
              name: skill.name,
              description: skill.description,
              owner: skill.owner,
              version: skill.version,
              level: skill.level,
              path: skill.path,
              source: skill.source,
              tags: skill.tags,
            }));
            setSkills(sanitizedSkills as any);
          }
        }
      } catch (e) {
        // Silent fail
      }
    };
    ensureSkills();
  }, [username, setSkills]);

  // Extract a clean string status from any value shape (string, object, nested)
  const extractStatus = (val: any): string => {
    if (!val) return '';
    if (typeof val === 'string') return val;
    if (typeof val === 'number') return String(val);
    if (typeof val === 'object') {
      // Try common status field names recursively
      const found = extractField(val, ['state', 'status', 'top', 'value', 'label']);
      if (found) return extractStatus(found);
    }
    return String(val);
  };

  // Deep-read a field from an object, returning its value or null
  const extractField = (obj: any, keys: string[]): any => {
    for (const k of keys) {
      if (obj && typeof obj === 'object' && k in obj) {
        return obj[k];
      }
    }
    return null;
  };

  const taskStatus = React.useMemo(() => {
    if (!task) return '';
    const t = task as any;
    const statusValue = t.status ?? t.state?.top ?? '';
    return extractStatus(statusValue);
  }, [task]);

  // Keep latestStatus reactive with the task
  React.useEffect(() => {
    setLatestStatus(taskStatus);
  }, [taskStatus]);

  // Initialize form
  useEffect(() => {
    if (task) {
      const rawSkillNames: string[] = (task as any).skill_names || [];
      const rawSkillIds: string[] = (task as any).skill_ids || [];
      const sourceLen = Math.max(rawSkillIds.length, rawSkillNames.length);
      const taskSkills: string[] = Array.from({ length: sourceLen }, (_, i) => {
        const rawId = String(rawSkillIds[i] || '');
        const rawName = String(rawSkillNames[i] || '');
        if (rawId) {
          const byId = skillsSimplified.find((sk) => String(sk.id) === rawId);
          if (byId) return String(byId.id);
        }
        if (rawName) {
          const byName = skillsSimplified.find((sk) => sk.name === rawName);
          if (byName) return String(byName.id);
          const byNameAsId = skillsSimplified.find((sk) => String(sk.id) === rawName);
          if (byNameAsId) return String(byNameAsId.id);
        }
        return rawId || rawName;
      });

      const metadata = (task as any).metadata || {};
      const metaStr = Object.keys(metadata).length > 0 ? JSON.stringify(metadata, null, 2) : '';

      const taskName = (task as any).name || '';
      const taskDescription = (task as any).description || (task as any).metadata?.description || '';
      const taskId = isNew ? generateTaskId() : (task as any).id;
      const taskOwner = isNew ? username : ((task as any).owner || username);
      const taskAgentId = (task as any).agent_id || (task as any).agentId || '';

      const t = task as any;
      const rawTrigger = t.trigger;
      const taskTrigger: string[] = Array.isArray(rawTrigger)
        ? rawTrigger
        : (typeof rawTrigger === 'string' && rawTrigger
            ? rawTrigger.split(',').map((s: string) => s.trim()).filter(Boolean)
            : ['schedule']);

      const formValues = {
        id: taskId,
        owner: taskOwner,
        name: taskName,
        description: taskDescription,
        task_type: (task as any).task_type || metadata?.task_type || 'local',
        companion_local_task: metadata?.companion_local_task || undefined,
        light_weight: !!metadata?.light_weight,
        skills: taskSkills,
        metadata_text: metaStr,
        agent_id: taskAgentId,
        latest_version: t.latest_version || '1.0.0',
        priority: t.priority || 'none',
        trigger: taskTrigger,
        // Shared-skill per-task variables (metadata.task_vars) — rendered as
        // form fields from the selected skills' need_inputs declarations.
        task_vars: metadata?.task_vars || {},
        schedule: {
          repeat_type: t.schedule?.repeat_type || 'none',
          repeat_number: t.schedule?.repeat_number || 1,
          repeat_unit: t.schedule?.repeat_unit || 'by hours',
          start_date_time: t.schedule?.start_date_time,
          end_date_time: t.schedule?.end_date_time,
          time_out: t.schedule?.time_out || 3600,
        },
      };

      form.setFieldsValue(formValues);
      const taskType = (task as any).task_type || metadata?.task_type || 'local';
      setCurrentTaskType(taskType);
      setCurrentTrigger(taskTrigger);
    } else {
      form.resetFields();
      setEditMode(false);
    }
  }, [task, isNew, username, skillsSimplified, form]);

  // Re-normalize skill IDs when skills store loads
  useEffect(() => {
    if (skillsSimplified.length === 0) return;
    const current: string[] = form.getFieldValue('skills') || [];
    if (current.length === 0) return;
    const resolved = current.map((s) => {
      const byId = skillsSimplified.find((sk) => String(sk.id) === String(s));
      if (byId) return String(byId.id);
      const byName = skillsSimplified.find((sk) => sk.name === s);
      if (byName) return String(byName.id);
      return s;
    }).filter(Boolean);
    if (resolved.length !== current.length || resolved.some((v, i) => v !== current[i])) {
      form.setFieldsValue({ skills: resolved });
    }
  }, [skillsKey]);

  const handleCancel = () => {
    if (isNew) {
      form.resetFields();
      if (onCancel) onCancel();
    } else {
      setEditMode(false);
    }
  };

  const isCodeGenerated = React.useMemo(() => {
    if (!task) return false;
    const t = task as any;
    if (t.source === 'code') return true;
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
      const skillIds = ((values as any).skills || []).map((s: string) => String(s || '').trim()).filter(Boolean);

      const payload: any = {
        id: (values as any).id,
        name: (values as any).name || t('pages.tasks.newTaskName', 'New Task'),
        owner: (values as any).owner || username,
        description: (values as any).description || '',
        task_type: (values as any).task_type || 'local',
        latest_version: (values as any).latest_version || '1.0.0',
        priority: (values as any).priority || 'medium',
        trigger: ((values as any).trigger || ['auto']).join(','),
        skill_ids: skillIds,
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
          timezone: (values as any).schedule?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
        },
        metadata: (() => {
          const baseMeta = (values as any).metadata_text ? JSON.parse((values as any).metadata_text) : {};
          // Merge form-entered task variables over any task_vars already in
          // the raw metadata JSON (form fields win; empty values dropped).
          const formVars = (values as any).task_vars || {};
          const cleanedVars = Object.fromEntries(
            Object.entries(formVars).filter(([, v]) => v !== undefined && v !== null && String(v).trim() !== '')
          );
          const mergedVars = { ...(baseMeta.task_vars || {}), ...cleanedVars };
          return {
            ...baseMeta,
            ...(Object.keys(mergedVars).length > 0 ? { task_vars: mergedVars } : {}),
            task_type: (values as any).task_type || 'local',
            ...((values as any).task_type === 'hybrid_cloud' && (values as any).companion_local_task
              ? { companion_local_task: (values as any).companion_local_task }
              : {}),
            ...((values as any).task_type === 'cloud'
              ? { light_weight: !!(values as any).light_weight }
              : {}),
          };
        })(),
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

      const syncTaskSkillRels = async (taskId: string, desiredSkillIds: string[]) => {
        const safeTaskId = String(taskId || '').trim();
        if (!safeTaskId) return;

        const desired = Array.from(new Set((desiredSkillIds || []).map((s) => String(s || '').trim()).filter(Boolean)));
        const q = await api.queryAgentTaskSkillRels({ task_id: safeTaskId, limit: 500, offset: 0 });
        if (!q.success) return;

        const existing = Array.isArray(q.data) ? q.data : [];
        const existingBySkill = new Map<string, any>();
        for (const rel of existing) {
          const sid = String(rel?.skill_id || '').trim();
          if (sid) existingBySkill.set(sid, rel);
        }

        const toAdd = desired.filter((sid) => !existingBySkill.has(sid)).map((sid) => ({
          task_id: safeTaskId,
          skill_id: sid,
        }));

        const desiredSet = new Set(desired);
        const toRemove = existing
          .filter((rel: any) => {
            const sid = String(rel?.skill_id || '').trim();
            return sid && !desiredSet.has(sid);
          })
          .map((rel: any) => ({
            task_id: safeTaskId,
            skill_id: String(rel?.skill_id || '').trim(),
          }))
          .filter((x: any) => x.skill_id);

        if (toAdd.length) await api.addAgentTaskSkillRels(toAdd);
        if (toRemove.length) await api.removeAgentTaskSkillRels(toRemove);
      };

      if (response.success) {
        message.success(t(isNew ? 'common.createSuccess' : 'common.saveSuccess'));
        setEditMode(false);
        if (onSave) {
          const responseData = (response as any).data;
          let newTaskId: string | undefined;
          if (isNew) {
            if (Array.isArray(responseData) && responseData.length > 0) {
              newTaskId = responseData[0]?.id;
            } else if (responseData?.task_id) {
              newTaskId = responseData.task_id;
            } else if (responseData?.id) {
              newTaskId = responseData.id;
            } else {
              newTaskId = payload.id;
            }
          } else {
            if (responseData?.task_id) newTaskId = responseData.task_id;
            else if (responseData?.id) newTaskId = responseData.id;
            else newTaskId = payload.id;
          }
          try {
            const finalTaskId = String(newTaskId || payload.id || '').trim();
            const desiredSkillIds = (payload.skill_ids || []).map((x: any) => String(x || '').trim()).filter(Boolean);
            await syncTaskSkillRels(finalTaskId, desiredSkillIds);
          } catch (e) {
            console.warn('[TaskDetail] syncTaskSkillRels error:', e);
          }
          onSave(newTaskId);
        }
      } else {
        message.error(response.error?.message || t(isNew ? 'common.createFailed' : 'common.saveFailed'));
      }
    } catch (error) {
      console.error(`Error ${isNew ? 'creating' : 'saving'} task:`, error);
      message.error(t(isNew ? 'common.createFailed' : 'common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshStatus = async () => {
    if (!task || isNew) return;
    const taskId = String((task as any).id || '');
    if (!taskId) return;

    setRefreshingStatus(true);
    try {
      const api = get_ipc_api();
      const response = await api.refreshAgentTaskStatus(username, taskId);
      if (response.success) {
        const refreshed = (response as any).data?.task || (response as any).data;
        let nextStatus = refreshed?.status ?? refreshed?.state?.top ?? taskStatus;
        if (nextStatus && typeof nextStatus === 'object') {
          nextStatus = nextStatus.state || nextStatus.status || String(nextStatus);
        }
        if (nextStatus) setLatestStatus(String(nextStatus));
        message.success(t('common.refresh_success', 'Refresh success'));
      } else {
        message.error(response.error?.message || t('common.refresh_failed', 'Refresh failed'));
      }
    } catch (error) {
      console.error('[TaskDetail] Refresh status error:', error);
      message.error(t('common.refresh_failed', 'Refresh failed'));
    } finally {
      setRefreshingStatus(false);
    }
  };

  const handleLaunchTask = async () => {
    if (!task || isNew) return;
    const taskId = String((task as any).id || '');
    if (!taskId) return;

    setLaunching(true);
    try {
      const api = get_ipc_api();
      const response = await api.runAgentTask(username, {
        task_id: taskId,
        task_type: (task as any).task_type || 'local',
        cloud_based: ((task as any).task_type || 'local') !== 'local',
        skill_id: (task as any).skill_id,
        skill: (task as any).skill,
      });
      if (response.success) {
        message.success(t('pages.tasks.launchSuccess', 'Task launched'));
      } else {
        message.error(response.error?.message || t('pages.tasks.launchFailed', 'Failed to launch task'));
      }
    } catch (error) {
      console.error('[TaskDetail] Launch task error:', error);
      message.error(t('pages.tasks.launchFailed', 'Failed to launch task'));
    } finally {
      setLaunching(false);
    }
  };

  const handleDelete = () => {
    if (!task || isNew) return;

    showDeleteConfirm({
      title: t('pages.tasks.deleteConfirmTitle', 'Delete Task'),
      message: t('pages.tasks.deleteConfirmMessage', `Are you sure you want to delete "${(task as any)?.name}"? This action cannot be undone.`),
      warningText: t('pages.tasks.deleteWarning', 'This operation cannot be undone'),
      okText: t('common.delete', 'Delete'),
      cancelText: t('common.cancel', 'Cancel'),
      onOk: async () => {
        try {
          const api = get_ipc_api();

          try {
            const taskId = String((task as any).id || '').trim();
            if (taskId) {
              const q = await api.queryAgentTaskSkillRels({ task_id: taskId, limit: 500, offset: 0 });
              if (q.success && Array.isArray(q.data) && q.data.length) {
                const relIds = q.data
                  .map((r: any) => ({ id: String(r?.id || '').trim() }))
                  .filter((x: any) => x.id);
                if (relIds.length) await api.removeAgentTaskSkillRels(relIds);
              }
            }
          } catch (e) {
            console.warn('[TaskDetail] cleanup AgentTaskSkillRels before delete failed:', e);
          }

          const resp = await api.deleteAgentTask(username, String((task as any).id));

          if (resp.success) {
            message.success(t('pages.tasks.deleteSuccess', 'Task deleted successfully'));
            if (onDelete) onDelete();
            else if (onSave) onSave();
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

  // Empty state
  if (!task && !isNew) {
    return (
      <FormContainer>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          color: 'var(--text-muted)',
          gap: 12,
        }}>
          <InfoCircleOutlined style={{ fontSize: 48, opacity: 0.5 }} />
          <div style={{ fontSize: 14 }}>{t('pages.tasks.selectTask', '请选择一个任务')}</div>
        </div>
      </FormContainer>
    );
  }

  // Scroll position management
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

  // Calculate task statistics
  const taskStats = {
    runCount: (task as any)?.metadata?.run_count || 0,
    successCount: (task as any)?.metadata?.success_count || 0,
    failCount: (task as any)?.metadata?.fail_count || 0,
    lastRun: (task as any)?.last_run_datetime || null,
  };

  return (
    <DetailContainer>
      {/* Statistics Summary */}
      <StatsGrid>
        <StatItem>
          <StatLabel>{t('pages.tasks.stats.totalRuns', '运行次数')}</StatLabel>
          <StatValue>{taskStats.runCount}</StatValue>
        </StatItem>
        <StatItem>
          <StatLabel>{t('pages.tasks.stats.successRuns', '成功次数')}</StatLabel>
          <StatValue $color="#52c41a">{taskStats.successCount}</StatValue>
        </StatItem>
        <StatItem>
          <StatLabel>{t('pages.tasks.stats.failedRuns', '失败次数')}</StatLabel>
          <StatValue $color="#ff4d4f">{taskStats.failCount}</StatValue>
        </StatItem>
        <StatItem>
          <StatLabel>{t('pages.tasks.stats.successRate', '成功率')}</StatLabel>
          <StatValue $color={taskStats.runCount > 0 ? (taskStats.successCount / taskStats.runCount >= 0.8 ? '#52c41a' : '#faad14') : '#8c8c8c'}>
            {taskStats.runCount > 0 ? `${((taskStats.successCount / taskStats.runCount) * 100).toFixed(1)}%` : '-'}
          </StatValue>
        </StatItem>
      </StatsGrid>

      {/* Status Bar (combined: status badge + version + prev/next + refresh) */}
      <StatusBarRow>
        <StatusBadge $status={latestStatus}>
          <StatusDot $status={latestStatus} />
          <span style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.2 }}>
            {latestStatus ? t(`pages.tasks.status.${latestStatus}`, latestStatus) : t('pages.tasks.status.unknown', '未知')}
          </span>
        </StatusBadge>

        {(task as any)?.latest_version && (
          <Tooltip title={t('pages.tasks.latestVersion', '版本')}>
            <InfoItem>
              <HistoryOutlined />
              <span>v{(task as any).latest_version}</span>
            </InfoItem>
          </Tooltip>
        )}

        <StatusBarSpacer />

        {!isNew && (hasPrev || hasNext) && (
          <>
            <Tooltip title={t('common.previous', '上一个')}>
              <Button
                type="text"
                icon={<LeftOutlined />}
                onClick={onPrev}
                disabled={!hasPrev}
              />
            </Tooltip>
            <Tooltip title={t('common.next', '下一个')}>
              <Button
                type="text"
                icon={<RightOutlined />}
                onClick={onNext}
                disabled={!hasNext}
              />
            </Tooltip>
          </>
        )}

        <Tooltip title={t('pages.tasks.refresh', '刷新状态')}>
          <Button
            type="text"
            icon={<ReloadOutlined spin={refreshingStatus} />}
            onClick={handleRefreshStatus}
            loading={refreshingStatus}
          />
        </Tooltip>
      </StatusBarRow>

      {/* Tabs */}
      {!isNew && (
        <TabSection>
          <Segmented
            value={activeTab}
            onChange={(value) => setActiveTab(value as string)}
            options={[
              { label: t('pages.tasks.tabs.basic', '基本信息'), value: 'basic' },
              { label: t('pages.tasks.tabs.schedule', '调度设置'), value: 'schedule' },
              { label: t('pages.tasks.tabs.metadata', '元数据'), value: 'metadata' },
            ]}
            block
          />
        </TabSection>
      )}

      {/* Form Content */}
        <FormContainer ref={scrollContainerRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 12px 8px' }}>
        <Form form={form} layout="vertical" onFinish={handleSave} disabled={!editMode && !isNew}>
          <Form.Item name="owner" hidden>
            <Input />
          </Form.Item>

          {(activeTab === 'basic' || isNew) && (
            <Space direction="vertical" style={{ width: '100%' }} size={6}>
              {/* Task Name */}
              <div>
                <StyledFormItem
                  name="name"
                  label={t('pages.tasks.name')}
                  rules={[{ required: true, message: t('pages.tasks.nameRequired', '请输入任务名称') }]}
                  style={{ marginBottom: 0 }}
                  htmlFor="task-name"
                >
                  <Input
                    id="task-name"
                    placeholder={t('pages.tasks.namePlaceholder', '输入任务名称...')}
                    autoComplete="off"
                    style={{ fontSize: 14, fontWeight: 500 }}
                  />
                </StyledFormItem>
              </div>

              {/* Basic Info Row */}
              <Row gutter={[12, 0]}>
                <Col span={12}>
                  <StyledFormItem label={t('pages.tasks.taskId', '任务 ID')} name="id">
                    <Input id="task-id" readOnly style={{ fontFamily: 'Monospace', fontSize: 12 }} />
                  </StyledFormItem>
                </Col>
                <Col span={12}>
                  <StyledFormItem label={t('pages.tasks.priorityLabel', '优先级')} name="priority">
                    <Select
                      id="task-priority"
                      options={PRIORITY_OPTIONS.map(v => ({ value: v, label: t(`pages.tasks.priority.${v}`, v) }))}
                    />
                  </StyledFormItem>
                </Col>
              </Row>

              <Row gutter={[12, 0]}>
                <Col span={12}>
                  <StyledFormItem label={t('pages.tasks.triggerLabel', '触发器')} name="trigger">
                    <Select
                      id="task-trigger"
                      mode="multiple"
                      maxTagCount="responsive"
                      maxTagTextLength={6}
                      options={TRIGGER_OPTIONS.map(v => ({ value: v, label: t(`pages.tasks.trigger.${v}`, v) }))}
                    />
                  </StyledFormItem>
                </Col>
                <Col span={12}>
                  <StyledFormItem label={t('pages.tasks.taskTypeLabel', '任务类型')} name="task_type">
                    <Select
                      id="task-type"
                      onChange={(value) => setCurrentTaskType(value)}
                      options={TASK_TYPE_OPTIONS.map(v => ({ value: v, label: t(`pages.tasks.taskType.${v}`, v) }))}
                    />
                  </StyledFormItem>
                </Col>
              </Row>

              {/* Task Type Specific Fields */}
              {currentTaskType === 'hybrid_cloud' && (
                <Col span={24}>
                  <StyledFormItem label={t('pages.tasks.companionLocalTask', '本地辅助任务')} name="companion_local_task">
                    <Select
                      allowClear
                      showSearch
                      placeholder={t('pages.tasks.selectCompanionTask', '选择本地辅助任务')}
                      options={localTaskOptions}
                    />
                  </StyledFormItem>
                </Col>
              )}

              {currentTaskType === 'cloud' && (
                <Col span={24}>
                  <StyledFormItem name="light_weight" valuePropName="checked" style={{ marginBottom: 0 }}>
                    <Checkbox>{t('pages.tasks.lightWeightDesc', '作为轻量级云任务运行')}</Checkbox>
                  </StyledFormItem>
                </Col>
              )}

              <Col span={24}>
                <StyledFormItem label={t('common.description', '描述')} name="description">
                  <Input.TextArea
                    id="task-description"
                    rows={2}
                    placeholder={t('pages.tasks.descriptionPlaceholder', '输入任务描述...')}
                    autoComplete="off"
                  />
                </StyledFormItem>
              </Col>

              {/* Skills Section */}
              <Col span={24}>
                <Form.List name="skills">
                  {(fields, { add, remove }) => (
                    <>
                      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontWeight: 500, color: 'rgba(255, 255, 255, 0.85)', fontSize: 13 }}>
                          {t('pages.tasks.skills', '关联技能')}
                        </span>
                        {(editMode || isNew) && (
                          <Button type="link" size="small" onClick={() => add('')} icon={<PlusOutlined />} style={{ marginLeft: 8 }}>
                            {t('common.add', '添加')}
                          </Button>
                        )}
                      </div>
                      {fields.length === 0 && (
                        <div style={{ color: 'rgba(255, 255, 255, 0.45)', marginBottom: 8, padding: 8, background: 'rgba(255,255,255,0.02)', borderRadius: 6, fontSize: 12 }}>
                          {t('pages.tasks.noSkillsAssociated', '尚未关联任何技能。点击"添加"以关联技能。')}
                        </div>
                      )}
                      {fields.map(({ key, name, ...restField }) => (
                        <div key={key} style={{ display: 'flex', alignItems: 'center', marginBottom: 4, gap: 6 }}>
                          <Form.Item {...restField} name={name} style={{ flex: 1, marginBottom: 0 }}>
                            {editMode || isNew ? (
                              <SkillSelect
                                skillOptions={skillOptions}
                                placeholder={t('pages.tasks.skillPlaceholder', '选择技能')}
                              />
                            ) : (
                              <Form.Item noStyle shouldUpdate>
                                {({ getFieldValue }) => {
                                  const skillId = getFieldValue(['skills', name]);
                                  const found = skillsSimplified.find((s) => String(s.id) === String(skillId) || s.name === skillId);
                                  let displayVal: string;
                                  if (found) displayVal = found.name;
                                  else {
                                    const backendName: string = ((task as any).skill_names || [])[name] || '';
                                    displayVal = backendName || (String(skillId || '').match(/^[0-9a-f-]{8,}$/i) ? '' : String(skillId || ''));
                                  }
                                  return <Input readOnly value={displayVal} />;
                                }}
                              </Form.Item>
                            )}
                          </Form.Item>
                          {(editMode || isNew) && fields.length > 0 && (
                            <MinusCircleOutlined onClick={() => remove(name)} style={{ color: '#ff4d4f', fontSize: 16, cursor: 'pointer' }} />
                          )}
                        </div>
                      ))}
                    </>
                  )}
                </Form.List>
              </Col>

              {/* Task Variables Section — per-task values for shared skills.
                  Fields come from the selected skills' need_inputs
                  declarations; values persist to metadata.task_vars and are
                  seeded into the run's prompt variables at start. */}
              <Col span={24}>
                <Form.Item noStyle shouldUpdate={(prev: any, cur: any) =>
                  JSON.stringify(prev.skills || []) !== JSON.stringify(cur.skills || [])
                }>
                  {({ getFieldValue }) => {
                    const selIds: string[] = (getFieldValue('skills') || []).map((s: any) => String(s || ''));
                    const declared: any[] = [];
                    const seen = new Set<string>();
                    for (const sid of selIds) {
                      const sk: any = (skills || []).find((s: any) => String(s.id) === sid || s.name === sid);
                      for (const inp of (sk?.need_inputs || [])) {
                        const nm = String(inp?.name || '').trim();
                        if (nm && !seen.has(nm)) { seen.add(nm); declared.push(inp); }
                      }
                    }
                    const existingVars: Record<string, any> = ((task as any)?.metadata?.task_vars) || {};
                    const extraNames = Object.keys(existingVars).filter((k) => !seen.has(k));
                    if (declared.length === 0 && extraNames.length === 0) return null;
                    return (
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
                          <span style={{ fontWeight: 500, color: 'rgba(255, 255, 255, 0.85)', fontSize: 13 }}>
                            {t('pages.tasks.taskVars', '任务变量')}
                          </span>
                          <span style={{ marginLeft: 8, color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>
                            {t('pages.tasks.taskVarsHelp', '填充技能提示词中的 {{变量}} 占位符')}
                          </span>
                        </div>
                        <Row gutter={[12, 0]}>
                          {declared.map((inp: any) => (
                            <Col span={12} key={inp.name}>
                              <StyledFormItem
                                label={inp.name}
                                name={['task_vars', inp.name]}
                                tooltip={inp.description || undefined}
                                rules={inp.required ? [{ required: true, message: `${inp.name} ${t('common.required', '为必填项')}` }] : []}
                              >
                                <Input
                                  disabled={!(editMode || isNew)}
                                  placeholder={inp.default !== undefined && inp.default !== null ? String(inp.default) : ''}
                                />
                              </StyledFormItem>
                            </Col>
                          ))}
                          {extraNames.map((nm) => (
                            <Col span={12} key={nm}>
                              <StyledFormItem label={nm} name={['task_vars', nm]}>
                                <Input disabled={!(editMode || isNew)} />
                              </StyledFormItem>
                            </Col>
                          ))}
                        </Row>
                      </div>
                    );
                  }}
                </Form.Item>
              </Col>
            </Space>
          )}

          {(activeTab === 'schedule' || isNew) && (
            <StyledCard
              size="small"
              title={
                <Space>
                  <SettingOutlined />
                  {t('pages.tasks.scheduleDetails', '调度详情')}
                </Space>
              }
              style={{
                marginTop: 8,
                background: 'rgba(59, 130, 246, 0.05)',
                borderColor: 'rgba(59, 130, 246, 0.15)'
              }}
            >
              <Row gutter={[12, 8]}>
                <Col span={24}>
                  <div style={{ padding: 8, background: 'rgba(255, 255, 255, 0.02)', borderRadius: 6 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'rgba(255, 255, 255, 0.65)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      {t('pages.tasks.repeatSettings', '重复设置')}
                    </div>
                    <Row gutter={[10, 0]}>
                      <Col span={8}>
                        <StyledFormItem label={t('pages.tasks.scheduleRepeatTypeLabel', '重复类型')} name={["schedule", "repeat_type"]} style={{ marginBottom: 0 }}>
                          <Select options={REPEAT_OPTIONS.map(v => ({ value: v, label: t(`pages.tasks.repeatType.${v}`, v === 'none' ? '不重复' : v) }))} />
                        </StyledFormItem>
                      </Col>
                      <Col span={8}>
                        <StyledFormItem label={t('pages.tasks.scheduleRepeatNumberLabel', '重复次数')} name={["schedule", "repeat_number"]} style={{ marginBottom: 0 }}>
                          <Input type="number" min={1} />
                        </StyledFormItem>
                      </Col>
                      <Col span={8}>
                        <StyledFormItem label={t('pages.tasks.scheduleRepeatUnitLabel', '重复单位')} name={["schedule", "repeat_unit"]} style={{ marginBottom: 0 }}>
                          <Select options={REPEAT_OPTIONS.filter(v => v !== 'none').map(v => ({ value: v, label: t(`pages.tasks.repeatType.${v}`, v) }))} />
                        </StyledFormItem>
                      </Col>
                    </Row>
                  </div>
                </Col>

                <Col span={24}>
                  <div style={{ padding: 8, background: 'rgba(255, 255, 255, 0.02)', borderRadius: 6 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'rgba(255, 255, 255, 0.65)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      {t('pages.tasks.timeSettings', '时间设置')}
                    </div>
                    <Row gutter={[10, 0]}>
                      <Col span={12}>
                        <StyledFormItem label={t('pages.tasks.scheduleStartTimeLabel', '开始时间')} name={["schedule", "start_date_time"]} style={{ marginBottom: 0 }}>
                          <DatePicker showTime style={{ width: '100%' }} />
                        </StyledFormItem>
                      </Col>
                      <Col span={12}>
                        <StyledFormItem label={t('pages.tasks.scheduleEndTimeLabel', '结束时间')} name={["schedule", "end_date_time"]} style={{ marginBottom: 0 }}>
                          <DatePicker showTime style={{ width: '100%' }} />
                        </StyledFormItem>
                      </Col>
                      <Col span={12}>
                        <StyledFormItem label={t('pages.tasks.scheduleTimeoutLabel', '超时时间(秒)')} name={["schedule", "time_out"]} style={{ marginBottom: 0 }}>
                          <Input type="number" min={60} step={60} />
                        </StyledFormItem>
                      </Col>
                      <Col span={12}>
                        <StyledFormItem label={t('pages.tasks.scheduleTimezoneLabel', '时区')} name={["schedule", "timezone"]} style={{ marginBottom: 0 }}>
                          <Select showSearch options={TIMEZONE_OPTIONS.map(tz => ({ value: tz, label: tz }))} />
                        </StyledFormItem>
                      </Col>
                    </Row>
                  </div>
                </Col>
              </Row>
            </StyledCard>
          )}

          {(activeTab === 'metadata' || isNew) && (
            <Col span={24}>
              <StyledFormItem
                label={t('pages.tasks.metadata', '元数据 (JSON)')}
                name="metadata_text"
                tooltip={t('pages.tasks.metadata_tooltip') || '必须是有效的 JSON 格式'}
                validateTrigger={['onChange', 'onBlur']}
                rules={[{
                  validator: (_, value) => {
                    if (!value || value.trim() === '') return Promise.resolve();
                    try {
                      JSON.parse(value);
                      return Promise.resolve();
                    } catch (e) {
                      return Promise.reject(new Error(t('pages.tasks.invalidJson') || 'JSON 格式无效'));
                    }
                  }
                }]}
              >
                <Input.TextArea
                  rows={5}
                  placeholder={JSON.stringify({ key: 'value' }, null, 2)}
                  style={{ fontFamily: 'Consolas, Monaco, monospace', fontSize: 12 }}
                />
              </StyledFormItem>
            </Col>
          )}
        </Form>
      </FormContainer>

      {/* Fixed Action Buttons */}
      <div style={{
        flexShrink: 0,
        display: 'flex',
        justifyContent: 'flex-end',
        gap: '8px',
        padding: '10px 12px',
        background: 'rgba(255, 255, 255, 0.02)',
        borderTop: '1px solid rgba(255, 255, 255, 0.06)'
      }}>
        {!editMode && !isNew && task && latestStatus.toLowerCase() === 'ready' && (
          <Button type="primary" onClick={handleLaunchTask} icon={<PlayCircleOutlined />} loading={launching} style={primaryButtonStyle}>
            {t('pages.tasks.launch', '启动')}
          </Button>
        )}

        {(editMode || isNew) && (
          <>
            <Button type="primary" onClick={() => form.submit()} loading={saving} disabled={saving} icon={<SaveOutlined />} style={primaryButtonStyle}>
              {isNew ? t('common.create') : t('common.save')}
            </Button>
            <Button onClick={handleCancel} disabled={saving} icon={<CloseOutlined />} style={buttonStyle}>
              {t('common.cancel')}
            </Button>
          </>
        )}

        {!editMode && !isNew && task && (
          <>
            {isCodeGenerated ? (
              <Button icon={<LockOutlined />} disabled style={{ ...buttonStyle, cursor: 'not-allowed' }}>
                {t('pages.tasks.readOnlyCodeGenerated') || '只读'}
              </Button>
            ) : (
              <>
                <Button type="primary" onClick={handleEdit} icon={<EditOutlined />} style={primaryButtonStyle}>
                  {t('common.edit')}
                </Button>
                <Button danger onClick={handleDelete} icon={<DeleteOutlined />} style={buttonStyle}>
                  {t('common.delete')}
                </Button>
              </>
            )}
          </>
        )}
      </div>
    </DetailContainer>
  );
};

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
} from '@ant-design/icons';
import { Button, Space, Form, Input, Row, Col, Select, DatePicker, App, Checkbox, Tag } from 'antd';
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
  trigger: ['schedule'] as string[],
  skills: [] as string[],  // Support multiple skills
  schedule: {
    repeat_type: 'none',  // Default to 'none' (one-time run)
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

  // Pre-process the task data - extract only primitive values to avoid circular references
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
    // Extract only primitive values, no spreading to avoid circular references
    return {
      id: raw.id,
      name: raw.name,
      description: raw.description,
      owner: raw.owner,
      agent_id: raw.agent_id || raw.agentId,
      latest_version: raw.latest_version,
      priority: raw.priority || 'none',
      trigger: raw.trigger,
      skill: raw.skill,
      skills: raw.skills,
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
  const [editMode, setEditMode] = React.useState(isNew);
  const [saving, setSaving] = React.useState(false);
  const [refreshingStatus, setRefreshingStatus] = React.useState(false);
  const [launching, setLaunching] = React.useState(false);
  const [latestStatus, setLatestStatus] = React.useState<string>('');
  // skills store and fetch-on-mount if needed
  const skills = useSkillStore((s) => s.items);
  const setSkills = useSkillStore((s) => s.setItems);

  // Extract only id and name to avoid circular reference in deep comparison
  // Use primitive dependencies to avoid triggering deep comparison on circular structures
  const skillsKey = React.useMemo(() => {
    // Use length as primitive dependency to avoid deep comparison
    return (skills || []).length;
  }, [skills?.length]);

  const skillsSimplified = React.useMemo(() => {
    return (skills || []).map((s: any) => ({ id: s.id, name: s.name }));
  }, [skillsKey]);  // Depend on primitive key instead of full skills object

  // Memoize skill options to avoid circular reference warnings
  const skillOptions = React.useMemo(() => {
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
          const res = await api.getAgentSkills<any[]>(uname, []);
          // API returns skills array directly in res.data (not res.data.skills)
          // due to resultPath: 'getAllMine.skills' in api config
          const skillsData = res?.data?.skills || res?.data;
          if (res?.success && Array.isArray(skillsData) && skillsData.length > 0) {
            
            // Sanitize skills data to remove circular references before storing
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
              examples: skill.examples,
              inputModes: skill.inputModes,
              outputModes: skill.outputModes,
              apps: skill.apps,
              limitations: skill.limitations,
              price: skill.price,
              price_model: skill.price_model,
              public: skill.public,
              rentable: skill.rentable,
              run_in_cloud: skill.run_in_cloud,
              // Explicitly exclude config, work_flow, ui_info and other fields that may contain circular refs
            }));
            
            setSkills(sanitizedSkills as any);
          }
        }
      } catch (e) {
        // Silently handle skill fetch errors - non-critical
      }
    };
    ensureSkills();
  }, [username, setSkills]);

  // Create a stable primitive key for task to avoid circular reference warnings
  const taskKey = React.useMemo(() => {
    if (!task) return 'no-task';
    const t = task as any;
    // Include status in the key so taskStatus updates when status changes
    const status = t.status ?? t.state?.top ?? '';
    const statusStr = typeof status === 'object' ? (status.state || status.status || '') : String(status || '');
    return `${t.id || ''}_${t.name || ''}_${t.latest_version || ''}_${statusStr}_${isNew ? 'new' : 'edit'}`;
  }, [task, isNew]);

  const taskStatus = React.useMemo(() => {
    if (!task) return '';
    const statusValue = (task as any).status ?? (task as any).state?.top ?? '';
    
    // Handle different status formats
    if (typeof statusValue === 'string') {
      return statusValue;
    } else if (statusValue && typeof statusValue === 'object') {
      // If status is an object like {state: 'submitted', message: null, timestamp: null}
      return statusValue.state || statusValue.status || String(statusValue);
    }
    
    return String(statusValue || '');
  }, [taskKey]);

  React.useEffect(() => {
    setLatestStatus(taskStatus);
  }, [taskStatus]);

  // Watch trigger changes to update repeat_type options
  const handleTriggerChange = React.useCallback(() => {
    // 'none' repeat_type is valid for schedule triggers (one-time run)
    // Trigger state is managed by form, no need for separate state
  }, []);

  React.useEffect(() => {
    if (task) {
      // Skill comes directly from task (loaded from relationship table)
      const taskSkill = (task as any).skill || '';
      const taskSkills = (task as any).skills || (taskSkill ? [taskSkill] : []);
      
      // Metadata is clean (no skill stored in it anymore)
      const metadata = (task as any).metadata || {};
      const metaStr = Object.keys(metadata).length > 0 ? JSON.stringify(metadata, null, 2) : '';

      // ä½¿ç"¨ name Fieldï¼ŒIfä¸å­˜åœ¨åˆ™ä½¿ç"¨ skill Fieldä½œä¸ºåŽå¤‡
      const taskName = (task as any).name || taskSkill || '';

      // ä½¿ç"¨ description Fieldï¼ŒIfä¸å­˜åœ¨åˆ™ä½¿ç"¨ metadata ä¸­çš„Descriptionä½œä¸ºåŽå¤‡
      const taskDescription = (task as any).description
        || (task as any).metadata?.description
        || '';

      // ç¡®ä¿AllFieldéƒ½æ­£ç¡®Settings
      // For new tasks, auto-generate ID and set owner
      const taskId = isNew ? generateTaskId() : (task as any).id;
      const taskOwner = isNew ? username : ((task as any).owner || username);
      const taskAgentId = (task as any).agent_id || (task as any).agentId || '';
      
      // Extract primitive values from task to avoid circular references
      const t = task as any;
      // Process trigger value - backend stores as comma-separated string
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
        cloud_based: !!(metadata?.cloud_run),
        skills: taskSkills,
        metadata_text: metaStr,
        agent_id: taskAgentId,
        latest_version: t.latest_version || '1.0.0',
        priority: t.priority || 'none',
        trigger: taskTrigger,  // Use processed trigger value
        schedule: {
          repeat_type: t.schedule?.repeat_type || 'none',
          repeat_number: t.schedule?.repeat_number || 1,
          repeat_unit: t.schedule?.repeat_unit || 'by hours',
          start_date_time: t.schedule?.start_date_time,
          end_date_time: t.schedule?.end_date_time,
          time_out: t.schedule?.time_out || 3600,
        },
      };

      // Set all form values at once, including trigger
      form.setFieldsValue(formValues);
    } else {
      form.resetFields();
      setEditMode(false);
    }
  }, [taskKey, username]); // form is stable and doesn't need to be a dependency

  const handleCancel = () => {
    if (isNew) {
      // New mode: Clear form and notify parent to close panel
      form.resetFields();
      if (onCancel) {
        onCancel();
      }
    } else {
      // Edit mode: Exit edit mode (form will be re-populated by useEffect)
      setEditMode(false);
      // Edit mode does not call onCancel to keep panel open
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
        trigger: ((values as any).trigger || ['auto']).join(','),
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
        metadata: {
          ...((values as any).metadata_text ? JSON.parse((values as any).metadata_text) : {}),
          cloud_run: !!(values as any).cloud_based,
        },
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
        if (!q.success) {
          console.warn('[TaskDetail] queryAgentTaskSkillRels failed:', q.error);
          return;
        }

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
          .map((rel: any) => ({ id: String(rel?.id || '').trim() }))
          .filter((x: any) => x.id);

        if (toAdd.length) {
          const r = await api.addAgentTaskSkillRels(toAdd);
          if (!r.success) console.warn('[TaskDetail] addAgentTaskSkillRels failed:', r.error);
        }
        if (toRemove.length) {
          const r = await api.removeAgentTaskSkillRels(toRemove);
          if (!r.success) console.warn('[TaskDetail] removeAgentTaskSkillRels failed:', r.error);
        }
      };

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

          // Web app: keep task↔skills relations in agent_task_skill_rels.
          // If this call fails (e.g., local dev GraphQL schema), we don't block saving the task itself.
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

  const handleRefreshStatus = async () => {
    if (!task || isNew) return;
    const taskId = String((task as any).id || '');
    if (!taskId) return;

    setRefreshingStatus(true);
    try {
      const api = get_ipc_api();
      const response = await api.refreshAgentTaskStatus<any>(username, taskId);
      if (response.success) {
        const refreshed = (response as any).data?.task || (response as any).data;
        let nextStatus = refreshed?.status ?? refreshed?.state?.top ?? taskStatus;
        
        // Handle object format status
        if (nextStatus && typeof nextStatus === 'object') {
          nextStatus = nextStatus.state || nextStatus.status || String(nextStatus);
        }
        
        if (nextStatus) {
          setLatestStatus(String(nextStatus));
        }
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
      const response = await api.runAgentTask<any>(username, {
        task_id: taskId,
        cloud_based: !!(task as any).cloud_based,
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
      warningText: t('pages.tasks.deleteWarning', 'æ­¤Operationæ— æ³•æ’¤é”€'),
      okText: t('common.delete', 'Delete'),
      cancelText: t('common.cancel', 'Cancel'),
      onOk: async () => {
        try {
          const api = get_ipc_api();

          // Best-effort: remove task↔skill relations first (keeps relation table clean in web mode)
          try {
            const taskId = String((task as any).id || '').trim();
            if (taskId) {
              const q = await api.queryAgentTaskSkillRels({ task_id: taskId, limit: 500, offset: 0 });
              if (q.success && Array.isArray(q.data) && q.data.length) {
                const relIds = q.data
                  .map((r: any) => ({ id: String(r?.id || '').trim() }))
                  .filter((x: any) => x.id);
                if (relIds.length) {
                  await api.removeAgentTaskSkillRels(relIds);
                }
              }
            }
          } catch (e) {
            console.warn('[TaskDetail] cleanup AgentTaskSkillRels before delete failed:', e);
          }

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

  // Status color mapping
  const getStatusColor = (status: string) => {
    const statusLower = status.toLowerCase();
    if (statusLower === 'completed' || statusLower === 'success') return 'success';
    if (statusLower === 'running' || statusLower === 'working') return 'processing';
    if (statusLower === 'failed' || statusLower === 'error') return 'error';
    if (statusLower === 'pending' || statusLower === 'submitted') return 'default';
    if (statusLower === 'cancelled' || statusLower === 'canceled') return 'warning';
    return 'default';
  };

  return (
    <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <FormContainer ref={scrollContainerRef} style={{ flex: 1, overflowY: 'auto', paddingBottom: '20px' }}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          padding: '12px 24px',
          background: 'rgba(255, 255, 255, 0.02)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
          marginBottom: '16px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'rgba(255, 255, 255, 0.65)', fontSize: 14 }}>
              {t('pages.tasks.statusLabel', 'Status')}:
            </span>
            <Tag 
              color={getStatusColor(latestStatus)} 
              style={{ margin: 0, fontSize: 13, padding: '2px 12px' }}
            >
              {latestStatus ? t(`pages.tasks.status.${latestStatus}`, latestStatus) : t('pages.tasks.status.unknown', 'Unknown')}
            </Tag>
          </div>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            loading={refreshingStatus}
            onClick={handleRefreshStatus}
            aria-label={t('pages.tasks.refresh', 'Refresh')}
          >
            {t('pages.tasks.refresh', 'Refresh')}
          </Button>
        </div>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          disabled={!editMode && !isNew}
        >
          <Form.Item name="owner" hidden>
            <Input />
          </Form.Item>
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
                  <StyledFormItem label={t('pages.tasks.ownerAgent', 'Owner(Agent)')} name="agent_id" htmlFor="task-agent-id">
                    <Input id="task-agent-id" readOnly aria-label={t('pages.tasks.ownerAgent', 'Owner(Agent)')} />
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
                      mode="multiple"
                      onChange={handleTriggerChange}
                      options={TRIGGER_OPTIONS.map(v => ({ value: v, label: t(`pages.tasks.trigger.${v}`, v) }))}
                      aria-label={t('pages.tasks.triggerLabel', 'Trigger')}
                      placeholder={t('pages.tasks.triggerPlaceholder', 'Select trigger sources')}
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
                              <StyledFormItem 
                                label={t('pages.tasks.scheduleRepeatTypeLabel', 'Repeat Type')} 
                                name={["schedule", "repeat_type"]} 
                                htmlFor="task-repeat-type"
                              >
                                <Select
                                  id="task-repeat-type"
                                  size="large"
                                  options={REPEAT_OPTIONS
                                    .map(v => ({ value: v, label: t(`pages.tasks.repeatType.${v}`, v === 'none' ? 'None (One-time)' : v) }))}
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
          {!editMode && !isNew && task && latestStatus.toLowerCase() === 'ready' && (
            <Button
              type="primary"
              onClick={handleLaunchTask}
              icon={<PlayCircleOutlined />}
              size="large"
              loading={launching}
              style={primaryButtonStyle}
            >
              {t('pages.tasks.launch', 'Launch')}
            </Button>
          )}
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

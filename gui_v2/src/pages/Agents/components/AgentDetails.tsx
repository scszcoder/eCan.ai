import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { App, Button, Card, Col, DatePicker, Form, Input, Radio, Row, Select, Spin, Tag, Tooltip, TreeSelect, Modal } from 'antd';
import { EditOutlined, SaveOutlined, InfoCircleOutlined, DeleteOutlined, CloseOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { useOrgStore } from '@/stores/orgStore';
import { useTaskStore, useSkillStore, useVehicleStore, useAgentStore } from '@/stores';
import { get_ipc_api } from '@/services/ipc_api';
import { StyledFormItem } from '@/components/Common/StyledForm';
import { AvatarManager, AvatarData } from '@/components/Avatar';
import { useEffectOnActive } from 'keepalive-for-react';
import { useDeleteConfirm } from '@/components/Common/DeleteConfirmModal';

type Gender = 'gender_options.male' | 'gender_options.female';

interface AgentDetailsForm {
  id?: string;
  name?: string;
  gender?: Gender;
  birthday?: Dayjs | null;
  owner?: string;
  personalities?: string[];  // Unified naming: personality_traits → personalities
  title?: string[];
  org_id?: string; // Organization ID (single selection)
  supervisor_id?: string; // Supervisor ID (single selection)
  tasks?: string[];
  skills?: string[];
  vehicle_id?: string | null;
  description?: string; // Agent description
  extra_data?: string; // Extra data/notes
}

// Predefined personality trait options (using i18n keys)
const knownPersonalities = [
  'personality.friendly',
  'personality.analytical',
  'personality.creative',
  'personality.efficient',
  'personality.empathetic',
  'personality.patient',
  'personality.detail_oriented',
  'personality.proactive',
  'personality.collaborative',
  'personality.innovative'
];

// 预Definition的职称选项（使用国际化 key）
const knownTitles = [
  'title.engineer',
  'title.manager',
  'title.analyst',
  'title.designer',
  'title.operator',
  'title.developer',
  'title.architect',
  'title.consultant',
  'title.specialist',
  'title.coordinator'
];

// Tasks and skills will be sourced from global store to link with Tasks/Skills pages

// 判断是否是代码生成的 skill/task（通过 source 字段判断）
const isCodeGenerated = (item: any): boolean => {
  if (!item || typeof item !== 'object') return false;
  
  // 使用 source 字段判断（后端已确保该字段存在）
  return item.source === 'code';
};

// 多选TagEdit器 - 使用 Select mode="tags" Implementation友好交互
// Support预Definition选项（国际化）和UserCustomInput
const TagsEditor: React.FC<{
  value?: string[];
  onChange?: (value: string[]) => void;
  options: Array<string | { label: string; value: string; hasId?: boolean }>;
  disabled?: boolean;
  placeholder?: string;
  'aria-label'?: string;
  id?: string;
  dataMap?: Map<string, any>;  // Used forDisplayDetailedInformation的DataMap
  dataType?: 'task' | 'skill';  // DataType，Used forDisplay不同的DetailedInformation
}> = ({ value, onChange, options, disabled, placeholder, 'aria-label': ariaLabel, id, dataMap, dataType }) => {
  const { t } = useTranslation();
  // DetailedInformationModalStatus
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedDetailItem, setSelectedDetailItem] = useState<any>(null);
  // GetDisplay文本
  // If是预Definition选项（如 personality.friendly），Display国际化翻译
  // If是UserCustomInput，直接Display原文
  const getDisplayText = useCallback((val: string) => {
    if (!val) return '';

    // Check是否是预Definition的国际化 key（Include . 的格式）
    if (val.includes('.')) {
      const translated = t(val);

      // If翻译Success（翻译Result不等于原 key），返回翻译
      if (translated && translated !== val) {
        return translated;
      }
      // If翻译Failed，返回 key 的最后一部分作为后备（如 friendly）
      const parts = val.split('.');
      return parts[parts.length - 1];
    }

    // 否则直接返回原Value（UserCustomInput）
    return val;
  }, [t]);

  // 使用 useMemo Cache选项，避免重复计算
  const selectOptions = useMemo(() => {
    return options.map((opt, index) => {
      // 支持对象格式（包含 hasId 标记）和字符串格式
      if (typeof opt === 'object') {
        return {
          label: getDisplayText(opt.label),
          value: opt.value,
          hasId: opt.hasId,
          key: `option-${index}-${opt.value}`,
          title: ''
        };
      }
      const displayText = getDisplayText(opt);
      return {
        label: displayText,
        value: opt,
        hasId: true, // 字符串格式默认为有效
        key: `option-${index}-${opt}`,
        title: ''
      };
    });
  }, [options, getDisplayText]);

  // ProcessSelect变化 - WhenUserSelect预Definition选项时，Storage国际化 key；CustomInput时，Storage原文
  const handleChange = useCallback((newValue: string[]) => {
    if (!onChange) return;

    // Process每个Value：Check是否是翻译文本，If是则Convert回国际化 key
    const processedValues = newValue.map(val => {
      // Check是否已经是国际化 key
      if (val.includes('.')) {
        return val;
      }

      // Check是否是翻译文本，NeedConvert回国际化 key
      const matchedOption = selectOptions.find(opt => opt.label === val);
      if (matchedOption) {
        return matchedOption.value;
      }

      // 否则是UserCustomInput，直接返回
      return val;
    }).filter(val => {
      // ⚠️ 过滤掉没有 id 的项（代码生成的临时数据）
      const option = selectOptions.find(opt => opt.value === val || opt.label === val);
      if (option && option.hasId === false) {
        console.warn(`[TagsEditor] 阻止选择无效的 ${dataType}: ${val}`);
        return false;
      }
      return true;
    });

    onChange(processedValues);
  }, [onChange, selectOptions, dataType]);

  // 确保 value 数组中的每个元素都是字符串，避免 key 警告
  const normalizedValue = useMemo(() => {
    if (!Array.isArray(value)) return [];
    return value.filter(v => v != null).map(v => String(v));
  }, [value]);

  return (
    <>
    <Select
      id={id}
      mode="tags"
      style={{ width: '100%' }}
      placeholder={placeholder}
      value={normalizedValue}
      onChange={handleChange}
      disabled={disabled}
      maxTagCount={10}  // 设置足够大的数字，确保所有 tag 都能显示
      showSearch
      allowClear
      tokenSeparators={[',']}
      aria-label={ariaLabel}
      // SearchFilter - Support模糊Searchlabel和value
      filterOption={(input, option) => {
        if (!input) return true;
        const searchText = input.toLowerCase();
        const label = (option?.label || '').toString().toLowerCase();
        const value = (option?.value || '').toString().toLowerCase();
        return label.includes(searchText) || value.includes(searchText);
      }}
      // 下拉框Positioning - 避免遮挡Input框
      popupMatchSelectWidth={false}
      listHeight={400}
      placement="bottomLeft"
      // TagRender - AddtooltipDisplayDescription
      tagRender={(props) => {
        const { value: tagValue, closable, onClose } = props;
        const displayText = getDisplayText(tagValue as string);
        const isCustom = tagValue && typeof tagValue === 'string' && !tagValue.includes('.');
        const itemData = dataMap?.get(tagValue as string);
        const description = itemData?.description || '';

        const tagContent = (
          <div
            onMouseDown={(e) => {
              // 在 mouseDown 阶段阻止事件，防止触发 Select 的下拉展开
              e.stopPropagation();
            }}
          >
            <Tag
              key={`tag-${tagValue}`}  // ✅ Add key
              color={isCustom ? 'green' : 'blue'}
              closable={closable && !disabled}
              onClose={(e) => {
                e.stopPropagation(); // 阻止事件冒泡
                onClose(e);
              }}
              style={{ marginRight: 3, cursor: itemData ? 'pointer' : 'default' }}
              onClick={(e) => {
                if (itemData) {
                  e.stopPropagation(); // 阻止事件冒泡
                  setSelectedDetailItem(itemData);
                  setDetailModalVisible(true);
                }
              }}
            >
              {displayText}
            </Tag>
          </div>
        );

        // If有DescriptionInformation，Addtooltip
        if (description && dataMap) {
          return (
            <Tooltip 
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ flex: 1 }}>{description}</div>
                  <InfoCircleOutlined 
                    style={{ fontSize: 14, cursor: 'pointer', color: '#40a9ff' }}
                    onClick={(e) => {
                      e.preventDefault(); // 阻止默认行为
                      e.stopPropagation(); // 阻止事件冒泡
                      setSelectedDetailItem(itemData);
                      setDetailModalVisible(true);
                    }}
                  />
                </div>
              }
              mouseEnterDelay={0.3}
            >
              {tagContent}
            </Tooltip>
          );
        }

        return tagContent;
      }}
      // 下拉选项Configuration - 使用Cache的选项
      options={selectOptions}
      // Custom下拉选项Render - Addtooltip显示描述
      optionRender={(option) => {
        const itemData = dataMap?.get(option.value as string);
        const description = itemData?.description || '';
        const optionData = option.data as any;
        const hasId = optionData?.hasId !== false; // 
        // 没有 id 的项样式 - 仅设置鼠标样式和透明度，文字颜色由内部span控制
        const invalidStyle = !hasId ? {
          cursor: 'not-allowed',
          opacity: 0.8 // 稍微降低透明度，表明不可选
        } : {};
        // 
        const content = (
          <div style={{ padding: '4px 0', width: '100%', display: 'flex', alignItems: 'center', gap: '8px', ...invalidStyle }}>
            {!hasId && <span style={{ color: '#ff4d4f', fontSize: '14px' }}>❌</span>}
            <span style={{ color: !hasId ? 'rgba(255, 255, 255, 0.85)' : 'inherit' }}>{option.label}</span>
          </div>
        );
        // 
        if (description && dataMap) {
          return (
            <Tooltip
              title={
                !hasId ? t('pages.agents.system_example_cannot_select') || 'System example cannot be selected' : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ flex: 1 }}>{description}</div>
                    <InfoCircleOutlined 
                      style={{ fontSize: 14, cursor: 'pointer', color: '#40a9ff' }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setSelectedDetailItem(itemData);
                        setDetailModalVisible(true);
                      }}
                    />
                  </div>
                )
              }
              placement="right"
              mouseEnterDelay={0.3}
            >
              {content}
            </Tooltip>
          );
        }
        // 
        return !hasId ? (
          <Tooltip title={t('pages.agents.system_example_cannot_select') || 'System example cannot be selected'}>
            {content}
          </Tooltip>
        ) : content;
      }}
      // DisabledSelect自带的titleProperty，避免tooltip冲突
      optionFilterProp="label"
      // 不使用 getPopupContainer，让下拉框自然Positioning，避免遮挡
      // 不Display下拉箭头，更像Input框
      suffixIcon={null}
      // 自动Get焦点时不自动Open下拉框
      open={undefined}
    />
    
    {/* DetailedInformationModal */}
    {dataMap && selectedDetailItem && (
      <Modal
        title={dataType === 'task' ? t('pages.tasks.details', 'Task Details') : t('pages.skills.details', 'Skill Details')}
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            {t('common.close', 'Close')}
          </Button>
        ]}
        width={600}
        centered
      >
        <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
          {/* Name */}
          <div style={{ marginBottom: 16 }}>
            <strong>{t('common.name', 'Name')}:</strong>{' '}
            <span style={{ color: selectedDetailItem.name || selectedDetailItem.skill ? 'inherit' : '#999' }}>
              {selectedDetailItem.name || selectedDetailItem.skill || '-'}
            </span>
          </div>
          
          {/* Description */}
          <div style={{ marginBottom: 16 }}>
            <strong>{t('common.description', 'Description')}:</strong>
            <div style={{ marginTop: 8, padding: 12, background: 'rgba(0,0,0,0.02)', borderRadius: 4, color: selectedDetailItem.description ? 'inherit' : '#999' }}>
              {selectedDetailItem.description || '-'}
            </div>
          </div>
          
          {/* Task特有Field */}
          {dataType === 'task' && (
            <>
              <div style={{ marginBottom: 16 }}>
                <strong>{t('pages.tasks.priorityLabel', 'Priority')}:</strong>{' '}
                <span style={{ color: selectedDetailItem.priority ? 'inherit' : '#999' }}>
                  {selectedDetailItem.priority || '-'}
                </span>
              </div>
              <div style={{ marginBottom: 16 }}>
                <strong>{t('pages.tasks.triggerLabel', 'Trigger')}:</strong>{' '}
                <span style={{ color: selectedDetailItem.trigger ? 'inherit' : '#999' }}>
                  {selectedDetailItem.trigger || '-'}
                </span>
              </div>
              <div style={{ marginBottom: 16 }}>
                <strong>{t('pages.tasks.statusLabel', 'Status')}:</strong>{' '}
                <span style={{ color: selectedDetailItem.status ? 'inherit' : '#999' }}>
                  {selectedDetailItem.status || '-'}
                </span>
              </div>
            </>
          )}
          
          {/* Skill特有Field */}
          {dataType === 'skill' && (
            <>
              <div style={{ marginBottom: 16 }}>
                <strong>{t('pages.skills.level', 'Level')}:</strong>{' '}
                <span style={{ color: selectedDetailItem.level !== undefined && selectedDetailItem.level !== null ? 'inherit' : '#999' }}>
                  {selectedDetailItem.level !== undefined && selectedDetailItem.level !== null ? selectedDetailItem.level : '-'}
                </span>
              </div>
              <div style={{ marginBottom: 16 }}>
                <strong>{t('pages.skills.statusLabel', 'Status')}:</strong>{' '}
                <span style={{ color: selectedDetailItem.status ? 'inherit' : '#999' }}>
                  {selectedDetailItem.status || '-'}
                </span>
              </div>
            </>
          )}
          
          {/* Metadata */}
          <div style={{ marginBottom: 16 }}>
            <strong>{t('common.metadata', 'Metadata')}:</strong>
            <pre style={{ marginTop: 8, padding: 12, background: 'rgba(0,0,0,0.02)', borderRadius: 4, fontSize: 12, overflowX: 'auto', color: selectedDetailItem.metadata ? 'inherit' : '#999' }}>
              {selectedDetailItem.metadata ? JSON.stringify(selectedDetailItem.metadata, null, 2) : '-'}
            </pre>
          </div>
        </div>
      </Modal>
    )}
  </>
  );
};

const AgentDetails: React.FC = () => {
  const { message } = App.useApp();
  const showDeleteConfirm = useDeleteConfirm();
  const navigate = useNavigate();
  const location = useLocation();
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const messageRef = useRef(message);
  const translationRef = useRef(t);

  useEffect(() => {
    messageRef.current = message;
  }, [message]);

  useEffect(() => {
    translationRef.current = t;
  }, [t]);
  
  // ScrollPositionSave
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  
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
  // Support两种新建模式：/agents/add 和 /agents/details/new
  const isNew = id === 'new' || location.pathname === '/agents/add';
  const username = useUserStore((s: any) => s.username);
  
  // 从QueryParameter中Get orgId（Used forSave后返回）
  const searchParams = new URLSearchParams(location.search);
  const defaultOrgId = searchParams.get('orgId');

  // Get vehicles List
  const { items: vehicles, fetchItems: fetchVehicles } = useVehicleStore();

  // 计算本机 vehicle ID（假设本机是 hostname 为 localhost 或 name Include "本机" 的）
  const localVehicleId = useMemo(() => {
    if (!vehicles || vehicles.length === 0) return null;
    // 优先查找 hostname 为 localhost 的
    const localVehicle = vehicles.find((v: any) =>
      v.hostname === 'localhost' ||
      v.name?.includes('本机') ||
      v.ip === '127.0.0.1' ||
      v.ip === '0.0.0.0'
    );
    return localVehicle?.id || vehicles[0]?.id || null;
  }, [vehicles]);

  // 使用专用的 taskStore 和 skillStore
  const storeTasks = useTaskStore((state) => state.items);
  const storeSkills = useSkillStore((state) => state.items);
  const setTasks = useTaskStore((state) => state.setItems);
  const setSkills = useSkillStore((state) => state.setItems);
  
  // Get组织Data
  const { treeOrgs, setAllOrgAgents, shouldFetchData, setLoading: setOrgLoading, setError: setOrgError } = useOrgStore();

  // Build options for selects with full object data for tooltips
  // Save完整的task和skill对象Map，Used forDisplayDetailedInformation
  const taskMap = useMemo(() => {
    const map = new Map();
    // ⚠️ 保护机制：只包含有 id 的 tasks
    (storeTasks || []).forEach((t: any) => {
      const key = t.name || t.skill;
      if (key && t.id) map.set(key, t);
    });
    return map;
  }, [storeTasks]);

  const skillMap = useMemo(() => {
    const map = new Map();
    // ⚠️ 保护机制：只包含有 id 的 skills
    (storeSkills || []).forEach((s: any) => {
      if (s.name && s.id) map.set(s.name, s);
    });
    return map;
  }, [storeSkills]);

  // For tasks, use task name or skill; for skills, use skill.name.
  const taskOptions = useMemo(() => {
    // ⚠️ 保护机制：标记代码生成的 tasks（通过 source 字段判断）
    // 去重：按 name 分组，收集所有同名项，然后选择优先级最高的（UI > Code）
    const taskGroups = new Map<string, any[]>();
    (storeTasks || []).forEach((t: any) => {
      const name = t.name || t.skill;
      if (!name) return;
      
      if (!taskGroups.has(name)) {
        taskGroups.set(name, []);
      }
      taskGroups.get(name)!.push(t);
    });
    
    // 对每组同名 tasks，选择优先级最高的：UI 创建 > 代码生成
    const uniqueTasks = Array.from(taskGroups.values()).map(group => {
      // 优先选择 UI 创建的（source !== 'code'）
      const uiTask = group.find(t => !isCodeGenerated(t));
      const selected = uiTask || group[0]; // 如果都是 code，选第一个
      
      return {
        id: selected.id,
        name: selected.name || selected.skill,
        isCodeGen: isCodeGenerated(selected),
      };
    });
    
    return uniqueTasks.map((t: any) => ({
      key: t.id || `task-${t.name}`,
      label: t.name,
      value: t.name, // ✅ 使用 name 作为 value（与 Agent 保存格式一致）
      disabled: t.isCodeGen,
      hasId: !t.isCodeGen, // hasId: false 表示代码生成的项，显示红色 ❌
    }));
  }, [storeTasks]);

  const skillOptions = useMemo(() => {
    // ⚠️ 保护机制：标记代码生成的 skills（通过 source 字段判断）
    // 去重：按 name 分组，收集所有同名项，然后选择优先级最高的（UI > Code）
    const skillGroups = new Map<string, any[]>();
    (storeSkills || []).forEach((s: any) => {
      const name = s.name;
      if (!name) return;
      
      if (!skillGroups.has(name)) {
        skillGroups.set(name, []);
      }
      skillGroups.get(name)!.push(s);
    });
    
    // 对每组同名 skills，选择优先级最高的：UI 创建 > 代码生成
    const uniqueSkills = Array.from(skillGroups.values()).map(group => {
      // 优先选择 UI 创建的（source !== 'code'）
      const uiSkill = group.find(s => !isCodeGenerated(s));
      const selected = uiSkill || group[0]; // 如果都是 code，选第一个
      
      return {
        id: selected.id,
        name: selected.name,
        isCodeGen: isCodeGenerated(selected),
      };
    });
    
    return uniqueSkills.map((s: any) => ({
      key: s.id || `skill-${s.name}`,
      label: s.name,
      value: s.name, // ✅ 使用 name 作为 value（与 Agent 保存格式一致）
      disabled: s.isCodeGen,
      hasId: !s.isCodeGen, // hasId: false 表示代码生成的项，显示红色 ❌
    }));
  }, [storeSkills]);

  // 构建组织树形Data供TreeSelect使用（避免LoopReference）
  const organizationTreeData = useMemo(() => {
    const buildTreeData = (node: any, parentPath: string = ''): any => {
      if (!node || !node.id) return null; // Add id Check
      
      // 构建When前节点的完整Path
      const currentPath = parentPath ? `${parentPath} / ${node.name}` : node.name;
      
      // 只提取必要的Field，避免LoopReference
      const treeNode: any = {
        title: currentPath, // 显示完整路径，更清晰
        value: node.id,
        key: node.id,
        fullPath: currentPath, // Storage完整Path，Used for选中后Display
      };
      
      // RecursiveProcess子节点，只传递必要的Data
      if (node.children && Array.isArray(node.children) && node.children.length > 0) {
        treeNode.children = node.children
          .filter((child: any) => child && child.id) // Filter掉无效节点
          .map((child: any) => {
            // 为每个子节点Create简化的对象，只Include必要Field
            const simplifiedChild = {
              id: child.id,
              name: child.name,
              children: child.children
            };
            return buildTreeData(simplifiedChild, currentPath);
          })
          .filter(Boolean);
      }
      
      return treeNode;
    };

    if (treeOrgs && treeOrgs.length > 0) {
      // Create根节点的简化Version
      const rootNode = {
        id: treeOrgs[0].id,
        name: treeOrgs[0].name,
        children: treeOrgs[0].children
      };
      const data = [buildTreeData(rootNode)].filter(Boolean);
      return data;
    }
    return [];
  }, [treeOrgs]);

  // GetWhen前层级及以上的Allagents（Used for上级Select）
  const [supervisorTreeData, setSupervisorTreeData] = useState<any[]>([]);

  // Get vehicles List
  useEffect(() => {
    if (username) {
      fetchVehicles(username).catch((error: any) => {
        console.error('[AgentDetails] Failed to fetch vehicles:', error);
      });
    }
  }, [username, fetchVehicles]);


  // Proactively fetch tasks/skills if empty so dropdowns populate without visiting their pages first
  useEffect(() => {
    const fetchIfNeeded = async () => {
      try {
        const api = get_ipc_api();
        let uname = username;
        if (!uname) {
          const loginInfo = await api.getLastLoginInfo<{ last_login: { username: string } }>();
          if (loginInfo?.success) {
            uname = loginInfo.data?.last_login?.username;
          }
        }
        if (uname) {
          // 并行加载 tasks 和 skills，提高加载速度
          const promises = [];
          
          if (!storeTasks || storeTasks.length === 0) {
            promises.push(
              api.getAgentTasks<{ tasks: any[] }>(uname, [])
                .then((res: any) => {
                  if (res?.success && res.data?.tasks) {
                    setTasks(res.data.tasks as any);
                  }
                })
                .catch((e: any) => {
                  console.warn('[AgentDetails] Failed to load tasks:', e);
                })
            );
          }
          
          if (!storeSkills || storeSkills.length === 0) {
            promises.push(
              api.getAgentSkills<{ skills: any[] }>(uname, [])
                .then((res2: any) => {
                  if (res2?.success && res2.data?.skills) {
                    setSkills(res2.data.skills as any);
                  }
                })
                .catch((e: any) => {
                  console.warn('[AgentDetails] Failed to load skills:', e);
                })
            );
          }
          
          // 等待所有加载完成
          if (promises.length > 0) {
            await Promise.all(promises);
          }
        }
      } catch (e) {
        console.error('[AgentDetails] Error in fetchIfNeeded:', e);
      }
    };
    fetchIfNeeded();
  }, [username, storeTasks?.length, storeSkills?.length, setTasks, setSkills]);

  const [form] = Form.useForm<AgentDetailsForm>();
  const [editMode, setEditMode] = useState(isNew);
  const [loading, setLoading] = useState(false);
  // 使用 ref 追踪初始化状态，避免 KeepAlive 恢复时重置
  const initializedRef = useRef(false);
  const [, forceUpdate] = useState({});
  // Initialize selectedOrgId 为 defaultOrgId（If存在）
  // Avatar Status
  const [avatarData, setAvatarData] = useState<AvatarData | undefined>();

  // Ensure we have a stable agentId for AvatarDisplay even before form finishes loading
  const watchedFormId = Form.useWatch('id', form);
  const resolvedAgentId = (id as string) || (watchedFormId as string) || '';
  
  // 确定Page模式：view（查看）、edit（Edit）、create（新增）
  const pageMode = useMemo(() => {
    if (isNew) return 'create';
    return editMode ? 'edit' : 'view';
  }, [isNew, editMode]);

  // 主动Load组织Data（If未Load）
  useEffect(() => {
    const loadOrgData = async () => {
      if (!username) return;
      
      // If已有Data且不NeedRefresh，则跳过
      if (treeOrgs && treeOrgs.length > 0 && !shouldFetchData()) {
        // 即使使用CacheData，也要确保新建模式下SettingsDefault组织
        if (isNew && defaultOrgId) {
          const currentOrg = form.getFieldValue('org_id');
          if (!currentOrg || currentOrg !== defaultOrgId) {
            form.setFieldsValue({ org_id: defaultOrgId });
          }
        }
        return;
      }

      try {
        setOrgLoading(true);
        const api = get_ipc_api();
        const response = await api.getAllOrgAgents(username) as any;

        if (response?.success && response.data?.orgs) {
          setAllOrgAgents(response.data);

          // DataLoadCompleted后，If是新建模式且有Default组织，SettingsDefaultValue
          if (isNew && defaultOrgId) {
            // 使用 setTimeout 确保在组织树DataUpdate后再SettingsFormValue
            setTimeout(() => {
              form.setFieldsValue({ org_id: defaultOrgId });
            }, 100);
          }
        } else {
          console.error('[AgentDetails] Failed to load org data:', response);
          setOrgError(response?.error?.message || 'Failed to load organization data');
        }
      } catch (e) {
        console.error('[AgentDetails] Error loading org data:', e);
        setOrgError('Error loading organization data');
      } finally {
        setOrgLoading(false);
      }
    };
    
    loadOrgData();
  }, [username, treeOrgs, shouldFetchData, setAllOrgAgents, setOrgLoading, setOrgError, isNew, defaultOrgId, form]);

  // 从IPCGetagentData（Edit模式）
  // Add一个 ref 来跟踪是否刚刚Save过
  const justSavedRef = useRef(false);
  
  useEffect(() => {
    const fetchAgentData = async () => {
      if (isNew || !id || !username) return;
      
      // If刚刚Save过，跳过这次Get（因为Data已经通过 agentStore Update了）
      if (justSavedRef.current) {
        justSavedRef.current = false;
        return;
      }
      
      try {
        setLoading(true);
        const api = get_ipc_api();
        const response = await api.getAgents(username, [id]) as any;
        
        if (response?.success && response.data?.agents && Array.isArray(response.data.agents) && response.data.agents.length > 0) {
          const agent = response.data.agents[0];

          // UpdateFormData
          // 优先使用 agent 自身的 org_id，If没有则使用 URL Parameter中的 defaultOrgId
          const orgId = agent.org_id || agent.organization || defaultOrgId || '';
          
          // Convert skills and tasks from objects to names (for Select component)
          // Skills/tasks from backend are objects with {id, name, ...}
          const skillNames = Array.from(new Set(
            (agent.skills || []).map((s: any) => {
              if (typeof s === 'string') return s;
              // Try multiple fields: name, skill_name, id
              return s.name || s.skill_name || s.id || String(s);
            }).filter(Boolean)  // Remove empty values
          )) as string[];
          
          const taskNames = Array.from(new Set(
            (agent.tasks || []).map((t: any) => {
              if (typeof t === 'string') return t;
              // Try multiple fields: name, task_name, id
              return t.name || t.task_name || t.skill || t.id || String(t);
            }).filter(Boolean)  // Remove empty values
          )) as string[];
          
          // Extract extra_data: if it's an object, get notes; if string, use as is
          let extraDataText = '';
          if (agent.extra_data) {
            if (typeof agent.extra_data === 'object') {
              extraDataText = agent.extra_data.notes || '';
            } else {
              extraDataText = agent.extra_data;
            }
          } else if (agent.metadata) {
            extraDataText = agent.metadata;
          }
          
          // Ensure title and personalities are arrays
          const titleArray = Array.isArray(agent.title) ? agent.title : (agent.title ? [agent.title] : []);
          const personalitiesArray = Array.isArray(agent.personalities) ? agent.personalities : (agent.personalities ? [agent.personalities] : []);
          
          form.setFieldsValue({
            id: agent.card?.id || agent.id,
            name: agent.card?.name || agent.name,
            gender: agent.gender && agent.gender.trim() !== '' ? agent.gender : 'gender_options.male', // 默认为男性
            birthday: agent.birthday ? dayjs(agent.birthday) : null,
            owner: agent.owner || username,
            personalities: personalitiesArray,  // Use personalities (unified naming)
            title: titleArray,
            org_id: orgId,
            supervisor_id: agent.supervisor_id || '',
            tasks: taskNames,
            skills: skillNames,
            vehicle_id: agent.vehicle_id || agent.vehicle || localVehicleId || '',
            description: agent.description || '',
            extra_data: extraDataText
          });
          
          // Settings Avatar Data - 保留完整的Data结构
          if (agent.avatar?.imageUrl) {
            setAvatarData({
              type: agent.avatar.type || 'system',
              imageUrl: agent.avatar.imageUrl,
              videoUrl: agent.avatar.videoPath || agent.avatar.videoUrl || '',
              thumbnailUrl: agent.avatar.thumbnailUrl || agent.avatar.imageUrl || '',
              id: agent.avatar.id || agent.avatar_resource_id || '',
              hash: agent.avatar.hash || ''
            });
          }
          
          // 更新 agentStore，确保面包屑能获取到 agent 名称
          const currentAgents = useAgentStore.getState().agents;
          const agentIndex = currentAgents.findIndex((a: any) => a.id === agent.id || a.card?.id === agent.id);
          if (agentIndex === -1) {
            // Agent 不在 store 中，添加它
            useAgentStore.getState().setAgents([...currentAgents, agent]);
          } else {
            // Agent 已在 store 中，更新它
            const newAgents = [...currentAgents];
            newAgents[agentIndex] = agent;
            useAgentStore.getState().setAgents(newAgents);
          }
          
          // 从 AgentCard Edit进入时，自动进入Edit模式
          setEditMode(true);
          initializedRef.current = true;
          forceUpdate({});
        } else {
          // If没有找到 agent Data，DisplayError
          messageRef.current.error(translationRef.current('pages.agents.fetch_failed') || 'Agent not found');
          initializedRef.current = true;
          forceUpdate({});
        }
      } catch (e) {
        console.error('Failed to fetch agent data:', e);
        messageRef.current.error(translationRef.current('pages.agents.fetch_failed') || 'Failed to fetch agent data');
        initializedRef.current = true;
        forceUpdate({});
      } finally {
        setLoading(false);
      }
    };

    fetchAgentData();
    // 使用 ref 避免 message 和 t 作为依赖触发重复执行
    // 注意：不要添加 localVehicleId 等会变化的值到依赖，否则会覆盖用户输入
  }, [id, isNew, username]);

  // 不再使用 initialValues，改为在 useEffect 中逐个SettingsField，避免LoopReferenceWarning

  // 使用 useEffect 来Settings初始FormValue（仅新建模式）
  // 合并了原来的两个 effect，减少状态更新次数
  const initRef = useRef(false); // 防止重复初始化
  useEffect(() => {
    // 防止重复初始化
    if (initRef.current) return;
    
    if (isNew && organizationTreeData.length > 0) {
      initRef.current = true;
      
      // Create completely independent initial values object to avoid any possible references
      const initialValues: Partial<AgentDetailsForm> = {
        id: '',
        name: '',
        gender: 'gender_options.male', // 默认为男性
        birthday: dayjs(),
        owner: username || 'owner',
        personalities: [],
        title: [],
        org_id: defaultOrgId || '',
        supervisor_id: '',
        tasks: [],
        skills: [],
        vehicle_id: localVehicleId || '',
        description: '',
        extra_data: ''
      };

      // Use setFieldsValue to set all values at once
      form.setFieldsValue(initialValues);
      setEditMode(true);
      initializedRef.current = true;
      forceUpdate({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNew, organizationTreeData.length]);

  // Get supervisor candidates (agents from current and parent organizations)
  useEffect(() => {
    const fetchAgentsForSupervisor = async () => {
      if (!treeOrgs || treeOrgs.length === 0) return;
      
      try {
        // Get agents from currently selected organization
        const currentOrgId = form.getFieldValue('org_id') || defaultOrgId;
        
        if (!currentOrgId) {
          setSupervisorTreeData([]);
          return;
        }
        
        const currentOrgIds = [currentOrgId]; // Convert to array for compatibility with subsequent logic
        
        // Find organization node and return path from root to target node (only return id and name to avoid circular references)
        const findOrgPath = (node: any, targetId: string, path: Array<{id: string, name: string}> = []): Array<{id: string, name: string}> | null => {
          const simplifiedNode = { id: node.id, name: node.name };
          const currentPath = [...path, simplifiedNode];
          
          if (node.id === targetId) return currentPath;
          
          if (node.children && Array.isArray(node.children)) {
            for (const child of node.children) {
              const found = findOrgPath(child, targetId, currentPath);
              if (found) return found;
            }
          }
          return null;
        };
        
        // 根据组织 ID Get完整的组织节点（从原始 treeOrgs 中查找）
        const getOrgNodeById = (root: any, orgId: string): any => {
          if (root.id === orgId) return root;
          if (root.children && Array.isArray(root.children)) {
            for (const child of root.children) {
              const found = getOrgNodeById(child, orgId);
              if (found) return found;
            }
          }
          return null;
        };
        
        // 构建上级Select的树形Data（按组织分组）
        const buildAgentTree = (orgId: string, orgFullPath: string): any => {
          // 从原始树中Get组织节点
          const orgNode = getOrgNodeById(treeOrgs[0], orgId);
          const agents = orgNode?.agents || [];

          if (agents.length === 0) return null;

          // 获取当前 agent 的 ID（用于过滤，不能选择自己作为上级）
          const currentAgentId = form.getFieldValue('id') || id;

          // 只提取必要的Field，避免LoopReference，Filter掉无效节点和当前 agent
          const agentNodes = agents
            .filter((agent: any) => agent && agent.id && agent.id !== currentAgentId) // Filter掉无效的 agent 和自己
            .map((agent: any) => ({
              // 显示格式：Agent名称 (组织完整路径)
              title: `${agent.name || agent.id} (${orgFullPath})`,
              value: agent.id,
              key: agent.id,
              isLeaf: true,
            }));

          // 如果过滤后没有可选的 agent，返回 null
          if (agentNodes.length === 0) return null;

          return {
            title: orgFullPath, // 显示完整路径，更清晰
            value: `org-${orgId}`,
            key: `org-${orgId}`,
            selectable: false,
            children: agentNodes,
          };
        };
        
        const treeData: any[] = [];
        const processedOrgIds = new Set<string>();
        
        // 对每个选中的组织，Get其到根节点的Path（IncludeAll父级组织）
        for (const orgId of currentOrgIds) {
          const orgPath = findOrgPath(treeOrgs[0], orgId);

          if (orgPath) {
            // 为Path上的每个组织构建agent树（从根到When前节点）
            for (let i = 0; i < orgPath.length; i++) {
              const simplifiedOrg = orgPath[i];
              // 避免重复Add
              if (!processedOrgIds.has(simplifiedOrg.id)) {
                processedOrgIds.add(simplifiedOrg.id);
                // 构建完整路径：从根节点到当前节点
                const fullPath = orgPath.slice(0, i + 1).map(org => org.name).join(' / ');
                const tree = buildAgentTree(simplifiedOrg.id, fullPath);
                if (tree) {
                  treeData.push(tree);
                }
              }
            }
          }
        }

        setSupervisorTreeData(treeData);
      } catch (e) {
        console.error('Failed to fetch agents for supervisor selection:', e);
      }
    };
    
    fetchAgentsForSupervisor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, defaultOrgId, treeOrgs.length]);




  const handleDelete = async () => {
    if (!id || !username) return;
    
    const agentName = form.getFieldValue('name') || 'this agent';
    
    showDeleteConfirm({
      title: t('pages.agents.deleteConfirmTitle', 'Delete Agent'),
      message: t('pages.agents.deleteConfirmMessage', `Are you sure you want to delete "${agentName}"? This action cannot be undone.`),
      okText: t('common.delete', 'Delete'),
      cancelText: t('common.cancel', 'Cancel'),
      onOk: async () => {
        try {
          setLoading(true);
          const api = get_ipc_api();
          const response = await api.deleteAgent(username, [id]);
          
          if (response.success) {
            message.success(t('pages.agents.deleteSuccess', 'Agent deleted successfully'));
            
            // 从 agentStore 中Remove已Delete的 agent
            const { removeAgent } = useAgentStore.getState();
            removeAgent(id);
            
            // 同时从 orgStore 中Remove
            const { removeAgentFromOrg } = useOrgStore.getState();
            removeAgentFromOrg(id);
            
            // Refresh组织和 agent Data
            try {
              const api = get_ipc_api();
              const refreshResponse = await api.getAllOrgAgents(username);
              if (refreshResponse?.success && refreshResponse.data) {
                useOrgStore.getState().setAllOrgAgents(refreshResponse.data as any);
              }
            } catch (error) {
              console.error('[AgentDetails] Error refreshing org data after delete:', error);
            }
            
            // 跳转回agentsList页
            navigate('/agents');
          } else {
            message.error(response.error?.message || t('pages.agents.deleteError', 'Failed to delete agent'));
          }
        } catch (error) {
          console.error('[AgentDetails] Delete error:', error);
          message.error(t('pages.agents.deleteError', 'Failed to delete agent'));
        } finally {
          setLoading(false);
        }
      },
    });
  };
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      
      // 检查 skills 和 tasks 数据是否已加载（如果表单中有这些字段）
      const hasSkills = values.skills && values.skills.length > 0;
      const hasTasks = values.tasks && values.tasks.length > 0;
      
      // 如果表单中有 skills/tasks，但 store 中的数据还未加载，给出提示
      if (hasSkills && (!storeSkills || storeSkills.length === 0)) {
        console.warn('[AgentDetails] Skills data not loaded yet, will preserve original values');
      }
      if (hasTasks && (!storeTasks || storeTasks.length === 0)) {
        console.warn('[AgentDetails] Tasks data not loaded yet, will preserve original values');
      }
      
      // Convert skills and tasks from names to IDs
      const skillIds = (values.skills || []).map((skillName: string) => {
        const skill = skillMap.get(skillName);
        return skill?.id || skillName;
      }).filter(Boolean);
      
      const taskIds = (values.tasks || []).map((taskName: string) => {
        const task = taskMap.get(taskName);
        return task?.id || taskName;
      }).filter(Boolean);
      
      // Serialize dayjs and metadata
      const payload = {
        ...values,
        id: values.id || id,  // 确保Include id Field
        birthday: values.birthday ? (values.birthday as Dayjs).toISOString() : null,
        skills: skillIds,  // 只Send ID 数组
        tasks: taskIds,    // 只Send ID 数组
        // Avatar Data - Send avatar_resource_id 而not完整的 avatar Data
        avatar_resource_id: avatarData?.id || null
      };
      setLoading(true);
      const api = get_ipc_api();
      const res = isNew
        ? await api.newAgent(username, [payload])
        : await api.saveAgent(username, [payload]);
      
      if (res.success) {
        message.success(t('common.saved_successfully') || 'Saved');
        
        // 策略：先用返回的DataFastUpdate UI，然后Refresh完整Data确保一致性
        let savedAgentData: any = null;
        try {
          const responseData = res.data as any;
          
          // 第一步：使用返回的 agent Data立即Update UI（FastResponse）
          if (responseData?.agents && Array.isArray(responseData.agents) && responseData.agents.length > 0) {
            savedAgentData = responseData.agents[0];
            
            // TemporaryUpdate agentStore 中的这个 agent（仅Used for立即Display）
            const agentStore = useAgentStore.getState();
            const currentAgents = agentStore.agents;
            const agentIndex = currentAgents.findIndex((a: any) => a.id === savedAgentData.id);
            
            if (agentIndex !== -1) {
              const newAgents = [...currentAgents];
              newAgents[agentIndex] = savedAgentData;
              agentStore.setAgents(newAgents);
            }
          }
          
          // 第二步：等待BackendData完全Update后，Refresh完整的组织和 agent Data
          // 这样Can确保：
          // 1. 组织关系正确（If agent Move到了不同组织）
          // 2. 统计Data正确（组织的 agent Count等）
          // 3. All关联Data都是最新的
          await new Promise(resolve => setTimeout(resolve, 500)); // 增加Delay确保BackendCompleted
          
          const refreshResponse = await api.getAllOrgAgents(username);
          
          if (refreshResponse?.success && refreshResponse.data) {
            // 这会Update orgStore
            useOrgStore.getState().setAllOrgAgents(refreshResponse.data as any);
            
            // 同时更新 agentStore（从 orgStore 提取 agents）
            const orgStoreAgents = useOrgStore.getState().agents;
            if (orgStoreAgents && orgStoreAgents.length > 0) {
              useAgentStore.getState().setAgents(orgStoreAgents as any);
            }
          } else {
            console.error('[AgentDetails] Failed to refresh org data:', refreshResponse);
          }
        } catch (error) {
          console.error('[AgentDetails] Error updating agent data:', error);
        }
        
        // If是Create模式，跳转到 agent List或组织Page
        if (isNew) {
          // AddDelay确保Data已经Update到 store
          await new Promise(resolve => setTimeout(resolve, 100));
          
          const orgId = form.getFieldValue('org_id');
          // 获取根组织 ID
          const rootOrgId = useOrgStore.getState().treeOrgs[0]?.id;
          
          if (orgId && orgId !== rootOrgId) {
            // 跳转到子组织的Page，使用 replace 强制Refresh
            navigate(`/agents/organization/${orgId}`, { replace: true });
          } else {
            // 跳转到 agents 根Page（包括根组织和未分配）
            navigate('/agents', { replace: true });
          }
          return;
        }
        
        // If是Edit模式，使用Save返回的DataUpdateForm（保留在EditPage）
        if (!isNew && id) {
          // 直接调用 getAgents API 获取包含完整 tasks/skills 的数据
          // 不从 agentStore 获取，因为 getAllOrgAgents 返回的数据不包含详细的 tasks
          try {
            const api = get_ipc_api();
            const refreshResponse = await api.getAgents(username, [id]) as any;
            
            let updatedAgent = null;
            if (refreshResponse?.success && refreshResponse.data?.agents && refreshResponse.data.agents.length > 0) {
              updatedAgent = refreshResponse.data.agents[0];
            }
            
            if (updatedAgent) {
              // Convert skills and tasks from objects to names for display in Select component
              const skillNames = (updatedAgent.skills || []).map((s: any) => {
                if (typeof s === 'object' && s !== null) {
                  return s.name || s.skill_name || s.id;
                } else if (typeof s === 'string') {
                  const skillFromMap = Array.from(skillMap.values()).find(skill => skill.id === s);
                  return skillFromMap ? skillFromMap.name : s;
                }
                return null;
              }).filter(Boolean);
              
              const taskNames = (updatedAgent.tasks || []).map((t: any) => {
                if (typeof t === 'object' && t !== null) {
                  return t.name || t.task_name || t.id;
                } else if (typeof t === 'string') {
                  const taskFromMap = Array.from(taskMap.values()).find(task => task.id === t);
                  return taskFromMap ? taskFromMap.name : t;
                }
                return null;
              }).filter(Boolean);
              
              // Extract extra_data: if it's an object, get notes; if string, use as is
              let extraDataText = '';
              if (updatedAgent.extra_data) {
                if (typeof updatedAgent.extra_data === 'object') {
                  extraDataText = updatedAgent.extra_data.notes || '';
                } else {
                  extraDataText = updatedAgent.extra_data;
                }
              }
              
              const formData = {
                id: updatedAgent.card?.id || updatedAgent.id,
                name: updatedAgent.card?.name || updatedAgent.name,
                description: updatedAgent.description || updatedAgent.card?.description || '',
                gender: updatedAgent.gender || 'gender_options.male',
                birthday: updatedAgent.birthday ? dayjs(updatedAgent.birthday) : null,
                owner: updatedAgent.owner || username,
                personalities: updatedAgent.personalities || [],
                title: updatedAgent.title || [],
                org_id: updatedAgent.org_id || '',
                supervisor_id: updatedAgent.supervisor_id || '',
                tasks: taskNames,
                skills: skillNames,
                vehicle_id: updatedAgent.vehicle_id || '',
                extra_data: extraDataText
              };
              
              form.setFieldsValue(formData);
              
              // Update Avatar Data - 保留完整的 avatar Data结构
              if (updatedAgent.avatar) {
                setAvatarData({
                  type: updatedAgent.avatar.type || 'system',
                  imageUrl: updatedAgent.avatar.imageUrl || '',
                  videoUrl: updatedAgent.avatar.videoPath || updatedAgent.avatar.videoUrl || '',
                  thumbnailUrl: updatedAgent.avatar.thumbnailUrl || updatedAgent.avatar.imageUrl || '',
                  id: updatedAgent.avatar.id || updatedAgent.avatar_resource_id || '',
                  hash: updatedAgent.avatar.hash || ''
                });
              }
              
              // Settings标志，防止 useEffect 重新GetData
              justSavedRef.current = true;
            } else {
              console.warn('[AgentDetails] ⚠️ Agent not found in agentStore, falling back to API call');
              // If store 中没有Data，fallback 到 API 调用
              const api = get_ipc_api();
              const refreshResponse = await api.getAgents(username, [id]) as any;
              
              if (refreshResponse?.success && refreshResponse.data?.agents && refreshResponse.data.agents.length > 0) {
                const apiAgent = refreshResponse.data.agents[0];
                
                // Convert并UpdateForm（使用相同的逻辑 - 与上面保持一致）
                const skillNames = (apiAgent.skills || []).map((s: any) => {
                  if (typeof s === 'object' && s !== null) {
                    return s.name || s.skill_name || s.id;
                  } else if (typeof s === 'string') {
                    const skillFromMap = Array.from(skillMap.values()).find(skill => skill.id === s);
                    return skillFromMap ? skillFromMap.name : s;
                  }
                  return null;
                }).filter(Boolean);
                
                const taskNames = (apiAgent.tasks || []).map((t: any) => {
                  if (typeof t === 'object' && t !== null) {
                    return t.name || t.task_name || t.id;
                  } else if (typeof t === 'string') {
                    const taskFromMap = Array.from(taskMap.values()).find(task => task.id === t);
                    return taskFromMap ? taskFromMap.name : t;
                  }
                  return null;
                }).filter(Boolean);
                
                let extraDataText = '';
                if (apiAgent.extra_data) {
                  if (typeof apiAgent.extra_data === 'object') {
                    extraDataText = apiAgent.extra_data.notes || '';
                  } else {
                    extraDataText = apiAgent.extra_data;
                  }
                }
                
                const formData = {
                  id: apiAgent.card?.id || apiAgent.id,
                  name: apiAgent.card?.name || apiAgent.name,
                  description: apiAgent.description || apiAgent.card?.description || '',
                  gender: apiAgent.gender || 'gender_options.male',
                  birthday: apiAgent.birthday ? dayjs(apiAgent.birthday) : null,
                  owner: apiAgent.owner || username,
                  personalities: apiAgent.personalities || [],
                  title: apiAgent.title || [],
                  org_id: apiAgent.org_id || '',
                  supervisor_id: apiAgent.supervisor_id || '',
                  tasks: taskNames,
                  skills: skillNames,
                  vehicle_id: apiAgent.vehicle_id || '',
                  extra_data: extraDataText
                };
                
                form.setFieldsValue(formData);
                
                if (apiAgent.avatar?.imageUrl) {
                  setAvatarData({
                    type: apiAgent.avatar.type || 'system',
                    imageUrl: apiAgent.avatar.imageUrl,
                    videoUrl: apiAgent.avatar.videoPath || apiAgent.avatar.videoUrl || '',
                    thumbnailUrl: apiAgent.avatar.thumbnailUrl || apiAgent.avatar.imageUrl || '',
                    id: apiAgent.avatar.id || apiAgent.avatar_resource_id || '',
                    hash: apiAgent.avatar.hash || ''
                  });
                }
                
              }
            }
          } catch (error) {
            console.error('[AgentDetails] ❌ Error refreshing agent data:', error);
          }
        }
        
        // ✅ 保持在Edit模式，AllowUser继续Edit
        // setEditMode(false);  // ← Remove这行，保持Edit模式
        
        if (isNew) {
          // After creation, navigate back to the OrgNavigator page with refresh flag
          const orgId = values.org_id;
          // 获取根组织 ID
          const rootOrgId = useOrgStore.getState().treeOrgs[0]?.id;
          
          if (orgId && orgId !== 'root' && orgId !== rootOrgId) {
            // 跳转到子组织的navigatorPage，AddTime戳强制Refresh
            navigate(`/agents/organization/${orgId}?refresh=${Date.now()}`);
          } else {
            // 跳转到根navigatorPage，AddTime戳强制Refresh（包括根组织和未分配）
            navigate(`/agents?refresh=${Date.now()}`);
          }
        }
      } else {
        // Check if this is a validation error for skills/tasks
        const errorData = res.error as any;
        if (errorData?.invalid_skills || errorData?.invalid_tasks) {
          // Build detailed error message
          let errorMsg = t('pages.agents.validation_error', 'Validation Error') + ':\n';
          
          if (errorData.invalid_skills && errorData.invalid_skills.length > 0) {
            errorMsg += `\n${t('pages.agents.invalid_skills', 'Invalid Skills')}: ${errorData.invalid_skills.join(', ')}`;
          }
          
          if (errorData.invalid_tasks && errorData.invalid_tasks.length > 0) {
            errorMsg += `\n${t('pages.agents.invalid_tasks', 'Invalid Tasks')}: ${errorData.invalid_tasks.join(', ')}`;
          }
          
          errorMsg += `\n\n${t('pages.agents.validation_hint', 'These items do not exist in the database. Please remove them and try again.')}`;
          
          Modal.error({
            title: t('pages.agents.save_failed', 'Save Failed'),
            content: errorMsg,
            width: 500,
          });
        } else {
          message.error(res.error?.message || t('common.save_failed') || 'Save failed');
        }
      }
    } catch (e: any) {
      message.error(e?.message || t('common.validation_failed') || 'Validation failed');
    } finally {
      setLoading(false);
    }
  };

  // 在初始化完成前显示 loading 状态，避免闪烁
  if (!initializedRef.current) {
    return (
      <div style={{ 
        paddingTop: 70,
        height: '100%', 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center',
        background: 'var(--bg-primary, #0f172a)'
      }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <>
      <style>{`
        .resizable-textarea .ant-input {
          resize: vertical !important;
          min-height: 200px !important;
          overflow: auto !important;
        }
        .resizable-textarea textarea {
          resize: vertical !important;
          min-height: 200px !important;
          overflow: auto !important;
        }
        .agent-basic-info-section {
          display: flex;
          gap: 40px;
          margin-bottom: 24px;
          align-items: center;
        }
        .agent-basic-info-left {
          flex: 1;
        }
        .agent-basic-info-left .ant-form-item {
          margin-bottom: 0;
        }
        .agent-basic-info-left .ant-form-item-label {
          padding-bottom: 4px;
        }
        .agent-basic-info-left .ant-form-item-label > label {
          height: auto;
        }
        .agent-basic-info-right {
          flex-shrink: 0;
          width: 280px;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
      `}</style>
      <div style={{ padding: '70px 16px 16px 16px', height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Card style={{ flex: 1, minHeight: 0, overflow: 'hidden' }} styles={{ body: { padding: 16, height: '100%', overflow: 'hidden' } }}>
          <div ref={scrollContainerRef} style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden', paddingRight: 8 }}>
          <Form
            form={form}
            layout="vertical"
            style={{ maxWidth: '100%' }}
            autoComplete="off"
            role="form"
            aria-label={t('pages.agents.form_label') || 'Agent Details Form'}
            initialValues={{
              gender: 'gender_options.male', // 默认为男性
              skills: [],
              tasks: [],
              personalities: [],
              title: []
            }}
          >
            {/* Basic Info Section with Avatar on the right */}
            <div className="agent-basic-info-section">
              <div className="agent-basic-info-left">
                {/* Name - with label on top */}
                <Form.Item 
                  name="name" 
                  label={t('common.name') || 'Name'}
                  htmlFor="agent-name"
                  rules={[{ required: true, message: t('common.please_input_name') || 'Please input name' }]}
                  style={{ marginBottom: 0 }}
                >
                  <Input
                    id="agent-name"
                    placeholder={t('common.name') || 'Name'}
                    disabled={!editMode}
                    autoComplete="name"
                    aria-label={t('common.name') || 'Name'}
                    aria-required="true"
                  />
                </Form.Item>
              </div>
              
              <div className="agent-basic-info-right">
                <AvatarManager
                  username={username || 'default'}
                  value={avatarData}
                  onChange={setAvatarData}
                  showVideo={true}
                  agentId={resolvedAgentId}
                />
                {/* Agent ID box for quick reference */}
                <div
                  style={{
                    marginTop: 8,
                    width: '100%',
                    padding: '8px 10px',
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: 6,
                    color: 'rgba(255,255,255,0.85)',
                    fontSize: 12
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Agent ID</div>
                  <div style={{
                    fontFamily: 'monospace',
                    wordBreak: 'break-all',
                    userSelect: 'text'
                  }}>
                    {watchedFormId || id || ''}
                  </div>
                </div>
              </div>
            </div>
            
            {/* Divider */}
            <div style={{ 
              height: '1px', 
              background: 'linear-gradient(to right, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.3), rgba(255, 255, 255, 0.1))',
              margin: '24px 0'
            }} />
            <Row gutter={[12, 0]} style={{ margin: 0 }}>
              {/* 第一行：Owner 和 Gender */}
              <Col span={12}>
                <StyledFormItem name="owner" label={t('common.owner') || 'Owner'} htmlFor="agent-owner">
                  <Input
                    id="agent-owner"
                    placeholder={t('common.owner') || 'Owner'}
                    disabled={pageMode !== 'create'}
                    autoComplete="username"
                    aria-label={t('common.owner') || 'Owner'}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ 
                    paddingBottom: 8,
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'rgba(255, 255, 255, 0.95)',
                    letterSpacing: '0.3px'
                  }}>
                    {t('common.gender') || 'Gender'}
                  </div>
                  <Form.Item name="gender" noStyle>
                    <Radio.Group 
                      disabled={!editMode} 
                      aria-label={t('common.gender') || 'Gender'}
                    >
                      <Radio value="gender_options.male">{t('common.gender_options.male') || 'Male'}</Radio>
                      <Radio value="gender_options.female">{t('common.gender_options.female') || 'Female'}</Radio>
                    </Radio.Group>
                  </Form.Item>
                </div>
              </Col>
              
              {/* 第二行：Description */}
              <Col span={24}>
                <StyledFormItem name="description" label={t('pages.agents.description') || 'Description'} htmlFor="agent-description">
                  <Input.TextArea
                    id="agent-description"
                    rows={3}
                    disabled={!editMode}
                    autoComplete="off"
                    placeholder={t('pages.agents.description_placeholder') || 'Enter agent description'}
                    aria-label={t('pages.agents.description') || 'Description'}
                    className="resizable-textarea"
                    style={{ minHeight: '80px', resize: 'vertical' }}
                  />
                </StyledFormItem>
              </Col>

              {/* 第二行：Birthday 和 Vehicle */}
              <Col span={12}>
                <StyledFormItem name="birthday" label={t('common.birthday') || 'Birthday'} htmlFor="agent-birthday">
                  <DatePicker
                    id="agent-birthday"
                    style={{ width: '100%' }}
                    disabled={!editMode}
                    getPopupContainer={() => document.body}
                    placement="bottomLeft"
                    aria-label={t('common.birthday') || 'Birthday'}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem name="vehicle_id" label={t('pages.agents.vehicle') || 'Vehicle'} htmlFor="agent-vehicle">
                  <Select
                    id="agent-vehicle"
                    disabled={!editMode}
                    allowClear
                    placeholder={t('common.select_vehicle') || 'Select vehicle'}
                    options={vehicles.map((v: any, index: number) => ({
                      key: v.id || `vehicle-${index}`,  // Add唯一 key
                      value: v.id,
                      label: `${v.name || v.id}${v.ip ? ` (${v.ip})` : ''}`
                    }))}
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                    aria-label={t('pages.agents.vehicle') || 'Vehicle'}
                  />
                </StyledFormItem>
              </Col>

              {/* 第五行：Organization 和 Supervisor */}
              <Col span={12}>
                <StyledFormItem
                  name="org_id"
                  label={t('pages.agents.organization') || 'Organization'}
                  rules={[{ required: true, message: t('common.please_select_organization') || 'Please select organization' }]}
                  htmlFor="agent-organization"
                >
                  <TreeSelect
                    id="agent-organization"
                    treeData={organizationTreeData}
                    disabled={!editMode}
                    placeholder={t('common.select_organization') || 'Select organization'}
                    style={{ width: '100%' }}
                    treeDefaultExpandAll
                    allowClear
                    showSearch
                    treeNodeFilterProp="title"
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                    aria-label={t('pages.agents.organization') || 'Organization'}
                    aria-required="true"
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="supervisor_id"
                  label={t('pages.agents.supervisors') || 'Supervisor'}
                  htmlFor="agent-supervisor"
                >
                  <TreeSelect
                    id="agent-supervisor"
                    treeData={supervisorTreeData}
                    disabled={!editMode}
                    placeholder={t('common.select_supervisor') || 'Select supervisor'}
                    style={{ width: '100%' }}
                    treeDefaultExpandAll
                    allowClear
                    getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
                    aria-label={t('pages.agents.supervisors') || 'Supervisor'}
                  />
                </StyledFormItem>
              </Col>

              {/* 第六行：Skills（Required）和 Tasks - 移到 Organization 后面 */}
              <Col span={12}>
                <StyledFormItem
                  name="skills"
                  label={t('pages.agents.skills') || 'Skills'}
                  htmlFor="agent-skills"
                  required
                  rules={[
                    {
                      validator: (_, value) => {
                        if (!value || value.length === 0) {
                          return Promise.reject(new Error(t('pages.agents.skills_required') || 'Please select at least one skill'));
                        }
                        return Promise.resolve();
                      },
                    },
                  ]}
                >
                  <TagsEditor
                    id="agent-skills"
                    options={skillOptions}
                    disabled={!editMode}
                    placeholder={t('common.select_skill') || 'Select skills'}
                    aria-label={t('pages.agents.skills') || 'Skills'}
                    dataMap={skillMap}
                    dataType="skill"
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="tasks"
                  label={t('pages.agents.tasks') || 'Tasks'}
                  htmlFor="agent-tasks"
                  required
                  rules={[
                    {
                      validator: (_, value) => {
                        if (!value || value.length === 0) {
                          return Promise.reject(new Error(t('pages.agents.tasks_required') || 'Please select at least one task'));
                        }
                        return Promise.resolve();
                      },
                    },
                  ]}
                >
                  <TagsEditor
                    id="agent-tasks"
                    options={taskOptions}
                    disabled={!editMode}
                    placeholder={t('common.select_task') || 'Select tasks'}
                    aria-label={t('pages.agents.tasks') || 'Tasks'}
                    dataMap={taskMap}
                    dataType="task"
                  />
                </StyledFormItem>
              </Col>

              {/* 第七行：Personality 和 Title */}
              <Col span={12}>
                <StyledFormItem
                  name="personalities"
                  label={t('pages.agents.personality') || 'Personality'}
                  htmlFor="agent-personality"
                >
                  <TagsEditor
                    id="agent-personality"
                    options={knownPersonalities}
                    disabled={!editMode}
                    placeholder={t('common.select_personality') || 'Select personality traits'}
                    aria-label={t('pages.agents.personality') || 'Personality'}
                  />
                </StyledFormItem>
              </Col>
              <Col span={12}>
                <StyledFormItem
                  name="title"
                  label={t('pages.agents.title') || 'Title'}
                  htmlFor="agent-title"
                >
                  <TagsEditor
                    id="agent-title"
                    options={knownTitles}
                    disabled={!editMode}
                    placeholder={t('common.select_title') || 'Select titles'}
                    aria-label={t('pages.agents.title') || 'Title'}
                  />
                </StyledFormItem>
              </Col>

              {/* 第八行：Extra Data */}
              <Col span={24}>
                <StyledFormItem 
                  name="extra_data" 
                  label={t('pages.agents.extra_data') || 'Extra Data / Notes'} 
                  htmlFor="agent-extra-data"
                  tooltip={t('pages.agents.extra_data_tooltip') || 'Must be valid JSON format (e.g., {"key": "value"}) or plain text'}
                  validateTrigger={['onChange', 'onBlur']}
                  rules={[
                    {
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
                              t('pages.agents.extra_data_invalid_json') || 
                              'Invalid JSON format. Please enter valid JSON (e.g., {"key": "value"})'
                            )
                          );
                        }
                      },
                    },
                  ]}
                >
                  <Input.TextArea
                    id="agent-extra-data"
                    rows={4}
                    disabled={!editMode}
                    autoComplete="off"
                    placeholder={t('pages.agents.extra_data_placeholder') || 'Enter valid JSON (e.g., {"notes": "text"}) or plain text'}
                    aria-label={t('pages.agents.extra_data') || 'Extra Data'}
                    className="resizable-textarea"
                    style={{ minHeight: '100px', resize: 'vertical' }}
                  />
                </StyledFormItem>
              </Col>
            </Row>
          </Form>
          </div>
        </Card>

        {/* OperationButton区域 - 固定在Bottom，不随FormScroll */}
        <div 
          style={{ 
            marginTop: '16px',
            padding: '16px 0',
            position: 'sticky',
            bottom: 0,
            zIndex: 100,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 12
          }}
        >
          {/* 新增模式：DisplayClose和SaveButton */}
          {pageMode === 'create' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || 'Close'}
              </Button>
              <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave} size="large">
                {t('common.create') || 'Create'}
              </Button>
            </>
          )}
          
          {/* 查看模式：DisplayClose、Delete和EditButton */}
          {pageMode === 'view' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || 'Close'}
              </Button>
              <Button icon={<DeleteOutlined />} danger onClick={handleDelete} size="large">
                {t('common.delete') || 'Delete'}
              </Button>
              <Button icon={<EditOutlined />} type="default" onClick={() => setEditMode(true)} size="large">
                {t('common.edit') || 'Edit'}
              </Button>
            </>
          )}
          
          {/* Edit模式：DisplayClose、Cancel和SaveButton */}
          {pageMode === 'edit' && (
            <>
              <Button icon={<CloseOutlined />} onClick={() => navigate(-1)} size="large">
                {t('common.close') || 'Close'}
              </Button>
              <Button onClick={() => {
                setEditMode(false);
                // 重新LoadData
                if (!isNew && id && username) {
                  const api = get_ipc_api();
                  api.getAgents(username, [id]).then((response: any) => {
                    if (response?.success && response.data?.agents?.[0]) {
                      const agent = response.data.agents[0];
                      const orgId = agent.org_id || agent.organization || '';
                      form.setFieldsValue({
                        id: agent.card?.id || agent.id,
                        name: agent.card?.name || agent.name,
                        gender: agent.gender || 'gender_options.male',
                        birthday: agent.birthday ? dayjs(agent.birthday) : null,
                        owner: agent.owner || username,
                        personalities: agent.personalities || [],  // Use personalities (unified naming)
                        title: agent.title || [],
                        org_id: orgId,
                        supervisor_id: agent.supervisor_id || '',
                        tasks: agent.tasks || [],
                        skills: agent.skills || [],
                        vehicle_id: agent.vehicle_id || agent.vehicle || localVehicleId || '',
                        description: agent.description || '',
                        extra_data: agent.extra_data || agent.metadata || ''  // Compatible旧Field metadata
                      });
                    }
                  });
                }
              }} size="large">
                {t('common.cancel') || 'Cancel'}
              </Button>
              <Button icon={<SaveOutlined />} type="primary" loading={loading} onClick={handleSave} size="large">
                {t('common.save') || 'Save'}
              </Button>
            </>
          )}
        </div>
      </div>
    </>
  );
};

export default AgentDetails;

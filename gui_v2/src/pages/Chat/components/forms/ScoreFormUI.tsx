import React, { useState } from 'react';
import { Card, Tooltip, Input, Button, Typography, Table, Slider } from '@douyinfe/semi-ui';
import { IconInfoCircle, IconFolder, IconFile, IconChevronDown, IconChevronRight } from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';

// Text content component for displaying chat-like text above form
const TextContent: React.FC<{ text?: string }> = ({ text }) => {
  if (!text?.trim()) return null;
  return (
    <div style={{ 
      marginBottom: 20, 
      padding: 16, 
      backgroundColor: 'var(--semi-color-bg-1)',
      borderRadius: 8,
      border: '1px solid var(--semi-color-border)'
    }}>
      <Typography.Paragraph style={{ 
        whiteSpace: 'pre-wrap', 
        wordBreak: 'break-word',
        margin: 0,
        lineHeight: 1.6,
        color: 'var(--semi-color-text-0)'
      }}>
        {text}
      </Typography.Paragraph>
    </div>
  );
};

interface ScoreComponent {
  name: string;
  type: string;
  raw_value: any;
  target_value?: number;
  max_value?: number;
  min_value?: number;
  unit?: string;
  tooltip?: string;
  score_formula?: string;
  score_lut?: Record<string, number>;
  weight?: number;
  components?: ScoreComponent[]; // for group
  // internal for table row stable key
  _lutRowIds?: Record<string, string>;
}

interface ScoreFormData {
  id: string;
  type: 'score';
  title?: string;
  components: ScoreComponent[];
}

interface ScoreFormUIProps {
  form: ScoreFormData & { text?: string };
  onSubmit?: (form: ScoreFormData, chatId?: string, messageId?: string) => void;
  chatId?: string;
  messageId?: string;
}

// 校验同级weight总和是否为1
function checkWeightSum(components: ScoreComponent[]): boolean {
  const sum = components.reduce((acc, c) => acc + (Number(c.weight) || 0), 0);
  return Math.abs(sum - 1) < 1e-6;
}

// 1. ToolFunction：生成唯一ID
function genRowId() {
  return Math.random().toString(36).slice(2) + Date.now();
}
// Initialize时为每个 score_lut 生成 _lutRowIds
function addLutRowIds(obj: any) {
  if (obj && typeof obj === 'object') {
    if (obj.score_lut && !obj._lutRowIds) {
      obj._lutRowIds = {};
      Object.keys(obj.score_lut).forEach(k => {
        obj._lutRowIds[k] = genRowId();
      });
    }
    if (obj.components) obj.components.forEach(addLutRowIds);
    if (obj.raw_value && typeof obj.raw_value === 'object') Object.values(obj.raw_value).forEach(addLutRowIds);
  }
}

const ScoreFormUI: React.FC<ScoreFormUIProps> = ({ form, onSubmit, chatId, messageId }) => {
  const { t } = useTranslation();
  const [formState, setFormState] = useState<ScoreFormData>(() => {
    const copy = JSON.parse(JSON.stringify(form));
    addLutRowIds(copy);
    return copy;
  });
  const [collapsedStates, setCollapsedStates] = useState<Record<string, boolean>>({});

  // ToolFunction：RecursivePositioning到path的对象
  const getNodeByPath = (obj: any, path: string[]) => {
    let node = obj;
    for (const p of path) node = node[p];
    return node;
  };

  // score_lut Operation
  const updateLutKey = (path: string[], idx: number, newKey: string) => {
    setFormState(prev => {
      const newState = JSON.parse(JSON.stringify(prev));
      const node = getNodeByPath(newState, path);
      const entries = Object.entries(node.score_lut || {});
      const [oldKey, value] = entries[idx];
      // Update _lutRowIds
      if (!node._lutRowIds) node._lutRowIds = {};
      const rowId = node._lutRowIds[oldKey] || genRowId();
      delete node._lutRowIds[oldKey];
      node._lutRowIds[newKey] = rowId;
      entries[idx] = [newKey, value];
      node.score_lut = Object.fromEntries(entries.filter(([k]) => k));
      return newState;
    });
  };
  const updateLutValue = (path: string[], idx: number, newValue: string) => {
    setFormState(prev => {
      const newState = JSON.parse(JSON.stringify(prev));
      const node = getNodeByPath(newState, path);
      const entries = Object.entries(node.score_lut || {});
      const [key] = entries[idx];
      entries[idx] = [key, newValue];
      node.score_lut = Object.fromEntries(entries.filter(([k]) => k));
      return newState;
    });
  };
  const removeLutRow = (path: string[], idx: number) => {
    setFormState(prev => {
      const newState = JSON.parse(JSON.stringify(prev));
      const node = getNodeByPath(newState, path);
      const entries = Object.entries(node.score_lut || {});
      const [key] = entries[idx];
      entries.splice(idx, 1);
      node.score_lut = Object.fromEntries(entries);
      if (node._lutRowIds) delete node._lutRowIds[key];
      return newState;
    });
  };
  const addLutRow = (path: string[]) => {
    setFormState(prev => {
      const newState = JSON.parse(JSON.stringify(prev));
      const node = getNodeByPath(newState, path);
      if (!node.score_lut) node.score_lut = {};
      if (!node._lutRowIds) node._lutRowIds = {};
      let newKey = '';
      let i = 1;
      while (node.score_lut.hasOwnProperty(newKey) || node._lutRowIds.hasOwnProperty(newKey)) {
        newKey = `new_${i++}`;
      }
      node.score_lut[newKey] = '';
      node._lutRowIds[newKey] = genRowId();
      return newState;
    });
  };

  // Toggle折叠Status
  const toggleCollapse = (path: string[]) => {
    const pathKey = path.join('.');
    setCollapsedStates(prev => ({
      ...prev,
      [pathKey]: !prev[pathKey]
    }));
  };

  // RecursiveRender评分项/分组
  const renderComponent = (comp: ScoreComponent, path: string[] = [], parentComponents?: ScoreComponent[]) => {
    const pathKey = path.join('.');
    const isCollapsed = collapsedStates[pathKey] || false;

    // 分组Component
    if (comp.components && Array.isArray(comp.components)) {
      // 校验同级weight
      const weightOk = checkWeightSum(comp.components);
      return (
        <Card
          key={pathKey}
          style={{ 
            marginBottom: 24, 
            marginLeft: path.length > 1 ? 24 : 0, 
            borderColor: weightOk ? undefined : 'red', 
            background: weightOk ? undefined : 'rgba(255,0,0,0.06)' 
          }}
          bodyStyle={{ padding: 18 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: isCollapsed ? 0 : 12 }}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <Button
                type="tertiary"
                theme="borderless"
                icon={isCollapsed ? <IconChevronRight /> : <IconChevronDown />}
                onClick={() => toggleCollapse(path)}
                style={{ padding: 4, marginRight: 8 }}
              />
              <Typography.Title heading={5} style={{ fontWeight: 700, marginBottom: 0 }}>
                {comp.name}
              </Typography.Title>
              {comp.tooltip && <Tooltip content={comp.tooltip}><IconInfoCircle style={{ marginLeft: 6, verticalAlign: 'middle', cursor: 'pointer' }} /></Tooltip>}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ color: 'var(--semi-color-text-2)', fontSize: 14 }}>{t('pages.chat.scoreForm.weight')}</span>
              <Input
                value={comp.weight ?? ''}
                onChange={v => {
                  const newState = JSON.parse(JSON.stringify(formState));
                  let node = newState;
                  for (const p of path) node = node[p];
                  node.weight = Number(v);
                  setFormState(newState);
                }}
                placeholder={t('pages.chat.scoreForm.weight')}
                type='number'
                step={0.1}
                style={{ width: 100 }}
              />
            </div>
          </div>
          
          {!isCollapsed && (
            <>
              {!weightOk && (
                <div style={{ color: 'red', marginTop: 8, fontWeight: 500 }}>{t('pages.chat.scoreForm.groupWeightSumError')}</div>
              )}
              <div style={{ marginTop: 12 }}>
                {comp.components.map((subComp, idx) =>
                  renderComponent(subComp, [...path, 'components', String(idx)], comp.components)
                )}
              </div>
            </>
          )}
        </Card>
      );
    }

    // 嵌套raw_value为对象的情况（如 performance）
    if (typeof comp.raw_value === 'object' && comp.raw_value !== null && !Array.isArray(comp.raw_value)) {
      // 计算同级weight校验
      let weightError = false;
      if (parentComponents) {
        const sum = parentComponents.reduce((acc, c) => acc + (Number(c.weight) || 0), 0);
        weightError = Math.abs(sum - 1) > 1e-6;
      }
      return (
        <div key={pathKey} style={{ marginBottom: 20 }}>
          {/* 父Component */}
          <Card
            style={{
              marginBottom: 16,
              marginLeft: path.length > 1 ? 24 : 0,
              border: '1px solid var(--semi-color-border)',
              borderRadius: 8,
              background: 'var(--semi-color-bg-0)'
            }}
            bodyStyle={{ padding: 16 }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: isCollapsed ? 0 : 12 }}>
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <Button
                  type="tertiary"
                  theme="borderless"
                  icon={isCollapsed ? <IconChevronRight /> : <IconChevronDown />}
                  onClick={() => toggleCollapse(path)}
                  style={{ padding: 4, marginRight: 8 }}
                />
                <IconFolder style={{ marginRight: 8, color: 'var(--semi-color-primary)', fontSize: 16 }} />
                <Typography.Text strong style={{ fontSize: 16, color: 'var(--semi-color-text-0)' }}>
                  {comp.name}
                </Typography.Text>
                {comp.tooltip && (
                  <Tooltip content={comp.tooltip}>
                    <IconInfoCircle style={{ marginLeft: 6, verticalAlign: 'middle', cursor: 'pointer', color: 'var(--semi-color-text-2)' }} />
                  </Tooltip>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ color: 'var(--semi-color-text-2)', fontSize: 14 }}>{t('pages.chat.scoreForm.weight')}</span>
                <Input
                  value={comp.weight ?? ''}
                  onChange={v => {
                    const newState = JSON.parse(JSON.stringify(formState));
                    let node = newState;
                    for (const p of path) node = node[p];
                    node.weight = Number(v);
                    setFormState(newState);
                  }}
                  placeholder={t('pages.chat.scoreForm.weight')}
                  type='number'
                  step={0.1}
                  style={{ width: 100, borderColor: weightError ? 'red' : undefined }}
                />
                {weightError && <span style={{ color: 'red', fontSize: 12 }}>{t('pages.chat.scoreForm.weightSumError')}</span>}
              </div>
            </div>
            
            {!isCollapsed && (
              <>
                {/* 父ComponentField */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ minWidth: 64, color: 'var(--semi-color-text-2)', textAlign: 'left' }}>{t('pages.chat.scoreForm.scoreFormula')}</span>
                    <Input
                      value={comp.score_formula ?? ''}
                      onChange={v => {
                        const newState = JSON.parse(JSON.stringify(formState));
                        let node = newState;
                        for (const p of path) node = node[p];
                        node.score_formula = v;
                        setFormState(newState);
                      }}
                      placeholder={t('pages.chat.scoreForm.scoreFormula')}
                      style={{ width: 220, textAlign: 'left' }}
                    />
                  </div>
                  
                  {/* 分数查找表 */}
                  <div>
                                          <Typography.Text strong style={{ marginBottom: 8, display: 'block', color: 'var(--semi-color-text-0)' }}>
                        {t('pages.chat.scoreForm.scoreLookupTable')}
                      </Typography.Text>
                    <Table
                      columns={[
                        {
                          title: t('pages.chat.scoreForm.inputValue'),
                          dataIndex: 'key',
                          render: (text: string, record: any) => (
                            <Input
                              value={text}
                              onChange={val => updateLutKey(path, record._idx, val)}
                              placeholder={t('pages.chat.scoreForm.inputValue')}
                              size="small"
                            />
                          ),
                        },
                        {
                          title: t('pages.chat.scoreForm.score'),
                          dataIndex: 'value',
                          render: (text: string, record: any) => (
                            <Input
                              value={text}
                              onChange={val => updateLutValue(path, record._idx, val)}
                              placeholder={t('pages.chat.scoreForm.score')}
                              type="number"
                              size="small"
                            />
                          ),
                        },
                        {
                          title: '',
                          dataIndex: 'action',
                          render: (_: any, record: any) => (
                            <Button type="danger" theme="borderless" size="small" onClick={() => removeLutRow(path, record._idx)}>{t('pages.chat.scoreForm.delete')}</Button>
                          ),
                        },
                      ]}
                      dataSource={Object.entries(comp.score_lut || {}).map(([key, value], idx) => ({
                        key,
                        value,
                        _idx: idx,
                        _rowId: (comp._lutRowIds && comp._lutRowIds[key]) || `__lut_${idx}`
                      }))}
                      pagination={false}
                      bordered
                      size="small"
                      style={{ marginTop: 4, maxWidth: 350 }}
                      rowKey="_rowId"
                    />
                    <Button size='small' theme='solid' type='primary' onClick={() => addLutRow(path)} style={{ marginTop: 6 }}>{t('pages.chat.scoreForm.addRow')}</Button>
                  </div>
                </div>
              </>
            )}
          </Card>
          
          {!isCollapsed && (
            /* 子ComponentContainer */
            <div style={{ 
              marginLeft: path.length > 1 ? 32 : 8, 
              paddingLeft: 16, 
              borderLeft: '2px solid var(--semi-color-border)',
              position: 'relative'
            }}>
              <div style={{ 
                position: 'absolute', 
                top: 0, 
                left: -6, 
                background: 'var(--semi-color-bg-0)', 
                color: 'var(--semi-color-text-2)', 
                padding: '2px 6px', 
                borderRadius: 4, 
                fontSize: 10, 
                fontWeight: 500,
                border: '1px solid var(--semi-color-border)',
                display: 'flex',
                alignItems: 'center',
                gap: 4
              }}>
                <IconFile style={{ fontSize: 10 }} />
              </div>
              
              {/* Render子Component */}
              <div style={{ paddingTop: 16 }}>
                {Object.entries(comp.raw_value).map(([k, v]) => {
                  // 为子ComponentAddNameDisplay
                  const childComponent = v as ScoreComponent;
                  const childWithName = {
                    ...childComponent,
                    name: k // 使用key作为Name
                  };
                  return renderComponent(childWithName, [...path, 'raw_value', k], Object.values(comp.raw_value) as ScoreComponent[]);
                })}
              </div>
            </div>
          )}
        </div>
      );
    }

    // 叶子评分项
    const min = comp.min_value;
    const max = comp.max_value;
    const showSlider = typeof min === 'number' && typeof max === 'number';
    // 计算同级weight校验
    let weightError = false;
    if (parentComponents) {
      const sum = parentComponents.reduce((acc, c) => acc + (Number(c.weight) || 0), 0);
      weightError = Math.abs(sum - 1) > 1e-6;
    }
    return (
      <Card key={pathKey} style={{ marginBottom: 16, marginLeft: path.length > 1 ? 24 : 0 }} bodyStyle={{ padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: isCollapsed ? 0 : 8 }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <Button
              type="tertiary"
              theme="borderless"
              icon={isCollapsed ? <IconChevronRight /> : <IconChevronDown />}
              onClick={() => toggleCollapse(path)}
              style={{ padding: 4, marginRight: 8 }}
            />
            <Typography.Text strong style={{ fontSize: 16 }}>{comp.name}</Typography.Text>
            {comp.tooltip && <Tooltip content={comp.tooltip}><IconInfoCircle style={{ marginLeft: 6, verticalAlign: 'middle', cursor: 'pointer' }} /></Tooltip>}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ color: 'var(--semi-color-text-2)', fontSize: 14 }}>{t('pages.chat.scoreForm.weight')}</span>
            <Input
              value={comp.weight ?? ''}
              onChange={v => {
                const newState = JSON.parse(JSON.stringify(formState));
                let node = newState;
                for (const p of path) node = node[p];
                node.weight = Number(v);
                setFormState(newState);
              }}
              placeholder={t('pages.chat.scoreForm.weight')}
              type='number'
              step={0.1}
              style={{ width: 100, borderColor: weightError ? 'red' : undefined }}
            />
            {weightError && <span style={{ color: 'red', fontSize: 13 }}>{t('pages.chat.scoreForm.groupWeightSumError')}</span>}
          </div>
        </div>
        
        {!isCollapsed && (
          <>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ minWidth: 64, color: '#888', textAlign: 'left' }}>{t('pages.chat.scoreForm.rawValue')}</span>
              <span style={{ color: '#fff' }}>
                {(typeof comp.raw_value === 'string' || typeof comp.raw_value === 'number')
                  ? `${comp.raw_value} ${comp.unit || ''}`
                  : '--'}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <span style={{ minWidth: 64, color: '#888', textAlign: 'left' }}>{t('pages.chat.scoreForm.targetValue')}</span>
              <Input
                value={comp.target_value ?? comp.raw_value ?? ''}
                onChange={v => {
                  const newState = JSON.parse(JSON.stringify(formState));
                  let node = newState;
                  for (const p of path) node = node[p];
                  node.target_value = v;
                  setFormState(newState);
                }}
                placeholder={t('pages.chat.scoreForm.targetValue')}
                style={{ width: 120, textAlign: 'left' }}
                suffix={comp.unit}
              />
              {showSlider && (
                <Slider
                  min={min}
                  max={max}
                  value={Number(comp.target_value ?? comp.raw_value ?? min)}
                  onChange={v => {
                    const newState = JSON.parse(JSON.stringify(formState));
                    let node = newState;
                    for (const p of path) node = node[p];
                    node.target_value = v;
                    setFormState(newState);
                  }}
                  style={{ width: 180 }}
                  tipFormatter={v => `${v}${comp.unit || ''}`}
                />
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <span style={{ minWidth: 64, color: '#888', textAlign: 'left' }}>{t('pages.chat.scoreForm.scoreFormula')}</span>
              <Input
                value={comp.score_formula ?? ''}
                onChange={v => {
                  const newState = JSON.parse(JSON.stringify(formState));
                  let node = newState;
                  for (const p of path) node = node[p];
                  node.score_formula = v;
                  setFormState(newState);
                }}
                placeholder={t('pages.chat.scoreForm.scoreFormula')}
                style={{ width: 220, textAlign: 'left' }}
              />
            </div>
                          <div style={{ marginBottom: 8 }}>
                <Typography.Text strong>{t('pages.chat.scoreForm.scoreLookupTable')}</Typography.Text>
              <Table
                columns={[
                  {
                    title: t('pages.chat.scoreForm.inputValue'),
                    dataIndex: 'key',
                    render: (text: string, record: any) => (
                      <Input
                        value={text}
                        onChange={val => updateLutKey(path, record._idx, val)}
                        placeholder={t('pages.chat.scoreForm.inputValue')}
                        size="small"
                      />
                    ),
                  },
                  {
                    title: t('pages.chat.scoreForm.score'),
                    dataIndex: 'value',
                    render: (text: string, record: any) => (
                      <Input
                        value={text}
                        onChange={val => updateLutValue(path, record._idx, val)}
                        placeholder={t('pages.chat.scoreForm.score')}
                        type="number"
                        size="small"
                      />
                    ),
                  },
                  {
                    title: '',
                    dataIndex: 'action',
                    render: (_: any, record: any) => (
                      <Button type="danger" theme="borderless" size="small" onClick={() => removeLutRow(path, record._idx)}>{t('pages.chat.scoreForm.delete')}</Button>
                    ),
                  },
                ]}
                dataSource={Object.entries(comp.score_lut || {}).map(([key, value], idx) => ({
                  key,
                  value,
                  _idx: idx,
                  _rowId: (comp._lutRowIds && comp._lutRowIds[key]) || `__lut_${idx}`
                }))}
                pagination={false}
                bordered
                size="small"
                style={{ marginTop: 4, maxWidth: 350 }}
                rowKey="_rowId"
              />
              <Button size='small' theme='solid' type='primary' onClick={() => addLutRow(path)} style={{ marginTop: 6 }}>{t('pages.chat.scoreForm.addRow')}</Button>
            </div>
          </>
        )}
      </Card>
    );
  };

  const handleSubmit = () => {
    onSubmit?.(formState, chatId, messageId);
  };

  return (
    <div>
      {/* Display text content above the form if it exists */}
      <TextContent text={form.text} />
      
      <Card bodyStyle={{ padding: 28 }}>
        {form.title && (
          <>
            <Typography.Title heading={4} style={{ textAlign: 'center', marginBottom: 8 }}>{form.title}</Typography.Title>
            <div style={{ borderBottom: '1px solid var(--semi-color-border)', margin: '0 auto 16px auto', width: '60%' }} />
          </>
        )}
        
        {/* RenderAll第一层Component */}
        {Array.isArray(formState.components) && formState.components.map((comp, idx) => renderComponent(comp, ['components', String(idx)], formState.components))}
        
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
          <Button type="primary" size="large" theme="solid" style={{ minWidth: 120, fontWeight: 600, borderRadius: 8 }} onClick={handleSubmit}>{t('pages.chat.scoreForm.save')}</Button>
        </div>
      </Card>
    </div>
  );
};

export default ScoreFormUI; 
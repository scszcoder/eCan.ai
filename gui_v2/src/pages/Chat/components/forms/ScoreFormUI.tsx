import React from 'react';
import { Card, Tooltip } from '@douyinfe/semi-ui';
import { IconInfoCircle } from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import { DynamicScoreFormProps } from './types';

const ScoreFormUI: React.FC<DynamicScoreFormProps> = ({ form }) => {
  const { t } = useTranslation();
  // 递归渲染评分项
  const renderComponent = (comp: any, parentKey = '') => {
    if (comp.raw_value && typeof comp.raw_value === 'object' && !Array.isArray(comp.raw_value)) {
      return (
        <Card key={parentKey + comp.name} style={{ marginBottom: 16, background: '#f7f9fa' }}>
          <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 16 }}>
            {comp.name} {comp.tooltip && <Tooltip content={comp.tooltip}><IconInfoCircle style={{ marginLeft: 4, color: 'var(--semi-color-primary)', verticalAlign: 'middle', cursor: 'pointer' }} /></Tooltip>}
          </div>
          <div style={{ marginLeft: 16 }}>
            {Object.entries(comp.raw_value).map(([k, v]: [string, any]) => renderComponent(v, parentKey + comp.name + '.'))}
          </div>
        </Card>
      );
    }
    return (
      <div key={parentKey + comp.name} style={{ display: 'flex', alignItems: 'center', marginBottom: 12, padding: 8, borderRadius: 6, background: '#fff', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
        <div style={{ flex: 2, fontWeight: 500, fontSize: 15 }}>
          {comp.name} {comp.tooltip && <Tooltip content={comp.tooltip}><IconInfoCircle style={{ marginLeft: 4, color: 'var(--semi-color-primary)', verticalAlign: 'middle', cursor: 'pointer' }} /></Tooltip>}
        </div>
        <div style={{ flex: 1, textAlign: 'right', color: '#888' }}>{comp.raw_value}{comp.unit ? ' ' + comp.unit : ''}</div>
        {comp.target_value !== undefined && <div style={{ flex: 1, textAlign: 'right', color: '#888' }}>{t('目标')}: {comp.target_value}{comp.unit ? ' ' + comp.unit : ''}</div>}
        {comp.weight !== undefined && <div style={{ flex: 1, textAlign: 'right', color: '#888' }}>{t('权重')}: {comp.weight}</div>}
        {comp.score_formula && <div style={{ flex: 2, textAlign: 'right', color: '#1890ff', fontSize: 13 }}>{t('公式')}: {comp.score_formula}</div>}
        {comp.score_lut && Object.keys(comp.score_lut).length > 0 && (
          <Tooltip content={Object.entries(comp.score_lut).map(([k, v]) => `${k}: ${v}`).join('\n')}><span style={{ marginLeft: 8, color: '#faad14', cursor: 'pointer' }}>{t('分数表')}</span></Tooltip>
        )}
      </div>
    );
  };
  return (
    <Card>
      {form.title && (
        <>
          <div style={{ fontWeight: 600, fontSize: 18, marginBottom: 8, textAlign: 'center' }}>{form.title}</div>
          <div style={{ borderBottom: '1px solid #e5e6eb', margin: '0 auto 16px auto', width: '60%' }} />
        </>
      )}
      {Array.isArray(form.components) && form.components.map((comp: any) => renderComponent(comp))}
    </Card>
  );
};

export default ScoreFormUI; 
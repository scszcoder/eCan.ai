import React from 'react';
import { Checkbox, Col, Form, InputNumber, Row, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import { StyledFormItem } from '@/components/Common/StyledForm';

interface Props {
  currentTaskId?: string;
  allTasks: any[];
}

const sectionStyle: React.CSSProperties = { padding: 8, background: 'rgba(255, 255, 255, 0.02)', borderRadius: 6 };
const titleStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 500, color: 'rgba(255, 255, 255, 0.65)', marginBottom: 8,
  textTransform: 'uppercase', letterSpacing: '0.5px',
};

/** Run rules of a task (priority class, lateness, overlap, prerequisites, exclusive resources). */
const RunRulesFields: React.FC<Props> = ({ currentTaskId, allTasks }) => {
  const { t } = useTranslation();
  const k = (key: string, def: string, o?: any): string =>
    String(t(`pages.tasks.runRules.${key}`, { defaultValue: def, ...(o || {}) }));
  const browserProfile = Form.useWatch('browser_profile_id', { preserve: true });
  const afterTasks: string[] = Form.useWatch('after_tasks', { preserve: true }) || [];
  const taskOptions = (allTasks || [])
    .filter((x) => x && String(x.id) !== String(currentTaskId || ''))
    .map((x) => ({ value: String(x.id), label: x.name || String(x.id) }));

  return (
    <div style={sectionStyle} data-testid="task-run-rules">
      <div style={titleStyle}>{k('title', 'Run rules')}</div>
      <Row gutter={[10, 0]}>
        <Col span={8}>
          <StyledFormItem label={k('runClass', 'Priority class')} tooltip={k('runClassTip', '')} name="run_class">
            <Select data-testid="run-class" options={[
              { value: 'normal', label: k('normal', 'Normal') },
              { value: 'background', label: k('background', 'Background') },
            ]} />
          </StyledFormItem>
        </Col>
        <Col span={8}>
          <StyledFormItem label={k('maxLateness', 'Max lateness (min)')} tooltip={k('maxLatenessTip', '')} name="max_lateness_min">
            <InputNumber min={0} style={{ width: '100%' }} placeholder={k('unlimited', 'No limit')} data-testid="max-lateness" />
          </StyledFormItem>
        </Col>
        <Col span={8}>
          <StyledFormItem label={k('overlap', 'If due while still running')} name="overlap_policy">
            <Select options={[
              { value: 'skip', label: k('overlapSkip', 'Skip this run') },
              { value: 'queue_one', label: k('overlapQueue', 'Run once more afterwards') },
            ]} />
          </StyledFormItem>
        </Col>
        <Col span={16}>
          <StyledFormItem label={k('afterTasks', 'Run after tasks')} tooltip={k('afterTasksTip', '')} name="after_tasks">
            <Select mode="multiple" allowClear showSearch optionFilterProp="label"
              options={taskOptions} data-testid="after-tasks" />
          </StyledFormItem>
        </Col>
        <Col span={8}>
          <StyledFormItem label=" " name="after_require_success" valuePropName="checked">
            <Checkbox disabled={!afterTasks.length}>{k('requireSuccess', 'Only if they succeeded')}</Checkbox>
          </StyledFormItem>
        </Col>
        <Col span={24}>
          <StyledFormItem label={k('exclusive', 'Exclusive resources')} tooltip={k('exclusiveTip', '')} name="exclusive_resources"
            extra={browserProfile ? k('browserAuto', '', { id: browserProfile }) : undefined}>
            <Select mode="tags" tokenSeparators={[',']} open={false}
              placeholder={k('exclusivePlaceholder', 'Type a name and press Enter')} data-testid="exclusive-resources" />
          </StyledFormItem>
        </Col>
      </Row>
    </div>
  );
};

export default RunRulesFields;

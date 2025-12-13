import React from 'react';
import { Form, InputNumber, Select, Input, Divider } from 'antd';
import styled from '@emotion/styled';
import { LabelConfig } from './types';

const PanelContainer = styled.div`
  padding: 16px;
  background: var(--bg-secondary, #1e293b);
  border-radius: 8px;
  height: 100%;
  overflow-y: auto;
`;

const SectionTitle = styled.div`
  font-size: 13px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const StyledForm = styled(Form)`
  .ant-form-item {
    margin-bottom: 12px;
  }
  
  .ant-form-item-label > label {
    color: #cbd5e1;
    font-size: 12px;
  }
  
  .ant-input-number,
  .ant-select,
  .ant-input {
    width: 100%;
  }
`;

interface ConfigPanelProps {
  config: LabelConfig | null;
  isEditable: boolean;
  onChange?: (field: keyof LabelConfig, value: any) => void;
}

const ConfigPanel: React.FC<ConfigPanelProps> = ({ config, isEditable, onChange }) => {
  if (!config) {
    return (
      <PanelContainer>
        <div style={{ color: '#94a3b8', textAlign: 'center', paddingTop: 40 }}>
          Select a configuration to view details
        </div>
      </PanelContainer>
    );
  }

  const handleChange = (field: keyof LabelConfig, value: any) => {
    if (onChange && isEditable) {
      onChange(field, value);
    }
  };

  const inputProps = {
    disabled: !isEditable,
    size: 'small' as const,
  };

  return (
    <PanelContainer>
      <StyledForm layout="vertical" size="small">
        {isEditable && (
          <>
            <SectionTitle>Configuration Info</SectionTitle>
            <Form.Item label="Name">
              <Input
                value={config.name}
                onChange={(e) => handleChange('name', e.target.value)}
                placeholder="Enter configuration name"
                {...inputProps}
              />
            </Form.Item>
            <Divider style={{ margin: '16px 0', borderColor: '#334155' }} />
          </>
        )}

        <SectionTitle>Unit</SectionTitle>
        <Form.Item label="Measurement Unit">
          <Select
            value={config.unit}
            onChange={(value) => handleChange('unit', value)}
            {...inputProps}
            options={[
              { value: 'in', label: 'Inches (in)' },
              { value: 'mm', label: 'Millimeters (mm)' },
            ]}
          />
        </Form.Item>

        <Divider style={{ margin: '16px 0', borderColor: '#334155' }} />

        <SectionTitle>Sheet Dimensions</SectionTitle>
        <Form.Item label="Sheet Width">
          <InputNumber
            value={config.sheet_width}
            onChange={(value) => handleChange('sheet_width', value)}
            min={0}
            step={0.1}
            precision={3}
            addonAfter={config.unit}
            {...inputProps}
          />
        </Form.Item>
        <Form.Item label="Sheet Height">
          <InputNumber
            value={config.sheet_height}
            onChange={(value) => handleChange('sheet_height', value)}
            min={0}
            step={0.1}
            precision={3}
            addonAfter={config.unit}
            {...inputProps}
          />
        </Form.Item>

        <Divider style={{ margin: '16px 0', borderColor: '#334155' }} />

        <SectionTitle>Label Dimensions</SectionTitle>
        <Form.Item label="Label Width">
          <InputNumber
            value={config.label_width}
            onChange={(value) => handleChange('label_width', value)}
            min={0}
            step={0.1}
            precision={3}
            addonAfter={config.unit}
            {...inputProps}
          />
        </Form.Item>
        <Form.Item label="Label Height">
          <InputNumber
            value={config.label_height}
            onChange={(value) => handleChange('label_height', value)}
            min={0}
            step={0.1}
            precision={3}
            addonAfter={config.unit}
            {...inputProps}
          />
        </Form.Item>

        <Divider style={{ margin: '16px 0', borderColor: '#334155' }} />

        <SectionTitle>Margins</SectionTitle>
        <Form.Item label="Top Margin">
          <InputNumber
            value={config.top_margin}
            onChange={(value) => handleChange('top_margin', value)}
            min={0}
            step={0.1}
            precision={3}
            addonAfter={config.unit}
            {...inputProps}
          />
        </Form.Item>
        <Form.Item label="Left Margin">
          <InputNumber
            value={config.left_margin}
            onChange={(value) => handleChange('left_margin', value)}
            min={0}
            step={0.1}
            precision={3}
            addonAfter={config.unit}
            {...inputProps}
          />
        </Form.Item>

        <Divider style={{ margin: '16px 0', borderColor: '#334155' }} />

        <SectionTitle>Layout</SectionTitle>
        <Form.Item label="Rows">
          <InputNumber
            value={config.rows}
            onChange={(value) => handleChange('rows', value)}
            min={1}
            max={100}
            step={1}
            precision={0}
            {...inputProps}
          />
        </Form.Item>
        <Form.Item label="Columns">
          <InputNumber
            value={config.cols}
            onChange={(value) => handleChange('cols', value)}
            min={1}
            max={100}
            step={1}
            precision={0}
            {...inputProps}
          />
        </Form.Item>

        <Divider style={{ margin: '16px 0', borderColor: '#334155' }} />

        <SectionTitle>Pitch (Gap Between Labels)</SectionTitle>
        <Form.Item label="Row Pitch">
          <InputNumber
            value={config.row_pitch}
            onChange={(value) => handleChange('row_pitch', value)}
            min={0}
            step={0.1}
            precision={3}
            addonAfter={config.unit}
            {...inputProps}
          />
        </Form.Item>
        <Form.Item label="Column Pitch">
          <InputNumber
            value={config.col_pitch}
            onChange={(value) => handleChange('col_pitch', value)}
            min={0}
            step={0.1}
            precision={3}
            addonAfter={config.unit}
            {...inputProps}
          />
        </Form.Item>
      </StyledForm>
    </PanelContainer>
  );
};

export default ConfigPanel;

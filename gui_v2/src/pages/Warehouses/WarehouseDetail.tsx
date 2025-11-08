import React, { useMemo, useState } from 'react';
import { Form, Input, Row, Col, Button, Switch, Card } from 'antd';
import type { Warehouse } from './types';

interface WarehouseDetailProps {
  warehouse: Warehouse | null;
  onChange: (w: Warehouse) => void;
}

function parseCostDescriptionToJson(text: string): any {
  // Naive parser: split by lines; extract key: value pairs if present, else collect keywords
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const obj: any = { summary: text.slice(0, 200) };
  for (const line of lines) {
    const m = line.match(/^([A-Za-z0-9 _-]+)\s*[:=]\s*(.+)$/);
    if (m) {
      const key = m[1].trim().replace(/\s+/g, '_').toLowerCase();
      const val = m[2].trim();
      obj[key] = val;
    }
  }
  if (!Object.keys(obj).length) {
    return { summary: text };
  }
  return obj;
}

const WarehouseDetail: React.FC<WarehouseDetailProps> = ({ warehouse, onChange }) => {
  const [edit, setEdit] = useState(false);
  const [form] = Form.useForm<Warehouse>();

  const jsonPreview = useMemo(() => parseCostDescriptionToJson(form.getFieldValue('costDescription') || warehouse?.costDescription || ''), [warehouse, form]);

  if (!warehouse) {
    return <div style={{ padding: 16, color: 'rgba(255,255,255,0.65)' }}>Select a warehouse to view details</div>;
  }

  const initialValues: Warehouse = { ...warehouse };

  const handleSaveToggle = async () => {
    if (edit) {
      const values = await form.validateFields();
      onChange({ ...warehouse, ...values });
    }
    setEdit(!edit);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Switch checked={edit} onChange={() => handleSaveToggle()} />
        <span style={{ color: '#fff' }}>{edit ? 'Save' : 'Edit'}</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 16 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={initialValues}
          disabled={!edit}
        >
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="ID" name="id">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="Contact First Name" name="contactFirstName"><Input /></Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Contact Last Name" name="contactLastName"><Input /></Form.Item>
                </Col>
              </Row>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}><Form.Item label="Phone" name="phone"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label="Email" name="email"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label="Messaging Platform" name="messagingPlatform"><Input /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item label="Messaging ID" name="messagingId"><Input /></Form.Item></Col>
          </Row>

          <Card title="Address" size="small" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={24}><Form.Item label="Street 1" name="address1"><Input /></Form.Item></Col>
              <Col span={24}><Form.Item label="Street 2" name="address2"><Input /></Form.Item></Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}><Form.Item label="City" name="addressCity"><Input /></Form.Item></Col>
              <Col span={8}><Form.Item label="State" name="addressState"><Input /></Form.Item></Col>
              <Col span={8}><Form.Item label="ZIP" name="addressZip"><Input /></Form.Item></Col>
            </Row>
          </Card>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Cost Structure Description" name="costDescription">
                <Input.TextArea autoSize={{ minRows: 6 }} onChange={() => { /* trigger preview via form state */ }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Parsed JSON (preview)">
                <pre style={{ background: '#0b1220', color: '#d6e3ff', padding: 12, borderRadius: 8, maxHeight: 240, overflow: 'auto' }}>
                  {JSON.stringify(jsonPreview, null, 2)}
                </pre>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </div>
    </div>
  );
};

export default WarehouseDetail;

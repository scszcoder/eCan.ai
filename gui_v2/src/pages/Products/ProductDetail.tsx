import React, { useState } from 'react';
import { Form, Input, Row, Col, Checkbox, Button, Space, Select, Divider, Typography } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import type { Product } from './types';

interface ProductDetailProps {
  product: Product | null;
  onChange: (p: Product) => void;
}

const inventoryOptions = [
  { label: 'West Coast Hub', value: 'west' },
  { label: 'East Fulfillment', value: 'east' },
  { label: 'Central', value: 'central' },
];

const dropShipperOptions = [
  { label: 'ShipBob', value: 'ShipBob' },
  { label: 'Deliverr', value: 'Deliverr' },
  { label: 'EasyShip', value: 'EasyShip' },
];

const platformOptions = [
  { label: 'Amazon', value: 'Amazon' },
  { label: 'eBay', value: 'eBay' },
  { label: 'Shopify', value: 'Shopify' },
];

const ProductDetail: React.FC<ProductDetailProps> = ({ product, onChange }) => {
  const [edit, setEdit] = useState(false);
  const [form] = Form.useForm<Product>();

  if (!product) {
    return <div style={{ padding: 16, color: 'rgba(255,255,255,0.65)' }}>Select a product to view details</div>;
  }

  const initialValues: Product = { ...product } as Product;

  const handleSaveToggle = async () => {
    if (edit) {
      const values = await form.validateFields();
      onChange({ ...product, ...values });
    }
    setEdit(!edit);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 16 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={initialValues}
          disabled={!edit}
        >
          <Row gutter={16}>
            <Col span={8}><Form.Item label="ID" name="id" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label="Nick Name" name="nickName"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label="Title" name="title"><Input /></Form.Item></Col>
          </Row>

          <Form.Item label="Features" name="features">
            <Input.TextArea autoSize={{ minRows: 3 }} />
          </Form.Item>

          <Row gutter={16}>
            <Col span={6}><Form.Item label="Size L (inches)" name="sizeL"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item label="Size W (inches)" name="sizeW"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item label="Size H (inches)" name="sizeH"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item label="Weight (oz)" name="weightOz"><Input /></Form.Item></Col>
          </Row>

          <Row gutter={16}>
            <Col span={6}><Form.Item name="fragile" valuePropName="checked"><Checkbox>Fragile</Checkbox></Form.Item></Col>
            <Col span={6}><Form.Item name="batteryInside" valuePropName="checked"><Checkbox>Battery Inside</Checkbox></Form.Item></Col>
            <Col span={6}><Form.Item name="chemical" valuePropName="checked"><Checkbox>Chemical</Checkbox></Form.Item></Col>
            <Col span={6}><Form.Item name="flammable" valuePropName="checked"><Checkbox>Flammable</Checkbox></Form.Item></Col>
          </Row>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>Inventories</Typography.Text></Divider>
          <Form.List name="inventories">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'location']} rules={[{ required: true, message: 'Select location' }]}
                               style={{ minWidth: 200 }}>
                      <Select options={inventoryOptions} placeholder="Location" />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'quantity']} rules={[{ required: true }]}>
                      <Input placeholder="Quantity" />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>Add Inventory</Button>
                </Form.Item>
              </>
            )}
          </Form.List>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>Drop Shippers</Typography.Text></Divider>
          <Form.List name="dropShippers">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'name']} rules={[{ required: true }]}
                               style={{ minWidth: 200 }}>
                      <Select options={dropShipperOptions} placeholder="Name" />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'quantity']} rules={[{ required: true }]}>
                      <Input placeholder="Quantity" />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>Add Drop Shipper</Button>
                </Form.Item>
              </>
            )}
          </Form.List>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>Images / Videos</Typography.Text></Divider>
          <Form.List name="media">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'url']} rules={[{ required: true }]}>
                      <Input placeholder="Link" style={{ minWidth: 280 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'description']}>
                      <Input placeholder="Description" style={{ minWidth: 280 }} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>Add Image/Video</Button>
                </Form.Item>
              </>
            )}
          </Form.List>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>Suppliers</Typography.Text></Divider>
          <Form.List name="suppliers">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'name']} rules={[{ required: true }]}>
                      <Input placeholder="Name" />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'link']}>
                      <Input placeholder="Link" style={{ minWidth: 240 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'factoryUnitPrice']}>
                      <Input placeholder="Factory Unit Price" style={{ minWidth: 160 }} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>Add Supplier</Button>
                </Form.Item>
              </>
            )}
          </Form.List>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>EC Platforms</Typography.Text></Divider>
          <Form.List name="platforms">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'name']}>
                      <Select options={platformOptions} placeholder="Name" style={{ minWidth: 160 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'link']}>
                      <Input placeholder="Link" style={{ minWidth: 240 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'id']}>
                      <Input placeholder="ID" style={{ minWidth: 160 }} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>Add Platform</Button>
                </Form.Item>
              </>
            )}
          </Form.List>
        </Form>
      </div>

      <div style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 12, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <Button type={edit ? 'primary' : 'default'} onClick={handleSaveToggle}>{edit ? 'Save' : 'Edit'}</Button>
      </div>
    </div>
  );
};

export default ProductDetail;

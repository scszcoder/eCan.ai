import React, { useState } from 'react';
import { Form, Input, Row, Col, Checkbox, Button, Space, Select, Divider, Typography } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import type { Product } from './types';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
  const [edit, setEdit] = useState(false);
  const [form] = Form.useForm<Product>();

  if (!product) {
    return <div style={{ padding: 16, color: 'rgba(255,255,255,0.65)' }}>{t('pages.products.empty.selectProduct')}</div>;
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
            <Col span={8}><Form.Item label={t('pages.products.fields.id')} name="id" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label={t('pages.products.fields.nickName')} name="nickName"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item label={t('pages.products.fields.title')} name="title"><Input /></Form.Item></Col>
          </Row>

          <Form.Item label={t('pages.products.fields.features')} name="features">
            <Input.TextArea rows={3} />
          </Form.Item>

          <Row gutter={16}>
            <Col span={6}><Form.Item label={t('pages.products.fields.sizeL')} name="sizeL"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item label={t('pages.products.fields.sizeW')} name="sizeW"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item label={t('pages.products.fields.sizeH')} name="sizeH"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item label={t('pages.products.fields.weightOz')} name="weightOz"><Input /></Form.Item></Col>
          </Row>

          <Row gutter={16}>
            <Col span={6}><Form.Item name="fragile" valuePropName="checked"><Checkbox>{t('pages.products.fields.fragile')}</Checkbox></Form.Item></Col>
            <Col span={6}><Form.Item name="batteryInside" valuePropName="checked"><Checkbox>{t('pages.products.fields.batteryInside')}</Checkbox></Form.Item></Col>
            <Col span={6}><Form.Item name="chemical" valuePropName="checked"><Checkbox>{t('pages.products.fields.chemical')}</Checkbox></Form.Item></Col>
            <Col span={6}><Form.Item name="flammable" valuePropName="checked"><Checkbox>{t('pages.products.fields.flammable')}</Checkbox></Form.Item></Col>
          </Row>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>{t('pages.products.sections.inventories')}</Typography.Text></Divider>
          <Form.List name="inventories">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'location']} rules={[{ required: true, message: t('pages.products.placeholders.selectLocation') }]}
                               style={{ minWidth: 200 }}>
                      <Select options={inventoryOptions} placeholder={t('pages.products.placeholders.location')} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'quantity']} rules={[{ required: true }]}>
                      <Input placeholder={t('pages.products.placeholders.quantity')} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>{t('pages.products.actions.addInventory')}</Button>
                </Form.Item>
              </>
            )}
          </Form.List>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>{t('pages.products.sections.dropShippers')}</Typography.Text></Divider>
          <Form.List name="dropShippers">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'name']} rules={[{ required: true }]}
                               style={{ minWidth: 200 }}>
                      <Select options={dropShipperOptions} placeholder={t('pages.products.placeholders.name')} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'quantity']} rules={[{ required: true }]}>
                      <Input placeholder={t('pages.products.placeholders.quantity')} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>{t('pages.products.actions.addDropShipper')}</Button>
                </Form.Item>
              </>
            )}
          </Form.List>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>{t('pages.products.sections.media')}</Typography.Text></Divider>
          <Form.List name="media">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'url']} rules={[{ required: true }]}>
                      <Input placeholder={t('pages.products.placeholders.link')} style={{ minWidth: 280 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'description']}>
                      <Input placeholder={t('pages.products.placeholders.description')} style={{ minWidth: 280 }} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>{t('pages.products.actions.addMedia')}</Button>
                </Form.Item>
              </>
            )}
          </Form.List>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>{t('pages.products.sections.suppliers')}</Typography.Text></Divider>
          <Form.List name="suppliers">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'name']} rules={[{ required: true }]}>
                      <Input placeholder={t('pages.products.placeholders.name')} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'link']}>
                      <Input placeholder={t('pages.products.placeholders.link')} style={{ minWidth: 240 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'factoryUnitPrice']}>
                      <Input placeholder={t('pages.products.placeholders.factoryUnitPrice')} style={{ minWidth: 160 }} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>{t('pages.products.actions.addSupplier')}</Button>
                </Form.Item>
              </>
            )}
          </Form.List>

          <Divider plain><Typography.Text style={{ color: '#fff' }}>{t('pages.products.sections.platforms')}</Typography.Text></Divider>
          <Form.List name="platforms">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...restField} name={[name, 'name']}>
                      <Select options={platformOptions} placeholder={t('pages.products.placeholders.name')} style={{ minWidth: 160 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'link']}>
                      <Input placeholder={t('pages.products.placeholders.link')} style={{ minWidth: 240 }} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'id']}>
                      <Input placeholder={t('pages.products.placeholders.id')} style={{ minWidth: 160 }} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>{t('pages.products.actions.addPlatform')}</Button>
                </Form.Item>
              </>
            )}
          </Form.List>
        </Form>
      </div>

      <div style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 12, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <Button type={edit ? 'primary' : 'default'} onClick={handleSaveToggle}>{edit ? t('common.save') : t('common.edit')}</Button>
      </div>
    </div>
  );
};

export default ProductDetail;

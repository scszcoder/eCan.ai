import React, { useEffect } from 'react';
import { Modal, Form, Input, Select, Switch } from 'antd';
import { Vehicle } from './types';
import { StyledFormItem } from '@/components/Common/StyledForm';

const { TextArea } = Input;

interface VehicleFormModalProps {
    visible: boolean;
    vehicle?: Vehicle | null;
    onOk: (values: any) => void;
    onCancel: () => void;
    t: any;
}

const VehicleFormModal: React.FC<VehicleFormModalProps> = ({
    visible,
    vehicle,
    onOk,
    onCancel,
    t
}) => {
    const [form] = Form.useForm();
    const isEdit = !!vehicle;

    useEffect(() => {
        if (visible && vehicle) {
            // Edit模式：填充现有Data
            form.setFieldsValue({
                name: vehicle.name,
                ip: vehicle.ip,
                os: vehicle.os,
                arch: vehicle.arch,
                status: vehicle.status || 'offline',
                functions: vehicle.functions,
                test_disabled: vehicle.test_disabled || false,
            });
        } else if (visible && !vehicle) {
            // Add模式：SettingsDefaultValue
            form.setFieldsValue({
                name: '',
                ip: '0.0.0.0',
                os: 'mac',
                arch: 'x86_64',
                status: 'offline',
                functions: '',
                test_disabled: false,
            });
        }
    }, [visible, vehicle, form]);

    const handleOk = async () => {
        try {
            const values = await form.validateFields();
            onOk(values);
            form.resetFields();
        } catch (error) {
            console.error('Form validation failed:', error);
        }
    };

    const handleCancel = () => {
        form.resetFields();
        onCancel();
    };

    return (
        <Modal
            title={isEdit ? t('pages.vehicles.editVehicle') : t('pages.vehicles.addVehicle')}
            open={visible}
            onOk={handleOk}
            onCancel={handleCancel}
            width={600}
            destroyOnHidden
        >
            <Form
                form={form}
                layout="vertical"
                autoComplete="off"
            >
                <StyledFormItem
                    name="name"
                    label={t('pages.vehicles.name')}
                    rules={[
                        { required: true, message: t('pages.vehicles.nameRequired') },
                        { max: 128, message: t('pages.vehicles.nameTooLong') }
                    ]}
                >
                    <Input placeholder={t('pages.vehicles.namePlaceholder')} />
                </StyledFormItem>

                <StyledFormItem
                    name="ip"
                    label={t('pages.vehicles.ipAddress')}
                    rules={[
                        { required: true, message: t('pages.vehicles.ipRequired') },
                        {
                            pattern: /^(\d{1,3}\.){3}\d{1,3}$/,
                            message: t('pages.vehicles.invalidIp')
                        }
                    ]}
                >
                    <Input placeholder="192.168.1.100" />
                </StyledFormItem>

                <StyledFormItem
                    name="os"
                    label={t('pages.vehicles.operatingSystem')}
                    rules={[{ required: true, message: t('pages.vehicles.osRequired') }]}
                >
                    <Select>
                        <Select.Option value="mac">macOS</Select.Option>
                        <Select.Option value="win">Windows</Select.Option>
                        <Select.Option value="linux">Linux</Select.Option>
                    </Select>
                </StyledFormItem>

                <StyledFormItem
                    name="arch"
                    label={t('pages.vehicles.architecture')}
                >
                    <Select>
                        <Select.Option value="x86_64">x86_64 (Intel)</Select.Option>
                        <Select.Option value="arm64">ARM64 (Apple Silicon)</Select.Option>
                        <Select.Option value="amd64">AMD64</Select.Option>
                    </Select>
                </StyledFormItem>

                <StyledFormItem
                    name="status"
                    label={t('pages.vehicles.statusLabel')}
                >
                    <Select>
                        <Select.Option value="active">{t('pages.vehicles.status.active')}</Select.Option>
                        <Select.Option value="offline">{t('pages.vehicles.status.offline')}</Select.Option>
                        <Select.Option value="maintenance">{t('pages.vehicles.status.maintenance')}</Select.Option>
                    </Select>
                </StyledFormItem>

                <StyledFormItem
                    name="functions"
                    label={t('pages.vehicles.functions')}
                >
                    <TextArea 
                        rows={3}
                        placeholder={t('pages.vehicles.functionsPlaceholder')}
                    />
                </StyledFormItem>

                <StyledFormItem
                    name="test_disabled"
                    label={t('pages.vehicles.testDisabled')}
                    valuePropName="checked"
                >
                    <Switch />
                </StyledFormItem>
            </Form>
        </Modal>
    );
};

export default VehicleFormModal;

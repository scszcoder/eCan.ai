/**
 * Schedule Form Modal Component
 * 日程FormModalComponent（Create/Edit）
 */

import React, { useEffect } from 'react';
import { Modal, Form, Input, DatePicker, Select, InputNumber, Checkbox, Space, Row, Col } from 'antd';
import { ClockCircleOutlined, SyncOutlined, CalendarOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { TaskSchedule } from '../Schedule.types';

const { RangePicker } = DatePicker;
const { Option } = Select;

interface ScheduleFormModalProps {
  visible: boolean;
  schedule?: TaskSchedule | null;
  onClose: () => void;
  onSubmit: (values: any) => void;
  loading?: boolean;
}

const ScheduleFormModal: React.FC<ScheduleFormModalProps> = ({
  visible,
  schedule,
  onClose,
  onSubmit,
  loading = false,
}) => {
  const [form] = Form.useForm();
  const isEdit = !!schedule;
  
  useEffect(() => {
    if (visible && schedule) {
      // Edit模式：填充Form
      form.setFieldsValue({
        taskName: schedule.taskName,
        taskId: schedule.taskId,
        repeat_type: schedule.repeat_type,
        repeat_number: schedule.repeat_number,
        repeat_unit: schedule.repeat_unit,
        time_out: schedule.time_out,
        dateRange: [
          dayjs(schedule.start_date_time, 'YYYY-MM-DD HH:mm:ss:SSS'),
          dayjs(schedule.end_date_time, 'YYYY-MM-DD HH:mm:ss:SSS'),
        ],
        week_days: schedule.week_days || [],
        months: schedule.months || [],
      });
    } else if (visible) {
      // Create模式：SettingsDefaultValue
      form.setFieldsValue({
        repeat_type: 'none',
        repeat_number: 1,
        repeat_unit: 'day',
        time_out: 3600,
        week_days: [],
        months: [],
      });
    }
  }, [visible, schedule, form]);
  
  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      
      // ConvertDate格式
      const [startDate, endDate] = values.dateRange;
      const formattedValues = {
        ...values,
        start_date_time: startDate.format('YYYY-MM-DD HH:mm:ss:SSS'),
        end_date_time: endDate.format('YYYY-MM-DD HH:mm:ss:SSS'),
      };
      
      delete formattedValues.dateRange;
      
      onSubmit(formattedValues);
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  };
  
  const handleCancel = () => {
    form.resetFields();
    onClose();
  };
  
  const repeatTypeOptions = [
    { label: '不重复', value: 'none' },
    { label: '按秒', value: 'by seconds' },
    { label: '按分钟', value: 'by minutes' },
    { label: '按小时', value: 'by hours' },
    { label: '按天', value: 'by days' },
    { label: '按周', value: 'by weeks' },
    { label: '按月', value: 'by months' },
    { label: '按年', value: 'by years' },
  ];
  
  const repeatUnitOptions = [
    { label: '秒', value: 'second' },
    { label: '分钟', value: 'minute' },
    { label: '小时', value: 'hour' },
    { label: '天', value: 'day' },
    { label: '周', value: 'week' },
    { label: '月', value: 'month' },
    { label: '年', value: 'year' },
  ];
  
  const weekDayOptions = [
    { label: '周一', value: 'M' },
    { label: '周二', value: 'Tu' },
    { label: '周三', value: 'W' },
    { label: '周四', value: 'Th' },
    { label: '周五', value: 'F' },
    { label: '周六', value: 'SA' },
    { label: '周日', value: 'SU' },
  ];
  
  const monthOptions = [
    { label: '1月', value: 'Jan' },
    { label: '2月', value: 'Feb' },
    { label: '3月', value: 'Mar' },
    { label: '4月', value: 'Apr' },
    { label: '5月', value: 'May' },
    { label: '6月', value: 'Jun' },
    { label: '7月', value: 'Jul' },
    { label: '8月', value: 'Aug' },
    { label: '9月', value: 'Sep' },
    { label: '10月', value: 'Oct' },
    { label: '11月', value: 'Nov' },
    { label: '12月', value: 'Dec' },
  ];
  
  return (
    <Modal
      title={
        <Space>
          <CalendarOutlined />
          {isEdit ? 'Edit日程' : 'Create日程'}
        </Space>
      }
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={loading}
      width={720}
      destroyOnHidden
      okText={isEdit ? 'Save' : 'Create'}
      cancelText="Cancel"
    >
      <Form
        form={form}
        layout="vertical"
        autoComplete="off"
      >
        {/* 基本Information */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="taskName"
              label="任务Name"
              rules={[{ required: true, message: '请Input任务Name' }]}
            >
              <Input 
                placeholder="Input任务Name" 
                prefix={<CalendarOutlined />}
                size="large"
              />
            </Form.Item>
          </Col>
        </Row>
        
        {isEdit && (
          <Row gutter={16}>
            <Col span={24}>
              <Form.Item
                name="taskId"
                label="任务ID"
              >
                <Input disabled />
              </Form.Item>
            </Col>
          </Row>
        )}
        
        {/* TimeRange */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="dateRange"
              label="TimeRange"
              rules={[{ required: true, message: '请SelectTimeRange' }]}
            >
              <RangePicker
                showTime
                format="YYYY-MM-DD HH:mm:ss"
                style={{ width: '100%' }}
                size="large"
              />
            </Form.Item>
          </Col>
        </Row>
        
        {/* 重复Settings */}
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="repeat_type"
              label={
                <Space>
                  <SyncOutlined />
                  重复Type
                </Space>
              }
              rules={[{ required: true, message: '请Select重复Type' }]}
            >
              <Select placeholder="Select重复Type">
                {repeatTypeOptions.map(option => (
                  <Option key={option.value} value={option.value}>
                    {option.label}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item
              name="repeat_number"
              label="重复次数"
              rules={[{ required: true, message: '请Input重复次数' }]}
            >
              <InputNumber
                min={1}
                style={{ width: '100%' }}
                placeholder="次数"
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item
              name="repeat_unit"
              label="重复单位"
              rules={[{ required: true, message: '请Select重复单位' }]}
            >
              <Select placeholder="单位">
                {repeatUnitOptions.map(option => (
                  <Option key={option.value} value={option.value}>
                    {option.label}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>
        
        {/* TimeoutSettings */}
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="time_out"
              label={
                <Space>
                  <ClockCircleOutlined />
                  TimeoutTime（秒）
                </Space>
              }
              rules={[{ required: true, message: '请InputTimeoutTime' }]}
            >
              <InputNumber
                min={1}
                style={{ width: '100%' }}
                placeholder="TimeoutTime"
                addonAfter="秒"
              />
            </Form.Item>
          </Col>
        </Row>
        
        {/* 星期Select */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="week_days"
              label="重复星期（Optional）"
              tooltip="If不Select，表示不Limit星期"
            >
              <Checkbox.Group 
                options={weekDayOptions}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
        </Row>
        
        {/* 月份Select */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="months"
              label="重复月份（Optional）"
              tooltip="If不Select，表示不Limit月份"
            >
              <Checkbox.Group 
                options={monthOptions}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
};

export default ScheduleFormModal;


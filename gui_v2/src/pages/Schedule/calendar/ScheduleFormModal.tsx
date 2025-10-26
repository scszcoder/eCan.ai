/**
 * Schedule Form Modal Component
 * 日程表单弹窗组件（创建/编辑）
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
      // 编辑模式：填充表单
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
      // 创建模式：设置默认值
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
      
      // 转换日期格式
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
          {isEdit ? '编辑日程' : '创建日程'}
        </Space>
      }
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={loading}
      width={720}
      destroyOnHidden
      okText={isEdit ? '保存' : '创建'}
      cancelText="取消"
    >
      <Form
        form={form}
        layout="vertical"
        autoComplete="off"
      >
        {/* 基本信息 */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="taskName"
              label="任务名称"
              rules={[{ required: true, message: '请输入任务名称' }]}
            >
              <Input 
                placeholder="输入任务名称" 
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
        
        {/* 时间范围 */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="dateRange"
              label="时间范围"
              rules={[{ required: true, message: '请选择时间范围' }]}
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
        
        {/* 重复设置 */}
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="repeat_type"
              label={
                <Space>
                  <SyncOutlined />
                  重复类型
                </Space>
              }
              rules={[{ required: true, message: '请选择重复类型' }]}
            >
              <Select placeholder="选择重复类型">
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
              rules={[{ required: true, message: '请输入重复次数' }]}
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
              rules={[{ required: true, message: '请选择重复单位' }]}
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
        
        {/* 超时设置 */}
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="time_out"
              label={
                <Space>
                  <ClockCircleOutlined />
                  超时时间（秒）
                </Space>
              }
              rules={[{ required: true, message: '请输入超时时间' }]}
            >
              <InputNumber
                min={1}
                style={{ width: '100%' }}
                placeholder="超时时间"
                addonAfter="秒"
              />
            </Form.Item>
          </Col>
        </Row>
        
        {/* 星期选择 */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="week_days"
              label="重复星期（可选）"
              tooltip="如果不选择，表示不限制星期"
            >
              <Checkbox.Group 
                options={weekDayOptions}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
        </Row>
        
        {/* 月份选择 */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="months"
              label="重复月份（可选）"
              tooltip="如果不选择，表示不限制月份"
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


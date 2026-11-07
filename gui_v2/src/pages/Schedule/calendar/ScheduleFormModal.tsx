/**
 * Schedule Form Modal Component
 * 日程表单弹窗组件（创建/编辑）
 */

import React, { useEffect } from 'react';
import { Modal, Form, Input, DatePicker, Select, InputNumber, Checkbox, Space, Row, Col } from 'antd';
import { ClockCircleOutlined, SyncOutlined, CalendarOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
    { label: t('pages.schedule.formModal.repeatType.none'), value: 'none' },
    { label: t('pages.schedule.formModal.repeatType.bySeconds'), value: 'by seconds' },
    { label: t('pages.schedule.formModal.repeatType.byMinutes'), value: 'by minutes' },
    { label: t('pages.schedule.formModal.repeatType.byHours'), value: 'by hours' },
    { label: t('pages.schedule.formModal.repeatType.byDays'), value: 'by days' },
    { label: t('pages.schedule.formModal.repeatType.byWeeks'), value: 'by weeks' },
    { label: t('pages.schedule.formModal.repeatType.byMonths'), value: 'by months' },
    { label: t('pages.schedule.formModal.repeatType.byYears'), value: 'by years' },
  ];
  
  const repeatUnitOptions = [
    { label: t('pages.schedule.formModal.repeatUnit.second'), value: 'second' },
    { label: t('pages.schedule.formModal.repeatUnit.minute'), value: 'minute' },
    { label: t('pages.schedule.formModal.repeatUnit.hour'), value: 'hour' },
    { label: t('pages.schedule.formModal.repeatUnit.day'), value: 'day' },
    { label: t('pages.schedule.formModal.repeatUnit.week'), value: 'week' },
    { label: t('pages.schedule.formModal.repeatUnit.month'), value: 'month' },
    { label: t('pages.schedule.formModal.repeatUnit.year'), value: 'year' },
  ];
  
  const weekDayOptions = [
    { label: t('pages.schedule.formModal.weekday.mo'), value: 'M' },
    { label: t('pages.schedule.formModal.weekday.tu'), value: 'Tu' },
    { label: t('pages.schedule.formModal.weekday.we'), value: 'W' },
    { label: t('pages.schedule.formModal.weekday.th'), value: 'Th' },
    { label: t('pages.schedule.formModal.weekday.fr'), value: 'F' },
    { label: t('pages.schedule.formModal.weekday.sa'), value: 'SA' },
    { label: t('pages.schedule.formModal.weekday.su'), value: 'SU' },
  ];
  
  const monthOptions = [
    { label: t('pages.schedule.formModal.month.jan'), value: 'Jan' },
    { label: t('pages.schedule.formModal.month.feb'), value: 'Feb' },
    { label: t('pages.schedule.formModal.month.mar'), value: 'Mar' },
    { label: t('pages.schedule.formModal.month.apr'), value: 'Apr' },
    { label: t('pages.schedule.formModal.month.may'), value: 'May' },
    { label: t('pages.schedule.formModal.month.jun'), value: 'Jun' },
    { label: t('pages.schedule.formModal.month.jul'), value: 'Jul' },
    { label: t('pages.schedule.formModal.month.aug'), value: 'Aug' },
    { label: t('pages.schedule.formModal.month.sep'), value: 'Sep' },
    { label: t('pages.schedule.formModal.month.oct'), value: 'Oct' },
    { label: t('pages.schedule.formModal.month.nov'), value: 'Nov' },
    { label: t('pages.schedule.formModal.month.dec'), value: 'Dec' },
  ];
  
  return (
    <Modal
      title={
        <Space>
          <CalendarOutlined />
          {isEdit ? t('pages.schedule.formModal.editTitle') : t('pages.schedule.formModal.createTitle')}
        </Space>
      }
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={loading}
      width={720}
      destroyOnHidden
      okText={isEdit ? t('common.save') : t('common.create')}
      cancelText={t('common.cancel')}
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
              label={t('pages.schedule.formModal.taskNameLabel')}
              rules={[{ required: true, message: t('pages.schedule.formModal.taskNameRequired') }]}
            >
              <Input 
                placeholder={t('pages.schedule.formModal.taskNamePlaceholder')} 
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
                label={t('pages.schedule.formModal.taskIdLabel')}
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
              label={t('pages.schedule.formModal.timeRangeLabel')}
              rules={[{ required: true, message: t('pages.schedule.formModal.timeRangeRequired') }]}
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
                  {t('pages.schedule.formModal.repeatTypeLabel')}
                </Space>
              }
              rules={[{ required: true, message: t('pages.schedule.formModal.repeatTypeRequired') }]}
            >
              <Select placeholder={t('pages.schedule.formModal.repeatTypePlaceholder')}>
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
              label={t('pages.schedule.formModal.repeatNumberLabel')}
              rules={[{ required: true, message: t('pages.schedule.formModal.repeatNumberRequired') }]}
            >
              <InputNumber
                min={1}
                style={{ width: '100%' }}
                placeholder={t('pages.schedule.formModal.repeatNumberPlaceholder')}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item
              name="repeat_unit"
              label={t('pages.schedule.formModal.repeatUnitLabel')}
              rules={[{ required: true, message: t('pages.schedule.formModal.repeatUnitRequired') }]}
            >
              <Select placeholder={t('pages.schedule.formModal.repeatUnitPlaceholder')}>
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
                  {t('pages.schedule.formModal.timeoutLabel')}
                </Space>
              }
              rules={[{ required: true, message: t('pages.schedule.formModal.timeoutRequired') }]}
            >
              <Space.Compact style={{ width: '100%' }}>
                <InputNumber
                  min={1}
                  style={{ width: '100%' }}
                  placeholder={t('pages.schedule.formModal.timeoutPlaceholder')}
                />
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '0 11px',
                  background: 'var(--surface-subtle)',
                  border: '1px solid var(--border-color-hover)',
                  borderLeft: 0,
                  borderRadius: '0 6px 6px 0',
                  color: 'var(--text-secondary)',
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                }}>{t('pages.schedule.formModal.secondsShort')}</span>
              </Space.Compact>
            </Form.Item>
          </Col>
        </Row>
        
        {/* 星期选择 */}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item
              name="week_days"
              label={t('pages.schedule.formModal.weekDaysLabel')}
              tooltip={t('pages.schedule.formModal.weekDaysTooltip')}
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
              label={t('pages.schedule.formModal.monthsLabel')}
              tooltip={t('pages.schedule.formModal.monthsTooltip')}
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

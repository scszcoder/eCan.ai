/**
 * Schedule Debug Page
 * 日程DebugPage - Used for查看原始Data
 */

import React, { useState, useEffect } from 'react';
import { Card, Button, Table, Tag, Space, Descriptions } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { get_ipc_api } from '@/services/ipc_api';
import type { TaskSchedule } from './Schedule.types';

const ScheduleDebug: React.FC = () => {
  const [schedules, setSchedules] = useState<TaskSchedule[]>([]);
  const [loading, setLoading] = useState(false);
  const [rawResponse, setRawResponse] = useState<any>(null);

  const loadSchedules = async () => {
    setLoading(true);
    try {
      const res = await get_ipc_api().getSchedules<any>();
      console.log('🔍 Raw API Response:', res);
      setRawResponse(res);
      
      if (res.success && res.data) {
        const scheduleData = res.data.schedules as TaskSchedule[];
        console.log('🔍 Schedules Count:', scheduleData.length);
        console.log('🔍 Schedules:', scheduleData);
        setSchedules(scheduleData);
      }
    } catch (error) {
      console.error('🔍 Error:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSchedules();
  }, []);

  const columns = [
    {
      title: 'Task Name',
      dataIndex: 'taskName',
      key: 'taskName',
      width: 200,
    },
    {
      title: 'Start Time',
      dataIndex: 'start_date_time',
      key: 'start_date_time',
      width: 180,
    },
    {
      title: 'End Time',
      dataIndex: 'end_date_time',
      key: 'end_date_time',
      width: 180,
    },
    {
      title: 'Repeat Type',
      dataIndex: 'repeat_type',
      key: 'repeat_type',
      width: 120,
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: 'Execution Status',
      dataIndex: 'executionStatus',
      key: 'executionStatus',
      width: 120,
      render: (status: string) => {
        const colors: Record<string, string> = {
          running: 'green',
          scheduled: 'blue',
          completed: 'default',
          pending: 'orange',
          error: 'red',
        };
        return <Tag color={colors[status] || 'default'}>{status || 'N/A'}</Tag>;
      },
    },
    {
      title: 'Flags',
      key: 'flags',
      width: 150,
      render: (_: any, record: TaskSchedule) => (
        <Space size="small">
          {record.isLongPeriod && <Tag color="blue">Long Period</Tag>}
          {record.isNextExecution && <Tag color="cyan">Next Exec</Tag>}
          {record.alreadyRun && <Tag color="purple">Already Run</Tag>}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="Schedule Debug Information"
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={loadSchedules}
            loading={loading}
          >
            Reload
          </Button>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {/* Summary */}
          <Descriptions title="Summary" bordered size="small">
            <Descriptions.Item label="Total Schedules">
              {schedules.length}
            </Descriptions.Item>
            <Descriptions.Item label="API Success">
              {rawResponse?.success ? 'Yes' : 'No'}
            </Descriptions.Item>
            <Descriptions.Item label="Response Message">
              {rawResponse?.data?.message || 'N/A'}
            </Descriptions.Item>
          </Descriptions>

          {/* Raw Response */}
          <Card title="Raw API Response" size="small">
            <pre style={{ 
              maxHeight: 200, 
              overflow: 'auto', 
              background: '#f5f5f5', 
              padding: 12,
              borderRadius: 4,
            }}>
              {JSON.stringify(rawResponse, null, 2)}
            </pre>
          </Card>

          {/* Schedules Table */}
          <Table
            columns={columns}
            dataSource={schedules}
            rowKey={(record) => record.taskId || Math.random().toString()}
            pagination={{ pageSize: 20 }}
            scroll={{ x: 1200 }}
            size="small"
          />

          {/* First Schedule Detail */}
          {schedules.length > 0 && (
            <Card title="First Schedule Detail" size="small">
              <pre style={{ 
                maxHeight: 300, 
                overflow: 'auto', 
                background: '#f5f5f5', 
                padding: 12,
                borderRadius: 4,
              }}>
                {JSON.stringify(schedules[0], null, 2)}
              </pre>
            </Card>
          )}
        </Space>
      </Card>
    </div>
  );
};

export default ScheduleDebug;

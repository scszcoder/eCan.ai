/**
 * Schedule Calendar Page
 * 日程日历页面（新版）
 */

import React, { useState, useEffect, useCallback } from 'react';
import styled from '@emotion/styled';
import { message } from 'antd';
import { CalendarView } from './calendar';
import type { TaskSchedule } from './Schedule.types';
import type { CalendarEvent } from './calendar/types';
import { get_ipc_api } from '@/services/ipc_api';
import { useTranslation } from 'react-i18next';

const PageContainer = styled.div`
  width: 100%;
  height: 100%;
  padding: 4px; // 最小化padding以最大化可视区域
  background: var(--bg-primary);
`;

const ScheduleCalendar: React.FC = () => {
  const { t } = useTranslation();
  const [schedules, setSchedules] = useState<TaskSchedule[]>([]);
  const [loading, setLoading] = useState(false);

  // Load schedules
  const loadSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await get_ipc_api().getSchedules<any>();
      console.log('📅 Schedule API Response:', res);
      if (res.success && res.data) {
        const scheduleData = res.data.schedules as TaskSchedule[];
        console.log('📅 Loaded Schedules Count:', scheduleData.length);
        console.log('📅 Schedules Data:', scheduleData);
        setSchedules(scheduleData);
      } else {
        console.error('❌ Schedule API failed:', res);
        message.error(t('pages.schedule.loadFailed', '加载日程失败'));
      }
    } catch (error) {
      console.error('❌ Failed to load schedules:', error);
      message.error(t('pages.schedule.loadFailed', '加载日程失败'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadSchedules();
  }, [loadSchedules]);

  // Handle refresh
  const handleRefresh = useCallback(() => {
    loadSchedules();
  }, [loadSchedules]);

  // Handle create schedule
  const handleCreateSchedule = useCallback(async (scheduleData: any) => {
    setLoading(true);
    try {
      // TODO: Implement create schedule API call
      console.log('Creating schedule:', scheduleData);
      message.success(t('pages.schedule.createSuccess', '创建日程成功'));
      await loadSchedules();
    } catch (error) {
      console.error('Failed to create schedule:', error);
      message.error(t('pages.schedule.createFailed', '创建日程失败'));
    } finally {
      setLoading(false);
    }
  }, [t, loadSchedules]);

  // Handle update schedule
  const handleUpdateSchedule = useCallback(async (schedule: TaskSchedule) => {
    setLoading(true);
    try {
      // TODO: Implement update schedule API call
      console.log('Updating schedule:', schedule);
      message.success(t('pages.schedule.updateSuccess', '更新日程成功'));
      await loadSchedules();
    } catch (error) {
      console.error('Failed to update schedule:', error);
      message.error(t('pages.schedule.updateFailed', '更新日程失败'));
    } finally {
      setLoading(false);
    }
  }, [t, loadSchedules]);

  // Handle delete schedule
  const handleDeleteSchedule = useCallback(async (schedule: TaskSchedule) => {
    setLoading(true);
    try {
      // TODO: Implement delete schedule API call
      console.log('Deleting schedule:', schedule);
      message.success(t('pages.schedule.deleteSuccess', '删除日程成功'));
      await loadSchedules();
    } catch (error) {
      console.error('Failed to delete schedule:', error);
      message.error(t('pages.schedule.deleteFailed', '删除日程失败'));
    } finally {
      setLoading(false);
    }
  }, [t, loadSchedules]);

  // Handle run task
  const handleRunTask = useCallback(async (event: CalendarEvent) => {
    try {
      // TODO: Implement run task API call
      console.log('Running task:', event);
      message.success(t('pages.schedule.runSuccess', '任务已启动'));
    } catch (error) {
      console.error('Failed to run task:', error);
      message.error(t('pages.schedule.runFailed', '任务启动失败'));
    }
  }, [t]);

  return (
    <PageContainer>
      <CalendarView
        schedules={schedules}
        onRefresh={handleRefresh}
        onCreateSchedule={handleCreateSchedule}
        onUpdateSchedule={handleUpdateSchedule}
        onDeleteSchedule={handleDeleteSchedule}
        onRunTask={handleRunTask}
        loading={loading}
      />
    </PageContainer>
  );
};

export default ScheduleCalendar;


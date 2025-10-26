import React, { useState, useEffect } from 'react';
import { Button, Tooltip } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import ScheduleList from './ScheduleList';
import ScheduleDetails from './ScheduleDetails';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import type { TaskSchedule } from './Schedule.types';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';

const StyledRefreshButton = styled(Button)`
  &.ant-btn {
    background: transparent !important;
    border: none !important;
    color: rgba(203, 213, 225, 0.9) !important;
    box-shadow: none !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;

    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
      color: rgba(248, 250, 252, 0.95) !important;
    }

    &:active {
      opacity: 0.8 !important;
    }

    .anticon {
      transition: all 0.3s ease !important;
    }
  }
`;


// 主组件
const Schedule: React.FC = () => {
    const { t } = useTranslation();
    const {
        selectedItem: selectedSchedule,
        items: schedules,
        setItems,
        selectItem,
    } = useDetailView<TaskSchedule>([]); // 初始为空

    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        get_ipc_api().getSchedules<any>().then((res: { success: boolean; data?: any }) => {
            if (res.success && res.data) {
                setItems(res.data.schedules as unknown as TaskSchedule[]);
            }
            setLoading(false);
        });
    }, [setItems]);

    const [filters, setFilters] = useState<Record<string, any>>({});

    const handleSearch = (value: string) => {
        // TODO: 实现搜索逻辑
    };

    const handleFilter = (newFilters: Record<string, any>) => {
        setFilters(newFilters);
    };

    const handleFilterReset = () => {
        setFilters({});
    };

    const handleRefresh = () => {
        setLoading(true);
        get_ipc_api().getSchedules<any>().then((res: { success: boolean; data?: any }) => {
            if (res.success && res.data) {
                setItems(res.data.schedules as unknown as TaskSchedule[]);
            }
            setLoading(false);
        });
    };

    if (loading) {
        return <div style={{ textAlign: 'center', padding: 48 }}>{t('common.loading') || '加载中...'}</div>;
    }

    const listTitle = (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <span style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px' }}>{t('pages.schedule.title')}</span>
            <Tooltip title={t('pages.schedule.refresh', '刷新')}>
                <StyledRefreshButton
                    shape="circle"
                    icon={<ReloadOutlined />}
                    onClick={handleRefresh}
                    loading={loading}
                />
            </Tooltip>
        </div>
    );

    return (
        <DetailLayout
            listTitle={listTitle}
            detailsTitle={t('pages.schedule.scheduleDetails')}
            listContent={
                <ScheduleList
                    schedules={schedules}
                    selectedSchedule={selectedSchedule}
                    onSelect={selectItem}
                    onSearch={handleSearch}
                    onFilter={handleFilter}
                    onFilterReset={handleFilterReset}
                    filters={filters}
                />
            }
            detailsContent={
                <ScheduleDetails
                    schedule={selectedSchedule}
                />
            }
        />
    );
};

export default Schedule; 
import React, { useState, useEffect } from 'react';
import { Button, Tooltip } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import ScheduleList from './ScheduleList';
import ScheduleDetails from './ScheduleDetails';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import type { TaskSchedule } from './Schedule.types';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';


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
            <span>{t('pages.schedule.title')}</span>
            <Tooltip title={t('pages.schedule.refresh', '刷新')}>
                <Button
                    type="default"
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
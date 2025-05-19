import React, { useState } from 'react';
import { List, Tag, Typography, Space, Button, Row, Col, Statistic, Card, Badge, Calendar } from 'antd';
import { 
    CalendarOutlined, 
    CheckCircleOutlined, 
    ClockCircleOutlined, 
    TeamOutlined,
    CarOutlined,
    PlusOutlined,
    EditOutlined,
    DeleteOutlined,
    HistoryOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';
import SearchFilter from '../components/Common/SearchFilter';
import ActionButtons from '../components/Common/ActionButtons';
import StatusTag from '../components/Common/StatusTag';
import DetailCard from '../components/Common/DetailCard';
import { useTranslation } from 'react-i18next';

const { Text, Title } = Typography;

const ScheduleItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid #f0f0f0;
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: background-color 0.3s;
    &:hover {
        background-color: #f5f5f5;
    }
`;

interface Schedule {
    id: number;
    title: string;
    type: 'meeting' | 'task' | 'maintenance';
    status: 'scheduled' | 'in-progress' | 'completed' | 'cancelled';
    startTime: string;
    endTime: string;
    location: string;
    participants: string[];
    description: string;
    priority: 'high' | 'medium' | 'low';
}

const initialSchedules: Schedule[] = [
    {
        id: 1,
        title: 'Team Meeting',
        type: 'meeting',
        status: 'scheduled',
        startTime: '2024-03-20 10:00',
        endTime: '2024-03-20 11:00',
        location: 'Conference Room A',
        participants: ['John Doe', 'Jane Smith', 'Mike Johnson'],
        description: 'Weekly team sync meeting to discuss project progress and upcoming tasks.',
        priority: 'high',
    },
    {
        id: 2,
        title: 'Vehicle Maintenance',
        type: 'maintenance',
        status: 'in-progress',
        startTime: '2024-03-20 14:00',
        endTime: '2024-03-20 16:00',
        location: 'Maintenance Bay',
        participants: ['Maintenance Team'],
        description: 'Regular maintenance check for Vehicle Alpha.',
        priority: 'medium',
    },
    {
        id: 3,
        title: 'Delivery Task',
        type: 'task',
        status: 'completed',
        startTime: '2024-03-19 09:00',
        endTime: '2024-03-19 10:00',
        location: 'Zone B',
        participants: ['Delivery Team'],
        description: 'Package delivery to Zone B.',
        priority: 'low',
    },
];

const Schedule: React.FC = () => {
    const { t } = useTranslation();
    const {
        selectedItem: selectedSchedule,
        items: schedules,
        selectItem,
        updateItem,
        removeItem,
    } = useDetailView<Schedule>(initialSchedules);

    const [filters, setFilters] = useState<Record<string, any>>({});

    const handleStatusChange = (id: number, newStatus: Schedule['status']) => {
        updateItem(id, { status: newStatus });
    };

    const handleDelete = (id: number) => {
        removeItem(id);
    };

    const handleSearch = (value: string) => {
        // Implement search logic
    };

    const handleFilterChange = (newFilters: Record<string, any>) => {
        setFilters(prev => ({ ...prev, ...newFilters }));
    };

    const handleReset = () => {
        setFilters({});
    };

    const renderListContent = () => (
        <>
            <Title level={2}>{t('pages.schedule.title')}</Title>
            <SearchFilter
                onSearch={handleSearch}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                filterOptions={[
                    {
                        key: 'status',
                        label: t('pages.schedule.status'),
                        options: [
                            { label: t('pages.schedule.scheduled'), value: 'scheduled' },
                            { label: t('pages.schedule.inProgress'), value: 'in-progress' },
                            { label: t('pages.schedule.completed'), value: 'completed' },
                            { label: t('pages.schedule.cancelled'), value: 'cancelled' },
                        ],
                    },
                    {
                        key: 'type',
                        label: t('pages.schedule.type'),
                        options: [
                            { label: t('pages.schedule.meeting'), value: 'meeting' },
                            { label: t('pages.schedule.task'), value: 'task' },
                            { label: t('pages.schedule.maintenance'), value: 'maintenance' },
                        ],
                    },
                    {
                        key: 'priority',
                        label: t('pages.schedule.priority'),
                        options: [
                            { label: t('pages.schedule.high'), value: 'high' },
                            { label: t('pages.schedule.medium'), value: 'medium' },
                            { label: t('pages.schedule.low'), value: 'low' },
                        ],
                    },
                ]}
                placeholder={t('pages.schedule.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
                addText={t('pages.schedule.addSchedule')}
                editText={t('pages.schedule.editSchedule')}
                deleteText={t('pages.schedule.deleteSchedule')}
                refreshText={t('pages.schedule.refreshSchedule')}
                exportText={t('pages.schedule.exportSchedule')}
                importText={t('pages.schedule.importSchedule')}
                settingsText={t('pages.schedule.scheduleSettings')}
            />
            <List
                dataSource={schedules}
                renderItem={schedule => (
                    <ScheduleItem onClick={() => selectItem(schedule)}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                                <StatusTag status={schedule.status} />
                                <CalendarOutlined />
                                <Text strong>{schedule.title}</Text>
                            </Space>
                            <Space>
                                <Tag color="blue">{t(`pages.schedule.${schedule.type}`)}</Tag>
                                <Tag color={
                                    schedule.priority === 'high' ? 'red' :
                                    schedule.priority === 'medium' ? 'orange' : 'green'
                                }>
                                    {t(`pages.schedule.${schedule.priority}`)} {t('pages.schedule.priority')}
                                </Tag>
                            </Space>
                            <Space>
                                <ClockCircleOutlined />
                                <Text type="secondary">
                                    {schedule.startTime} - {schedule.endTime}
                                </Text>
                            </Space>
                            <Space>
                                <TeamOutlined />
                                <Text type="secondary">
                                    {schedule.participants.length} {t('pages.schedule.participants')}
                                </Text>
                            </Space>
                        </Space>
                    </ScheduleItem>
                )}
            />
        </>
    );

    const renderDetailsContent = () => {
        if (!selectedSchedule) {
            return <Text type="secondary">{t('pages.schedule.selectSchedule')}</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <DetailCard
                    title={t('pages.schedule.scheduleInformation')}
                    items={[
                        {
                            label: t('common.title'),
                            value: selectedSchedule.title,
                            icon: <CalendarOutlined />,
                        },
                        {
                            label: t('pages.schedule.type'),
                            value: t(`pages.schedule.${selectedSchedule.type}`),
                            icon: <CalendarOutlined />,
                        },
                        {
                            label: t('pages.schedule.status'),
                            value: <StatusTag status={selectedSchedule.status} />,
                            icon: <CheckCircleOutlined />,
                        },
                        {
                            label: t('pages.schedule.priority'),
                            value: (
                                <Tag color={
                                    selectedSchedule.priority === 'high' ? 'red' :
                                    selectedSchedule.priority === 'medium' ? 'orange' : 'green'
                                }>
                                    {t(`pages.schedule.${selectedSchedule.priority}`)}
                                </Tag>
                            ),
                            icon: <ClockCircleOutlined />,
                        },
                    ]}
                />
                <DetailCard
                    title={t('pages.schedule.timeAndLocation')}
                    items={[
                        {
                            label: t('pages.schedule.startTime'),
                            value: selectedSchedule.startTime,
                            icon: <ClockCircleOutlined />,
                        },
                        {
                            label: t('pages.schedule.endTime'),
                            value: selectedSchedule.endTime,
                            icon: <ClockCircleOutlined />,
                        },
                        {
                            label: t('pages.schedule.location'),
                            value: selectedSchedule.location,
                            icon: <CarOutlined />,
                        },
                    ]}
                />
                <DetailCard
                    title={t('pages.schedule.participants')}
                    items={[
                        {
                            label: t('pages.schedule.participants'),
                            value: selectedSchedule.participants.join(', '),
                            icon: <TeamOutlined />,
                        },
                    ]}
                />
                <DetailCard
                    title={t('pages.schedule.description')}
                    items={[
                        {
                            label: t('pages.schedule.description'),
                            value: selectedSchedule.description,
                            icon: <EditOutlined />,
                        },
                    ]}
                />
                <Space>
                    <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={() => handleStatusChange(selectedSchedule.id, 'scheduled')}
                        disabled={selectedSchedule.status === 'scheduled'}
                    >
                        {t('pages.schedule.schedule')}
                    </Button>
                    <Button 
                        icon={<ClockCircleOutlined />}
                        onClick={() => handleStatusChange(selectedSchedule.id, 'in-progress')}
                        disabled={selectedSchedule.status === 'in-progress'}
                    >
                        {t('pages.schedule.start')}
                    </Button>
                    <Button 
                        icon={<CheckCircleOutlined />}
                        onClick={() => handleStatusChange(selectedSchedule.id, 'completed')}
                        disabled={selectedSchedule.status === 'completed'}
                    >
                        {t('pages.schedule.complete')}
                    </Button>
                    <Button 
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleDelete(selectedSchedule.id)}
                    >
                        {t('common.delete')}
                    </Button>
                </Space>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle={t('pages.schedule.title')}
            detailsTitle={t('pages.schedule.scheduleDetails')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Schedule; 
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
            <SearchFilter
                onSearch={handleSearch}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                filterOptions={[
                    {
                        key: 'status',
                        label: 'Status',
                        options: [
                            { label: 'Scheduled', value: 'scheduled' },
                            { label: 'In Progress', value: 'in-progress' },
                            { label: 'Completed', value: 'completed' },
                            { label: 'Cancelled', value: 'cancelled' },
                        ],
                    },
                    {
                        key: 'type',
                        label: 'Type',
                        options: [
                            { label: 'Meeting', value: 'meeting' },
                            { label: 'Task', value: 'task' },
                            { label: 'Maintenance', value: 'maintenance' },
                        ],
                    },
                    {
                        key: 'priority',
                        label: 'Priority',
                        options: [
                            { label: 'High', value: 'high' },
                            { label: 'Medium', value: 'medium' },
                            { label: 'Low', value: 'low' },
                        ],
                    },
                ]}
                placeholder="Search schedules..."
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
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
                                <Tag color="blue">{schedule.type}</Tag>
                                <Tag color={
                                    schedule.priority === 'high' ? 'red' :
                                    schedule.priority === 'medium' ? 'orange' : 'green'
                                }>
                                    {schedule.priority} priority
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
                                    {schedule.participants.length} participants
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
            return <Text type="secondary">Select a schedule to view details</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <DetailCard
                    title="Schedule Information"
                    items={[
                        {
                            label: 'Title',
                            value: selectedSchedule.title,
                            icon: <CalendarOutlined />,
                        },
                        {
                            label: 'Type',
                            value: selectedSchedule.type,
                            icon: <CalendarOutlined />,
                        },
                        {
                            label: 'Status',
                            value: <StatusTag status={selectedSchedule.status} />,
                            icon: <CheckCircleOutlined />,
                        },
                        {
                            label: 'Priority',
                            value: (
                                <Tag color={
                                    selectedSchedule.priority === 'high' ? 'red' :
                                    selectedSchedule.priority === 'medium' ? 'orange' : 'green'
                                }>
                                    {selectedSchedule.priority}
                                </Tag>
                            ),
                            icon: <ClockCircleOutlined />,
                        },
                    ]}
                />
                <DetailCard
                    title="Time and Location"
                    items={[
                        {
                            label: 'Start Time',
                            value: selectedSchedule.startTime,
                            icon: <ClockCircleOutlined />,
                        },
                        {
                            label: 'End Time',
                            value: selectedSchedule.endTime,
                            icon: <ClockCircleOutlined />,
                        },
                        {
                            label: 'Location',
                            value: selectedSchedule.location,
                            icon: <CarOutlined />,
                            span: 24,
                        },
                    ]}
                />
                <DetailCard
                    title="Description"
                    items={[
                        {
                            label: 'Details',
                            value: selectedSchedule.description,
                            span: 24,
                        },
                    ]}
                />
                <DetailCard
                    title="Participants"
                    items={[
                        {
                            label: 'Team',
                            value: (
                                <Space wrap>
                                    {selectedSchedule.participants.map(participant => (
                                        <Tag key={participant} icon={<TeamOutlined />}>
                                            {participant}
                                        </Tag>
                                    ))}
                                </Space>
                            ),
                            span: 24,
                        },
                    ]}
                />
                <Space>
                    <Button 
                        type="primary" 
                        icon={<CheckCircleOutlined />}
                        onClick={() => handleStatusChange(selectedSchedule.id, 'completed')}
                        disabled={selectedSchedule.status === 'completed'}
                    >
                        Mark as Completed
                    </Button>
                    <Button 
                        icon={<ClockCircleOutlined />}
                        onClick={() => handleStatusChange(selectedSchedule.id, 'in-progress')}
                        disabled={selectedSchedule.status === 'in-progress'}
                    >
                        Start
                    </Button>
                    <Button 
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleDelete(selectedSchedule.id)}
                    >
                        Delete
                    </Button>
                </Space>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle="Schedule"
            detailsTitle="Schedule Details"
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Schedule; 
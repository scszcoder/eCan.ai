import React, { useState, useCallback, useEffect } from 'react';
import { List, Tag, Typography, Space, Button, Avatar, Row, Col, Progress, Card } from 'antd';
import { 
    OrderedListOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    DownloadOutlined,
    SettingOutlined,
    DeleteOutlined,
    ReloadOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../../components/Common/ActionButtons';
import { IPCAPI } from '@/services/ipc/api';

const { Text, Title } = Typography;

const TaskItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: var(--bg-secondary);
    border-radius: 8px;
    margin: 4px 0;
    &:hover {
        background-color: var(--bg-tertiary);
        transform: translateX(4px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
    .ant-typography {
        color: var(--text-primary);
    }
    .ant-tag {
        background-color: var(--bg-primary);
        border-color: var(--border-color);
    }
    .ant-progress-text {
        color: var(--text-primary);
    }
`;

interface Task {
    id: number;
    name: string;
    version: string;
    status: 'active' | 'updating' | 'error';
    category: string;
    size: string;
    lastUpdated: string;
    rating: number;
    description: string;
    features: string[];
}

const getStatusColor = (status: Task['status']): string => {
    switch (status) {
        case 'active':
            return 'success';
        case 'updating':
            return 'processing';
        case 'error':
            return 'error';
        default:
            return 'default';
    }
};

const initialTasks: Task[] = [
    {
        id: 1,
        name: 'TaskManager',
        version: '2.1.0',
        status: 'active',
        category: 'Productivity',
        size: '45MB',
        lastUpdated: '2 days ago',
        rating: 4.5,
        description: 'TaskManager',
        features: ['TaskCreation', 'ProgressTracking', 'TeamCollaboration', 'FileSharing'],
    },
    {
        id: 2,
        name: 'DataAnalyzer',
        version: '1.5.2',
        status: 'updating',
        category: 'Analytics',
        size: '78MB',
        lastUpdated: '1 hour ago',
        rating: 4.2,
        description: 'DataAnalyzer',
        features: ['DataImport', 'Visualization', 'ReportGeneration', 'ExportOptions'],
    },
    {
        id: 3,
        name: 'SystemMonitor',
        version: '3.0.1',
        status: 'error',
        category: 'System',
        size: '32MB',
        lastUpdated: '1 week ago',
        rating: 4.8,
        description: 'SystemMonitor',
        features: ['ResourceMonitoring', 'AlertSystem', 'PerformanceReports', 'LogAnalysis'],
    },
];

const tasksEventBus = {
    listeners: new Set<(data: Task[]) => void>(),
    subscribe(listener: (data: Task[]) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    },
    emit(data: Task[]) {
        this.listeners.forEach(listener => listener(data));
    }
};

// 导出更新数据的函数
export const updateTasksGUI = (data: Task[]) => {
    tasksEventBus.emit(data);
};



const Tasks: React.FC = () => {
    const { t } = useTranslation();
    const [loading, setLoading] = useState(false);
    const {
        selectedItem: selectedTask,
        items: tasks,
        selectItem,
        removeItem,
        updateItem,
        setItems: setTasks  // Add this line
    } = useDetailView<Task>(initialTasks);

    const fetchTasks = useCallback(async () => {
        try {
            setLoading(true);
            const response = await IPCAPI.getInstance().getTasks([]);
            if (response && response.success && response.data) {
                setTasks(response.data);
            }
        } catch (error) {
            console.error('Error fetching tasks:', error);
        } finally {
            setLoading(false);
        }
    }, [setTasks]);

    useEffect(() => {
        fetchTasks();
    }, [fetchTasks]);

    const handleRefresh = useCallback(async () => {
        await fetchTasks();
    }, [fetchTasks]);


    const listTitle = (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>{t('pages.tasks.title')}</span>
            <Button
                type="text"
                icon={<ReloadOutlined style={{ color: 'white' }} />}
                onClick={handleRefresh}
                loading={loading}
                title={t('pages.tasks.refresh')}
            />
        </div>
    );

    const translateTask = (task: Task): Task => {
        return {
            ...task,
            name: t(`pages.tasks.tasks.${task.name}.name`, { defaultValue: task.name }),
            category: t(`pages.tasks.categories.${task.category}`, { defaultValue: task.category }),
            description: t(`pages.tasks.tasks.${task.name}.description`, { defaultValue: task.description }),
            features: task.features.map(feature => 
                t(`pages.tasks.tasks.${task.name}.features.${feature}`, { defaultValue: feature })
            ),
            lastUpdated: task.lastUpdated === '2 days ago'
                ? t('pages.tasks.time.daysAgo', { days: 2 })
                : task.lastUpdated === '1 hour ago'
                ? t('pages.tasks.time.hoursAgo', { hours: 1 })
                : task.lastUpdated === '1 week ago'
                ? t('pages.tasks.time.weeksAgo', { weeks: 1 })
                : task.lastUpdated
        };
    };

    const translatedTasks = tasks.map(translateTask);

    const handleUpdate = (id: number) => {
        updateItem(id, { status: 'updating' });
        // Simulate update process
        setTimeout(() => {
            updateItem(id, { 
                status: 'active',
                version: (parseFloat(tasks.find(task => task.id === id)?.version || '0') + 0.1).toFixed(1),
                lastUpdated: t('pages.tasks.time.justNow')
            });
        }, 2000);
    };

    const handleUninstall = (id: number) => {
        removeItem(id);
    };

    const renderListContent = () => (
        <List
            dataSource={translatedTasks}
            renderItem={task => (
                <TaskItem onClick={() => selectItem(task)}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                            <Avatar icon={<OrderedListOutlined />} />
                            <Text strong>{task.name}</Text>
                        </Space>
                        <Space>
                            <Tag color={getStatusColor(task.status)}>{t(`pages.tasks.status.${task.status}`)}</Tag>
                            <Tag color="blue">{task.category}</Tag>
                        </Space>
                        <Space>
                            <Text type="secondary">v{task.version}</Text>
                            <Text type="secondary">{task.size}</Text>
                        </Space>
                    </Space>
                </TaskItem>
            )}
        />
    );

    const renderDetailsContent = () => {
        if (!selectedTask) {
            return <Text type="secondary">{t('pages.tasks.selectTask')}</Text>;
        }

        const translatedTask = translateTask(selectedTask);

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                    <Avatar size={64} icon={<OrderedListOutlined />} />
                    <div>
                        <Title level={4} style={{ margin: 0 }}>{translatedTask.name}</Title>
                        <Text type="secondary">{t('pages.tasks.version', { version: translatedTask.version })}</Text>
                    </div>
                </Space>
                <Space>
                    <Tag color={getStatusColor(translatedTask.status)}>
                        <CheckCircleOutlined /> {t('pages.tasks.status')}: {t(`pages.tasks.status.${translatedTask.status}`)}
                    </Tag>
                    <Tag>
                        <ClockCircleOutlined /> {t('pages.tasks.lastUpdated')}: {translatedTask.lastUpdated}
                    </Tag>
                    <Tag>
                        <StarOutlined /> {t('pages.tasks.rating')}: {translatedTask.rating}/5
                    </Tag>
                </Space>
                <div>
                    <Text strong>{t('pages.tasks.description')}</Text>
                    <br />
                    <Text>{translatedTask.description}</Text>
                </div>
                <div>
                    <Text strong>{t('pages.tasks.features')}</Text>
                    <br />
                    <Space wrap>
                        {translatedTask.features.map(feature => (
                            <Tag key={feature} color="green">{feature}</Tag>
                        ))}
                    </Space>
                </div>
                <Row gutter={16}>
                    <Col span={12}>
                        <Card>
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <Text>{t('pages.tasks.storageUsage')}</Text>
                                <Progress percent={75} />
                                <Text type="secondary">{translatedTask.size}</Text>
                            </Space>
                        </Card>
                    </Col>
                    <Col span={12}>
                        <Card>
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <Text>{t('pages.tasks.userRating')}</Text>
                                <Progress percent={translatedTask.rating * 20} />
                                <Text type="secondary">{translatedTask.rating}/5</Text>
                            </Space>
                        </Card>
                    </Col>
                </Row>
                <Space>
                    <Button 
                        type="primary" 
                        icon={<DownloadOutlined />}
                        onClick={() => handleUpdate(translatedTask.id)}
                        disabled={translatedTask.status === 'updating'}
                    >
                        {t('pages.tasks.update')}
                    </Button>
                    <Button 
                        icon={<SettingOutlined />}
                        onClick={() => {}}
                    >
                        {t('pages.tasks.settings')}
                    </Button>
                    <Button 
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleUninstall(translatedTask.id)}
                    >
                        {t('pages.tasks.uninstall')}
                    </Button>
                </Space>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle={listTitle}
            detailsTitle={t('pages.tasks.details')}
            listContent={renderListContent()}
            detailsContent={
                <>
                {renderDetailsContent()}
                <ActionButtons
                    onAdd={() => {}}
                    onEdit={() => {}}
                    onDelete={() => {}}
                    onRefresh={handleRefresh}
                    onExport={() => {}}
                    onImport={() => {}}
                    onSettings={() => {}}
                    addText={t('pages.tasks.addTask')}
                    editText={t('pages.tasks.editTask')}
                    deleteText={t('pages.tasks.deleteTask')}
                    refreshText={t('pages.tasks.refreshTasks')}
                    exportText={t('pages.tasks.exportTasks')}
                    importText={t('pages.tasks.importTasks')}
                    settingsText={t('pages.tasks.taskSettings')}
                />
                </>
            }
        />
    );
};

export default Tasks;
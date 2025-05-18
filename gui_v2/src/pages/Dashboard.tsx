import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Alert, Spin } from 'antd';
import { useAppStore } from '../store/appStore';
import { ipcClient } from '../services/ipc';

const Dashboard: React.FC = () => {
    const { systemInfo, setSystemInfo } = useAppStore();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const loadSystemInfo = async () => {
            setLoading(true);
            setError(null);
            try {
                const info = await ipcClient.getSystemInfo();
                setSystemInfo(info);
            } catch (error) {
                console.error('Failed to load system info:', error);
                setError('无法连接到服务器，请确保后端服务正在运行');
            } finally {
                setLoading(false);
            }
        };

        loadSystemInfo();
    }, [setSystemInfo]);

    if (loading) {
        return (
            <div style={{ textAlign: 'center', padding: '50px' }}>
                <Spin size="large" />
                <p style={{ marginTop: '20px' }}>正在加载系统信息...</p>
            </div>
        );
    }

    if (error) {
        return (
            <Alert
                message="连接错误"
                description={error}
                type="error"
                showIcon
            />
        );
    }

    return (
        <div>
            <h1>系统仪表盘</h1>
            <Row gutter={16}>
                <Col span={8}>
                    <Card>
                        <Statistic
                            title="系统版本"
                            value={systemInfo?.version || '未知'}
                        />
                    </Card>
                </Col>
                <Col span={8}>
                    <Card>
                        <Statistic
                            title="平台"
                            value={systemInfo?.platform || '未知'}
                        />
                    </Card>
                </Col>
                <Col span={8}>
                    <Card>
                        <Statistic
                            title="内存使用率"
                            value={systemInfo ? (systemInfo.memory.used / systemInfo.memory.total * 100).toFixed(1) : 0}
                            suffix="%"
                        />
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default Dashboard; 
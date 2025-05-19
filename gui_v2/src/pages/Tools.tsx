import React, { useState } from 'react';
import { Card, Button, Space, message } from 'antd';

const Tools: React.FC = () => {
    const [loading, setLoading] = useState(false);

    const handleProcessData = async () => {
        setLoading(true);
        try {
            // 模拟数据处理
            await new Promise(resolve => setTimeout(resolve, 1000));
            message.success('数据处理成功');
        } catch (error) {
            message.error('操作失败');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <h1>工具</h1>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
                <Card title="数据处理">
                    <Button
                        type="primary"
                        onClick={handleProcessData}
                        loading={loading}
                    >
                        开始处理
                    </Button>
                </Card>
            </Space>
        </div>
    );
};

export default Tools; 
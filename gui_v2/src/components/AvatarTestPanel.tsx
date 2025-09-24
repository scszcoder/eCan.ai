import React, { useState } from 'react';
import { runQuickTest, AvatarSceneTestUtils } from '../utils/avatarSceneTestUtils';
import { Button, Input, Card, Space, Typography, Divider } from 'antd';
import { PlayCircleOutlined, BugOutlined, BarChartOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

/**
 * Development panel for testing the avatar scene system
 * Add this component to any page during development
 */
export const AvatarTestPanel: React.FC = () => {
  const [agentId, setAgentId] = useState('test-agent-1');
  const [isRunning, setIsRunning] = useState(false);
  const [stats, setStats] = useState<any>(null);

  const handleQuickTest = async () => {
    setIsRunning(true);
    console.log(`🚀 Starting Avatar Scene System Test for agent: ${agentId}`);
    
    try {
      // Run the quick test
      runQuickTest(agentId);
      
      // Get stats after a delay
      setTimeout(() => {
        const testUtils = new AvatarSceneTestUtils();
        const systemStats = testUtils.getSystemStats();
        setStats(systemStats);
        setIsRunning(false);
        console.log('✅ Test completed!');
      }, 26000); // Wait for test to complete
      
    } catch (error) {
      console.error('❌ Test failed:', error);
      setIsRunning(false);
    }
  };

  const handleWorkflowTest = () => {
    const testUtils = new AvatarSceneTestUtils();
    testUtils.simulateAgentWorkflow(agentId);
    console.log(`🔄 Workflow simulation started for ${agentId}`);
  };

  const handlePriorityTest = () => {
    const testUtils = new AvatarSceneTestUtils();
    testUtils.testPriorityHandling(agentId);
    console.log(`⚡ Priority test started for ${agentId}`);
  };

  const handleErrorTest = () => {
    const testUtils = new AvatarSceneTestUtils();
    testUtils.testErrorHandling(agentId);
    console.log(`🐛 Error handling test started for ${agentId}`);
  };

  const getStats = () => {
    const testUtils = new AvatarSceneTestUtils();
    const systemStats = testUtils.getSystemStats();
    setStats(systemStats);
    console.log('📊 Current system stats:', systemStats);
  };

  return (
    <Card 
      title={
        <Space>
          <BugOutlined />
          <Title level={4} style={{ margin: 0 }}>Avatar Scene System Test Panel</Title>
        </Space>
      }
      style={{ margin: '20px', maxWidth: '600px' }}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <div>
          <Text strong>Agent ID:</Text>
          <Input
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            placeholder="Enter agent ID to test"
            style={{ marginTop: '8px' }}
          />
        </div>

        <Divider />

        <Space wrap>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleQuickTest}
            loading={isRunning}
            size="large"
          >
            {isRunning ? 'Running Test...' : 'Run Quick Test'}
          </Button>

          <Button onClick={handleWorkflowTest}>
            Workflow Test
          </Button>

          <Button onClick={handlePriorityTest}>
            Priority Test
          </Button>

          <Button onClick={handleErrorTest} danger>
            Error Test
          </Button>

          <Button 
            icon={<BarChartOutlined />}
            onClick={getStats}
          >
            Get Stats
          </Button>
        </Space>

        {isRunning && (
          <div style={{ 
            padding: '12px', 
            background: '#f0f9ff', 
            border: '1px solid #0ea5e9',
            borderRadius: '6px' 
          }}>
            <Text type="secondary">
              🔄 Test is running... Check the browser console for detailed logs. 
              The test will complete in about 25 seconds.
            </Text>
          </div>
        )}

        {stats && (
          <Card size="small" title="System Statistics">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Text><strong>Total Scene Plays:</strong> {stats.totalScenePlays}</Text>
              <Text><strong>Total Errors:</strong> {stats.totalErrors}</Text>
              <Text><strong>Average Duration:</strong> {stats.averageSceneDuration}ms</Text>
              <Text><strong>Active Agents:</strong> {stats.agentCount}</Text>
            </Space>
          </Card>
        )}

        <div style={{ 
          padding: '12px', 
          background: '#f6f8fa', 
          borderRadius: '6px',
          fontSize: '12px'
        }}>
          <Text type="secondary">
            <strong>Instructions:</strong><br/>
            1. Enter an agent ID above<br/>
            2. Click "Run Quick Test" to start a full system test<br/>
            3. Watch the browser console for detailed logs<br/>
            4. Use other buttons for specific test scenarios<br/>
            5. Check stats to monitor system performance
          </Text>
        </div>
      </Space>
    </Card>
  );
};

export default AvatarTestPanel;

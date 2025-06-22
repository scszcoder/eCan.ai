import React, { useState, useEffect } from 'react';
import { Space, Select, Input, Button, Card, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {get_ipc_api} from '../../services/ipc_api';
import { useUserStore } from '../../stores/userStore';

const { Title, Text } = Typography;
const { TextArea } = Input;

const Tests: React.FC = () => {
    const { t } = useTranslation();
    const [selectedTest, setSelectedTest] = useState<string>('');
    const [testArgument, setTestArgument] = useState<string>('');
    const [testOutput, setTestOutput] = useState<string>('');
    const [isLoading, setIsLoading] = useState<boolean>(false);
    const [isTestRunning, setIsTestRunning] = useState<boolean>(false);
    const username = useUserStore((state) => state.username);

    // Add default test at the top of the component
    const defaultTest = {
        label: 'Default Test',
        value: 'default_test'
    };
    const [tests, setTests] = useState<Array<{label: string, value: string}>>([defaultTest]);

    // Fetch available tests
    const fetchTests = async () => {
        try {
            const response = await get_ipc_api().getAvailableTests();
            const backendTests = response && response.success && Array.isArray(response.data)
            ? response.data.map(test => ({
                label: test.name || test,
                value: test.id || test
            }))
            : [];

            // Combine default test with backend tests, ensuring no duplicates
            const allTests = [defaultTest, ...backendTests.filter(
                test => test.value !== defaultTest.value
            )];

            setTests(allTests);
        } catch (error) {
            console.error('Error fetching tests:', error);
            message.error(t('pages.tests.fetchError'));
            // Still show default test even if fetch fails
            if (tests.length === 0 || tests[0].value !== defaultTest.value) {
                setTests([defaultTest]);
            }
        }
    };

    const getAllTest = async () => {
        try {
            console.log('current username is:', username);
            const response = await get_ipc_api().getAll(username || '');
            // Update testOutput with the response
            setTestOutput(JSON.stringify(response, null, 2));

        } catch (error) {
            console.error('Error fetching tests:', error);
            message.error(t('pages.tests.fetchError'));
            // Still show default test even if fetch fails
            if (tests.length === 0 || tests[0].value !== defaultTest.value) {
                setTests([defaultTest]);
            }
        }
    };

    // Load tests on component mount
    useEffect(() => {
        fetchTests();
    }, []);

    // Handle test execution
    const handleRunTest = async () => {
        if (!selectedTest) {
            message.warning(t('pages.tests.selectTestWarning'));
            return;
        }

        setIsTestRunning(true);
        setTestOutput(t('pages.tests.runningTest'));

        try {
            // Use the correct IPC method based on the selected test
            let response;
            if (selectedTest === 'default_test') {
                // For default test, use the run_tests method
                const testConfig = {
                    test_id: 'default_test',
                    args: testArgument ? JSON.parse(testArgument) : {}
                };
                response = await get_ipc_api().runTest([testConfig]);
            } else {
                // For other tests, use the appropriate method
                const testConfig = {
                    test_id: selectedTest,
                    args: testArgument ? JSON.parse(testArgument) : {}
                };
                response = await get_ipc_api().runTest([testConfig]);
            }
            
            setTestOutput(JSON.stringify(response || 'No response data', null, 2));
            message.success(t('pages.tests.testCompleted'));
        } catch (error) {
            console.error('Test execution failed:', error);
            const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
            setTestOutput(`Error: ${errorMessage}`);
            message.error(t('pages.tests.testError'));
        } finally {
            setIsTestRunning(false);
        }
    };

    // Handle test stop
    const handleStopTest = async () => {
        try {
            await get_ipc_api().stopTest([selectedTest]);
            setTestOutput(prev => prev + '\n' + t('pages.tests.testStopped'));
        } catch (error) {
            console.error('Error stopping test:', error);
            message.error(t('pages.tests.stopError'));
        } finally {
            setIsTestRunning(false);
        }
    };

    return (
        <div style={{ padding: '24px' }}>
            <Card>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {/* Test Selection */}
                    <Space align="center" style={{ width: '100%', marginBottom: '16px' }}>
                        <Text style={{ color: 'white', marginRight: '8px' }}>{t('pages.tests.testsToRun')}:</Text>
                        <Select
                            style={{ width: 300 }}
                            placeholder={t('pages.tests.selectTest')}
                            options={tests}
                            value={selectedTest || undefined}
                            onChange={setSelectedTest}
                            disabled={isTestRunning}
                        />
                        <Button
                            icon={<ReloadOutlined style={{ color: 'white' }} />}
                            onClick={fetchTests}
                            disabled={isLoading}
                            loading={isLoading}
                            type="text"
                        />
                    </Space>

                    {/* Test Argument */}
                    <Space align="center" style={{ width: '100%', marginBottom: '16px' }}>
                        <Text style={{ color: 'white', marginRight: '8px' }}>{t('pages.tests.testArgument')}:</Text>
                        <Input
                            style={{ width: 300 }}
                            value={testArgument}
                            onChange={(e) => setTestArgument(e.target.value)}
                            disabled={isTestRunning}
                            placeholder={t('pages.tests.argumentPlaceholder')}
                        />
                    </Space>

                    {/* Action Buttons */}
                    <Space style={{ marginBottom: '16px' }}>
                        <Button
                            type="default"
                            onClick={handleRunTest}
                            disabled={!selectedTest || isTestRunning}
                            style={{
                                color: 'white',
                                borderColor: 'white',
                                background: 'transparent'
                            }}
                        >
                            {t('pages.tests.runTest')}
                        </Button>
                        <Button
                            danger
                            onClick={handleStopTest}
                            disabled={!isTestRunning}
                            style={{
                                color: 'white',
                                borderColor: 'white',
                                background: 'transparent'
                            }}
                        >
                            {t('pages.tests.stopTest')}
                        </Button>
                    </Space>

                    <Space style={{ marginBottom: '16px' }}>
                        <Button
                            type="default"
                            onClick={getAllTest}
                            disabled={!selectedTest || isTestRunning}
                            style={{
                                color: 'white',
                                borderColor: 'white',
                                background: 'transparent'
                            }}
                        >
                            {t('pages.tests.getAllTest')}
                        </Button>

                    </Space>

                    {/* Test Output */}
                    <div>
                        <Text style={{ color: 'white', display: 'block', marginBottom: '8px' }}>
                            {t('pages.tests.testOutput')}:
                        </Text>
                        <TextArea
                            value={testOutput}
                            readOnly
                            style={{
                                width: '100%',
                                minHeight: '200px',
                                backgroundColor: '#1f1f1f',
                                color: 'white',
                                fontFamily: 'monospace'
                            }}
                        />
                    </div>
                </Space>
            </Card>
        </div>
    );
};

export default Tests;
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

    // Debug: Ping IPC
    const handlePingIPC = async () => {
        const hasIPC = typeof window !== 'undefined' && !!(window as any).ipc;
        console.log('[Tests] PingIPC: hasIPC?', hasIPC);
        message.info(`Ping IPC: hasIPC=${hasIPC}`);
        if (!hasIPC) {
            setTestOutput('PingIPC: window.ipc missing');
            return;
        }
        try {
            const t0 = Date.now();
            const resp: any = await Promise.race([
                get_ipc_api().getAvailableTests(),
                new Promise((_, reject) => setTimeout(() => reject(new Error('Ping timeout (2s)')), 2000))
            ]);
            console.log('[Tests] PingIPC response in', Date.now() - t0, 'ms', resp);
            setTestOutput('PingIPC response: ' + JSON.stringify(resp, null, 2));
        } catch (e) {
            console.warn('[Tests] PingIPC error', e);
            setTestOutput('PingIPC error: ' + (e instanceof Error ? e.message : String(e)));
        }
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
        console.log('[Tests] getAllTest:clicked', { username });
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

    const workflowTest = async () => {
        console.log('[Tests] workflowTest:clicked', { username, selectedTest });
        try {
            console.log('current username is:', username);
            let parsedArgs: any = {};
            try {
                parsedArgs = testArgument ? JSON.parse(testArgument) : {};
            } catch (e) {
                message.error('Invalid JSON in Test Argument');
                return;
            }
            const testConfig = {
                    test_id: "workflow0",
                    args: parsedArgs
                };
            const response = await get_ipc_api().runTest([testConfig]);
            if (!response.success) {
                message.error(response.error?.message || t('pages.tests.testError'));
                return;
            }
            // Update testOutput with the response
            setTestOutput(JSON.stringify(response, null, 2));
            message.success(t('pages.tests.testCompleted'));

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
        console.log('[Tests] mounted');
        fetchTests();
    }, []);

    // Handle test execution (STEP7: deferred IPC with then/catch/finally)
    const handleRunTest = async () => {
        const hasIPC = typeof window !== 'undefined' && !!(window as any).ipc;
        console.log('[Tests] STEP7: start run (deferred IPC)', { selectedTest, hasIPC });
        setIsTestRunning(true);
        setTestOutput(t('pages.tests.runningTest'));

        // Defer IPC call to next tick to avoid blocking click event stack
        setTimeout(() => {
            // 1) Build testConfig
            let parsedArgs: any = {};
            try {
                parsedArgs = testArgument ? JSON.parse(testArgument) : {};
            } catch (e) {
                console.warn('[Tests] STEP7: args JSON parse failed');
                setTestOutput('Invalid JSON in Test Argument');
                setIsTestRunning(false);
                return;
            }
            const testConfig = { test_id: selectedTest || 'default_test', args: parsedArgs };
            console.log('[Tests] STEP7: about to call run_tests (array) with 5s timeout', testConfig);

            Promise.race([
                get_ipc_api().runTest([testConfig]),
                new Promise((_, reject) => setTimeout(() => reject(new Error('RUN_ARRAY_TIMEOUT')), 5000))
            ])
            .then((resp: any) => {
                console.log('[Tests] STEP7: run_tests(array) result', resp);
                setTestOutput(JSON.stringify(resp, null, 2));
            })
            .catch((err: any) => {
                console.error('[Tests] STEP7: run error', err);
                setTestOutput(`Error: ${err instanceof Error ? err.message : String(err)}`);
            })
            .finally(() => {
                setIsTestRunning(false);
                console.log('[Tests] STEP7: finished');
            });
        }, 0);
    };

    // Minimal-only button handler
    const handleRunMinimal = () => {
        console.log('[Tests] RunMinimal clicked');
        setTestOutput('Run Minimal OK');
    };

    const handleStopTest = async () => {
        try {
            const response = await get_ipc_api().stopTest([selectedTest]);
            if (!response.success) {
                message.error(response.error?.message || t('pages.tests.stopError'));
                return;
            }
            setTestOutput(prev => prev + '\n' + t('pages.tests.testStopped'));
        } catch (error) {
            console.error('Error stopping test:', error);
            message.error(t('pages.tests.stopError'));
        } finally {
            setIsTestRunning(false);
        }
    };

    const handlePageClick: React.MouseEventHandler<HTMLDivElement> = (e) => {
        const target = e.target as HTMLElement;
        console.log('[Tests] Page click:', {
            tag: target.tagName,
            class: target.className,
            id: target.id,
            text: (target.innerText || '').slice(0, 40)
        });
    };

    return (
        <div style={{ padding: '24px' }}>
            <Card>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {/* Debug Buttons */}
                    <Space style={{ marginBottom: '8px' }}>
                        <Button onClick={() => { console.log('[Tests] Debug button clicked'); message.info('Debug button clicked'); }}>
                            Debug: Click me
                        </Button>
                        <Button onClick={handlePingIPC} style={{ marginLeft: 8 }}>
                            Ping IPC
                        </Button>
                        <Button
                            onClick={async () => {
                                console.log('[Tests] Smoke IPC button: get_available_tests (2s)');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().getAvailableTests(),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('SMOKE_TIMEOUT')), 2000))
                                    ]);
                                    console.log('[Tests] Smoke IPC result', resp);
                                    setTestOutput('Smoke IPC result: ' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    console.warn('[Tests] Smoke IPC error', e);
                                    setTestOutput('Smoke IPC error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{ marginLeft: 8 }}
                        >
                            Smoke IPC
                        </Button>
                        <Button
                            onClick={async () => {
                                // Direct array-form run_tests without changing component state
                                const hasIPC = typeof window !== 'undefined' && !!(window as any).ipc;
                                console.log('[Tests] Direct API: run_tests array (5s)', { hasIPC, selectedTest });
                                let parsedArgs: any = {};
                                try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch {}
                                const testConfig = { test_id: selectedTest || 'default_test', args: parsedArgs };
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().runTest([testConfig]),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('RUN_ARRAY_TIMEOUT')), 5000))
                                    ]);
                                    console.log('[Tests] Direct API: array result', resp);
                                    setTestOutput('Direct run_tests(array) result: ' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    console.warn('[Tests] Direct API: array error', e);
                                    setTestOutput('Direct run_tests(array) error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{ marginLeft: 8 }}
                        >
                            Run API (array)
                        </Button>
                        <Button
                            onClick={async () => {
                                // Direct single-form run_tests without changing component state
                                const hasIPC = typeof window !== 'undefined' && !!(window as any).ipc;
                                console.log('[Tests] Direct API: runSingleTest (3s)', { hasIPC, selectedTest });
                                let parsedArgs: any = {};
                                try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch {}
                                const testConfig = { test_id: selectedTest || 'default_test', args: parsedArgs };
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().runSingleTest(testConfig),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('RUN_SINGLE_TIMEOUT')), 3000))
                                    ]);
                                    console.log('[Tests] Direct API: single result', resp);
                                    setTestOutput('Direct runSingleTest result: ' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    console.warn('[Tests] Direct API: single error', e);
                                    setTestOutput('Direct runSingleTest error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{ marginLeft: 8 }}
                        >
                            Run API (single)
                        </Button>
                        <Button onClick={handleRunMinimal} style={{ marginLeft: 8 }}>
                            Run Minimal
                        </Button>
                    </Space>
                    {/* Test Selection */}
                    <Space align="center" style={{ width: '100%', marginBottom: '16px' }}>
                        <Text style={{ color: 'white', marginRight: '8px' }}>{t('pages.tests.testsToRun')}:</Text>
                        <Select
                            style={{ width: 300 }}
                            placeholder={t('pages.tests.selectTest')}
                            options={tests}
                            value={selectedTest || undefined}
                            onChange={(v) => { console.log('[Tests] Select changed:', v); setSelectedTest(v); }}
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
                            onClick={() => { console.log('[Tests] RunTest button onClick fired -> invoking handler'); handleRunTest(); }}
                            disabled={false /* DEBUG: force enabled to ensure click handler fires */}
                            style={{
                                color: 'white',
                                borderColor: 'white',
                                background: 'transparent',
                                position: 'relative'
                            }}
                        >
                            {t('pages.tests.runTest')} [DEBUG]
                        </Button>
                        {/* Plain HTML button to verify native click behavior in same spot */}
                        <button
                            onMouseDown={() => console.log('[Tests] Native button onMouseDown')}
                            onMouseUp={() => console.log('[Tests] Native button onMouseUp')}
                            onClick={() => { console.log('[Tests] Native button onClick'); message.info('Native button click ok'); }}
                            style={{ marginLeft: 8 }}
                        >
                            Native Button [DEBUG]
                        </button>
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
                        <Button
                            type="default"
                            onClick={workflowTest}
                            disabled={!selectedTest || isTestRunning}
                            style={{
                                color: 'white',
                                borderColor: 'white',
                                background: 'transparent'
                            }}
                        >
                            {t('pages.tests.flowTest')}
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
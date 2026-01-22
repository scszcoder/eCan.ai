import React, { useState, useEffect } from 'react';
import { Space, Select, Input, Button, Card, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {get_ipc_api} from '../../services/ipc_api';
import { useUserStore } from '../../stores/userStore';
import { useSettingsStore } from '../../stores/settingsStore';

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
    const settings = useSettingsStore((state) => state.settings);
    const loadSettings = useSettingsStore((state) => state.loadSettings);

    const appendTestOutput = (line: string) => {
        setTestOutput(prev => (prev ? `${prev}\n${line}` : line));
    };

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

    useEffect(() => {
        if (!settings) {
            loadSettings().catch((error) => {
                console.error('[Tests] Failed to load settings:', error);
            });
        }
    }, [settings, loadSettings]);

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

    const handleWebsocketTest = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const defaultWsEndpoint = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql';
        const defaultWsHost = '3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com';

        let parsedArgs: any = {};
        try {
            parsedArgs = testArgument ? JSON.parse(testArgument) : {};
        } catch (e) {
            appendTestOutput('WebSocket Test: Invalid JSON in Test Argument');
            return;
        }

        const wsEndpoint = (settings?.ws_api_endpoint?.trim() || parsedArgs.wsEndpoint || defaultWsEndpoint);
        const wsHost = (settings?.ws_api_host?.trim() || parsedArgs.wsHost || defaultWsHost);
        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || defaultWanEndpoint);
        const wanApiKey = (settings?.wan_api_key?.trim() || parsedArgs.wanApiKey || parsedArgs.apiKey || '');

        setTestOutput('');

        if (!wanApiKey) {
            appendTestOutput('WebSocket Test: Missing wan_api_key. Provide in Settings or Test Argument as {"wanApiKey":"..."}.');
            return;
        }

        if (!settings?.ws_api_endpoint || !settings?.ws_api_host || !settings?.wan_api_endpoint) {
            appendTestOutput('WebSocket Test: Using hardcoded AppSync endpoints (settings missing).');
        }

        const channelId = parsedArgs.channelId || `a2a-test-${username || 'web'}-${Date.now()}`;
        const messageText = parsedArgs.message || 'Hello from WebSocket Test';
        const senderId = parsedArgs.senderId || username || 'web-client';
        const sessionId = parsedArgs.sessionId || `session-${Date.now()}`;
        const recipientId = parsedArgs.recipientId || senderId;
        const owner = parsedArgs.owner || username || 'web-client';
        const acctSiteID = parsedArgs.acctSiteID || parsedArgs.acctSiteId || `site-${username || 'web'}`;
        const sceneId = parsedArgs.scene_id || `scene-${Date.now()}`;
        const requestId = parsedArgs.request_id || `req-${Date.now()}`;

        const a2aSubscriptionQuery = `subscription OnA2AMessageReceived($channelId: String!) {\n  onA2AMessageReceived(channelId: $channelId) {\n    id\n    channelId\n    senderId\n    sessionId\n    timestamp\n    message {\n      role\n      parts {\n        type\n        text\n        data\n        metadata\n        file {\n          name\n          uri\n          mimeType\n          bytes\n        }\n      }\n    }\n  }\n}`;

        const a2aMutationQuery = `mutation SendA2AMessage($input: A2AMessageInput!) {\n  sendA2AMessage(input: $input) {\n    id\n    channelId\n    senderId\n    sessionId\n    timestamp\n    message {\n      role\n      parts {\n        type\n        text\n      }\n    }\n  }\n}`;

        const a2aInput = {
            channelId,
            senderId,
            recipientId,
            sessionId,
            acceptedOutputModes: ['text'],
            historyLength: 10,
            message: {
                role: 'user',
                parts: [
                    { type: 'text', text: messageText }
                ]
            }
        };

        const accountSubscriptionQuery = `subscription OnAccountNotification($owner: ID!) {\n  onAccountNotification(owner: $owner) {\n    id\n    owner\n    type\n    title\n    message\n    payload\n    created_at\n    cta_url\n  }\n}`;

        const accountMutationQuery = `mutation PublishAccountNotification($input: AccountNotificationInput!) {\n  publishAccountNotification(input: $input) {\n    id\n    owner\n    type\n    title\n    message\n    payload\n    created_at\n    cta_url\n  }\n}`;

        const accountInput = {
            owner,
            type: parsedArgs.accountType || 'TEST',
            title: parsedArgs.accountTitle || 'WebSocket Test',
            message: parsedArgs.accountMessage || 'Account notification echo test',
            payload: parsedArgs.accountPayload || { source: 'websocket-test' },
            cta_url: parsedArgs.accountCtaUrl || ''
        };

        const sceneSubscriptionQuery = `subscription OnAgentSceneEvent($acctSiteID: String!) {\n  onAgentSceneEvent(acctSiteID: $acctSiteID) {\n    id\n    acctSiteID\n    scene_id\n    status\n    timestamp\n    label\n  }\n}`;

        const sceneMutationQuery = `mutation UpdateScene($input: SceneInput!) {\n  updateScene(input: $input) {\n    id\n    acctSiteID\n    scene_id\n    status\n    timestamp\n    label\n  }\n}`;

        const sceneInput = {
            acctSiteID,
            agent_ids: parsedArgs.agent_ids || [senderId],
            clip: parsedArgs.clip || 'clip',
            images: parsedArgs.images || ['image'],
            label: parsedArgs.label || 'WebSocket Test Scene',
            scene_id: sceneId,
            status: parsedArgs.sceneStatus || 'PENDING',
            thumbnails: parsedArgs.thumbnails || ['thumbnail'],
            video: parsedArgs.video || ['video'],
            actions: parsedArgs.actions,
            captions: parsedArgs.captions,
            description: parsedArgs.description || 'Scene echo test',
            dialogs: parsedArgs.dialogs,
            duration_ms: parsedArgs.duration_ms || 1000,
            n_repeat: parsedArgs.n_repeat,
            priority: parsedArgs.priority,
            trigger_events: parsedArgs.trigger_events
        };

        const sceneCompleteSubscriptionQuery = `subscription OnSceneComplete($acctSiteID: String!) {\n  onSceneComplete(acctSiteID: $acctSiteID) {\n    id\n    acctSiteID\n    scene_id\n    request_id\n    status\n    timestamp\n  }\n}`;

        const sceneCompleteMutationQuery = `mutation PublishSceneResult($input: SceneResultInput!) {\n  publishSceneResult(input: $input) {\n    id\n    acctSiteID\n    scene_id\n    request_id\n    status\n    timestamp\n  }\n}`;

        const sceneResultInput = {
            acctSiteID,
            agent_ids: parsedArgs.agent_ids || [senderId],
            request_id: requestId,
            scene_id: sceneId,
            status: parsedArgs.sceneResultStatus || 'COMPLETED',
            video: parsedArgs.video || ['video'],
            actions: parsedArgs.result_actions,
            description: parsedArgs.result_description,
            dialogs: parsedArgs.result_dialogs,
            duration_ms: parsedArgs.result_duration_ms,
            emotion: parsedArgs.result_emotion,
            error: parsedArgs.result_error,
            mind_state: parsedArgs.result_mind_state,
            thumbnail: parsedArgs.result_thumbnail
        };

        const toBase64 = (value: string) => {
            try {
                return window.btoa(unescape(encodeURIComponent(value)));
            } catch {
                return window.btoa(value);
            }
        };

        const authHeaders = {
            host: wsHost,
            'x-api-key': wanApiKey
        };

        const headerParam = toBase64(JSON.stringify(authHeaders));
        const payloadParam = toBase64(JSON.stringify({}));
        const realtimeUrl = `${wsEndpoint}?header=${encodeURIComponent(headerParam)}&payload=${encodeURIComponent(payloadParam)}`;

        const subscriptionTests = [
            {
                key: 'a2a',
                label: 'A2A Message',
                subscriptionQuery: a2aSubscriptionQuery,
                subscriptionVariables: { channelId },
                mutationQuery: a2aMutationQuery,
                mutationVariables: { input: a2aInput }
            },
            {
                key: 'account',
                label: 'Account Notification',
                subscriptionQuery: accountSubscriptionQuery,
                subscriptionVariables: { owner },
                mutationQuery: accountMutationQuery,
                mutationVariables: { input: accountInput }
            },
            {
                key: 'scene',
                label: 'Agent Scene Event',
                subscriptionQuery: sceneSubscriptionQuery,
                subscriptionVariables: { acctSiteID },
                mutationQuery: sceneMutationQuery,
                mutationVariables: { input: sceneInput }
            },
            {
                key: 'sceneComplete',
                label: 'Scene Complete',
                subscriptionQuery: sceneCompleteSubscriptionQuery,
                subscriptionVariables: { acctSiteID },
                mutationQuery: sceneCompleteMutationQuery,
                mutationVariables: { input: sceneResultInput }
            }
        ];

        const requestedTests = Array.isArray(parsedArgs.subscriptions) && parsedArgs.subscriptions.length > 0
            ? parsedArgs.subscriptions
            : subscriptionTests.map((test) => test.key);

        const testsToRun = subscriptionTests.filter((test) => requestedTests.includes(test.key));

        const runEchoTest = async (test: typeof subscriptionTests[number]) => {
            appendTestOutput(`WebSocket Test (${test.label}): Connecting to ${wsEndpoint}`);
            appendTestOutput(`WebSocket Test (${test.label}): Subscribing with ${JSON.stringify(test.subscriptionVariables)}`);

            return new Promise<void>((resolve) => {
                const ws = new WebSocket(realtimeUrl, 'graphql-ws');
                const subscriptionId = `sub-${test.key}-${Date.now()}`;
                let hasAck = false;
                let hasReceived = false;
                let finished = false;

                const finish = (note?: string) => {
                    if (finished) return;
                    finished = true;
                    if (note) {
                        appendTestOutput(note);
                    }
                    try {
                        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                            ws.close(1000, 'WebSocket test complete');
                        }
                    } catch (e) {
                        console.warn('[Tests] WebSocket cleanup error', e);
                    }
                    resolve();
                };

                const timeoutId = window.setTimeout(() => {
                    finish(`WebSocket Test (${test.label}): Timeout waiting for data`);
                }, parsedArgs.timeoutMs || 15000);

                ws.onopen = () => {
                    appendTestOutput(`WebSocket Test (${test.label}): Socket open, sending connection_init`);
                    ws.send(JSON.stringify({
                        type: 'connection_init'
                    }));
                };

                ws.onmessage = async (event) => {
                    let messageData: any;
                    try {
                        messageData = JSON.parse(event.data as string);
                    } catch {
                        appendTestOutput(`WebSocket Test (${test.label}): Received non-JSON message`);
                        return;
                    }

                    if (messageData.type === 'connection_ack') {
                        hasAck = true;
                        appendTestOutput(`WebSocket Test (${test.label}): connection_ack received, starting subscription`);
                        ws.send(JSON.stringify({
                            id: subscriptionId,
                            type: 'start',
                            payload: {
                                data: JSON.stringify({
                                    query: test.subscriptionQuery,
                                    variables: test.subscriptionVariables
                                }),
                                extensions: {
                                    authorization: authHeaders
                                }
                            }
                        }));

                        appendTestOutput(`WebSocket Test (${test.label}): Sending mutation via AppSync HTTP`);
                        try {
                            const response = await fetch(wanEndpoint, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'x-api-key': wanApiKey
                                },
                                body: JSON.stringify({
                                    query: test.mutationQuery,
                                    variables: test.mutationVariables
                                })
                            });
                            const payload = await response.json();
                            appendTestOutput(`WebSocket Test (${test.label}): Mutation response ${response.status} ${response.statusText}`);
                            appendTestOutput(JSON.stringify(payload, null, 2));
                        } catch (e) {
                            appendTestOutput(`WebSocket Test (${test.label}): Mutation failed - ${e instanceof Error ? e.message : String(e)}`);
                        }
                        return;
                    }

                    if (messageData.type === 'ka') {
                        return;
                    }

                    if (messageData.type === 'data') {
                        hasReceived = true;
                        appendTestOutput(`WebSocket Test (${test.label}): Subscription data received`);
                        appendTestOutput(JSON.stringify(messageData.payload, null, 2));
                        window.clearTimeout(timeoutId);
                        finish();
                        return;
                    }

                    if (messageData.type === 'error' || messageData.type === 'connection_error') {
                        appendTestOutput(`WebSocket Test (${test.label}): Error - ${JSON.stringify(messageData, null, 2)}`);
                        window.clearTimeout(timeoutId);
                        finish();
                    }
                };

                ws.onerror = (event) => {
                    appendTestOutput(`WebSocket Test (${test.label}): WebSocket error`);
                    console.error('[Tests] WebSocket error', event);
                };

                ws.onclose = (event) => {
                    window.clearTimeout(timeoutId);
                    const suffix = hasReceived ? ' (message received)' : hasAck ? ' (connected)' : '';
                    appendTestOutput(`WebSocket Test (${test.label}): Socket closed ${event.code}${suffix}`);
                    finish();
                };
            });
        };

        if (testsToRun.length === 0) {
            appendTestOutput('WebSocket Test: No subscriptions selected to run.');
            return;
        }

        appendTestOutput(`WebSocket Test: Running ${testsToRun.length} subscription echo tests`);
        for (const test of testsToRun) {
            await runEchoTest(test);
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
                        <Button onClick={handleWebsocketTest} style={{ marginLeft: 8 }}>
                            WebSocket Test
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
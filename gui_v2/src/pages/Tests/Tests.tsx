import React, { useState, useEffect } from 'react';
import { Space, Select, Input, Button, Card, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {get_ipc_api} from '../../services/ipc_api';
import { useUserStore } from '../../stores/userStore';
import { useSettingsStore } from '../../stores/settingsStore';
import {
    downloadWithPresignedUrl,
    uploadWithPresignedUrl,
    PresignedRequest
} from '../../services/web/presignedFileOps';

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
        const runId = parsedArgs.runId || parsedArgs.run_id || parsedArgs.runID || `run-${Date.now()}`;
        const runner = parsedArgs.runner || username || 'web-client';

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

        const accountSubscriptionQuery = `subscription OnAccountNotification($owner: String!) {\n  onAccountNotification(owner: $owner) {\n    id\n    owner\n    ntype\n    title\n    message\n    payload\n    created_at\n    cta_url\n  }\n}`;

        const accountMutationQuery = `mutation PublishAccountNotification($input: AccountNotificationInput!) {\n  publishAccountNotification(input: $input) {\n    id\n    owner\n    ntype\n    title\n    message\n    payload\n    created_at\n    cta_url\n  }\n}`;

        const accountPayloadValue = parsedArgs.accountPayload ?? { source: 'websocket-test' };
        const accountPayload = typeof accountPayloadValue === 'string'
            ? accountPayloadValue
            : JSON.stringify(accountPayloadValue);

        const accountInput = {
            owner,
            ntype: parsedArgs.accountType || 'TEST',
            title: parsedArgs.accountTitle || 'WebSocket Test',
            message: parsedArgs.accountMessage || 'Account notification echo test',
            payload: accountPayload,
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

        const taskStatusSubscriptionQuery = `subscription OnTaskStatus($runner: String!) {\n  onTaskStatus(runner: $runner) {\n    id\n    runID\n    runner\n    error\n    success\n    status\n    timestamp\n  }\n}`;

        const taskStatusMutationQuery = `mutation PublishTaskStatus($input: TaskStatusInput!) {\n  publishTaskStatus(input: $input) {\n    id\n    runID\n    runner\n    error\n    success\n    status\n    timestamp\n  }\n}`;

        const taskStatusInput = {
            runID: runId,
            runner,
            success: parsedArgs.taskSuccess ?? true,
            error: parsedArgs.taskError || undefined,
            status: JSON.stringify({
                runID: runId,
                runner,
                echo: parsedArgs.taskStatus || 'task-status-echo',
                timestamp: new Date().toISOString()
            })
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

        const parseJsonMaybe = (value: any) => {
            if (typeof value !== 'string') return value;
            try {
                return JSON.parse(value);
            } catch {
                return value;
            }
        };

        const normalizePresignedRequest = (entry: any, fallbackMethod?: PresignedRequest['method']): PresignedRequest | null => {
            const parsed = parseJsonMaybe(entry);
            if (!parsed || typeof parsed !== 'object') return null;
            const url =
                parsed.url ||
                parsed.upload_url ||
                parsed.download_url ||
                parsed.presigned_url ||
                parsed.s3_url ||
                parsed.s3PresignedUrl;

            if (!url || typeof url !== 'string') return null;

            const fields = parsed.fields && typeof parsed.fields === 'object' ? parsed.fields : undefined;
            const headers = parsed.headers || parsed.requestHeaders;

            return {
                url,
                method: parsed.method || fallbackMethod || (fields ? 'POST' : undefined),
                fields,
                headers,
                raw: parsed
            };
        };

        const tryPresignedFlow = async (payload: any) => {
            const data = payload?.data || payload;
            const notification = data?.onAccountNotification || data?.accountNotification || data;
            const rawPayload = parseJsonMaybe(notification?.payload ?? notification?.data ?? notification);
            if (!rawPayload || typeof rawPayload !== 'object') {
                return false;
            }

            const uploadEntry =
                rawPayload.upload ||
                rawPayload.uploadInfo ||
                rawPayload.upload_request ||
                {
                    url: rawPayload.upload_url || rawPayload.uploadUrl || rawPayload.presigned_upload_url,
                    headers: rawPayload.upload_headers,
                    method: rawPayload.upload_method || 'PUT'
                };

            const downloadEntry =
                rawPayload.download ||
                rawPayload.downloadInfo ||
                rawPayload.download_request ||
                {
                    url: rawPayload.download_url || rawPayload.downloadUrl || rawPayload.presigned_download_url,
                    headers: rawPayload.download_headers,
                    method: rawPayload.download_method || 'GET'
                };

            const upload = normalizePresignedRequest(uploadEntry, 'PUT');
            const download = normalizePresignedRequest(downloadEntry, 'GET');

            if (!upload || !download) {
                return false;
            }

            const contentType = rawPayload.contentType || rawPayload.content_type || 'text/plain';
            const testBody = rawPayload.testBody || rawPayload.test_body || `presigned-test-${Date.now()}`;
            const blob = new Blob([testBody], { type: contentType });

            appendTestOutput('WebSocket Test: Presigned payload detected, starting upload');
            await uploadWithPresignedUrl(blob, upload, contentType);
            appendTestOutput('WebSocket Test: Upload completed, downloading');
            const downloaded = await downloadWithPresignedUrl(download);
            const downloadedText = await downloaded.text();

            if (downloadedText !== testBody) {
                appendTestOutput('WebSocket Test: Downloaded content mismatch');
            } else {
                appendTestOutput('WebSocket Test: Downloaded content verified');
            }

            return true;
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
            },
            {
                key: 'taskStatus',
                label: 'Task Status',
                subscriptionQuery: taskStatusSubscriptionQuery,
                subscriptionVariables: { runner },
                mutationQuery: taskStatusMutationQuery,
                mutationVariables: { input: taskStatusInput }
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
                const skipMutation =
                    parsedArgs.skipMutation === true ||
                    (Array.isArray(parsedArgs.skipMutationFor) && parsedArgs.skipMutationFor.includes(test.key));

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
                }, parsedArgs.timeoutMs || 30000);

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

                        if (skipMutation) {
                            appendTestOutput(`WebSocket Test (${test.label}): Skipping mutation (awaiting external publisher)`);
                            return;
                        }

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
                        try {
                            const handled = await tryPresignedFlow(messageData.payload);
                            if (handled) {
                                appendTestOutput(`WebSocket Test (${test.label}): Presigned upload/download test finished`);
                            }
                        } catch (e) {
                            appendTestOutput(`WebSocket Test (${test.label}): Presigned flow failed - ${e instanceof Error ? e.message : String(e)}`);
                        }
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

    const handleLocalWebsocketTest = async () => {
        setTestOutput('');
        appendTestOutput('Local WS Test: Starting...');
        
        // Force-connect the local WebSocket client first
        appendTestOutput('Local WS Test: Connecting to local WebSocket...');
        try {
            const { localWebSocketClient } = await import('../../services/web/localWebSocketClient');
            const { initWebSocketEventListeners } = await import('../../services/web/wsEventListeners');
            initWebSocketEventListeners();
            const connected = await localWebSocketClient.connect(true); // force=true bypasses platform check
            if (connected) {
                appendTestOutput('Local WS Test: WebSocket connected successfully');
            } else {
                appendTestOutput('Local WS Test: WebSocket connection failed or already connecting');
            }
            // Give WebSocket a moment to fully establish
            await new Promise(resolve => setTimeout(resolve, 500));
        } catch (wsError) {
            appendTestOutput(`Local WS Test: WebSocket connect error - ${wsError}`);
        }
        
        // Get the local server port from settings
        const port = settings?.local_server_port || '4668';
        const testUrl = `http://localhost:${port}/api/local-ws-test`;
        
        appendTestOutput(`Local WS Test: Calling ${testUrl}`);
        appendTestOutput('Local WS Test: Make sure local WebSocket is connected (check console for [LocalWS] logs)');
        
        try {
            const response = await fetch(testUrl, { method: 'GET' });
            const result = await response.json();
            
            if (result.status === 'success') {
                appendTestOutput(`Local WS Test: SUCCESS - Test ID: ${result.testId}`);
                appendTestOutput(`Local WS Test: Sent ${result.eventsSent}/${result.eventsTotal} events`);
                appendTestOutput('Local WS Test: Check browser console (F12) for received messages');
                appendTestOutput('Local WS Test: Look for [LocalWS] logs showing received events');
                appendTestOutput('');
                appendTestOutput('Events sent:');
                result.results.forEach((r: any) => {
                    appendTestOutput(`  - ${r.event}: ${r.status}`);
                });
            } else {
                appendTestOutput(`Local WS Test: FAILED - ${result.error}`);
                if (result.traceback) {
                    appendTestOutput(result.traceback);
                }
            }
        } catch (error) {
            appendTestOutput(`Local WS Test: ERROR - ${error instanceof Error ? error.message : String(error)}`);
            appendTestOutput('Make sure the local server is running and accessible.');
        }
    };

    const handleC2CWebsocketTest = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const getEnv = () => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {});
        const env = getEnv();
        
        // Parse test argument first to allow API key override
        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }
        
        setTestOutput('');
        appendTestOutput('C2C WS Test: Starting...');
        appendTestOutput('C2C WS Test: This calls cloud runTest mutation directly from web frontend');
        appendTestOutput('C2C WS Test: The cloud_tester lambda will publish skill_editor.log events');
        appendTestOutput('C2C WS Test: If pub/sub works, you should see a log message in Skill Editor Console');
        
        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || env.VITE_APPSYNC_HTTP_ENDPOINT || defaultWanEndpoint);
        const wanApiKey = (settings?.wan_api_key?.trim() || parsedArgs.wanApiKey || parsedArgs.apiKey || env.VITE_APPSYNC_API_KEY || '');
        const owner = username || parsedArgs.owner || env.VITE_ACCOUNT_OWNER || '';
        
        appendTestOutput(`C2C WS Test: endpoint=${wanEndpoint}`);
        
        if (!wanApiKey) {
            appendTestOutput('C2C WS Test: ERROR - Missing API key. Set wan_api_key in Settings or VITE_APPSYNC_API_KEY env var');
            return;
        }
        if (!owner) {
            appendTestOutput('C2C WS Test: ERROR - Not logged in (no username)');
            return;
        }
        
        appendTestOutput(`C2C WS Test: owner=${owner}`);
        appendTestOutput(`C2C WS Test: Calling runTest mutation...`);
        
        const runTestMutation = `
            mutation RunTest($input: [TestInput]!) {
                runTest(input: $input)
            }
        `;
        
        const testInput = [{
            id: `c2c-ws-test-${Date.now()}`,
            name: 'C2C_WS_Test',
            description: 'Cloud to Cloud WebSocket Test',
            input: JSON.stringify({
                owner: owner,
                acctSiteID: `site-${owner}`,
                runner: owner,
            })
        }];
        
        try {
            const response = await fetch(wanEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-key': wanApiKey,
                },
                body: JSON.stringify({
                    query: runTestMutation,
                    variables: { input: testInput },
                }),
            });
            
            const result = await response.json();
            
            if (result.errors) {
                appendTestOutput(`C2C WS Test: GraphQL Errors: ${JSON.stringify(result.errors, null, 2)}`);
            }
            
            if (result.data?.runTest) {
                const parsed = typeof result.data.runTest === 'string' 
                    ? JSON.parse(result.data.runTest) 
                    : result.data.runTest;
                appendTestOutput(`C2C WS Test: SUCCESS`);
                appendTestOutput(`C2C WS Test: Response: ${JSON.stringify(parsed, null, 2)}`);
                appendTestOutput('');
                appendTestOutput('>>> Now check the Skill Editor Console (bottom panel) for a log message! <<<');
                appendTestOutput('>>> The message should say: "[C2C_WS_Test] Cloud tester log message..." <<<');
            } else {
                appendTestOutput(`C2C WS Test: No data returned`);
                appendTestOutput(`C2C WS Test: Full response: ${JSON.stringify(result, null, 2)}`);
            }
        } catch (error) {
            appendTestOutput(`C2C WS Test: ERROR - ${error instanceof Error ? error.message : String(error)}`);
        }
    };

    const handleSendPassiveCmd = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const getEnv = () => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {});
        const env = getEnv();
        
        // Parse test argument first to allow API key override
        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }
        
        setTestOutput('');
        appendTestOutput('Send PASSIVE CMD: Starting...');
        appendTestOutput('Send PASSIVE CMD: Calls publishPassiveCommand mutation directly');
        appendTestOutput('Send PASSIVE CMD: Required fields: clientId, runId, stepId, command');
        
        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || env.VITE_APPSYNC_HTTP_ENDPOINT || defaultWanEndpoint);
        const wanApiKey = (settings?.wan_api_key?.trim() || parsedArgs.wanApiKey || parsedArgs.apiKey || env.VITE_APPSYNC_API_KEY || '');
        
        appendTestOutput(`Send PASSIVE CMD: endpoint=${wanEndpoint}`);
        
        if (!wanApiKey) {
            appendTestOutput('Send PASSIVE CMD: ERROR - Missing API key. Provide in Settings (wan_api_key) or Test Argument as {"wanApiKey":"..."}');
            return;
        }
        
        // Required fields for publishPassiveCommand
        const clientId = parsedArgs.clientId || `client-${Date.now()}`;
        const runId = parsedArgs.runId || `run-${Date.now()}`;
        const stepId = parsedArgs.stepId || `step-${Date.now()}`;
        const command = parsedArgs.command || { action: 'ping', timestamp: new Date().toISOString() };
        
        appendTestOutput(`Send PASSIVE CMD: clientId=${clientId}`);
        appendTestOutput(`Send PASSIVE CMD: runId=${runId}`);
        appendTestOutput(`Send PASSIVE CMD: stepId=${stepId}`);
        appendTestOutput(`Send PASSIVE CMD: command=${JSON.stringify(command)}`);
        
        const publishPassiveCommandMutation = `
            mutation PublishPassiveCommand($input: PassiveBrowserCommandEnvelopeInput!) {
                publishPassiveCommand(input: $input) {
                    id
                    clientId
                    runId
                    stepId
                    command
                    timestamp
                }
            }
        `;
        
        const input = {
            clientId,
            runId,
            stepId,
            command: JSON.stringify(command)
        };
        
        appendTestOutput(`Send PASSIVE CMD: Sending mutation...`);
        
        try {
            const response = await fetch(wanEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'x-api-key': wanApiKey },
                body: JSON.stringify({ query: publishPassiveCommandMutation, variables: { input } }),
            });
            const result = await response.json();
            if (result.errors) {
                appendTestOutput(`Send PASSIVE CMD: GraphQL Errors:\n${JSON.stringify(result.errors, null, 2)}`);
            }
            if (result.data?.publishPassiveCommand) {
                appendTestOutput(`Send PASSIVE CMD: SUCCESS`);
                appendTestOutput(JSON.stringify(result.data.publishPassiveCommand, null, 2));
                appendTestOutput('');
                appendTestOutput('NOTE: Backend must be subscribed with matching clientId and runId to receive this.');
            } else {
                appendTestOutput(`Send PASSIVE CMD: No data returned\n${JSON.stringify(result, null, 2)}`);
            }
        } catch (error) {
            appendTestOutput(`Send PASSIVE CMD: ERROR - ${error instanceof Error ? error.message : String(error)}`);
        }
    };

    const handlePingCloudWorker = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const getEnv = () => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {});
        const env = getEnv();
        
        // Parse test argument first to allow API key override
        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }
        
        setTestOutput('');
        appendTestOutput('Ping Cloud Worker: Starting...');
        
        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || env.VITE_APPSYNC_HTTP_ENDPOINT || defaultWanEndpoint);
        const wanApiKey = (settings?.wan_api_key?.trim() || parsedArgs.wanApiKey || parsedArgs.apiKey || env.VITE_APPSYNC_API_KEY || '');
        const owner = username || parsedArgs.owner || env.VITE_ACCOUNT_OWNER || '';
        
        appendTestOutput(`Ping Cloud Worker: endpoint=${wanEndpoint}`);
        
        if (!wanApiKey) {
            appendTestOutput('Ping Cloud Worker: ERROR - Missing API key');
            return;
        }
        if (!owner) {
            appendTestOutput('Ping Cloud Worker: ERROR - Not logged in');
            return;
        }
        
        appendTestOutput(`Ping Cloud Worker: owner=${owner}`);
        
        const runTestMutation = `mutation RunTest($input: [TestInput]!) { runTest(input: $input) }`;
        
        const testInput = [{
            id: `ping-worker-${Date.now()}`,
            name: 'Ping_Cloud_Worker',
            description: 'Ping cloud worker lambda to check health',
            input: JSON.stringify({
                owner, acctSiteID: `site-${owner}`, runner: owner,
                action: 'ping', timestamp: new Date().toISOString(),
            })
        }];
        
        try {
            const response = await fetch(wanEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'x-api-key': wanApiKey },
                body: JSON.stringify({ query: runTestMutation, variables: { input: testInput } }),
            });
            const result = await response.json();
            if (result.errors) appendTestOutput(`Ping Cloud Worker: Errors: ${JSON.stringify(result.errors, null, 2)}`);
            if (result.data?.runTest) {
                const parsed = typeof result.data.runTest === 'string' ? JSON.parse(result.data.runTest) : result.data.runTest;
                appendTestOutput(`Ping Cloud Worker: SUCCESS\n${JSON.stringify(parsed, null, 2)}`);
                appendTestOutput('>>> Cloud worker is alive! <<<');
            } else {
                appendTestOutput(`Ping Cloud Worker: No data returned\n${JSON.stringify(result, null, 2)}`);
            }
        } catch (error) {
            appendTestOutput(`Ping Cloud Worker: ERROR - ${error instanceof Error ? error.message : String(error)}`);
        }
    };

    
    const handleStepCloudWorker = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const getEnv = () => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {});
        const env = getEnv();
        
        // Parse test argument first to allow API key override
        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }
        
        setTestOutput('');
        appendTestOutput('Step Cloud Worker: Starting...');
        
        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || env.VITE_APPSYNC_HTTP_ENDPOINT || defaultWanEndpoint);
        const wanApiKey = (settings?.wan_api_key?.trim() || parsedArgs.wanApiKey || parsedArgs.apiKey || env.VITE_APPSYNC_API_KEY || '');
        const owner = username || parsedArgs.owner || env.VITE_ACCOUNT_OWNER || '';
        
        appendTestOutput(`Step Cloud Worker: endpoint=${wanEndpoint}`);
        
        if (!wanApiKey) {
            appendTestOutput('Step Cloud Worker: ERROR - Missing API key');
            return;
        }
        if (!owner) {
            appendTestOutput('Step Cloud Worker: ERROR - Not logged in');
            return;
        }
        
        appendTestOutput(`Step Cloud Worker: owner=${owner}`);
        
        const runTestMutation = `mutation RunTest($input: [TestInput]!) { runTest(input: $input) }`;
        
        const testInput = [{
            id: `step-worker-${Date.now()}`,
            name: 'Step_Cloud_Worker',
            description: 'Step cloud worker to execute next action',
            input: JSON.stringify({
                owner, acctSiteID: parsedArgs.acctSiteID || `site-${owner}`, runner: owner,
                action: 'step', step_id: parsedArgs.step_id || 'default',
                payload: parsedArgs.payload || {},
            })
        }];
        
        try {
            const response = await fetch(wanEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'x-api-key': wanApiKey },
                body: JSON.stringify({ query: runTestMutation, variables: { input: testInput } }),
            });
            const result = await response.json();
            if (result.errors) appendTestOutput(`Step Cloud Worker: Errors: ${JSON.stringify(result.errors, null, 2)}`);
            if (result.data?.runTest) {
                const parsed = typeof result.data.runTest === 'string' ? JSON.parse(result.data.runTest) : result.data.runTest;
                appendTestOutput(`Step Cloud Worker: SUCCESS\n${JSON.stringify(parsed, null, 2)}`);
                appendTestOutput('>>> Cloud worker step executed! <<<');
            } else {
                appendTestOutput(`Step Cloud Worker: No data returned\n${JSON.stringify(result, null, 2)}`);
            }
        } catch (error) {
            appendTestOutput(`Step Cloud Worker: ERROR - ${error instanceof Error ? error.message : String(error)}`);
        }
    };

    const handleC2LWebsocketTest = async () => {
        setTestOutput('');
        appendTestOutput('C2L WS Test: Starting...');
        appendTestOutput('C2L WS Test: This sends a runTest mutation to cloud AppSync');
        
        // Get the local server port from settings
        const port = settings?.local_server_port || '4668';
        const testUrl = `http://localhost:${port}/api/c2l-ws-test`;
        
        appendTestOutput(`C2L WS Test: Calling ${testUrl}`);
        
        try {
            const response = await fetch(testUrl, { method: 'GET' });
            const result = await response.json();
            
            if (result.status === 'success') {
                appendTestOutput(`C2L WS Test: SUCCESS - Test ID: ${result.testId}`);
                appendTestOutput(`C2L WS Test: Cloud Response: ${JSON.stringify(result.cloudResponse, null, 2)}`);
                appendTestOutput('C2L WS Test: Check browser console (F12) for any WebSocket messages pushed from cloud');
            } else {
                appendTestOutput(`C2L WS Test: FAILED - ${result.error || 'Unknown error'}`);
                if (result.errors) {
                    appendTestOutput(`C2L WS Test: Errors: ${JSON.stringify(result.errors, null, 2)}`);
                }
                if (result.traceback) {
                    appendTestOutput(result.traceback);
                }
            }
        } catch (error) {
            appendTestOutput(`C2L WS Test: ERROR - ${error instanceof Error ? error.message : String(error)}`);
            appendTestOutput('Make sure the local server is running and you are logged in.');
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
                    {/* WebSocket Test Buttons - 2nd row */}
                    <Space style={{ marginBottom: '8px' }}>
                        <Button onClick={handleWebsocketTest}>
                            WebSocket Test
                        </Button>
                        <Button onClick={handleLocalWebsocketTest} style={{ marginLeft: 8 }}>
                            Local WS Test
                        </Button>
                        <Button onClick={handleC2LWebsocketTest} style={{ marginLeft: 8 }}>
                            C2L WS Test
                        </Button>
                        <Button onClick={handleC2CWebsocketTest} style={{ marginLeft: 8 }} type="primary">
                            C2C WS Test
                        </Button>
                        <Button onClick={handleSendPassiveCmd} style={{ marginLeft: 8 }}>
                            Send PASSIVE CMD
                        </Button>
                        <Button onClick={handlePingCloudWorker} style={{ marginLeft: 8 }}>
                            Ping Cloud Worker
                        </Button>
                    </Space>
                    {/* Cloud Worker Test Buttons - 3rd row */}
                    <Space style={{ marginBottom: '8px' }}>
                        <Button onClick={handleStepCloudWorker} style={{ marginLeft: 8 }}>
                            Step Cloud Worker
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
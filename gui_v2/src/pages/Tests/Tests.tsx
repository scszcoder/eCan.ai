import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Space, Select, Input, Button, Card, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {get_ipc_api} from '../../services/ipc_api';
import { useUserStore } from '../../stores/userStore';
import { useSettingsStore } from '../../stores/settingsStore';
import { isDesktopPlatform, detectPlatform } from '../../config/platform';
import { useNavigate } from 'react-router-dom';
import { canvasController } from '../../modules/skill-editor/services/canvas-controller';
import {
    downloadWithPresignedUrl,
    uploadWithPresignedUrl,
    PresignedRequest
} from '../../services/web/presignedFileOps';

const { Title, Text } = Typography;
const { TextArea } = Input;

// ── Channel test types & constants (outside component to avoid recreation) ──
interface ChannelEntry { id: string; label: string; enabled: boolean; status: string; }
interface ChanMsg { direction: 'in' | 'out'; channel_id: string; chat_id: string; sender_name: string; text: string; timestamp: number; message_id: string; }

const CHAN_LABELS: Record<string, string> = {
    whatsapp_baileys: 'WhatsApp (Baileys)', whatsapp: 'WhatsApp (Cloud API)',
    telegram: 'Telegram', slack: 'Slack', discord: 'Discord',
    dingtalk: 'DingTalk', messenger: 'Messenger', twitter: 'Twitter/X', webchat: 'Web Chat',
};

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
    const navigate = useNavigate();

    const appendTestOutput = (line: string) => {
        setTestOutput(prev => (prev ? `${prev}\n${line}` : line));
    };

    // ── Channel test state ────────────────────────────────────────────────────

    const [channelList, setChannelList] = useState<ChannelEntry[]>([]);
    const [selectedChannel, setSelectedChannel] = useState<string>('');
    const [channelRecipient, setChannelRecipient] = useState<string>('');
    const [channelSending, setChannelSending] = useState(false);
    const [chanMessages, setChanMessages] = useState<ChanMsg[]>([]);
    const sinceTs = useRef<number>(Date.now() / 1000);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const msgBoxRef = useRef<HTMLDivElement>(null);

    const loadChannels = useCallback(async () => {
        try {
            const resp: any = await get_ipc_api().getChannels();
            if (resp?.success && resp.data?.channels) {
                setChannelList(Object.entries(resp.data.channels).map(([id, entry]: any) => ({
                    id,
                    label: CHAN_LABELS[id] || id,
                    enabled: entry.config?.enabled === true,
                    status: entry.status || 'stopped',
                })));
            }
        } catch {}
    }, []);

    useEffect(() => { loadChannels(); }, [loadChannels]);

    // Poll for inbound messages when a channel is selected
    useEffect(() => {
        if (!selectedChannel) { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } return; }
        if (pollRef.current) return;
        pollRef.current = setInterval(async () => {
            try {
                const resp: any = await get_ipc_api().getChannelTestMessages(selectedChannel, sinceTs.current);
                if (resp?.success && resp.data?.messages?.length) {
                    const incoming: ChanMsg[] = resp.data.messages.map((m: any) => ({ ...m, direction: 'in' as const }));
                    setChanMessages(prev => [...prev, ...incoming]);
                    // Also append to the shared test output
                    incoming.forEach(m => appendTestOutput(`[${m.channel_id}] FROM ${m.sender_name || m.chat_id}: ${m.text}`));
                    sinceTs.current = Math.max(...incoming.map((m: any) => m.received_at ?? m.timestamp)) + 0.001;
                }
            } catch {}
        }, 2000);
        return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
    }, [selectedChannel]);

    useEffect(() => {
        if (msgBoxRef.current) msgBoxRef.current.scrollTop = msgBoxRef.current.scrollHeight;
    }, [chanMessages]);

    const handleTestChannel = async () => {
        if (!selectedChannel || !channelRecipient.trim() || !testArgument.trim()) {
            message.warning('Select a channel, enter a recipient, and type a message in Test Argument');
            return;
        }
        setChannelSending(true);
        const outMsg: ChanMsg = { direction: 'out', channel_id: selectedChannel, chat_id: channelRecipient, sender_name: 'Me', text: testArgument, timestamp: Date.now() / 1000, message_id: String(Math.random()) };
        setChanMessages(prev => [...prev, outMsg]);
        appendTestOutput(`[${selectedChannel}] TO ${channelRecipient}: ${testArgument}`);
        try {
            const resp: any = await get_ipc_api().sendChannelMessage(selectedChannel, channelRecipient, testArgument);
            if (!resp?.success) {
                message.error(resp?.error?.message || 'Send failed');
                setChanMessages(prev => prev.filter(m => m.message_id !== outMsg.message_id));
                appendTestOutput(`[SEND ERROR] ${resp?.error?.message || 'Send failed'}`);
            } else {
                const jid = resp.data?.resolved_jid || channelRecipient;
                appendTestOutput(`[SENT OK] to JID: ${jid}`);
            }
        } catch (e: any) {
            message.error(String(e?.message || e));
            appendTestOutput(`[SEND ERROR] ${e?.message || e}`);
        } finally {
            setChannelSending(false);
        }
    };

    // Add default test at the top of the component
    const defaultTest = {
        label: 'Default Test',
        value: 'default_test'
    };

    // Debug: Ping IPC
    const handlePingIPC = async () => {
        const isDesktop = isDesktopPlatform();
        console.log('[Tests] PingIPC: isDesktop?', isDesktop);
        message.info(`Ping IPC: isDesktop=${isDesktop}`);
        if (!isDesktop) {
            setTestOutput('PingIPC: Web mode (no IPC support)');
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
        const isDesktop = isDesktopPlatform();
        console.log('[Tests] STEP7: start run (deferred IPC)', { selectedTest, isDesktop });
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

    const handleTestHybridCloud = async () => {
        setTestOutput('');
        appendTestOutput('Hybrid Cloud Test: Calling launch_agent_task for test_hybrid_worker...');
        const port = settings?.local_server_port || '4668';
        const testUrl = `http://localhost:${port}/api/test-hybrid-cloud`;
        try {
            const response = await fetch(testUrl, { method: 'GET' });
            const result = await response.json();
            appendTestOutput(`Hybrid Cloud Test: Response ${response.status}`);
            appendTestOutput(JSON.stringify(result, null, 2));
            if (result.status === 'ok' && result.result?.success) {
                message.success(`Hybrid cloud task launched: ${result.result.message}`);
            } else {
                message.error(`Failed: ${result.result?.error || result.error || 'Unknown error'}`);
            }
        } catch (error) {
            appendTestOutput(`Hybrid Cloud Test: ERROR - ${error instanceof Error ? error.message : String(error)}`);
            message.error('Failed to call test-hybrid-cloud endpoint');
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
        const getEnv = (): ImportMetaEnv => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : ({} as ImportMetaEnv));
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
        const getEnv = (): ImportMetaEnv => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : ({} as ImportMetaEnv));
        const env = getEnv();
        
        // Parse test argument first to allow overrides
        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }
        
        setTestOutput('');
        appendTestOutput('Send PASSIVE CMD: Starting...');
        appendTestOutput('Send PASSIVE CMD: Calls cloud runTest mutation -> Lambda -> publishPassiveCommand');
        
        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || env.VITE_APPSYNC_HTTP_ENDPOINT || defaultWanEndpoint);
        const wanApiKey = (settings?.wan_api_key?.trim() || parsedArgs.wanApiKey || parsedArgs.apiKey || env.VITE_APPSYNC_API_KEY || '');
        const owner = username || parsedArgs.owner || env.VITE_ACCOUNT_OWNER || '';
        
        appendTestOutput(`Send PASSIVE CMD: endpoint=${wanEndpoint}`);
        
        if (!wanApiKey) {
            appendTestOutput('Send PASSIVE CMD: ERROR - Missing API key. Provide in Settings (wan_api_key) or Test Argument as {"wanApiKey":"..."}');
            return;
        }
        if (!owner) {
            appendTestOutput('Send PASSIVE CMD: ERROR - Not logged in');
            return;
        }
        
        appendTestOutput(`Send PASSIVE CMD: owner=${owner}`);
        
        // Build params for Lambda's testSendPassiveCmd function
        // Lambda expects: clientId, runId, stepId, command
        const clientId = parsedArgs.clientId || parsedArgs.client_id || `client-${Date.now()}`;
        const runId = parsedArgs.runId || parsedArgs.run_id || `run-${Date.now()}`;
        const stepId = parsedArgs.stepId || parsedArgs.step_id || `step-${Date.now()}`;
        const command = parsedArgs.command || { action: 'ping', timestamp: new Date().toISOString() };
        
        appendTestOutput(`Send PASSIVE CMD: clientId=${clientId}`);
        appendTestOutput(`Send PASSIVE CMD: runId=${runId}`);
        appendTestOutput(`Send PASSIVE CMD: stepId=${stepId}`);
        appendTestOutput(`Send PASSIVE CMD: command=${JSON.stringify(command)}`);
        
        const runTestMutation = `mutation RunTest($input: [TestInput]!) { runTest(input: $input) }`;
        
        const testInput = [{
            id: `passive-cmd-${Date.now()}`,
            name: 'Send_PASSIVE_CMD',
            description: 'Send a passive command via cloud Lambda',
            input: JSON.stringify({
                owner,
                clientId,
                runId,
                stepId,
                command
            })
        }];
        
        appendTestOutput('Send PASSIVE CMD: Sending runTest mutation to Lambda...');
        
        try {
            const response = await fetch(wanEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'x-api-key': wanApiKey },
                body: JSON.stringify({ query: runTestMutation, variables: { input: testInput } }),
            });
            const result = await response.json();
            if (result.errors) appendTestOutput(`Send PASSIVE CMD: Errors: ${JSON.stringify(result.errors, null, 2)}`);
            if (result.data?.runTest) {
                const parsed = typeof result.data.runTest === 'string' ? JSON.parse(result.data.runTest) : result.data.runTest;
                appendTestOutput(`Send PASSIVE CMD: SUCCESS\n${JSON.stringify(parsed, null, 2)}`);
            } else {
                appendTestOutput(`Send PASSIVE CMD: No data returned\n${JSON.stringify(result, null, 2)}`);
            }
        } catch (error) {
            appendTestOutput(`Send PASSIVE CMD: ERROR - ${error instanceof Error ? error.message : String(error)}`);
        }
    };

    const handlePingCloudWorker = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const getEnv = (): ImportMetaEnv => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : ({} as ImportMetaEnv));
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
        const getEnv = (): ImportMetaEnv => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : ({} as ImportMetaEnv));
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

    const handleL2CWebsocketTest = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const getEnv = (): ImportMetaEnv => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : ({} as ImportMetaEnv));
        const env = getEnv();
        
        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }
        
        setTestOutput('');
        appendTestOutput('L2C WS Test: Starting...');
        appendTestOutput('L2C WS Test: Sends publishPassiveStepResult mutation directly to AppSync');
        appendTestOutput('L2C WS Test: This simulates a local client sending step results to cloud');
        
        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || env.VITE_APPSYNC_HTTP_ENDPOINT || defaultWanEndpoint);
        const owner = username || parsedArgs.owner || env.VITE_ACCOUNT_OWNER || '';
        
        appendTestOutput(`L2C WS Test: endpoint=${wanEndpoint}`);
        
        // Get Cognito JWT token from Python backend via IPC
        const { IPCAPI } = await import('../../services/ipc/api');
        let cognitoToken = '';
        try {
            appendTestOutput('L2C WS Test: Calling IPC get_auth_token...');
            const api = IPCAPI.getInstance();
            const tokenResp = await api.getAuthToken();
            appendTestOutput(`L2C WS Test: IPC response: success=${tokenResp.success}, hasData=${!!tokenResp.data}, error=${JSON.stringify(tokenResp.error || null)}`);
            if (tokenResp.success && tokenResp.data) {
                cognitoToken = tokenResp.data;
                appendTestOutput(`L2C WS Test: Got token from IPC (length: ${cognitoToken.length})`);
            }
        } catch (e) {
            appendTestOutput(`L2C WS Test: IPC get_auth_token error: ${e}`);
        }
        
        // Fallback to web session if IPC fails
        if (!cognitoToken) {
            appendTestOutput('L2C WS Test: IPC token not available, trying web session...');
            const { webAuthSession } = await import('../../services/auth/webAuthSession');
            const session = webAuthSession.getSession();
            appendTestOutput(`L2C WS Test: Web session: hasIdToken=${!!session?.idToken}, hasAccessToken=${!!session?.accessToken}`);
            cognitoToken = session?.idToken || session?.accessToken || '';
        }
        
        if (!cognitoToken) {
            appendTestOutput('L2C WS Test: ERROR - No Cognito JWT token found. Please log in first.');
            return;
        }
        
        appendTestOutput(`L2C WS Test: Using Cognito JWT auth (token length: ${cognitoToken.length})`);
        appendTestOutput(`L2C WS Test: owner=${owner || '(anonymous)'}`);
        
        const clientId = parsedArgs.clientId || parsedArgs.client_id || 'songc_yahoo_com_SCHOME';
        const runId = parsedArgs.runId || parsedArgs.run_id || '0123456789';
        const stepId = parsedArgs.stepId || parsedArgs.step_id || '001';
        
        // Default test data packet
        const resultPayload = parsedArgs.result || {
            schema_version: 1,
            type: 'browser_use_passive_step_result',
            ok: true,
            elapsed_ms: 5,
            actions: [{ action: 'noop' }],
            action_results: [{ ok: true }],
            errors: [],
            browser: {}
        };
        
        // Default dom_tree
        const domTreePayload = parsedArgs.dom_tree || parsedArgs.domTree || { nodes: [] };
        
        appendTestOutput(`L2C WS Test: clientId=${clientId}`);
        appendTestOutput(`L2C WS Test: runId=${runId}`);
        appendTestOutput(`L2C WS Test: stepId=${stepId}`);
        appendTestOutput(`L2C WS Test: result=${JSON.stringify(resultPayload).substring(0, 100)}...`);
        appendTestOutput(`L2C WS Test: dom_tree=${JSON.stringify(domTreePayload).substring(0, 50)}...`);
        
        const publishPassiveStepResultMutation = `
            mutation PublishPassiveStepResult($input: PassiveBrowserStepResultEnvelopeInput!) {
                publishPassiveStepResult(input: $input) {
                    clientId
                    runId
                    stepId
                    result
                    dom_tree
                }
            }
        `;
        
        // Both result and dom_tree are AWSJSON - send as JSON strings
        const mutationInput = {
            clientId,
            runId,
            stepId,
            result: JSON.stringify(resultPayload),
            dom_tree: JSON.stringify(domTreePayload),
        };
        
        appendTestOutput('L2C WS Test: Sending publishPassiveStepResult mutation with Cognito JWT...');
        const mutationPayload = {
            query: publishPassiveStepResultMutation,
            variables: { input: mutationInput },
        };
        appendTestOutput(`L2C WS Test: Full mutation payload=${JSON.stringify(mutationPayload)}`);
        
        try {
            const response = await fetch(wanEndpoint, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json', 
                    'Authorization': cognitoToken,  // Cognito JWT auth
                },
                body: JSON.stringify(mutationPayload),
            });
            const result = await response.json();
            
            if (result.errors) {
                appendTestOutput(`L2C WS Test: GraphQL Errors: ${JSON.stringify(result.errors, null, 2)}`);
            }
            
            if (result.data?.publishPassiveStepResult) {
                appendTestOutput(`L2C WS Test: SUCCESS`);
                appendTestOutput(`L2C WS Test: Response: ${JSON.stringify(result.data.publishPassiveStepResult, null, 2)}`);
                appendTestOutput('');
                appendTestOutput('>>> If cloud agent is subscribed to onPassiveStepResult, it should receive this! <<<');
            } else {
                appendTestOutput(`L2C WS Test: No data returned`);
                appendTestOutput(`L2C WS Test: Full response: ${JSON.stringify(result, null, 2)}`);
            }
        } catch (error) {
            appendTestOutput(`L2C WS Test: ERROR - ${error instanceof Error ? error.message : String(error)}`);
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

    const handleRunCloudTask = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const getEnv = (): ImportMetaEnv => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : ({} as ImportMetaEnv));
        const env = getEnv();

        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }

        setTestOutput('');
        appendTestOutput('Run Cloud Task: Starting...');

        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || env.VITE_APPSYNC_HTTP_ENDPOINT || defaultWanEndpoint);

        const { IPCAPI } = await import('../../services/ipc/api');
        let cognitoToken = '';
        try {
            const api = IPCAPI.getInstance();
            const tokenResp = await api.getAuthToken();
            if (tokenResp.success && tokenResp.data) {
                cognitoToken = tokenResp.data;
                appendTestOutput(`Run Cloud Task: Got auth token (length: ${cognitoToken.length})`);
            }
        } catch (e) {
            appendTestOutput(`Run Cloud Task: IPC get_auth_token error: ${e}`);
        }

        if (!cognitoToken) {
            appendTestOutput('Run Cloud Task: ERROR - No Cognito JWT token. Please log in first.');
            return;
        }

        // Build CloudTaskInput list from test arguments
        // Use task_id for actual IDs, task_name for human-readable names
        const taskIds = parsedArgs.taskIds || parsedArgs.task_ids || null;
        const taskId = parsedArgs.taskId || parsedArgs.task_id || null;
        const agentId = parsedArgs.agentId || parsedArgs.agent_id || null;
        const taskName = parsedArgs.taskName || parsedArgs.task_name || 'test_hybrid_worker';
        const options = parsedArgs.options || {};

        const cloudTaskInputs: any[] = [];
        if (taskIds) {
            // Explicit list of task IDs
            for (const tid of taskIds) {
                const entry: any = { task_id: tid, options: JSON.stringify(options) };
                if (agentId) entry.agent_id = agentId;
                if (taskName && taskName !== 'test_hybrid_worker') entry.task_name = taskName;
                cloudTaskInputs.push(entry);
            }
        } else {
            // Single task: use task_id if provided, otherwise use task_name
            const entry: any = { options: JSON.stringify(options) };
            if (taskId) entry.task_id = taskId;
            if (taskName) entry.task_name = taskName;
            if (agentId) entry.agent_id = agentId;
            cloudTaskInputs.push(entry);
        }

        appendTestOutput(`Run Cloud Task: input=${JSON.stringify(cloudTaskInputs)}`);
        appendTestOutput(`Run Cloud Task: endpoint=${wanEndpoint}`);

        const runCloudTasksMutation = `
            mutation RunCloudTasks($input: [CloudTaskInput]!) {
                runCloudTasks(input: $input)
            }
        `;

        appendTestOutput('Run Cloud Task: Sending runCloudTasks mutation...');

        try {
            const response = await fetch(wanEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': cognitoToken,
                },
                body: JSON.stringify({
                    query: runCloudTasksMutation,
                    variables: { input: cloudTaskInputs },
                }),
            });
            const result = await response.json();

            if (result.errors) {
                appendTestOutput(`Run Cloud Task: GraphQL Errors: ${JSON.stringify(result.errors, null, 2)}`);
            }

            if (result.data?.runCloudTasks) {
                const raw = result.data.runCloudTasks;
                const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
                appendTestOutput(`Run Cloud Task: SUCCESS`);
                appendTestOutput(`Run Cloud Task: Response: ${JSON.stringify(parsed, null, 2)}`);
            } else {
                appendTestOutput(`Run Cloud Task: No data returned`);
                appendTestOutput(`Run Cloud Task: Full response: ${JSON.stringify(result, null, 2)}`);
            }
        } catch (error) {
            appendTestOutput(`Run Cloud Task: ERROR - ${error instanceof Error ? error.message : String(error)}`);
        }
    };

    const handleGetRunId = async () => {
        const defaultWanEndpoint = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
        const getEnv = (): ImportMetaEnv => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : ({} as ImportMetaEnv));
        const env = getEnv();

        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }

        setTestOutput('');
        appendTestOutput('Get Run ID: Starting...');

        const wanEndpoint = (settings?.wan_api_endpoint?.trim() || parsedArgs.wanEndpoint || env.VITE_APPSYNC_HTTP_ENDPOINT || defaultWanEndpoint);

        const { IPCAPI } = await import('../../services/ipc/api');
        let cognitoToken = '';
        try {
            const api = IPCAPI.getInstance();
            const tokenResp = await api.getAuthToken();
            if (tokenResp.success && tokenResp.data) {
                cognitoToken = tokenResp.data;
                appendTestOutput(`Get Run ID: Got auth token (length: ${cognitoToken.length})`);
            }
        } catch (e) {
            appendTestOutput(`Get Run ID: IPC get_auth_token error: ${e}`);
        }

        if (!cognitoToken) {
            appendTestOutput('Get Run ID: ERROR - No Cognito JWT token. Please log in first.');
            return;
        }

        const taskId = parsedArgs.taskId || parsedArgs.task_id || 'test_hybrid_worker';
        const hostName = parsedArgs.hostName || parsedArgs.host_name || null;
        const metaData = parsedArgs.metaData || parsedArgs.meta_data || {};

        appendTestOutput(`Get Run ID: task_id=${taskId}`);
        appendTestOutput(`Get Run ID: host_name=${hostName}`);
        appendTestOutput(`Get Run ID: endpoint=${wanEndpoint}`);

        const queryCloudTaskRunIdQuery = `
            query QueryCloudTaskRunId($input: TaskRunQueryInput!) {
                queryCloudTaskRunId(input: $input) {
                    id runID runner status success error timestamp
                }
            }
        `;

        const toAwsJson = (value: any) => {
            if (value === undefined || value === null) return null;
            return typeof value === 'string' ? value : JSON.stringify(value);
        };

        const input = {
            task_id: taskId,
            host_name: hostName,
            meta_data: toAwsJson(metaData),
        };

        appendTestOutput('Get Run ID: Sending queryCloudTaskRunId query...');

        try {
            const response = await fetch(wanEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': cognitoToken,
                },
                body: JSON.stringify({
                    query: queryCloudTaskRunIdQuery,
                    variables: { input },
                }),
            });
            const result = await response.json();

            if (result.errors) {
                appendTestOutput(`Get Run ID: GraphQL Errors: ${JSON.stringify(result.errors, null, 2)}`);
            }

            const data = result.data?.queryCloudTaskRunId;
            if (data) {
                appendTestOutput(`Get Run ID: SUCCESS`);
                appendTestOutput(`Get Run ID: runID=${data.runID}`);
                appendTestOutput(`Get Run ID: runner=${data.runner}`);
                appendTestOutput(`Get Run ID: status=${data.status}`);
                appendTestOutput(`Get Run ID: success=${data.success}`);
                appendTestOutput(`Get Run ID: error=${data.error}`);
                appendTestOutput(`Get Run ID: Full response: ${JSON.stringify(data, null, 2)}`);
            } else {
                appendTestOutput(`Get Run ID: No data returned`);
                appendTestOutput(`Get Run ID: Full response: ${JSON.stringify(result, null, 2)}`);
            }
        } catch (error) {
            appendTestOutput(`Get Run ID: ERROR - ${error instanceof Error ? error.message : String(error)}`);
        }
    };

    const handleOcrTest = async () => {
        setTestOutput('');
        appendTestOutput('OCR Test: Starting...');

        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }

        const winTitleKw = parsedArgs.win_title_kw || '';
        const port = settings?.local_server_port || '4668';
        const testUrl = `http://localhost:${port}/api/test-ocr`;

        appendTestOutput(`OCR Test: endpoint=${testUrl}`);
        appendTestOutput(`OCR Test: win_title_kw="${winTitleKw}"`);
        appendTestOutput('OCR Test: Capturing screen and running OCR...');

        try {
            const response = await fetch(testUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ win_title_kw: winTitleKw }),
            });
            const result = await response.json();

            if (result.status === 'success') {
                appendTestOutput(`OCR Test: SUCCESS - ${result.result_count} items detected`);
                appendTestOutput(`OCR Test: win_title_kw="${result.win_title_kw}"`);
                appendTestOutput(JSON.stringify(result.result, null, 2));
            } else {
                appendTestOutput(`OCR Test: FAILED - ${result.error}`);
                if (result.traceback) {
                    appendTestOutput(result.traceback);
                }
            }
        } catch (error) {
            appendTestOutput(`OCR Test: ERROR - ${error instanceof Error ? error.message : String(error)}`);
            appendTestOutput('Make sure the local server is running.');
        }
    };

    const handleOcrLocalTest = async () => {
        setTestOutput('');
        appendTestOutput('OCR Local Test: Starting (PaddleOCR)...');

        let parsedArgs: any = {};
        try { parsedArgs = testArgument ? JSON.parse(testArgument) : {}; } catch (e) { }

        const port = settings?.local_server_port || '4668';
        const testUrl = `http://localhost:${port}/api/test-ocr-local`;

        const imagePath = parsedArgs.image_path || '';
        appendTestOutput(`OCR Local Test: endpoint=${testUrl}`);
        appendTestOutput(`OCR Local Test: image_path="${imagePath || '(default: ocr/test_image0.PNG)'}"`);
        appendTestOutput('OCR Local Test: Running PaddleOCR...');

        try {
            const bodyPayload: any = {};
            if (imagePath) bodyPayload.image_path = imagePath;

            const response = await fetch(testUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(bodyPayload),
            });
            const result = await response.json();

            if (result.status === 'success') {
                appendTestOutput(`OCR Local Test: SUCCESS - ${result.results?.length || 0} text items detected`);
                appendTestOutput(`OCR Local Test: image_path="${result.image_path}"`);
                if (result.results && result.results.length > 0) {
                    result.results.forEach((item: any, idx: number) => {
                        appendTestOutput(`  [${idx}] "${item.text}" (conf=${item.confidence}) box=${JSON.stringify(item.box)}`);
                    });
                } else {
                    appendTestOutput('OCR Local Test: No text detected in image.');
                }
            } else {
                appendTestOutput(`OCR Local Test: FAILED - ${result.error}`);
                if (result.traceback) {
                    appendTestOutput(result.traceback);
                }
            }
        } catch (error) {
            appendTestOutput(`OCR Local Test: ERROR - ${error instanceof Error ? error.message : String(error)}`);
            appendTestOutput('Make sure the local server is running and paddleocr is installed.');
        }
    };

    const handleTestRxSkill = async () => {
        setTestOutput('');
        appendTestOutput('Test RX Skill: Emulating cloud-generated skill receive + load...');
        appendTestOutput(`Platform: ${detectPlatform()}`);
        appendTestOutput(`Username: ${username || '(none)'}`);

        // Build a mock flowgram identical to what ChatPanel receives from the cloud agent
        const mockFlowgram = {
            nodes: [
                {
                    id: 'start',
                    type: 'start',
                    meta: { position: { x: 100, y: 200 } },
                    data: { title: 'Start', outputs: { type: 'object', properties: {} } },
                },
                {
                    id: 'code_1',
                    type: 'code',
                    meta: { position: { x: 400, y: 200 } },
                    data: { title: 'Code Node', inputsValues: { code: 'print("hello")' } },
                },
                {
                    id: 'end',
                    type: 'end',
                    meta: { position: { x: 700, y: 200 } },
                    data: { title: 'End' },
                },
            ],
            edges: [
                { sourceNodeID: 'start', targetNodeID: 'code_1' },
                { sourceNodeID: 'code_1', targetNodeID: 'end' },
            ],
            metadata: {
                skillName: 'generated',
                description: 'Test RX mock skill',
            },
        };

        appendTestOutput(`Mock flowgram: ${mockFlowgram.nodes.length} nodes, ${mockFlowgram.edges.length} edges`);
        appendTestOutput('Loading flowgram into canvasController (same as ChatPanel does)...');

        try {
            const loadResult = await canvasController.loadFlowgram(mockFlowgram);
            appendTestOutput('--- loadFlowgram result ---');
            appendTestOutput(JSON.stringify(loadResult, null, 2));

            if (loadResult.success) {
                appendTestOutput('Flowgram loaded OK. Navigating to Skill Editor in 1s...');
                appendTestOutput('Once there, click Save to test the save path.');
                setTimeout(() => {
                    navigate('/skill_editor');
                }, 1000);
            } else {
                appendTestOutput('FAIL: loadFlowgram returned error: ' + (loadResult.error || 'unknown'));
            }
        } catch (error) {
            appendTestOutput('ERROR: ' + (error instanceof Error ? error.message : String(error)));
            console.error('[Tests] handleTestRxSkill error:', error);
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
                                const isDesktop = isDesktopPlatform();
                                console.log('[Tests] Direct API: run_tests array (5s)', { isDesktop, selectedTest });
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
                                const isDesktop = isDesktopPlatform();
                                console.log('[Tests] Direct API: runSingleTest (3s)', { isDesktop, selectedTest });
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
                        <Button onClick={handleL2CWebsocketTest} style={{ marginLeft: 8 }}>
                            L2C WS Test
                        </Button>
                        <Button onClick={handleRunCloudTask} style={{ marginLeft: 8 }} type="primary">
                            Run Cloud Task
                        </Button>
                        <Button
                            type="primary"
                            onClick={handleTestHybridCloud}
                            style={{
                                marginLeft: 8,
                                background: '#722ed1',
                                borderColor: '#722ed1',
                            }}
                        >
                            Test Hybrid Cloud
                        </Button>
                        <Button onClick={handleGetRunId} style={{ marginLeft: 8 }}>
                            Get Run ID
                        </Button>
                        <Button
                            onClick={handleOcrTest}
                            style={{
                                marginLeft: 8,
                                background: '#13c2c2',
                                borderColor: '#13c2c2',
                                color: '#fff',
                            }}
                        >
                            OCR Test
                        </Button>
                    </Space>
                    {/* Local OCR & Misc Test Buttons - 4th row */}
                    <Space style={{ marginBottom: '8px' }}>
                        <Button
                            onClick={handleOcrLocalTest}
                            style={{
                                background: '#fa8c16',
                                borderColor: '#fa8c16',
                                color: '#fff',
                            }}
                        >
                            Test OCR Local
                        </Button>
                        <Button
                            onClick={handleTestRxSkill}
                            style={{
                                marginLeft: 8,
                                background: '#1890ff',
                                borderColor: '#1890ff',
                                color: '#fff',
                            }}
                        >
                            Test RX Skill
                        </Button>
                        <Button
                            onClick={async () => {
                                console.log('[Tests] Test Task button clicked');
                                setTestOutput('Test Task: calling create_agent_task_with_skill + launch_agent_task...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testTask(),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('TEST_TASK_TIMEOUT (30s)')), 30000))
                                    ]);
                                    console.log('[Tests] Test Task result', resp);
                                    setTestOutput('Test Task result:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    console.warn('[Tests] Test Task error', e);
                                    setTestOutput('Test Task error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#52c41a',
                                borderColor: '#52c41a',
                                color: '#fff',
                            }}
                        >
                            Test Task
                        </Button>
                        <Button
                            onClick={async () => {
                                setTestOutput('Test Feige Tabs (Inventory): enumerating Chrome targets and snapshotting each Feige tab...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testFeigeTabs({ mode: 'inventory' }),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('FEIGE_TAB_TEST_TIMEOUT (45s)')), 45000)),
                                    ]);
                                    setTestOutput('Feige Tabs Inventory:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('Feige Tabs Inventory error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#eb2f96',
                                borderColor: '#eb2f96',
                                color: '#fff',
                            }}
                        >
                            Test Feige Tabs (Inventory)
                        </Button>
                        <Button
                            onClick={async () => {
                                // testArgument: comma-separated "customer_a,customer_b,optional_message_text"
                                const argRaw = (testArgument || '').trim();
                                const parts = argRaw.split(',').map(s => s.trim()).filter(s => s.length > 0);
                                const customer_a = parts[0] || '';
                                const customer_b = parts[1] || '';
                                const message_text = parts[2] || undefined;
                                if (!customer_a || !customer_b) {
                                    message.warning('Concurrent Send: put "customerA,customerB[,messageText]" in Test Argument first (e.g. "客户01,客户02"). Test customers only — they will receive a real message.');
                                    return;
                                }
                                setTestOutput(`Test Feige Tabs (Concurrent Send): typing into "${customer_a}" and "${customer_b}" simultaneously...`);
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testFeigeTabs({
                                            mode: 'concurrent_send',
                                            customer_a,
                                            customer_b,
                                            message_text,
                                        }),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('FEIGE_TAB_TEST_TIMEOUT (60s)')), 60000)),
                                    ]);
                                    setTestOutput('Feige Tabs Concurrent Send:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('Feige Tabs Concurrent Send error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#cf1322',
                                borderColor: '#cf1322',
                                color: '#fff',
                            }}
                        >
                            Test Feige Tabs (Concurrent Send)
                        </Button>
                    </Space>
                    {/* LLM Proxy Test Buttons - 5th row */}
                    <Space style={{ marginBottom: '8px' }}>
                        <Button
                            onClick={async () => {
                                setTestOutput('Pinging Lambda proxy...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testLambdaProxyPing(),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('PING_TIMEOUT (10s)')), 10000))
                                    ]);
                                    setTestOutput('Proxy Ping:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('Proxy Ping error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                background: '#722ed1',
                                borderColor: '#722ed1',
                                color: '#fff',
                            }}
                        >
                            Ping Proxy
                        </Button>
                        <Button
                            onClick={async () => {
                                setTestOutput('Listing proxy models...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testLlmProxyModels(),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('MODELS_TIMEOUT (20s)')), 20000))
                                    ]);
                                    setTestOutput('Proxy Models:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('Proxy Models error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#722ed1',
                                borderColor: '#722ed1',
                                color: '#fff',
                            }}
                        >
                            Models
                        </Button>
                        <Button
                            onClick={async () => {
                                const prompt = testArgument || undefined;
                                setTestOutput('Testing LLM via proxy...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testLambdaProxyLlm(prompt ? { prompt } : undefined),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('LLM_TIMEOUT (60s)')), 60000))
                                    ]);
                                    setTestOutput('Proxy LLM Test:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('Proxy LLM error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#722ed1',
                                borderColor: '#722ed1',
                                color: '#fff',
                            }}
                        >
                            Proxy LLM
                        </Button>
                        <Button
                            onClick={async () => {
                                const prompt = testArgument || undefined;
                                setTestOutput('Testing browser-use LLM via proxy...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testLambdaProxyBrowserUse(prompt ? { prompt } : undefined),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('BU_TIMEOUT (60s)')), 60000))
                                    ]);
                                    setTestOutput('Proxy Browser-Use Test:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('Proxy Browser-Use error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#722ed1',
                                borderColor: '#722ed1',
                                color: '#fff',
                            }}
                        >
                            Proxy BU LLM
                        </Button>
                        <Button
                            onClick={async () => {
                                const text = testArgument || undefined;
                                setTestOutput('Testing embedding via proxy...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testLambdaProxyEmbedding(text ? { text } : undefined),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('EMBED_TIMEOUT (30s)')), 30000))
                                    ]);
                                    setTestOutput('Proxy Embedding Test:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('Proxy Embedding error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#722ed1',
                                borderColor: '#722ed1',
                                color: '#fff',
                            }}
                        >
                            Proxy Embed
                        </Button>
                        <Button
                            onClick={async () => {
                                setTestOutput('Running health check on all cloud providers...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testLambdaProxyHealthCheck(),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('HEALTH_TIMEOUT (120s)')), 120000))
                                    ]);
                                    setTestOutput('Provider Health Check:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('Health Check error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#389e0d',
                                borderColor: '#389e0d',
                                color: '#fff',
                            }}
                        >
                            Health Check
                        </Button>
                        <Button
                            onClick={async () => {
                                setTestOutput('Testing req_create_scene (paper tiger image)...');
                                try {
                                    const resp: any = await Promise.race([
                                        get_ipc_api().testReqCreateScene(),
                                        new Promise((_, reject) => setTimeout(() => reject(new Error('TIMEOUT (120s)')), 120000))
                                    ]);
                                    setTestOutput('req_create_scene Test:\n' + JSON.stringify(resp, null, 2));
                                } catch (e) {
                                    setTestOutput('req_create_scene error: ' + (e instanceof Error ? e.message : String(e)));
                                }
                            }}
                            style={{
                                marginLeft: 8,
                                background: '#d4380d',
                                borderColor: '#d4380d',
                                color: '#fff',
                            }}
                        >
                            Create Scene
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

                    {/* Channel Test Row */}
                    <Space align="center" style={{ width: '100%', marginBottom: '8px', flexWrap: 'wrap' }}>
                        <Button
                            type="default"
                            loading={channelSending}
                            disabled={!selectedChannel || channelSending || !channelRecipient.trim() || !testArgument.trim()}
                            onClick={handleTestChannel}
                            style={{ color: 'white', borderColor: 'white', background: 'transparent' }}
                        >
                            Test Channel
                        </Button>
                        <Select
                            style={{ width: 200 }}
                            placeholder="Select channel…"
                            value={selectedChannel || undefined}
                            onChange={(v) => { setSelectedChannel(v as string); setChanMessages([]); sinceTs.current = Date.now() / 1000; }}
                            allowClear
                            onClear={() => setSelectedChannel('')}
                        >
                            {channelList.map(ch => (
                                <Select.Option key={ch.id} value={ch.id} disabled={!ch.enabled}>
                                    <span style={{ color: ch.enabled ? undefined : '#888' }}>
                                        {ch.label}{!ch.enabled ? ' (disabled)' : ''}
                                    </span>
                                </Select.Option>
                            ))}
                        </Select>
                        <Input
                            style={{ width: 220 }}
                            placeholder="Recipient (phone / JID / chat ID)"
                            value={channelRecipient}
                            onChange={e => setChannelRecipient(e.target.value)}
                            disabled={!selectedChannel}
                        />
                        <Button
                            size="small"
                            type="text"
                            onClick={loadChannels}
                            style={{ color: '#aaa' }}
                        >
                            <ReloadOutlined />
                        </Button>
                    </Space>

                    {/* Channel message thread */}
                    {chanMessages.length > 0 && (
                        <div style={{ marginBottom: 16 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <Text style={{ color: '#aaa', fontSize: 12 }}>Channel messages</Text>
                                <Button size="small" type="text" style={{ color: '#aaa', fontSize: 11 }} onClick={() => setChanMessages([])}>Clear</Button>
                            </div>
                            <div
                                ref={msgBoxRef}
                                style={{ maxHeight: 160, overflowY: 'auto', background: '#111', borderRadius: 6, padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}
                            >
                                {chanMessages.map(msg => (
                                    <div key={msg.message_id} style={{ alignSelf: msg.direction === 'out' ? 'flex-end' : 'flex-start', maxWidth: '85%', background: msg.direction === 'out' ? '#1a3a5c' : '#2a2a2a', borderRadius: 6, padding: '3px 8px' }}>
                                        <div style={{ fontSize: 10, color: '#888', marginBottom: 2 }}>
                                            {msg.direction === 'out' ? 'You' : (msg.sender_name || msg.chat_id)} · {new Date(msg.timestamp * 1000).toLocaleTimeString()}
                                        </div>
                                        <div style={{ color: '#fff', fontSize: 13 }}>{msg.text}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

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
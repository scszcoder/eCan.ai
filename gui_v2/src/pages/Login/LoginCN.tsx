/**
 * CN 版本登录页面
 * 使用腾讯云 CloudBase 认证
 * 主流居中卡片式布局
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Select, App, Spin, Checkbox, Typography } from 'antd';
import { UserOutlined, LockOutlined, MobileOutlined, WechatOutlined, MailOutlined, SafetyCertificateOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { APIResponse } from '../../services/ipc/api';
import { get_ipc_api } from '../../services/ipc_api';
import { userStorageManager, type LoginSession } from '../../services/storage/UserStorageManager';
import { pageRefreshManager } from '../../services/events/PageRefreshManager';
import { eventBus } from '../../utils/eventBus';
import { tokenRefreshService } from '../../services/auth/tokenRefreshService';
import { webAuthSession } from '../../services/auth/webAuthSession';
import { cloudbaseAuth, getWechatOAuthRedirectUri } from '../../services/auth/cloudbaseAuth';
import { localWebSocketClient } from '../../services/web/localWebSocketClient';
import { isDesktopPlatform } from '../../config/platform';
import { useAppConfig } from '../../contexts/AppConfigContext';
import LoadingProgress from '../../components/LoadingProgress/LoadingProgress';
import logo from '../../assets/logoWhite22.png';
import './Login.css';

const { Text } = Typography;

interface LoginFormValues {
  username: string;
  password: string;
  confirmPassword?: string;
  role: string;
  phone?: string;
  code?: string;
  newPassword?: string;
}

type AuthMode = 'email-login' | 'email-signup' | 'email-signup-verify' | 'phone-login' | 'phone-signup' | 'forgot';

/** Convert CloudBase's "+86 13800138000" form back to the 11-digit value
 * accepted by the CN phone input. */
export const normalizeSavedCnPhone = (identifier?: string): string => {
  const digits = (identifier || '').replace(/\D/g, '');
  return digits.length === 13 && digits.startsWith('86') ? digits.slice(2) : digits;
};

const WECHAT_DIAGNOSTIC_KEY = 'wechat_auth_diagnostic';

function summarizeWechatError(error: unknown): Record<string, string> {
  const source = error as { name?: unknown; code?: unknown; error?: unknown; message?: unknown };
  const redact = (value: unknown): string => String(value || '')
    .replace(/\b(code|token|openid|access_token|refresh_token|provider_token)\s*[:=]\s*[^,\s]+/gi, '$1=[redacted]')
    .replace(/\beyJ[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+){1,2}\b/g, '[redacted-jwt]')
    .slice(0, 240);

  return {
    name: redact(source?.name),
    code: redact(source?.code || source?.error),
    message: redact(source?.message),
  };
}

function recordWechatDiagnostic(
  traceId: string,
  stage: string,
  details: Record<string, unknown> = {},
): void {
  const record = {
    traceId,
    stage,
    updatedAt: new Date().toISOString(),
    ...details,
  };
  try {
    sessionStorage.setItem(WECHAT_DIAGNOSTIC_KEY, JSON.stringify(record));
  } catch {
    // Diagnostics must never interfere with authentication.
  }
  console.info('[WeChat OAuth]', record);
}

const LoginCN: React.FC = () => {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { config: appConfig } = useAppConfig();
  const [form] = Form.useForm<LoginFormValues>();

  // 订阅 phone 字段变化: form.getFieldValue('phone') 是 getter,不触发组件 re-render。
  // 这里用 useWatch 让 disabled prop 在用户输入时能响应式更新 (修复 Bug:
  // "手机登陆点击不了获取验证吗按钮")。同理 code 字段也订阅,让 onClick handler
  // 在用户输入验证码时拿到最新值,避免闭包过期问题。
  const phoneValue = Form.useWatch('phone', form);
  const codeValue = Form.useWatch('code', form);

  // State
  const [activeTab, setActiveTab] = useState<'email' | 'phone' | 'wechat'>('email');
  const [mode, setMode] = useState<AuthMode>('email-login');
  const [loading, setLoading] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [loginSuccessful, setLoginSuccessful] = useState(false);
  const [hasNavigated, setHasNavigated] = useState(false);
  const [loginProgress, setLoginProgress] = useState<'idle' | 'authenticating' | 'success' | 'redirecting'>('idle');
  const [lastError, setLastError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const [verificationId, setVerificationId] = useState<string | null>(null);
  const [wechatAvailable, setWechatAvailable] = useState(false);

  // Regression: "登录后再次进入登录页看不到微信 tab / 邮箱/电话流程不可用".
  //
  // LogoutManager.clearLocalStorage() now also calls
  // ``cloudbaseAuth.clearAuthState()`` (see LogoutManager.ts) so this state is
  // normally already clean by the time LoginCN mounts.  We additionally
  // defensively clear here so:
  //   * any path that resets state without going through LogoutManager
  //     (e.g. token expired mid-session that landed on /login) still wipes
  //     the stale CloudBase token before the next login attempt;
  //   * the in-memory `cloudbaseAuth.token === null` invariant holds
  //     during the first render so the WeChat availability check below
  //     doesn't race with a restore from localStorage.
  useEffect(() => {
    try {
      cloudbaseAuth.clearAuthState();
    } catch (e) {
      console.warn('[LoginCN] Failed to clear CloudBase auth state on mount:', e);
    }

    // Re-arm the dev-mode LocalWebSocket reconnect loop.  LogoutManager
    // called ``localWebSocketClient.disconnect()`` (which sets
    // ``userInitiatedDisconnect = true``) so the auto-reconnect loop is
    // stopped while we're on the login screen.  Re-enable it now so the
    // link comes back automatically once the user logs in (and the
    // backend `python3 main.py` is reachable again).
    try {
      localWebSocketClient.enableAutoReconnect();
      // Kick off a connect attempt now; if the backend is back, we'll
      // get a healthy WebSocket before the user finishes typing their
      // email.  If it's still down, the backoff loop takes over quietly.
      if (localWebSocketClient.shouldUseLocalWebSocket()) {
        localWebSocketClient.connect().catch(() => {
          /* errors are logged inside connect() — swallow here */
        });
      }
    } catch (e) {
      console.warn('[LoginCN] Failed to re-arm LocalWebSocketClient:', e);
    }
  }, []);
  const [pendingSignupCode, setPendingSignupCode] = useState<{ email: string; password: string; verificationId: string } | null>(null);
  // 记住密码状态，默认开启
  const [rememberMe, setRememberMe] = useState(true);

  const lastLoginAttemptRef = useRef<number>(0);
  const LOGIN_DEBOUNCE_MS = 3000;

  // 初始化

  // 清空表单的初始状态 — 防止 Antd Form 在 mount 时从 localStorage /
  // 上次会话残留恢复任何字段值。这是修复"邮箱输入框里有 wechat /
  // 电话号码"的最后一道防线:即使后端 last_login 返回了非 password
  // 模式的 username/password(理论上后端已 gating),前端也会主动清空。
  //
  // 只清空跨登录方式的标识字段(username/password/phone/code/newPassword/
  // confirmPassword),不碰 role,避免 100ms IPC 延迟期间角色下拉框变空。
  useEffect(() => {
    form.resetFields(['username', 'password', 'confirmPassword', 'phone', 'code', 'newPassword']);
  }, [form]);

  // 浏览器自动填充防御:延迟清空 username 字段
  // 浏览器自动填充发生在页面渲染完成后,约 500ms-1s。
  // 这里在 1.5s 后强制清空 username 字段,确保任何浏览器的自动填充
  // 值都会被清除。
  useEffect(() => {
    const timer = setTimeout(() => {
      // 只有当 activeTab 是 email 且 login_type 不是 password 时才清空
      // 这样可以避免清除正常的 rememberMe 回填值
      const loginTypeFromStorage = sessionStorage.getItem('last_login_type');
      if (
        activeTab === 'email' &&
        loginTypeFromStorage &&
        loginTypeFromStorage !== 'password' &&
        !form.isFieldTouched('username')
      ) {
        form.setFieldValue('username', '');
        console.log('[LoginCN] Browser autofill cleared: username field reset for non-password login');
      }
    }, 1500);
    return () => clearTimeout(timer);
  }, [activeTab, form]);

  // 初始化 CloudBase
  useEffect(() => {
    const envId = appConfig?.auth?.cloudbase_env_id || '';
    if (envId) {
      cloudbaseAuth.initialize({ envId });
    }
  }, [appConfig?.auth?.cloudbase_env_id]);

  // 检查微信登录是否可用
  //
  // Optimistic flow (regression: 2026-08-24 "退出后再进来,微信的 tab 不见了"):
  //   1. If `appConfig.auth.wechat_app_id` is set, show the WeChat tab
  //      immediately.  This handles the post-logout window where the LOCAL
  //      GraphQL server is still restarting (terminals/7.txt:895-985 shows
  //      `cloudbase_check_config` HTTP-failing for ~6s after logout while
  //      uvicorn's graceful shutdown runs).
  //   2. Kick off `cloudbaseAuth.checkConfig()` to learn the canonical
  //      `wechat_configured` state.  Only OVERWRITE the optimistic default
  //      when the IPC actually succeeded (`result.success === true` and a
  //      real `wechatAvailable` boolean comes back).  If the IPC failed,
  //      we treat the answer as "unknown" and keep the optimistic value
  //      — a flickering WeChat tab is a worse UX than a slightly stale one.
  useEffect(() => {
    const initialAvailable = Boolean(appConfig?.auth?.wechat_app_id);
    if (initialAvailable) {
      setWechatAvailable(true);
    }
    const checkWechat = async () => {
      let result;
      try {
        result = await cloudbaseAuth.checkConfig();
      } catch (e) {
        // Synchronous throw — e.g. import failure.  Treat as unknown.
        console.warn('[LoginCN] checkConfig() threw, keeping optimistic default:', e);
        return;
      }

      // result.success === false ⇒ backend IPC failed (server is restarting,
      // or method not registered on this build).  Preserve the optimistic
      // state so the tab doesn't flash away.
      if (result?.success === false) {
        console.warn(
          '[LoginCN] checkConfig() IPC unreachable (reason=%s); keeping optimistic wechat tab',
          result.reason || 'unknown',
        );
        return;
      }

      // result.wechatAvailable === null  ⇒ backend reachable but reported
      // "unknown" (legacy handler, partial response).  Same policy.
      if (result?.wechatAvailable === null || result?.wechatAvailable === undefined) {
        return;
      }

      // Definite answer from the backend — trust it over the appConfig hint.
      setWechatAvailable(Boolean(result.wechatAvailable));
    };
    checkWechat();
  }, [appConfig?.auth?.wechat_app_id]);

  // 监听 URL 参数（微信回调）
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, '').split('?')[1] || '');
    const customTicket = urlParams.get('ticket') || hashParams.get('ticket');
    const ticketOpenid = urlParams.get('openid') || hashParams.get('openid');
    const code = urlParams.get('code') || hashParams.get('code');
    const state = urlParams.get('state') || hashParams.get('state');
    const savedState = sessionStorage.getItem('wx_state');

    if (customTicket && ticketOpenid) {
      window.history.replaceState({}, '', `${window.location.pathname}#/login`);

      (async () => {
        try {
          setLoginProgress('authenticating');
          const cloudbase = (await import('@cloudbase/js-sdk')).default;
          const app = cloudbase.init({
            env: appConfig?.auth?.cloudbase_env_id || '',
            region: 'ap-shanghai',
          });
          const auth = app.auth();
          const ticketLogin = await auth.signInWithCustomTicket(
            () => Promise.resolve(customTicket),
          );
          if (ticketLogin?.error) {
            throw new Error(ticketLogin.error.message || 'CloudBase ticket sign-in failed');
          }

          const accessTokenResult = await auth.getAccessToken();
          const accessToken = typeof accessTokenResult === 'string'
            ? accessTokenResult
            : accessTokenResult?.accessToken || '';
          if (!accessToken) {
            throw new Error('CloudBase did not return an access token');
          }

          const webSession = await cloudbaseAuth.registerWechatSession(accessToken);
          if (!webSession.success || !webSession.sessionToken) {
            throw new Error(webSession.error || 'Failed to create WeChat session');
          }

          const userIdentifier = `wechat_${ticketOpenid}`;
          const userInfo = {
            username: userIdentifier,
            email: '',
            name: '',
            given_name: '',
            family_name: '',
            picture: '',
            email_verified: false,
            login_type: 'wechat' as const,
          };
          webAuthSession.setSession({
            accessToken: webSession.sessionToken,
            tokenType: 'Bearer',
            expiresAt: webSession.expiresIn
              ? Date.now() + webSession.expiresIn * 1000
              : undefined,
            userInfo: { ...userInfo, sub: ticketOpenid },
          });
          saveLoginSession(webSession.sessionToken, userInfo, 'Commander', 'wechat');
          setLoginProgress('success');
          setLoginSuccessful(true);
          setLoginProgress('redirecting');
        } catch (err: any) {
          console.error('[WeChat Ticket Callback] Error:', err);
          setLoginProgress('idle');
          messageApi.error(err?.message || t('login.wechat_login_failed'));
        }
      })();
      return;
    }

    if (code && state && savedState && state === savedState) {
      const traceId = sessionStorage.getItem('wechat_auth_trace_id') || 'unknown';
      const providerRedirectUri = getWechatOAuthRedirectUri();
      recordWechatDiagnostic(traceId, 'callback-received', {
        callbackLocation: urlParams.has('code') ? 'query' : 'hash',
      });
      window.history.replaceState({}, '', window.location.pathname);
      sessionStorage.removeItem('wx_state');

      (async () => {
        try {
          setLoginProgress('authenticating');
          recordWechatDiagnostic(traceId, 'initializing-cloudbase');

          const cloudbase = (await import('@cloudbase/js-sdk')).default;
          const app = cloudbase.init({
            env: appConfig?.auth?.cloudbase_env_id || '',
            region: 'ap-shanghai',
            auth: { detectSessionInUrl: true },
          });
          const auth = app.auth();

          recordWechatDiagnostic(traceId, 'granting-provider-token');
          const { provider_token } = await auth.grantProviderToken({
            provider_id: 'wx_open',
            provider_redirect_uri: providerRedirectUri,
            provider_code: code,
          });

          let loginResult;
          try {
            recordWechatDiagnostic(traceId, 'signing-in-with-provider');
            loginResult = await auth.signInWithProvider({ provider_token });
          } catch (e: any) {
            if (e?.error === 'not_found') {
              recordWechatDiagnostic(traceId, 'creating-provider-account');
              loginResult = await auth.signUp({ provider_token });
            }
            else {
              throw e;
            }
          }

          const accessTokenResult = await auth.getAccessToken();
          const accessToken =
            typeof accessTokenResult === 'string'
              ? accessTokenResult
              : accessTokenResult?.accessToken || '';
          if (!accessToken) {
            throw new Error('CloudBase did not return an access token');
          }
          const cbUserInfo: any = loginResult?.user || {};
          // WeChat identity contract: always use openid as the stable identifier
          // (same WeChat account → same openid forever). uuid/email come from
          // CloudBase's internal user record and may differ across re-link flows.
          //
          // Strategy:
          //   1. Prefer the SDK-returned openId (or openid) — this is the
          //      canonical WeChat identity and matches the server-side JWT.
          //   2. If the SDK didn't return openid, decode the access_token JWT
          //      ourselves (same logic as the server-side decodeOpenidFromJwt
          //      in cloudbase-graphql/resolvers/auth.js). This guarantees
          //      parity with what the server stores in weChatSession.openid.
          //   3. Fall back to uuid/email/sub only as a last resort.
          let openid =
            cbUserInfo.wxOpenId || cbUserInfo.wx_openid || cbUserInfo.openId || cbUserInfo.openid || '';
          if (!openid && accessToken && accessToken.split('.').length >= 2) {
            try {
              const payloadB64 = accessToken.split('.')[1];
              const padded = payloadB64 + '='.repeat((4 - payloadB64.length % 4) % 4);
              const payload = JSON.parse(
                atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
              );
              openid =
                payload.openid ||
                payload.openId ||
                payload.uid ||
                payload.sub ||
                '';
            } catch {
              /* JWT decode failed — leave openid empty */
            }
          }
          const userIdentifier =
            (openid && `wechat_${openid}`) ||
            cbUserInfo.uuid ||
            cbUserInfo.email ||
            cbUserInfo.sub ||
            `wechat_unknown_${Date.now()}`;

          const userInfo = {
            username: userIdentifier,
            email: cbUserInfo.email || '',
            name: cbUserInfo.nickName || cbUserInfo.nickname || cbUserInfo.displayName || '',
            given_name: '',
            family_name: '',
            picture: cbUserInfo.avatarUrl || '',
            email_verified: !!cbUserInfo.email,
            login_type: 'wechat' as const,
            uuid: cbUserInfo.uuid || '',
          };

          let sessionToken: string;
          let backendUserInfo: typeof userInfo;
          if (isDesktopPlatform()) {
            recordWechatDiagnostic(traceId, 'finalizing-ecan-session');
            const finalizeResult = await cloudbaseAuth.finalizeSession({
              access_token: accessToken,
              refresh_token: accessToken,
              expires_in: 7200,
              user_identifier: userIdentifier,
              user_info: userInfo,
              role: 'Commander',
              lang: i18n.language,
            });

            if (!finalizeResult.success) {
              recordWechatDiagnostic(traceId, 'ecan-session-finalization-failed', {
                error: summarizeWechatError({ message: finalizeResult.error }),
              });
              throw new Error(finalizeResult.error || 'Finalize session failed');
            }

            sessionToken = finalizeResult.ipc_token || accessToken;
            backendUserInfo = finalizeResult.data?.userInfo || userInfo;
          } else {
            recordWechatDiagnostic(traceId, 'registering-web-session');
            const webSession = await cloudbaseAuth.registerWechatSession(accessToken);
            if (!webSession.success || !webSession.sessionToken) {
              recordWechatDiagnostic(traceId, 'web-session-registration-failed', {
                error: summarizeWechatError({ message: webSession.error }),
              });
              throw new Error(webSession.error || 'Failed to create WeChat session');
            }

            sessionToken = webSession.sessionToken;
            backendUserInfo = userInfo;
            webAuthSession.setSession({
              accessToken: sessionToken,
              tokenType: 'Bearer',
              expiresAt: webSession.expiresIn
                ? Date.now() + webSession.expiresIn * 1000
                : undefined,
              userInfo: {
                username: userIdentifier,
                email: userInfo.email,
                name: userInfo.name,
                given_name: userInfo.given_name,
                family_name: userInfo.family_name,
                picture: userInfo.picture,
                email_verified: userInfo.email_verified,
                sub: cbUserInfo.sub || openid || undefined,
              },
            });
          }

          saveLoginSession(
            sessionToken,
            {
              username: userIdentifier,
              email: backendUserInfo.email || '',
              name: backendUserInfo.name || '',
              given_name: backendUserInfo.given_name || '',
              family_name: backendUserInfo.family_name || '',
              picture: backendUserInfo.picture || '',
              email_verified: backendUserInfo.email_verified ?? !!cbUserInfo.email,
              login_type: 'wechat',
            },
            'Commander',
            'wechat',
          );

          setLoginProgress('success');
          recordWechatDiagnostic(traceId, 'completed');
          messageApi.success(t('login.wechat_login_success') || '微信登录成功');
          setLoginSuccessful(true);
          setLoginProgress('redirecting');
        } catch (err: any) {
          console.error('[WeChat Callback] Error:', err);
          recordWechatDiagnostic(traceId, 'failed', {
            error: summarizeWechatError(err),
          });
          setLoginProgress('idle');
          messageApi.error(err?.message || t('login.wechat_login_failed'));
        }
      })();
    }
  }, [navigate, messageApi, t, appConfig?.auth?.cloudbase_env_id]);

  // 导航逻辑 - 登录成功后直接跳转，不需要等待 initProgress
  useEffect(() => {
    if (!loginSuccessful) return;
    if (hasNavigated) return;

    setHasNavigated(true);
    setLoading(false);
    navigate('/agents');
  }, [loginSuccessful, hasNavigated, navigate]);

  // 加载上次登录信息
  //
  // Cross-tab field-bleed fix (邮件 / 手机号 / 微信 三种登录方式间切换时,
  // 旧登录方式的字段残留到新登录方式的输入框):
  //
  // 之前这段代码只会在用户主动点击 tab 时跑 ``handleTabChange`` —— 而
  // ``handleTabChange`` 已经会 reset 跨 tab 字段。但是这里直接走
  // ``setActiveTab('wechat' / 'phone' / 'email')``,绕过了
  // ``handleTabChange`` 的清理逻辑,导致 form store 中其他 tab 的字段
  // 值依然保留(例如: 用户先在 email tab 输入过 username,再切到 phone
  // tab 用手机号登录成功,退出后再进来,email tab 的 username 字段仍
  // 残留旧值)。
  //
  // 同时,后端 ``get_saved_login_info`` 已经根据 ``login_type`` 过滤掉
  // 非 password 模式的 username/password — 这里直接根据 ``login_type``
  // 分发,既不会再误填,也能让 phone/wechat 模式显式清掉 email tab 的
  // 字段。
  useEffect(() => {
    const initialize = async (attempt = 0) => {
      try {
        const api = get_ipc_api();
        if (!api) return;

        const timeoutPromise = new Promise((_, reject) => {
          setTimeout(() => reject(new Error('IPC initialization timeout')), 15000);
        });

        const response = await Promise.race([
          api.getLastLoginInfo(),
          timeoutPromise
        ]) as APIResponse<any>;

        const loginData = (response?.data as any)?.last_login;
        // Post-logout race: MainLayout navigates here BEFORE the logout
        // cleanup finishes, so this first fetch can land mid-cleanup and
        // come back empty even though credentials are saved. Retry once
        // after the dust settles instead of leaving the form blank
        // (2026-09-02 customer report).
        if (attempt === 0 && (!loginData || (!loginData.username && !loginData.login_type))) {
          setTimeout(() => { void initialize(1); }, 1800);
          if (!loginData) return;
        }
        if (loginData) {
          const { username, password, machine_role, language, login_type, last_identifier } = loginData;

          if (language && i18n.language !== language) {
            await i18n.changeLanguage(language);
            localStorage.setItem('i18nextLng', language);
          }

          // 保存 login_type 到 sessionStorage,供延迟清空逻辑判断
          sessionStorage.setItem('last_login_type', login_type || 'password');

          // 根据 login_type 决定激活哪个 tab + 哪些字段需要被清空。
          //
          // 字段清理原则 (修复 "邮箱输入框里有 wechat / 电话号码"):
          //   * 微信登录 (login_type='wechat')  → 清空 email tab 的
          //     username/password (因为后端会保留 wechat_xxx 这种标识符
          //     到 last_identifier,但前端不应该让它出现在 email 字段)。
          //   * 手机登录 (login_type='phone')   → 清空 email tab 的
          //     username/password。
          //   * 密码登录 (login_type='password' 或未设置) → 把 username
          //     和 password 填进 email tab,正常使用 rememberMe。
          //
          // 注意:不能在此统一调用 ``form.resetFields()`` 清空全部字段,
          // 因为用户切换 tab 时 ``handleTabChange`` 会做精细清理,而这里
          // 我们只需要确保"非 password 模式不会污染 email 字段"。
          if (login_type === 'wechat') {
            // 微信登录:切到微信 tab,清掉 email / phone 字段防止误填。
            setActiveTab('wechat');
            setMode('email-login'); // mode 维持默认,微信 tab 不依赖 mode
            form.resetFields(['username', 'password', 'confirmPassword', 'phone', 'code', 'newPassword']);
            form.setFieldsValue({
              role: machine_role || 'Commander'
            });
          } else if (login_type === 'phone') {
            // 手机登录:后端为了避免污染邮箱输入框，会将 username 清空，
            // 手机号保存在 last_identifier。CloudBase profile 可能返回
            // "+86 13800138000"，回填前规范化为 11 位国内号码。
            // 邮箱字段使用独立的 form key，不会显示在手机号 tab。
            setActiveTab('phone');
            setMode('phone-login');
            form.resetFields(['username', 'password', 'confirmPassword', 'code', 'newPassword']);
            form.setFieldsValue({
              phone: normalizeSavedCnPhone(last_identifier),
              role: machine_role || 'Commander'
            });
          } else {
            // 邮箱/密码登录（默认）
            setActiveTab('email');
            setMode('email-login');
            // 清掉其他 tab 的字段(phone/code),但保留 username/password
            // 让 rememberMe 起作用。
            form.resetFields(['phone', 'code', 'newPassword', 'confirmPassword']);
            form.setFieldsValue({
              username,
              password,
              role: machine_role || 'Commander'
            });
          }

          // 如果从 keyring 加载到密码，设置 rememberMe 为 true
          if (password) {
            setRememberMe(true);
          }
        } else {
          // 没有 last_login 数据时,设置默认的 login_type
          // (避免延迟清空逻辑误判)
          sessionStorage.setItem('last_login_type', 'password');
        }
      } catch (error) {
        console.warn('[LoginCN] Failed to load last login info:', error);
      }
    };

    const timer = setTimeout(initialize, 100);
    return () => clearTimeout(timer);
  }, [form, i18n.language]);

  // 用户主动取消勾选"记住密码"时清除 keyring 中的密码。
  // 必须是 checkbox 的显式操作 — 之前监听 rememberMe state 变化会在
  // handleModeChange 程序化地把 rememberMe 置 false（切到注册/手机页）时
  // 也触发清除，用户只是看了一眼注册页，保存的密码就被抹掉了
  // (2026-09-02 客户反馈：记住密码后登录框仍为空的元凶之一)。
  const handleRememberMeChange = (checked: boolean) => {
    setRememberMe(checked);
    if (!checked) {
      const identifier = (mode === 'phone-login' || mode === 'phone-signup')
        ? (form.getFieldValue('phone') || '')
        : (form.getFieldValue('username') || '');
      if (identifier) {
        const api = get_ipc_api();
        if (api) {
          api.clearLoginInfo(identifier).catch((err) => {
            console.warn('[LoginCN] Failed to clear login info:', err);
          });
        }
      }
    }
  };

  // 验证码倒计时
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  // 处理语言切换
  const handleLanguageChange = useCallback(async (value: string) => {
    if (i18n.language !== value) {
      await i18n.changeLanguage(value);
      localStorage.setItem('i18nextLng', value);

      try {
        const api = get_ipc_api();
        if (api) {
          await api.updateUserPreferences(value);
        }
      } catch (error) {
        console.error('[LoginCN] Error saving language preference:', error);
      }
    }
  }, [i18n]);

  // Tab 切换
  const handleTabChange = useCallback((tab: 'email' | 'phone' | 'wechat') => {
    const prevTab = activeTab;
    setActiveTab(tab);
    if (tab === 'email') {
      setMode('email-login');
    } else if (tab === 'phone') {
      setMode('phone-login');
    }
    // 微信 tab 不改变 mode，点击后直接触发登录

    // 保存 role
    const savedRole = form.getFieldValue('role');

    // username/password 与 phone 是不同的 Form 字段，不会跨 tab 显示，
    // 因此切换时保留它们，让用户返回原 tab 后仍能继续登录。只清理
    // 验证码、确认密码等与当前流程绑定的一次性字段。
    const fieldsToReset: (keyof LoginFormValues)[] = [];
    if (tab === 'email') {
      fieldsToReset.push('code', 'newPassword', 'confirmPassword');
      // 浏览器自动填充防御:如果上次登录不是 password 类型,清空 username
      // (防止 wechat/phone 的凭证被浏览器填充到 email 输入框)
      const loginTypeFromStorage = sessionStorage.getItem('last_login_type');
      // 仅清除浏览器悄悄填入的值；用户已在本次页面会话中输入的邮箱
      // 必须保留。dirty/touched 表明该字段经过了用户操作。
      if (
        loginTypeFromStorage &&
        loginTypeFromStorage !== 'password' &&
        !form.isFieldTouched('username')
      ) {
        fieldsToReset.push('username');
      }
    } else if (tab === 'phone') {
      fieldsToReset.push('confirmPassword', 'newPassword');
    } else if (tab === 'wechat') {
      fieldsToReset.push('confirmPassword', 'code', 'newPassword');
    }
    if (fieldsToReset.length > 0) {
      form.resetFields(fieldsToReset);
    }

    if (savedRole) {
      form.setFieldValue('role', savedRole);
    }

    // 切 tab 时清掉验证码/session 状态(同 handleModeChange)
    setCodeSent(false);
    setVerificationId(null);
    setPendingSignupCode(null);
    setCountdown(0);
    setLastError(null);
  }, [form, activeTab]);

  const ensureCloudbase = useCallback((): boolean => {
    if (!appConfig?.auth?.cloudbase_env_id) {
      messageApi.error(t('login.cloudbaseNotConfigured'));
      return false;
    }
    return true;
  }, [appConfig?.auth?.cloudbase_env_id, messageApi, t]);

  // 保存登录会话
  const saveLoginSession = useCallback((
    token: string,
    userInfo: any,
    role: string,
    loginType: 'password' | 'google' | 'wechat' | 'phone' = 'password'
  ) => {
    const loginSession: LoginSession = {
      token,
      userInfo: {
        username: userInfo.username || userInfo.email || userInfo.phone || userInfo.phoneNumber || '',
        email: userInfo.email || '',
        role,
        name: userInfo.name || '',
        given_name: userInfo.given_name || '',
        family_name: userInfo.family_name || '',
        picture: userInfo.picture || '',
        email_verified: userInfo.email_verified ?? true,
        login_type: loginType
      },
      loginTime: Date.now()
    };

    userStorageManager.saveLoginSession(loginSession);
    // Backend initialization events can arrive a few milliseconds before the
    // login response is stored. Emit once more after username is available so
    // org/agent loading starts immediately instead of waiting for a later push.
    eventBus.emit('org-agents-update', { source: 'login-session-saved' });
    pageRefreshManager.enable();
    sessionStorage.removeItem('token_expired_notification_shown');

    tokenRefreshService.start(token, {
      checkInterval: 30 * 60 * 1000,
      refreshThreshold: 60 * 60,
      onTokenRefreshed: (newToken: string) => {
        userStorageManager.setToken(newToken);
      },
      onTokenExpired: () => {
        messageApi.warning(t('login.sessionExpired'));
        userStorageManager.logout();
        navigate('/login');
      }
    });
  }, [messageApi, navigate, t]);

  // 发送手机验证码
  const handleSendCode = useCallback(async (phone: string) => {
    if (countdown > 0) return;
    if (!ensureCloudbase()) return;

    try {
      const result = await cloudbaseAuth.sendPhoneCode(phone, 'login');
      if (result.success) {
        // CloudBase 在不同版本下可能不返回 verification_id (rate-limit 边界、字段命名
        // 差异 verification_id vs verificationId 等)。必须 fail-safe：缺失时立刻报错，
        // 而不是 setCodeSent(true) 让用户看到"验证码已发送"但后续 login 必然 401。
        if (!result.verificationId) {
          messageApi.error(
            t('login.codeSendFailed') || '验证码发送失败，请稍后重试'
          );
          setCodeSent(false);
          setVerificationId(null);
          return;
        }
        setCodeSent(true);
        setCountdown(60);
        setVerificationId(result.verificationId);
        messageApi.success(t('login.codeSent'));
        if (result.devCode) {
          messageApi.info(`[Dev] Code: ${result.devCode}`, 5);
        }
      } else {
        messageApi.error(result.error || t('login.codeSendFailed'));
        setVerificationId(null);
      }
    } catch (error) {
      messageApi.error(String(error));
      setVerificationId(null);
    }
  }, [countdown, ensureCloudbase, messageApi, t]);

  // 手机号登录
  const handlePhoneLogin = useCallback(async (phone: string, code: string) => {
    if (!ensureCloudbase()) {
      setLoginProgress('idle');
      return false;
    }
    setLoginProgress('authenticating');

    // 防御性检查: 必须在发送验证码后才有 verificationId
    if (!verificationId) {
      messageApi.error(
        t('login.codeSendFailed') || '请先发送验证码'
      );
      setLoginProgress('idle');
      setLastError(t('login.codeSendFailed') || '请先发送验证码');
      return false;
    }

    try {
      const result = await cloudbaseAuth.loginWithPhone(phone, code, verificationId);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setLoginProgress('success');
        saveLoginSession(token, userInfo, 'Commander', 'phone');
        messageApi.success(t('login.success'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        setVerificationId(null);
        return true;
      }

      messageApi.error(result.error || t('login.failed'));
      setLastError(result.error || t('login.failed'));
      setLoginProgress('idle');
      return false;
    } catch (error) {
      messageApi.error(String(error));
      setLastError(String(error));
      setLoginProgress('idle');
      return false;
    }
  }, [saveLoginSession, messageApi, t, verificationId]);

  // 邮箱登录
  const handleEmailLogin = useCallback(async (email: string, password: string, role: string) => {
    if (!ensureCloudbase()) {
      setLoginProgress('idle');
      return false;
    }

    // 防止空密码触发 CloudBase 远程调用（keyring 中无密码时会被回填为空字符串）
    if (!password || !password.trim()) {
      const msg = t('login.passwordRequired') || '请输入密码';
      messageApi.warning(msg);
      setLastError(msg);
      setLoginProgress('idle');
      return false;
    }

    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.loginWithEmail(email, password);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setLoginProgress('success');
        saveLoginSession(token, userInfo, role, 'password');
        
        // 根据"记住密码"状态决定是否保存凭证到 keyring
        if (rememberMe) {
          const api = get_ipc_api();
          if (api) {
            const username = userInfo.username || userInfo.email || email;
            api.saveLoginInfo(username, password, role, i18n.language, 'password')
              .then(() => console.log('[LoginCN] Credentials saved to keyring'))
              .catch((err) => console.warn('[LoginCN] Failed to save credentials:', err));
          }
        }
        
        messageApi.success(t('login.success'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        return true;
      }

      messageApi.error(result.error || t('login.failed'));
      setLastError(result.error || t('login.failed'));
      setLoginProgress('idle');
      return false;
    } catch (error) {
      messageApi.error(String(error));
      setLastError(String(error));
      setLoginProgress('idle');
      return false;
    }
  }, [ensureCloudbase, saveLoginSession, messageApi, t, rememberMe, i18n.language]);

  // 发送密码重置验证码
  const handleSendForgotCode = useCallback(async (phone: string) => {
    if (countdown > 0) return;
    if (!ensureCloudbase()) return;

    try {
      const result = await cloudbaseAuth.sendPasswordResetCode(phone);
      if (result.success) {
        // 同 handleSendCode：verification_id 缺失必须 fail-safe
        if (!result.verificationId) {
          messageApi.error(
            t('login.codeSendFailed') || '验证码发送失败，请稍后重试'
          );
          setCodeSent(false);
          setVerificationId(null);
          return;
        }
        setCodeSent(true);
        setCountdown(60);
        setVerificationId(result.verificationId);
        messageApi.success(t('login.codeSent'));
        if (result.devCode) {
          messageApi.info(`[Dev] Code: ${result.devCode}`, 5);
        }
      } else {
        messageApi.error(result.error || t('login.codeSendFailed'));
        setVerificationId(null);
      }
    } catch (error) {
      messageApi.error(String(error));
      setVerificationId(null);
    }
  }, [countdown, ensureCloudbase, messageApi, t]);

  // 重置密码
  const handleResetPassword = useCallback(async (phone: string, code: string, newPassword: string) => {
    if (!ensureCloudbase()) {
      setLoginProgress('idle');
      return;
    }
    setLoginProgress('authenticating');

    // 防御性检查: 必须先发送验证码获得 verificationId
    if (!verificationId) {
      messageApi.error(
        t('login.codeSendFailed') || '请先发送验证码'
      );
      setLoginProgress('idle');
      return;
    }

    try {
      const result = await cloudbaseAuth.resetPasswordWithPhone(phone, code, newPassword, verificationId);

      if (result.success) {
        messageApi.success(t('login.forgotSuccess'));
        setMode('email-login');
        setActiveTab('email');
        form.resetFields();
        setCodeSent(false);
        setVerificationId(null);
      } else {
        messageApi.error(result.error || t('login.forgotResetError'));
      }
    } catch (error) {
      messageApi.error(String(error));
    } finally {
      setLoginProgress('idle');
    }
  }, [ensureCloudbase, messageApi, t, form, verificationId]);

  // 手机号注册
  const handlePhoneSignup = useCallback(async (phone: string, code: string) => {
    if (!ensureCloudbase()) {
      setLoginProgress('idle');
      return false;
    }
    setLoginProgress('authenticating');

    // 防御性检查: 必须先发送验证码获得 verificationId
    if (!verificationId) {
      messageApi.error(
        t('login.codeSendFailed') || '请先发送验证码'
      );
      setLoginProgress('idle');
      return false;
    }

    try {
      const result = await cloudbaseAuth.signupWithPhone(phone, code, undefined, verificationId);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setLoginProgress('success');
        saveLoginSession(token, userInfo, 'Commander', 'password');
        messageApi.success(t('login.signupSuccess'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        setVerificationId(null);
        return true;
      }

      messageApi.error(result.error || t('login.signupFailed'));
      setLoginProgress('idle');
      return false;
    } catch (error) {
      messageApi.error(String(error));
      setLoginProgress('idle');
      return false;
    }
  }, [ensureCloudbase, saveLoginSession, messageApi, t, verificationId]);

  // 邮箱注册
  const handleSignup = useCallback(async (email: string, password: string) => {
    if (!ensureCloudbase()) {
      return;
    }

    setLoading(true);
    setLoginProgress('authenticating');
    console.log('[LoginCN] handleSignup: calling signupWithEmail');
    const result = await cloudbaseAuth.signupWithEmail(email, password);
    console.log('[LoginCN] handleSignup: result', result);

    if (result.success) {
      // verificationId 缺失 fail-safe: 不能进入 pendingSignupCode 状态,
      // 否则后续 confirm 时 backend 会 INVALID_PARAMS
      if (!result.verificationId) {
        messageApi.error(
          result.error || t('login.codeSendFailed') || '验证码发送失败，请稍后重试'
        );
        setLoading(false);
        setLoginProgress('idle');
        return;
      }
      // 与国际版一致：注册成功后切换到验证邮箱页面，等用户确认后才登录
      console.log('[LoginCN] handleSignup: setting pendingSignupCode and switching to email-signup-verify');
      setPendingSignupCode({ email, password, verificationId: result.verificationId });
      setMode('email-signup-verify');
      setActiveTab('email');
      messageApi.success(t('login.codeSent') || '验证码已发送');
      setLoading(false);
      setLoginProgress('idle');
    } else {
      messageApi.error(result.error || t('login.failed'));
      setLoading(false);
      setLoginProgress('idle');
    }
  }, [ensureCloudbase, messageApi, t]);

  // 邮箱注册 - 确认验证码完成注册
  const handleSignupVerify = useCallback(async () => {
    console.log('[LoginCN] handleSignupVerify called');
    if (!pendingSignupCode) {
      console.log('[LoginCN] handleSignupVerify: pendingSignupCode is null, returning to email-signup');
      messageApi.error(t('login.registrationSessionExpired'));
      setMode('email-signup');
      setPendingSignupCode(null);
      return;
    }

    const values = form.getFieldsValue(['code']) as { code?: string };
    const code = (values.code || '').trim();
    if (!code) {
      messageApi.error(t('login.codeRequired') || '请输入验证码');
      return;
    }

    // 二次提交时,如果 pendingSignupCode.verificationId 缺失 (state 闭包异常),
    // 不应继续提交,而是提示用户重新发送验证码
    if (!pendingSignupCode.verificationId) {
      console.log('[LoginCN] handleSignupVerify: verificationId is missing');
      messageApi.error(
        t('login.codeSendFailed') || '验证码已过期，请重新发送'
      );
      setPendingSignupCode(null);
      setMode('email-signup');
      return;
    }

    setLoading(true);
    try {
      console.log('[LoginCN] handleSignupVerify: calling confirmSignupWithEmail');
      const result = await cloudbaseAuth.confirmSignupWithEmail(
        pendingSignupCode.email,
        code,
        pendingSignupCode.password,
        pendingSignupCode.verificationId,
      );
      console.log('[LoginCN] handleSignupVerify: result', result);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        saveLoginSession(token, userInfo, 'Commander', 'password');
        messageApi.success(t('login.signupSuccess'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        setPendingSignupCode(null);
        setVerificationId(null);
        setCodeSent(false);
      } else {
        messageApi.error(result.error || t('login.signupFailed'));
      }
    } catch (error) {
      messageApi.error(String(error));
    } finally {
      setLoading(false);
    }
  }, [pendingSignupCode, form, saveLoginSession, messageApi, t]);

  // 微信登录
  const handleWechatLogin = useCallback(async () => {
    if (!ensureCloudbase()) return;

    const traceId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem('wechat_auth_trace_id', traceId);
    recordWechatDiagnostic(traceId, 'redirecting-to-wechat');

    // 桌面 App：内嵌浏览器弹窗扫码，后端 finalize 后返回会话；
    // Web：走 CloudBase/PHP 托管页重定向（保持原行为）。
    if (isDesktopPlatform()) {
      try {
        setLoading(true);
        setLoginProgress('authenticating');
        const resp = await cloudbaseAuth.loginWithWechatQR('Commander', i18n.language);
        if (resp.success && resp.data) {
          const { token } = resp.data;
          const ui: any = resp.data.userInfo || {};
          setLoginProgress('success');
          saveLoginSession(
            token,
            {
              username: ui.username || ui.email || '',
              email: ui.email || '',
              name: ui.nickname || '',
              login_type: 'wechat',
            },
            'Commander',
            'wechat',
          );
          messageApi.success(t('login.wechat_login_success') || '微信登录成功');
          setLoginSuccessful(true);
          setLoginProgress('redirecting');
        } else {
          setLoading(false);
          setLoginProgress('idle');
          messageApi.error(resp.error || 'WeChat login failed');
        }
      } catch (error) {
        setLoading(false);
        setLoginProgress('idle');
        console.error('[WeChat QR] Error:', error);
        messageApi.error(String(error));
      }
      return;
    }

    try {
      const resp = await cloudbaseAuth.loginWithCloudBaseWechat(
        appConfig?.auth?.wechat_app_id,
      );
      console.log('[WeChat H5] Response:', resp);

      if (!resp.success) {
        messageApi.error(t('login.wechatFailedToStart'));
      }
    } catch (error) {
      console.error('[WeChat H5] Error:', error);
      messageApi.error(String(error));
    }
  }, [
    appConfig?.auth?.wechat_app_id,
    ensureCloudbase,
    messageApi,
    t,
    i18n.language,
    saveLoginSession,
  ]);

  // 提交处理
  const handleSubmit = useCallback(async (values: LoginFormValues) => {
    if (loading || loginSuccessful) {
      console.log(`[LoginCN] handleSubmit BLOCKED: loading=${loading}, loginSuccessful=${loginSuccessful}`);
      return;
    }

    const now = Date.now();
    if (now - lastLoginAttemptRef.current < LOGIN_DEBOUNCE_MS) {
      return;
    }
    lastLoginAttemptRef.current = now;

    // Log current mode to help debug "signup triggers login" issue
    console.log(`[LoginCN] handleSubmit START: mode=${mode}, activeTab=${activeTab}, values.keys=${Object.keys(values)}`);

    setLoading(true);
    setLoginSuccessful(false);
    setHasNavigated(false);
    setLastError(null);

    let loginAttempted = false;

    try {
      switch (mode) {
        case 'email-login':
          loginAttempted = true;
          await handleEmailLogin(values.username, values.password, values.role);
          return;
        case 'email-signup':
          if (values.password !== values.confirmPassword) {
            messageApi.error(t('login.passwordMismatch'));
            setLoading(false);
            return;
          }
          await handleSignup(values.username, values.password);
          break;
        case 'email-signup-verify':
          await handleSignupVerify();
          break;
        case 'phone-login':
          await handlePhoneLogin(values.phone!, values.code!);
          break;
        case 'phone-signup':
          await handlePhoneSignup(values.phone!, values.code!);
          break;
        case 'forgot':
          if (values.newPassword !== values.confirmPassword) {
            messageApi.error(t('login.passwordMismatch'));
            setLoading(false);
            return;
          }
          await handleResetPassword(values.phone!, values.code!, values.newPassword!);
          break;
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setLastError(errorMessage);
      messageApi.error(errorMessage);
      setLoginProgress('idle');

      if (mode === 'email-login' && loginAttempted) {
        setLoading(false);
      }
    } finally {
      if (mode !== 'email-login' || !loginAttempted) {
        setLoading(false);
      }
    }
  }, [loading, loginSuccessful, mode, handleEmailLogin, handleSignup, handleSignupVerify, handlePhoneLogin, handlePhoneSignup, handleResetPassword, messageApi, t]);

  // 模式切换
  const handleModeChange = useCallback((newMode: AuthMode) => {
    // 保存 role 字段 (跨模式保留)
    const savedRole = form.getFieldValue('role');

    console.log(`[LoginCN] handleModeChange: ${mode} -> ${newMode}`);
    setMode(newMode);
    if (newMode === 'email-login' || newMode === 'email-signup' || newMode === 'email-signup-verify') {
      setActiveTab('email');
    } else if (newMode === 'phone-login' || newMode === 'phone-signup') {
      setActiveTab('phone');
    }

    // 重置表单: 切到 signup/forgot 模式时,清掉 username+password,避免用户
    // 误以为在"注册"而实际表单已被自动填充成旧账号的登录凭证 — 这是
    // "邮箱注册号码直接登录"的根本原因 (见 CLAUDE.md §6: 必须 fail-safe,
    // 不能让旧 keyring 凭证污染新流程)。
    if (newMode === 'email-signup') {
      // 注册是"创建新账号",必须清空旧 login 凭证
      form.resetFields(['username', 'password', 'confirmPassword', 'code', 'newPassword']);
    } else if (newMode === 'email-signup-verify') {
      // 验证页面保留 username，只清掉密码相关字段
      form.resetFields(['password', 'confirmPassword', 'newPassword']);
    } else if (newMode === 'phone-signup' || newMode === 'phone-login') {
      form.resetFields(['username', 'password', 'confirmPassword', 'code', 'newPassword']);
    } else if (newMode === 'email-login') {
      // 切回 login 时清掉 code + confirmPassword + newPassword,保留 username/password 让 rememberMe 起作用
      form.resetFields(['code', 'confirmPassword', 'newPassword']);
    } else if (newMode === 'forgot') {
      form.resetFields(['username', 'password', 'confirmPassword', 'code', 'newPassword']);
    }

    // 恢复 role
    if (savedRole) {
      form.setFieldValue('role', savedRole);
    }

    // 切到 signup 模式时: 关闭 rememberMe,避免注册成功后自动保存旧密码到 keyring
    if (newMode === 'email-signup' || newMode === 'phone-signup') {
      setRememberMe(false);
    } else if (newMode === 'email-login' || newMode === 'phone-login') {
      setRememberMe(true);
    }

    // 切模式时清掉所有验证码/session 状态
    setLoading(false);
    setLoginSuccessful(false);
    setHasNavigated(false);
    setCodeSent(false);
    setLoginProgress('idle');
    setLastError(null);
    setCountdown(0);
    setVerificationId(null);
    setPendingSignupCode(null);
  }, [form]);

  // 获取标题
  const getTitle = () => {
    switch (mode) {
      case 'email-login': return t('login.title');
      case 'email-signup': return t('login.createAccount');
      case 'email-signup-verify': return t('login.verifyEmail');
      case 'phone-login': return t('login.phoneLogin'); // "手机登录 / 注册"
      case 'phone-signup': return t('login.phoneSignup'); // 不再通过 UI 进入
      case 'forgot': return t('login.forgotPassword');
      default: return t('login.title');
    }
  };

  return (
    <div className="cn-login-container">
      <div className="cn-login-decoration" />

      {/* 语言选择器 */}
      <div className="cn-language-selector">
        <Select
          value={i18n.language}
          size="small"
          onChange={handleLanguageChange}
          variant="borderless"
        >
          <Select.Option value="en-US">{t('languages.en-US')}</Select.Option>
          <Select.Option value="zh-CN">{t('languages.zh-CN')}</Select.Option>
        </Select>
      </div>

      {/* 加载进度 - email-signup 模式不显示（发送验证码很快，不需要遮罩） */}
      <LoadingProgress
        visible={loading && mode !== 'email-signup'}
        message={loginProgress === 'redirecting'
          ? t('login.redirectingToMain')
          : loginProgress === 'success'
            ? t('login.success')
            : t('login.verifying')}
      />

      {/* 隐藏登录卡片 during loading */}
      {!loading && (
        <div className="cn-login-card">
          <>
            {/* Logo */}
            <div className="cn-login-logo">
              <img src={logo} alt={t('login.logoAlt')} />
            </div>

            {/* 标题 */}
            <h1 className="cn-login-title">{getTitle()}</h1>
            <p className="cn-login-subtitle">{t('login.subtitle')}</p>

            {/* Tab 切换 */}
            {mode !== 'forgot' && (
              <div className="cn-login-tabs">
                <button
                  type="button"
                  className={`cn-tab ${activeTab === 'email' ? 'active' : ''}`}
                  onClick={() => handleTabChange('email')}
                >
                  <MailOutlined />
                  <span>{t('login.emailTab')}</span>
                </button>
                <button
                  type="button"
                  className={`cn-tab ${activeTab === 'phone' ? 'active' : ''}`}
                  onClick={() => handleTabChange('phone')}
                >
                  <MobileOutlined />
                  <span>{t('login.phoneTab')}</span>
                </button>
                {wechatAvailable && (
                  <button
                    type="button"
                    className={`cn-tab ${activeTab === 'wechat' ? 'active' : ''}`}
                    onClick={() => handleTabChange('wechat')}
                  >
                    <WechatOutlined />
                    <span>{t('login.wechatTab')}</span>
                  </button>
                )}
              </div>
            )}

            {/* 表单 */}
            <Form
              form={form}
              name="login"
              onFinish={handleSubmit}
              layout="vertical"
              requiredMark={false}
              initialValues={{ role: 'Commander' }}
              className="cn-login-form"
            >
              {/* 邮箱登录/注册表单 */}
              {(activeTab === 'email' && mode !== 'forgot') && (
                <>
                  <Form.Item
                    name="username"
                    rules={[{ required: true, message: t('login.usernameRequired') }]}
                  >
                    <Input
                      prefix={<UserOutlined />}
                      placeholder={t('common.email')}
                      size="large"
                      autoComplete="off"
                      id="ecan-email-login-username"
                    />
                  </Form.Item>

                  {mode === 'email-login' && (
                    <Form.Item
                      name="password"
                      rules={[{ required: true, message: t('login.passwordRequired') }]}
                    >
                      <Input.Password
                        prefix={<LockOutlined />}
                        placeholder={t('common.password')}
                        size="large"
                        autoComplete="current-password"
                      />
                    </Form.Item>
                  )}

                  {mode === 'email-login' && (
                    <div style={{ marginTop: -8, marginBottom: 16 }}>
                      <Checkbox
                        checked={rememberMe}
                        onChange={(e) => handleRememberMeChange(e.target.checked)}
                        style={{ color: 'rgba(255, 255, 255, 0.7)' }}
                      >
                        {t('login.rememberMe') || '记住密码'}
                      </Checkbox>
                    </div>
                  )}

                  {mode === 'email-signup' && (
                    <>
                      <Form.Item
                        name="password"
                        rules={[
                          { required: true, message: t('login.passwordRequired') },
                          { min: 8, message: t('login.passwordMinLength') },
                          { pattern: /[A-Z]/, message: t('login.passwordNeedUppercase') },
                          { pattern: /[a-z]/, message: t('login.passwordNeedLowercase') },
                          { pattern: /[0-9]/, message: t('login.passwordNeedNumber') },
                        ]}
                      >
                        <Input.Password
                          prefix={<LockOutlined />}
                          placeholder={t('common.password')}
                          size="large"
                          autoComplete="new-password"
                        />
                      </Form.Item>
                      <Form.Item
                        name="confirmPassword"
                        rules={[
                          { required: true, message: t('login.confirmPasswordRequired') },
                          ({ getFieldValue }) => ({
                            validator(_, value) {
                              if (!value || getFieldValue('password') === value) {
                                return Promise.resolve();
                              }
                              return Promise.reject(new Error(t('login.passwordMismatch')));
                            },
                          }),
                        ]}
                      >
                        <Input.Password
                          prefix={<LockOutlined />}
                          placeholder={t('login.confirmPassword')}
                          size="large"
                          autoComplete="new-password"
                        />
                      </Form.Item>
                    </>
                  )}

                  {/* 邮箱注册 - 验证邮箱页面 */}
                  {mode === 'email-signup-verify' && pendingSignupCode && (
                    <>
                      <div style={{
                        marginBottom: 16,
                        padding: '12px 16px',
                        background: 'rgba(56, 161, 105, 0.1)',
                        border: '1px solid rgba(56, 161, 105, 0.3)',
                        borderRadius: 8,
                        textAlign: 'center'
                      }}>
                        <Text style={{ color: '#73d13d', fontSize: 13 }}>
                          {t('login.signupCodeSent') || '验证码已发送到您的邮箱'}
                        </Text>
                        <br />
                        <Text style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>
                          {pendingSignupCode.email}
                        </Text>
                      </div>
                      <Form.Item
                        name="code"
                        rules={[{ required: true, message: t('login.codeRequired') }]}
                      >
                        <Input
                          prefix={<SafetyCertificateOutlined />}
                          placeholder={t('login.codePlaceholder')}
                          size="large"
                          maxLength={6}
                        />
                      </Form.Item>
                    </>
                  )}

                  {mode === 'email-login' && (
                    <Form.Item name="role" rules={[{ required: true }]}>
                      <Select size="large">
                        <Select.Option value="Commander">{t('roles.commander')}</Select.Option>
                        <Select.Option value="Platoon">{t('roles.platoon')}</Select.Option>
                        <Select.Option value="Staff Officer">{t('roles.staff_office')}</Select.Option>
                      </Select>
                    </Form.Item>
                  )}
                </>
              )}

              {/* 手机号表单 */}
              {activeTab === 'phone' && mode !== 'forgot' && (
                <>
                  <Form.Item
                    name="phone"
                    rules={[
                      { required: true, message: t('login.phoneRequired') },
                      { pattern: /^1[3-9]\d{9}$/, message: t('login.invalidPhone') }
                    ]}
                  >
                    <Input
                      prefix={<MobileOutlined />}
                      placeholder={t('login.phonePlaceholder')}
                      size="large"
                      disabled={codeSent}
                      maxLength={11}
                    />
                  </Form.Item>
                  <Form.Item
                    name="code"
                    rules={[{ required: true, message: t('login.codeRequired') }]}
                  >
                    <Input
                      prefix={<SafetyCertificateOutlined />}
                      placeholder={t('login.codePlaceholder')}
                      size="large"
                      maxLength={6}
                      suffix={
                        <button
                          type="button"
                          className="cn-send-code-btn"
                          disabled={countdown > 0 || !phoneValue}
                          onClick={() => handleSendCode(phoneValue)}
                        >
                          {countdown > 0 ? `${countdown}s` : t('login.sendCode')}
                        </button>
                      }
                    />
                  </Form.Item>
                  <Form.Item name="role" rules={[{ required: true }]}>
                    <Select size="large">
                      <Select.Option value="Commander">{t('roles.commander')}</Select.Option>
                      <Select.Option value="Platoon">{t('roles.platoon')}</Select.Option>
                      <Select.Option value="Staff Officer">{t('roles.staff_office')}</Select.Option>
                    </Select>
                  </Form.Item>
                </>
              )}

              {/* 微信扫码区域 */}
              {activeTab === 'wechat' && wechatAvailable && (
                <div className="cn-wechat-area">
                  <div className="cn-wechat-icon">
                    <WechatOutlined style={{ fontSize: 36, color: '#07c160' }} />
                  </div>
                  <p className="cn-wechat-hint">{t('login.wechatHint') || '使用微信扫码登录'}</p>
                  <button
                    type="button"
                    className="cn-wechat-btn"
                    onClick={handleWechatLogin}
                    disabled={loading}
                  >
                    <WechatOutlined />
                    <span>{t('login.loginWithWechat')}</span>
                  </button>
                </div>
              )}

              {/* 忘记密码表单 */}
              {mode === 'forgot' && (
                <>
                  <Form.Item
                    name="phone"
                    rules={[
                      { required: true, message: t('login.phoneRequired') },
                      { pattern: /^1[3-9]\d{9}$/, message: t('login.invalidPhone') }
                    ]}
                  >
                    <Input
                      prefix={<MobileOutlined />}
                      placeholder={t('login.phonePlaceholder')}
                      size="large"
                      disabled={codeSent}
                      maxLength={11}
                    />
                  </Form.Item>
                  <Form.Item
                    name="code"
                    rules={[{ required: true, message: t('login.codeRequired') }]}
                  >
                    <Input
                      prefix={<SafetyCertificateOutlined />}
                      placeholder={t('login.codePlaceholder')}
                      size="large"
                      maxLength={6}
                      suffix={
                        <button
                          type="button"
                          className="cn-send-code-btn"
                          disabled={countdown > 0 || !phoneValue}
                          onClick={() => handleSendForgotCode(phoneValue)}
                        >
                          {countdown > 0 ? `${countdown}s` : t('login.sendCode')}
                        </button>
                      }
                    />
                  </Form.Item>
                  <Form.Item
                    name="newPassword"
                    rules={[
                      { required: true, message: t('login.passwordRequired') },
                      { min: 8, message: t('login.passwordMinLength') },
                      { pattern: /[A-Z]/, message: t('login.passwordNeedUppercase') },
                      { pattern: /[a-z]/, message: t('login.passwordNeedLowercase') },
                      { pattern: /[0-9]/, message: t('login.passwordNeedNumber') },
                    ]}
                  >
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder={t('login.newPassword')}
                      size="large"
                    />
                  </Form.Item>
                  <Form.Item
                    name="confirmPassword"
                    rules={[
                      { required: true, message: t('login.confirmPasswordRequired') },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue('newPassword') === value) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error(t('login.passwordMismatch')));
                        },
                      }),
                    ]}
                  >
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder={t('login.confirmPassword')}
                      size="large"
                    />
                  </Form.Item>
                </>
              )}

              {/* 提交按钮 */}
              {mode !== 'forgot' && activeTab !== 'wechat' && (
                <Form.Item className="cn-submit-item">
                  <Button
                    type="primary"
                    htmlType="submit"
                    size="large"
                    block
                    loading={loading}
                    disabled={loading || loginSuccessful}
                    className="cn-login-button"
                  >
                    {loading
                      ? t('login.loggingIn')
                      : mode === 'email-login' || mode === 'phone-login'
                        ? t('login.loginButton')
                        : mode === 'email-signup-verify'
                          ? t('login.confirmSignup') || '确认注册'
                          : t('login.signUp')}
                  </Button>
                </Form.Item>
              )}

              {mode === 'forgot' && (
                <Form.Item className="cn-submit-item">
                  <Button
                    type="primary"
                    htmlType="submit"
                    size="large"
                    block
                    loading={loading}
                    className="cn-login-button"
                  >
                    {t('login.resetPassword')}
                  </Button>
                </Form.Item>
              )}

              {/* 错误提示 */}
              {lastError && !loading && (
                <div className="cn-error-message">{lastError}</div>
              )}

              {/* 链接按钮 */}
              <div className="cn-link-row">
                {mode === 'forgot' || mode === 'email-signup-verify' ? (
                  <button
                    type="button"
                    className="cn-link-button"
                    onClick={() => handleModeChange('email-login')}
                  >
                    <CheckCircleOutlined />
                    <span>{t('login.backToLogin')}</span>
                  </button>
                ) : (
                  <>
                    {/* 忘记密码 */}
                    {mode === 'email-login' && (
                      <button
                        type="button"
                        className="cn-link-button"
                        onClick={() => handleModeChange('forgot')}
                      >
                        {t('login.forgotPassword')}
                      </button>
                    )}

                    {/* 切换登录/注册 — 手机号模式不显示 (智能登录/注册一站式,后端自动 sign_in/sign_up) */}
                    {(mode === 'email-login' || mode === 'email-signup') && (
                      <button
                        type="button"
                        className="cn-link-button cn-link-primary"
                        onClick={() => handleModeChange(
                          mode === 'email-login' ? 'email-signup' : 'email-login'
                        )}
                      >
                        {mode === 'email-signup'
                          ? t('login.backToLogin')
                          : t('login.signUp')}
                      </button>
                    )}
                  </>
                )}
              </div>
            </Form>
          </>
        </div>
      )}
    </div>
  );
};

export default LoginCN;

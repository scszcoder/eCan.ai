/**
 * 微信登录回调页
 * 处理微信 OAuth 回调，使用 code 换取登录态
 */

import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Spin } from 'antd';
import { cloudbaseAuth } from '../../services/auth/cloudbaseAuth';
import { getCurrentRegion } from '../../services/auth/AuthProvider';
import { useTranslation } from 'react-i18next';
import { useAppConfig } from '../../contexts/AppConfigContext';
import { userStorageManager } from '../../services/storage/UserStorageManager';

const WechatCallback: React.FC = () => {
  const navigate = useNavigate();
  const { message: messageApi } = App.useApp();
  const { t } = useTranslation();
  const { config } = useAppConfig();
  const processed = useRef(false);
  const [initError, setInitError] = useState<string | null>(null);

  // 初始化 CloudBase 配置
  useEffect(() => {
    if (!config) return;
    const envId = config.auth?.cloudbase_env_id;
    if (envId && !cloudbaseAuth.isInitialized()) {
      cloudbaseAuth.initialize({ envId });
    }
  }, [config]);

  useEffect(() => {
    // CN 版本才允许
    if (getCurrentRegion() !== 'cn') {
      navigate('/login', { replace: true });
      return;
    }

    // 防止 React 18 严格模式下重复处理
    if (processed.current) return;
    processed.current = true;

    const handleCallback = async () => {
      // 等待 CloudBase 初始化
      if (!cloudbaseAuth.isInitialized()) {
        // 等待一下配置加载
        await new Promise(resolve => setTimeout(resolve, 500));
        if (!cloudbaseAuth.isInitialized()) {
          setInitError(t('login.cloudbaseNotConfigured') || 'CloudBase not configured');
          setTimeout(() => navigate('/login', { replace: true }), 2000);
          return;
        }
      }

      try {
        // 从 URL hash/query 解析 code
        const hash = window.location.hash;
        const search = window.location.search;
        const queryFromHash = hash.includes('?') ? hash.substring(hash.indexOf('?') + 1) : '';
        const query = queryFromHash || (search.startsWith('?') ? search.substring(1) : '');
        const params = new URLSearchParams(query);

        const code = params.get('code');
        const state = params.get('state');
        const error = params.get('error');

        if (error) {
          messageApi.error(`WeChat error: ${error}`);
          navigate('/login', { replace: true });
          return;
        }

        if (!code) {
          messageApi.error('Missing WeChat code');
          navigate('/login', { replace: true });
          return;
        }

        // 验证 state（防 CSRF）
        const storedState = sessionStorage.getItem('wechat_oauth_state');
        if (storedState && state && storedState !== state) {
          messageApi.error('Invalid state. Possible CSRF attack.');
          navigate('/login', { replace: true });
          return;
        }

        sessionStorage.removeItem('wechat_oauth_state');

        // 调用 cloudbaseAuth.loginWithWechat（走 IPC）
        const result = await cloudbaseAuth.loginWithWechat(code);

        if (result.success && result.data) {
          const { token, userInfo } = result.data;

          // 保存登录会话
          userStorageManager.saveLoginSession({
            token,
            userInfo,
            loginTime: Date.now(),
          });

          messageApi.success(t('login.loginSuccess') || 'Login successful');
          // 跳转到主页
          setTimeout(() => navigate('/agents', { replace: true }), 200);
        } else {
          messageApi.error(result.error || 'WeChat login failed');
          setTimeout(() => navigate('/login', { replace: true }), 1000);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        messageApi.error(msg);
        setTimeout(() => navigate('/login', { replace: true }), 1000);
      }
    };

    // 延迟执行，等待配置加载
    const timer = setTimeout(handleCallback, 100);
    return () => clearTimeout(timer);
  }, [navigate, messageApi, t, config]);

  if (initError) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#1a1a1a',
          color: '#fff',
          gap: 16,
        }}
      >
        <Spin size="large" />
        <div style={{ color: '#ff4d4f' }}>{initError}</div>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#1a1a1a',
        color: '#fff',
        gap: 16,
      }}
    >
      <Spin size="large" />
      <div>{t('login.authenticating') || 'Authenticating...'}</div>
    </div>
  );
};

export default WechatCallback;

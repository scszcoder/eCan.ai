import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Spin, Typography, App } from 'antd';
import { cognitoAuth } from '../../services/auth/cognitoAuth';
import { ciamAuth } from '../../services/auth/ciamAuth';
import { webAuthSession } from '../../services/auth/webAuthSession';
import { userStorageManager } from '../../services/storage/UserStorageManager';
import { tokenRefreshService } from '../../services/auth/tokenRefreshService';
import { refreshAllMineStores } from '../../services/web/webStoreSync';

const { Title, Text } = Typography;

const AuthCallback: React.FC = () => {
  const navigate = useNavigate();
  const { message: messageApi } = App.useApp();
  const [status, setStatus] = React.useState<'processing' | 'success' | 'error'>('processing');
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    const run = async () => {
      try {
        // Dispatch to the right auth client by the marker set at login start.
        // Default (no marker) = Cognito, so the global path is unchanged.
        const loginProvider = sessionStorage.getItem('login_provider');
        const isWechat = loginProvider === 'wechat';
        const authClient = isWechat ? ciamAuth : cognitoAuth;

        const params = authClient.parseCallbackParams();
        if (params.error) {
          throw new Error(params.error);
        }
        if (!params.code) {
          throw new Error('Missing authorization code.');
        }

        const tokens = await authClient.exchangeCodeForTokens(params.code, params.state);
        const expiresAt = tokens.expires_in ? Date.now() + tokens.expires_in * 1000 : undefined;
        const payload = authClient.decodeIdToken(tokens.id_token);

        const storedLoginMethod = sessionStorage.getItem('cognito_login_method');
        const identities = Array.isArray(payload.identities) ? payload.identities : [];
        const providerName = identities[0]?.providerName || identities[0]?.providerType || '';
        const loginType: 'google' | 'password' | 'wechat' = isWechat
          ? 'wechat'
          : storedLoginMethod === 'google'
            ? 'google'
            : storedLoginMethod === 'password'
              ? 'password'
              : (providerName.toLowerCase().includes('google') ? 'google' : 'password');
        sessionStorage.removeItem('cognito_login_method');
        sessionStorage.removeItem('login_provider');

        // Email is the primary identifier for the user
        const email = payload.email || '';
        const cognitoUsername = payload['cognito:username'] || payload.username || email || 'user';
        
        // Sanitize email to create a safe username for S3 paths
        // e.g., "jack@gmail.com" -> "jack_gmail_com"
        // This must match backend _safe_user_dir_name() in skill_editor_agent.py
        const sanitizeUsername = (u: string): string => {
          const trimmed = (u || '').trim();
          if (!trimmed) return 'unknown';
          if (trimmed.includes('@')) {
            const [localPart, domainPart] = trimmed.split('@', 2);
            return `${localPart}_${(domainPart || '').replace(/\./g, '_')}`;
          }
          return trimmed.replace(/@/g, '_').replace(/\./g, '_');
        };
        
        // Use sanitized email as the username for API calls and file paths
        // This ensures consistency between frontend and backend S3 paths
        const sanitizedUsername = email ? sanitizeUsername(email) : sanitizeUsername(cognitoUsername);
        
        const userInfo = {
          username: sanitizedUsername,  // Sanitized for API calls and S3 paths
          email: email,  // Raw email for display
          name: payload.name,
          given_name: payload.given_name,
          family_name: payload.family_name,
          picture: payload.picture,
          email_verified: payload.email_verified,
          sub: payload.sub,
          cognito_username: cognitoUsername,  // Original cognito username if needed
        };

        webAuthSession.setSession({
          accessToken: tokens.access_token,
          idToken: tokens.id_token,
          refreshToken: tokens.refresh_token,
          tokenType: tokens.token_type,
          expiresAt,
          userInfo,
        });

        try {
          userStorageManager.setUserInfo({
            username: userInfo.username,
            role: 'Commander',
            email: userInfo.email,
            name: userInfo.name,
            given_name: userInfo.given_name,
            family_name: userInfo.family_name,
            picture: userInfo.picture,
            email_verified: userInfo.email_verified,
            login_type: loginType,
          });
          userStorageManager.setAuthenticationState(true);
        } catch {}

        setStatus('success');
        messageApi.success('Login successful');
        tokenRefreshService.start(tokens.access_token, {
          checkInterval: 10 * 60 * 1000,
          refreshThreshold: 10 * 60,
          onTokenExpired: () => {
            messageApi.warning('Session expired. Please sign in again.');
            userStorageManager.logout();
            navigate('/login');
          }
        });

        try {
          await refreshAllMineStores(userInfo.username);
        } catch (loadError) {
          console.warn('[AuthCallback] getAllMine failed:', loadError);
        }

        navigate('/agents');
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        setStatus('error');
        setErrorMessage(msg);
        messageApi.error(`Login failed: ${msg}`);
      }
    };

    run();
  }, [navigate, messageApi]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Card style={{ maxWidth: 480, width: '90%' }}>
        {status === 'processing' && (
          <div style={{ textAlign: 'center' }}>
            <Spin size="large" />
            <Title level={4} style={{ marginTop: 16 }}>Completing sign-in...</Title>
            <Text type="secondary">Please wait while we finish authentication.</Text>
          </div>
        )}
        {status === 'error' && (
          <div style={{ textAlign: 'center' }}>
            <Title level={4}>Login failed</Title>
            <Text type="secondary">{errorMessage}</Text>
          </div>
        )}
      </Card>
    </div>
  );
};

export default AuthCallback;

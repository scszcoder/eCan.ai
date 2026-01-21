import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Spin, Typography, App } from 'antd';
import { cognitoAuth } from '../../services/auth/cognitoAuth';
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
        const params = cognitoAuth.parseCallbackParams();
        if (params.error) {
          throw new Error(params.error);
        }
        if (!params.code) {
          throw new Error('Missing authorization code.');
        }

        const tokens = await cognitoAuth.exchangeCodeForTokens(params.code, params.state);
        const expiresAt = tokens.expires_in ? Date.now() + tokens.expires_in * 1000 : undefined;
        const payload = cognitoAuth.decodeIdToken(tokens.id_token);

        const storedLoginMethod = sessionStorage.getItem('cognito_login_method');
        const identities = Array.isArray(payload.identities) ? payload.identities : [];
        const providerName = identities[0]?.providerName || identities[0]?.providerType || '';
        const loginType: 'google' | 'password' = storedLoginMethod === 'google'
          ? 'google'
          : storedLoginMethod === 'password'
            ? 'password'
            : (providerName.toLowerCase().includes('google') ? 'google' : 'password');
        sessionStorage.removeItem('cognito_login_method');

        const userInfo = {
          username: payload['cognito:username'] || payload.username || payload.email || 'user',
          email: payload.email,
          name: payload.name,
          given_name: payload.given_name,
          family_name: payload.family_name,
          picture: payload.picture,
          email_verified: payload.email_verified,
          sub: payload.sub,
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
          await refreshAllMineStores();
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

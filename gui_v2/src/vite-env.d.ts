/// <reference types="vite/client" />

/**
 * 自定义 VITE_* 环境变量类型声明
 *
 * 运行时真值源（API/WS endpoint、app_id、is_cn、auth_type）由后端 IPC
 * handler `getAppConfig`（见 gui/ipc/w2p_handlers/app_config_handler.py）
 * 提供，前端构建期不再需要这些变量。VITE_* 此处仅保留：
 *   - IPC 模式开关（dev/test 行为差异）
 *   - Web 部署 / Tests 页面用的 AppSync 端点
 *   - dev 用的 CloudBase / Cognito 兜底字段（仅 web 部署生效）
 */
interface ImportMetaEnv {
  // ===== 平台 / 路由 =====
  readonly VITE_PLATFORM?: 'desktop' | 'web';
  readonly VITE_BASE?: string;

  // ===== IPC 模式 =====
  readonly VITE_IPC_MODE?: string;
  readonly VITE_LOCAL_SERVER_PORT?: string;

  // ===== 区域标识 (已弃用: 构建期不区分 CN/Intl) =====
  readonly VITE_APP_ID?: 'cn' | 'intl';
  readonly VITE_IS_CN?: 'true' | 'false';

  // ===== CloudBase (CN) =====
  readonly VITE_CLOUDBASE_ENV_ID?: string;
  readonly VITE_WECHAT_APP_ID?: string;

  // ===== Cognito (Intl) =====
  readonly VITE_COGNITO_DOMAIN?: string;
  readonly VITE_COGNITO_CLIENT_ID?: string;
  readonly VITE_COGNITO_REDIRECT_URI?: string;
  readonly VITE_COGNITO_LOGOUT_URI?: string;
  readonly VITE_COGNITO_SCOPES?: string;

  // ===== AppSync (Intl Web / Tests) =====
  readonly VITE_APPSYNC_ENDPOINT?: string;
  readonly VITE_APPSYNC_HTTP_ENDPOINT?: string;
  readonly VITE_APPSYNC_WS_ENDPOINT?: string;
  readonly VITE_APPSYNC_WS_HOST?: string;
  readonly VITE_APPSYNC_API_KEY?: string;

  // ===== 调试 =====
  readonly VITE_VERBOSE_GRAPHQL?: 'true' | 'false';

  // ===== Tests 页面专用 =====
  readonly VITE_ACCOUNT_OWNER?: string;
  readonly VITE_ACCT_SITE_ID?: string;
  readonly VITE_A2A_CHANNEL_ID?: string;
  readonly VITE_TASK_RUNNER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
/**
 * Onboarding Service
 * 引导页服务 - 根据后端指令类型显示不同的引导页
 */

import React from "react";
import { Modal, Button } from "antd";
import { createRoot, Root } from "react-dom/client";

import { RocketOutlined, SettingOutlined } from "@ant-design/icons";
import { logger } from "@/utils/logger";
import i18n from "@/i18n";
// Guard to ensure only one onboarding modal is displayed at a time
let __onboardingShowing = false;

// Optional context-aware modal API from App.useApp()
type ModalAPI = {
  confirm: (config: any) => any;
};
let __modalAPI: ModalAPI | null = null;

export const registerOnboardingModalApi = (modalApi: ModalAPI | null) => {
  __modalAPI = modalApi;
};

// Persistent React root to avoid flicker from mount/unmount of Modal
let __onboardingContainer: HTMLDivElement | null = null;
let __onboardingRoot: Root | null = null;
type HostState = {
  open: boolean;
  config?: OnboardingConfig;
  localized?: LocalizedOnboardingContent;
  context?: OnboardingContext;
  onNavigate?: (path: string) => void;
};
let __hostState: HostState = { open: false };

// Clean up and fully unmount the persistent host
const cleanupHost = () => {
  try {
    if (__onboardingRoot) {
      __onboardingRoot.unmount();
      __onboardingRoot = null as unknown as Root;
    }
    if (__onboardingContainer && __onboardingContainer.parentNode) {
      __onboardingContainer.parentNode.removeChild(__onboardingContainer);
    }
  } catch {}
  __onboardingContainer = null;
};

const ensureHost = () => {
  if (__onboardingRoot) return __onboardingRoot;
  const container = document.createElement('div');
  container.id = 'onboarding-react-host';
  document.body.appendChild(container);
  __onboardingContainer = container;
  __onboardingRoot = createRoot(container);
  return __onboardingRoot;
};
 

// Render (or re-render) the persistent AntD Modal host
const renderHost = () => {
  const root = ensureHost();
  const { open, config, localized, context, onNavigate } = __hostState;

  const handleClose = () => {
    __hostState.open = false;
    __onboardingShowing = false;
    renderHost();
    // Fully remove the host after the state update render
    setTimeout(() => cleanupHost(), 0);
  };

  const handlePrimary = () => {
    try {
      if (config && onNavigate) {
        const path = config.getNavigationPath(context);
        __hostState.open = false;
        __onboardingShowing = false;
        renderHost();
        // Fully remove the host before navigation to avoid lingering overlay
        setTimeout(() => cleanupHost(), 0);
        onNavigate(path);
      }
    } catch (e) {
      logger.error('[Onboarding] Navigation failed:', e);
    }
  };

  const modalBody = config && localized
    ? createModalContent(config, localized, handlePrimary, handleClose)
    : null;

  root.render(
    React.createElement(
      React.Fragment,
      null,
      // Custom static mask (no animations). Visible only when open.
      React.createElement('div', {
        className: 'onboarding-static-mask',
        style: {
          position: 'fixed',
          inset: 0 as any,
          background: 'rgba(0,0,0,0.45)',
          display: open ? 'block' : 'none',
          zIndex: 2147483000,
          pointerEvents: open ? 'auto' : 'none',
          transition: 'none',
        } as any,
      }),
      React.createElement(
        Modal,
        {
          open,
          centered: true,
          footer: null,
          closable: false,
          mask: false,
          keyboard: false,
          // Disable AntD animations at component level
          transitionName: '',
          maskTransitionName: '',
          forceRender: true,
          className: 'onboarding-modal',
          rootClassName: 'onboarding-modal-root',
          getContainer: () => document.body,
          zIndex: 2147483600,
          onCancel: handleClose,
          width: 480,
          styles: {
            body: { transition: 'none' },
            header: { transition: 'none' },
            footer: { transition: 'none' },
            content: { transition: 'none' },
          } as any,
          style: { transition: 'none' } as any,
        } as any,
        modalBody,
      )
    )
  );
};

/**
 * Onboarding context from backend
 * 后端传递的上下文信息
 */
export interface OnboardingContext {
  suggestedAction?: {
    type: string;
    path?: string;
    params?: Record<string, string>;
  };
  [key: string]: any;
}

/**
 * Onboarding configuration for each type
 * 每种引导类型的配置
 */
interface OnboardingTextKeys {
  title: string;
  message: string;
  primaryButton: string;
  skipButton?: string;
}

interface LocalizedOnboardingContent {
  title: string;
  message: string;
  primaryButtonText: string;
  skipButtonText?: string;
}

interface OnboardingConfig {
  icon: any;
  iconColor: string;
  textKeys: OnboardingTextKeys;
  showSkipButton: boolean;
  getNavigationPath: (context?: OnboardingContext) => string;
}

/**
 * Onboarding configurations for different types
 * 不同类型引导页的配置定义
 */
const ONBOARDING_CONFIGS: Record<string, OnboardingConfig> = {
  llm_provider_config: {
    icon: RocketOutlined,
    iconColor: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    textKeys: {
      title: "onboarding.llmProviderConfig.title",
      message: "onboarding.llmProviderConfig.message",
      primaryButton: "onboarding.llmProviderConfig.primaryButton",
      skipButton: "onboarding.llmProviderConfig.skipButton",
    },
    showSkipButton: true,
    getNavigationPath: (context) => {
      if (context?.suggestedAction?.path) {
        const params = context.suggestedAction.params;
        if (params && Object.keys(params).length > 0) {
          const query = new URLSearchParams(params).toString();
          return `${context.suggestedAction.path}?${query}`;
        }
        return context.suggestedAction.path;
      }
      return "/settings?tab=llm";
    },
  },
  embedding_provider_config: {
    icon: RocketOutlined,
    iconColor: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
    textKeys: {
      title: "onboarding.embeddingProviderConfig.title",
      message: "onboarding.embeddingProviderConfig.message",
      primaryButton: "onboarding.embeddingProviderConfig.primaryButton",
      skipButton: "onboarding.embeddingProviderConfig.skipButton",
    },
    showSkipButton: true,
    getNavigationPath: (context) => {
      if (context?.suggestedAction?.path) {
        const params = context.suggestedAction.params;
        if (params && Object.keys(params).length > 0) {
          const query = new URLSearchParams(params).toString();
          return `${context.suggestedAction.path}?${query}`;
        }
        return context.suggestedAction.path;
      }
      return "/settings?tab=embedding";
    },
  },
  // 可以轻松添加更多引导类型
  // agent_setup: { ... },
  // first_task: { ... },
};

const resolveOnboardingContent = (
  config: OnboardingConfig,
): LocalizedOnboardingContent => ({
  title: i18n.t(config.textKeys.title),
  message: i18n.t(config.textKeys.message),
  primaryButtonText: i18n.t(config.textKeys.primaryButton),
  skipButtonText: config.textKeys.skipButton
    ? i18n.t(config.textKeys.skipButton)
    : undefined,
});

/**
 * Create default navigation function
 * 创建默认的导航函数
 */
const createNavigateFunction = (): ((path: string) => void) => {
  return (path: string) => {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const hashPath = `#${normalizedPath}`;

    if (window.location.hash !== hashPath) {
      window.location.hash = hashPath;
    } else {
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
  };
};

/**
 * Handle onboarding request from backend
 * Main entry point for processing onboarding requests
 */
export const handleOnboardingRequest = async (
  onboardingType: string,
  context?: OnboardingContext,
): Promise<void> => {
  try {
    logger.info(
      `[OnboardingService] Processing onboarding request: ${onboardingType}`,
    );

    // Import styles lazily to avoid bundling issues
    await import("./onboardingStyles.css");

    const navigate = createNavigateFunction();

    // Reset stale state if flag is set but container is missing
    if (__onboardingShowing && !document.querySelector('.onboarding-modal-container')) {
      __onboardingShowing = false;
    }

    // Prevent multiple modals from being shown simultaneously
    if (__onboardingShowing) {
      logger.warn("[OnboardingService] Onboarding modal already visible, skip duplicate show.");
      return;
    }

    showOnboardingGuide(onboardingType, context, navigate);
    logger.info(
      `[OnboardingService] Onboarding guide displayed: ${onboardingType}`,
    );
  } catch (error) {
    logger.error(
      "[OnboardingService] Error processing onboarding request:",
      error,
    );
    throw error;
  }
};

/**
 * Onboarding modal props for the React renderer
 */
// No React component interface needed for host-driven Modal rendering

/**
 * Create the modern onboarding modal content
 */
const createModalContent = (
  config: OnboardingConfig,
  content: LocalizedOnboardingContent,
  handlePrimary: () => void,
  handleSkip: () => void,
): React.ReactElement => {
  return React.createElement(
    "div",
    {
      style: {
        textAlign: "center",
        padding: "20px 0",
      },
    },
    // Icon container with gradient background
    React.createElement(
      "div",
      {
        style: {
          width: "80px",
          height: "80px",
          margin: "0 auto 24px",
          borderRadius: "50%",
          background: '#667eea',
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 4px 12px rgba(102, 126, 234, 0.24)",
        },
      },
      React.createElement(config.icon, {
        style: {
          fontSize: "40px",
          color: "#ffffff",
        },
      }),
    ),
    // Title
    React.createElement(
      "h2",
      {
        style: {
          fontSize: "24px",
          fontWeight: 600,
          marginBottom: "16px",
          color: "rgba(0, 0, 0, 0.85)",
          lineHeight: "1.4",
        },
      },
      content.title,
    ),
    // Message
    React.createElement(
      "p",
      {
        style: {
          fontSize: "15px",
          lineHeight: "1.6",
          color: "rgba(0, 0, 0, 0.65)",
          marginBottom: "32px",
          padding: "0 20px",
        },
      },
      content.message,
    ),
    // Action buttons container
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          gap: "12px",
          justifyContent: "center",
          flexDirection: "column",
          padding: "0 20px",
        },
      },
      // Primary action button
      React.createElement(
        Button,
        {
          type: "primary",
          size: "large",
          icon: React.createElement(SettingOutlined),
          onClick: handlePrimary,
          style: {
            height: "48px",
            fontSize: "16px",
            fontWeight: 500,
            borderRadius: "8px",
            background: '#667eea',
            border: "none",
            boxShadow: "0 2px 8px rgba(102, 126, 234, 0.25)",
          },
        },
        content.primaryButtonText,
      ),
      // Secondary action - Skip
      config.showSkipButton
        ? React.createElement(
            Button,
            {
              type: "text",
              size: "large",
              onClick: handleSkip,
              style: {
                height: "40px",
                fontSize: "14px",
                color: "rgba(0, 0, 0, 0.45)",
              },
            },
            content.skipButtonText,
          )
        : null,
    ),
  );
};
/**
 * Render the onboarding modal into a portal attached to document.body
 */
const renderOnboardingModal = (
  config: OnboardingConfig,
  localized: LocalizedOnboardingContent,
  context: OnboardingContext | undefined,
  onNavigate: (path: string) => void,
): void => {
  try {
    // Update host state and render AntD Modal without mounting/unmounting root
    __hostState = {
      open: true,
      config,
      localized,
      context,
      onNavigate,
    };
    __onboardingShowing = true;
    renderHost();
  } catch (error) {
    logger.error("[Onboarding] Failed to render onboarding modal:", error);
  }
};

/**
 * Show onboarding guide modal based on type
 * 根据类型显示引导页对话框
 */
export const showOnboardingGuide = (
  onboardingType: string,
  context?: OnboardingContext,
  onNavigate?: (path: string) => void,
): void => {
  if (__onboardingShowing) {
    logger.warn("[Onboarding] Modal already showing, skip.");
    return;
  }
  const config = ONBOARDING_CONFIGS[onboardingType];

  if (!config) {
    logger.warn(`[Onboarding] Unknown onboarding type: ${onboardingType}`);
    return;
  }

  const navigate = onNavigate || createNavigateFunction();
  const localized = resolveOnboardingContent(config);
  renderOnboardingModal(config, localized, context, navigate);
};

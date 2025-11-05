/**
 * Onboarding Service
 * 引导页服务 - 根据后端指令类型显示不同的引导页
 */

import React from "react";
import { Modal, Button } from "antd";
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
interface OnboardingModalProps {
  config: OnboardingConfig;
  context?: OnboardingContext;
  onNavigate: (path: string) => void;
  onClose: () => void;
  localized: LocalizedOnboardingContent;
}

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
          background: config.iconColor,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 8px 24px rgba(102, 126, 234, 0.3)",
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
            background: config.iconColor,
            border: "none",
            boxShadow: "0 4px 12px rgba(102, 126, 234, 0.4)",
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
 * React component that renders the onboarding modal using Ant Design's Modal component
 */
const OnboardingModal: React.FC<OnboardingModalProps> = ({
  config,
  context,
  onNavigate,
  onClose,
  localized,
}) => {
  const [open, setOpen] = React.useState(true);
  const hasClosedRef = React.useRef(false);

  const scheduleCleanup = React.useCallback(() => {
    if (hasClosedRef.current) {
      return;
    }
    hasClosedRef.current = true;
    onClose();
  }, [onClose]);

  const closeModal = React.useCallback(() => {
    setOpen(false);
    window.setTimeout(scheduleCleanup, 0);
  }, [scheduleCleanup]);

  React.useEffect(() => {
    if (!open) {
      const timer = window.setTimeout(scheduleCleanup, 200);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [open, scheduleCleanup]);

  const handleSkip = () => {
    closeModal();
  };

  const handlePrimary = () => {
    try {
      const navigationPath = config.getNavigationPath(context);
      closeModal();
      setTimeout(() => {
        onNavigate(navigationPath);
      }, 120);
    } catch (error) {
      logger.error(
        "[Onboarding] Error during primary action navigation:",
        error,
      );
    }
  };

  const modalContent = createModalContent(
    config,
    localized,
    handlePrimary,
    handleSkip,
  );

  return React.createElement(
    Modal,
    {
      open,
      centered: true,
      footer: null,
      closable: false,
      maskClosable: false,
      onCancel: handleSkip,
      className: "onboarding-modal",
      rootClassName: "onboarding-modal-root",
      getContainer: () => document.body,
      zIndex: 2147483000,
      styles: {
        body: {
          padding: "40px 24px",
        },
      },
      width: 480,
      focusTriggerAfterClose: false,
      keyboard: false,
    },
    modalContent,
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
    // Use AntD standard confirm modal for reliability
    __onboardingShowing = true;

    const onOk = async () => {
      try {
        const navigationPath = config.getNavigationPath(context);
        onNavigate(navigationPath);
      } catch (e) {
        logger.error('[Onboarding] Navigation failed:', e);
      }
    };

    const onCancel = () => {
      /* no-op, just close */
    };

    const confirmFn = __modalAPI ? __modalAPI.confirm : Modal.confirm;
    const instance = confirmFn({
      title: localized.title,
      content: localized.message,
      okText: localized.primaryButtonText,
      cancelText: config.showSkipButton ? (localized.skipButtonText || undefined) : undefined,
      icon: React.createElement(config.icon, { style: { color: '#667eea' } }),
      onOk,
      onCancel,
      closable: false,
      keyboard: false,
      maskClosable: false,
      transitionName: '',
      maskTransitionName: '',
      centered: true,
      className: 'onboarding-modal',
      rootClassName: 'onboarding-modal-root',
      zIndex: 2147483000,
      getContainer: () => document.body,
    });

    // Ensure flag reset when closed
    const finalize = () => { __onboardingShowing = false; };
    // AntD confirm doesn't expose onClose, so we poll for DOM removal as a simple finalize
    const finalizeCheck = () => {
      const exists = document.querySelector('.onboarding-modal');
      if (!exists) {
        finalize();
      } else {
        setTimeout(finalizeCheck, 100);
      }
    };
    setTimeout(finalizeCheck, 100);

    const applyInlineFixes = () => {
      try {
        const wrap = document.querySelector('.onboarding-modal-root .ant-modal-wrap') as HTMLElement | null;
        const modal = document.querySelector('.onboarding-modal-root .ant-modal') as HTMLElement | null;
        const mask = document.querySelector('.onboarding-modal-root .ant-modal-mask') as HTMLElement | null;
        if (wrap) {
          wrap.style.position = 'fixed';
          (wrap.style as any).inset = '0';
          wrap.style.display = 'flex';
          wrap.style.alignItems = 'center';
          wrap.style.justifyContent = 'center';
          wrap.style.zIndex = '2147483001';
          wrap.style.pointerEvents = 'auto';
          wrap.style.opacity = '1';
          wrap.style.visibility = 'visible';
        }
        if (modal) {
          modal.style.margin = '0 auto';
          modal.style.opacity = '1';
          modal.style.visibility = 'visible';
          modal.style.transform = 'none';
          modal.style.zIndex = '2147483002';
        }
        if (mask) {
          mask.style.zIndex = '2147483000';
          mask.style.opacity = '1';
          mask.style.visibility = 'visible';
        }
      } catch {}
    };

    const ensureVisible = () => {
      try {
        const modalContent = document.querySelector('.onboarding-modal .ant-modal-content') as HTMLElement | null;
        if (modalContent) {
          const rect = modalContent.getBoundingClientRect();
          const styles = getComputedStyle(modalContent);
          const inViewport = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth;
          const visible = styles.visibility !== 'hidden' && styles.opacity !== '0';
          if (inViewport && visible) return true;
        }
        return false;
      } catch {
        return false;
      }
    };

    window.setTimeout(() => {
      if (ensureVisible()) {
        return;
      }
      // attempt inline fixes first
      applyInlineFixes();
      if (ensureVisible()) {
        return;
      }
      const fallback = document.createElement('div');
      fallback.setAttribute('data-onboarding-fallback', 'true');
      fallback.style.position = 'fixed';
      fallback.style.inset = '0';
      fallback.style.zIndex = '2147483003';
      fallback.style.background = 'rgba(0,0,0,0.45)';
      fallback.style.display = 'flex';
      fallback.style.alignItems = 'center';
      fallback.style.justifyContent = 'center';

      const card = document.createElement('div');
      card.style.width = '480px';
      card.style.maxWidth = '90vw';
      card.style.background = '#fff';
      card.style.borderRadius = '16px';
      card.style.boxShadow = '0 20px 60px rgba(0,0,0,0.15)';
      card.style.padding = '32px 24px';
      card.style.textAlign = 'center';

      const titleEl = document.createElement('h2');
      titleEl.textContent = localized.title;
      titleEl.style.margin = '0 0 12px';
      titleEl.style.fontSize = '22px';
      titleEl.style.color = 'rgba(0,0,0,0.85)';

      const msgEl = document.createElement('p');
      msgEl.textContent = localized.message;
      msgEl.style.margin = '0 0 24px';
      msgEl.style.color = 'rgba(0,0,0,0.65)';

      const btnRow = document.createElement('div');
      btnRow.style.display = 'flex';
      btnRow.style.gap = '12px';
      btnRow.style.justifyContent = 'center';

      const primaryBtn = document.createElement('button');
      primaryBtn.textContent = localized.primaryButtonText;
      primaryBtn.style.padding = '10px 16px';
      primaryBtn.style.border = 'none';
      primaryBtn.style.borderRadius = '8px';
      primaryBtn.style.background = '#3b82f6';
      primaryBtn.style.color = '#fff';
      primaryBtn.style.cursor = 'pointer';
      primaryBtn.onclick = () => {
        try {
          const path = config.getNavigationPath(context);
          if (fallback.parentNode) fallback.parentNode.removeChild(fallback);
          __onboardingShowing = false;
          onNavigate(path);
        } catch {}
      };

      const skipBtn = document.createElement('button');
      skipBtn.textContent = localized.skipButtonText || 'Close';
      skipBtn.style.padding = '10px 16px';
      skipBtn.style.border = '1px solid #d9d9d9';
      skipBtn.style.borderRadius = '8px';
      skipBtn.style.background = '#fff';
      skipBtn.style.color = 'rgba(0,0,0,0.65)';
      skipBtn.style.cursor = 'pointer';
      skipBtn.onclick = () => {
        if (fallback.parentNode) fallback.parentNode.removeChild(fallback);
        __onboardingShowing = false;
      };

      btnRow.appendChild(primaryBtn);
      if (config.showSkipButton) btnRow.appendChild(skipBtn);

      card.appendChild(titleEl);
      card.appendChild(msgEl);
      card.appendChild(btnRow);
      fallback.appendChild(card);
      document.body.appendChild(fallback);
    }, 160);
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

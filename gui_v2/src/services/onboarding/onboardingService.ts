/**
 * Onboarding Service
 * 引导页服务 - 根据后端指令类型显示不同的引导页
 */

import React from "react";
import { createRoot } from "react-dom/client";
import { Modal, Button } from "antd";
import { RocketOutlined, SettingOutlined } from "@ant-design/icons";
import { logger } from "@/utils/logger";
import i18n from "@/i18n";

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
    const container = document.createElement("div");
    container.className = "onboarding-modal-container";
    document.body.appendChild(container);

    const root = createRoot(container);

    const cleanup = () => {
      try {
        root.unmount();
      } finally {
        if (container.parentNode) {
          container.parentNode.removeChild(container);
        }
      }
    };

    root.render(
      React.createElement(OnboardingModal, {
        config,
        context,
        onNavigate,
        onClose: cleanup,
        localized,
      }),
    );
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
  const config = ONBOARDING_CONFIGS[onboardingType];

  if (!config) {
    logger.warn(`[Onboarding] Unknown onboarding type: ${onboardingType}`);
    return;
  }

  const navigate = onNavigate || createNavigateFunction();
  const localized = resolveOnboardingContent(config);
  renderOnboardingModal(config, localized, context, navigate);
};
